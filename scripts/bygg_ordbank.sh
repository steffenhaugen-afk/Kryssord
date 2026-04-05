#!/usr/bin/env bash
# =============================================================================
# bygg_ordbank.sh
# Kjører alle innhentingsskript i riktig rekkefølge for å bygge den norske
# orddatabasen fra bunnen av.
#
# Bruk:
#   ./scripts/bygg_ordbank.sh               # Full kjøring
#   ./scripts/bygg_ordbank.sh --skip-ordbokene  # Hopp over Ordbøkene-steget
#   ./scripts/bygg_ordbank.sh --dry-run     # Valider miljø uten å kjøre
#
# Krav:
#   - Python-venv aktivert ELLER satt i PATH
#   - .env med DATABASE_URL i prosjektrot
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Konfigurasjon
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$SCRIPT_DIR/logs"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
BUILD_LOG="$LOG_DIR/bygg_ordbank_${TIMESTAMP}.log"

PYTHON="${PYTHON:-python3}"
VENV_PATH="$ROOT_DIR/backend/.venv"

SKIP_ORDBOKENE=false
DRY_RUN=false

# ---------------------------------------------------------------------------
# Farger og logging
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0m'

log()     { echo -e "${BLU}[$(date '+%H:%M:%S')]${NC} $*" | tee -a "$BUILD_LOG"; }
ok()      { echo -e "${GRN}[$(date '+%H:%M:%S')] ✓${NC} $*" | tee -a "$BUILD_LOG"; }
warn()    { echo -e "${YLW}[$(date '+%H:%M:%S')] ⚠${NC}  $*" | tee -a "$BUILD_LOG"; }
fail()    { echo -e "${RED}[$(date '+%H:%M:%S')] ✗${NC} $*" | tee -a "$BUILD_LOG"; exit 1; }

# ---------------------------------------------------------------------------
# Argumentparsing
# ---------------------------------------------------------------------------
for arg in "$@"; do
    case $arg in
        --skip-ordbokene) SKIP_ORDBOKENE=true ;;
        --dry-run)        DRY_RUN=true ;;
        --help|-h)
            echo "Bruk: $0 [--skip-ordbokene] [--dry-run]"
            exit 0 ;;
        *) warn "Ukjent argument: $arg" ;;
    esac
done

# ---------------------------------------------------------------------------
# Miljøvalidering
# ---------------------------------------------------------------------------
validate_env() {
    log "Validerer miljø ..."

    # Sjekk at vi er i riktig katalog
    if [[ ! -f "$ROOT_DIR/.env" ]]; then
        fail ".env ikke funnet i $ROOT_DIR — kopier .env.example og fyll inn verdier"
    fi

    # Last DATABASE_URL fra .env
    # shellcheck disable=SC2046
    export $(grep -v '^#' "$ROOT_DIR/.env" | grep 'DATABASE_URL' | xargs)
    if [[ -z "${DATABASE_URL:-}" ]]; then
        fail "DATABASE_URL mangler i .env"
    fi

    # Finn Python
    if [[ -f "$VENV_PATH/bin/python3" ]]; then
        PYTHON="$VENV_PATH/bin/python3"
        ok "Bruker venv: $PYTHON"
    elif command -v python3 &>/dev/null; then
        PYTHON="python3"
        ok "Bruker system-python: $(which python3)"
    else
        fail "python3 ikke funnet — aktiver venv eller installer Python"
    fi

    # Sjekk at nødvendige pakker er installert
    if ! "$PYTHON" -c "import psycopg2, requests, dotenv" 2>/dev/null; then
        fail "Manglende Python-pakker — kjør: pip install -r scripts/requirements.txt"
    fi

    # Test databasetilkobling
    if ! "$PYTHON" -c "
import os, psycopg2
try:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.close()
except Exception as e:
    raise SystemExit(f'Databasefeil: {e}')
" 2>>"$BUILD_LOG"; then
        fail "Klarte ikke koble til databasen — sjekk DATABASE_URL i .env"
    fi

    ok "Miljøvalidering OK"
}

# ---------------------------------------------------------------------------
# Kjøringsfunksjon med tidslogging
# ---------------------------------------------------------------------------
run_step() {
    local navn="$1"
    local skript="$2"
    shift 2
    local ekstra_args=("$@")

    echo "" | tee -a "$BUILD_LOG"
    log "━━━ Steg: $navn ━━━"

    if [[ "$DRY_RUN" == true ]]; then
        warn "DRY-RUN: Ville kjørt: $PYTHON $skript${ekstra_args:+ ${ekstra_args[*]}}"
        return 0
    fi

    local start_tid
    start_tid=$(date +%s)

    if "$PYTHON" "$SCRIPT_DIR/$skript" ${ekstra_args[@]+"${ekstra_args[@]}"} 2>&1 | tee -a "$BUILD_LOG"; then
        local slutt_tid elapsed
        slutt_tid=$(date +%s)
        elapsed=$(( slutt_tid - start_tid ))
        ok "$navn fullført på ${elapsed}s"
    else
        local exit_kode=$?
        fail "$navn feilet med exit-kode $exit_kode — se $BUILD_LOG"
    fi
}

# ---------------------------------------------------------------------------
# Statistikkrapport
# ---------------------------------------------------------------------------
print_rapport() {
    log ""
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "RAPPORT"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    "$PYTHON" - <<'EOF' 2>>"$BUILD_LOG" | tee -a "$BUILD_LOG"
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM ord")
    antall_ord = cur.fetchone()[0]

    cur.execute("SELECT ordklasse, COUNT(*) FROM ord GROUP BY ordklasse ORDER BY COUNT(*) DESC")
    per_klasse = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM synonymer")
    antall_syn = cur.fetchone()[0]

    cur.execute("SELECT navn, COUNT(ok.ord_id) FROM kategorier k JOIN ord_kategorier ok ON ok.kategori_id = k.id GROUP BY k.navn ORDER BY COUNT(ok.ord_id) DESC")
    kategorier = cur.fetchall()

conn.close()

print(f"\n  Ord totalt:       {antall_ord:>8,}")
print(f"  Synonympar:       {antall_syn:>8,}")
print()
print("  Fordeling per ordklasse:")
for klasse, antall in per_klasse:
    print(f"    {klasse:<18} {antall:>7,}")
print()
print("  Kategorier:")
for navn, antall in kategorier:
    print(f"    {navn:<30} {antall:>6,}")
EOF

    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ---------------------------------------------------------------------------
# Hovedprogram
# ---------------------------------------------------------------------------
main() {
    mkdir -p "$LOG_DIR"

    echo ""
    echo -e "${BLU}╔══════════════════════════════════╗${NC}"
    echo -e "${BLU}║     Kryssord Norge – Ordbank     ║${NC}"
    echo -e "${BLU}╚══════════════════════════════════╝${NC}"
    echo ""

    log "Byggelogg: $BUILD_LOG"
    [[ "$DRY_RUN"  == true ]] && warn "DRY-RUN aktivert — ingen endringer gjøres"
    [[ "$SKIP_ORDBOKENE" == true ]] && warn "--skip-ordbokene: Hopper over Ordbøkene-steget"

    validate_env

    local total_start
    total_start=$(date +%s)

    # Steg 1 – Bokmålsordboka (~70 000 artikler, ~15 min)
    if [[ "$SKIP_ORDBOKENE" == false ]]; then
        run_step "Ordbøkene (bokmålsord)" "hent_ordbokene.py"
    else
        warn "Hopper over steg 1: hent_ordbokene.py"
    fi

    # Steg 2 – Wikidata (egennavn)
    run_step "Wikidata (egennavn)" "hent_wikidata.py"

    # Steg 3 – Synonymer
    run_step "Synonymer" "hent_synonymer.py"

    local total_slutt elapsed_total
    total_slutt=$(date +%s)
    elapsed_total=$(( total_slutt - total_start ))

    print_rapport

    echo ""
    ok "Alt ferdig på $(( elapsed_total / 60 ))m $(( elapsed_total % 60 ))s"
    log "Full logg: $BUILD_LOG"
    echo ""
}

main "$@"
