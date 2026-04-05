# Kryssord Norge

Fullstack-applikasjon for norske kryssord med daglig generering.

## Struktur

```
kryssord-norge/
├── backend/        # Python FastAPI
│   ├── app/        # API-endepunkter, modeller, schemas
│   └── generator/  # MCV-backtracking kryssordgenerator + ledetråder
├── frontend/       # Next.js med TypeScript og Tailwind CSS
├── database/       # SQL-migrasjoner
└── scripts/        # Datainnhenting og ordbankbygging
```

## Kom i gang

### Krav

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+

### Lokal oppsett

1. Klon repoet og kopier `.env.example` til `.env`:

   ```bash
   cp .env.example .env
   # Fyll inn DATABASE_URL og andre verdier
   ```

2. Kjør databasemigrasjoner:

   ```bash
   pip install psycopg2-binary python-dotenv
   python database/migrate.py
   ```

3. Start backend:

   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

4. Start frontend (nytt terminalvindu):

   ```bash
   cd frontend
   cp .env.local.example .env.local
   # Sett NEXT_PUBLIC_API_URL=http://localhost:8000
   npm install
   npm run dev
   ```

Åpne [http://localhost:3000](http://localhost:3000) for å se appen.
API-dokumentasjon: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## GitHub Actions

| Workflow | Trigger | Beskrivelse |
|---|---|---|
| `generer_kryssord.yml` | Mandag 06:00 UTC + manuell | Genererer og publiserer 9×9, 13×13 og 17×17 kryssord |
| `deploy.yml` | Push til `main` + manuell | Bygger og deployer frontend (Vercel) og backend (Railway) |

### Sett opp GitHub Secrets

Gå til **Settings → Secrets and variables → Actions** i GitHub-repoet ditt og legg til følgende:

#### Påkrevd for begge workflows

| Secret | Beskrivelse | Eksempel |
|---|---|---|
| `PROD_DATABASE_URL` | PostgreSQL connection string til produksjonsbasen | `postgresql://user:pass@host:5432/kryssord` |

#### Frontend — Vercel

| Secret | Beskrivelse | Hvor du finner den |
|---|---|---|
| `VERCEL_TOKEN` | Vercel API-token | vercel.com → Settings → Tokens → Create |
| `VERCEL_ORG_ID` | Vercel organisasjons-ID | Se steg 1 under |
| `VERCEL_PROJECT_ID` | Vercel prosjekt-ID | Se steg 1 under |
| `NEXT_PUBLIC_API_URL` | URL til backend-API | `https://api.kryssord.no` |

**Steg 1 — Hent Vercel IDs:**

```bash
cd frontend
npx vercel login
npx vercel link          # Kobler lokalt prosjekt til Vercel
cat .vercel/project.json # Viser orgId og projectId
```

Kopier `orgId` → `VERCEL_ORG_ID` og `projectId` → `VERCEL_PROJECT_ID`.

#### Backend — Railway

| Secret | Beskrivelse | Hvor du finner den |
|---|---|---|
| `RAILWAY_TOKEN` | Railway API-token | railway.app → Account Settings → Tokens → New Token |

**Steg 2 — Koble Railway til prosjektet:**

```bash
npm install -g @railway/cli
railway login
cd backend
railway init            # Eller railway link for eksisterende prosjekt
railway variables set DATABASE_URL="<din-prod-db-url>"
railway variables set ADMIN_API_KEY="<tilfeldig-sterk-nokkel>"
```

Railway bruker `backend/` som rot. Sørg for at `Procfile` eller `railway.json` peker på riktig startkommando:

```json
// backend/railway.json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "NIXPACKS" },
  "deploy": { "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT" }
}
```

#### Manuell kjøring

Workflows kan kjøres manuelt fra GitHub:
**Actions → velg workflow → Run workflow**

For `generer_kryssord.yml` kan du spesifisere størrelser og om kryssordene skal publiseres.

---

## Bygg orddatabasen

Kjør orkestreringssskriptet som tar seg av alt i riktig rekkefølge:

```bash
source backend/.venv/bin/activate
bash scripts/bygg_ordbank.sh
```

Estimert kjøretid: **~30–45 minutter** (Ordbøkene er det tyngste steget).

```bash
# Tørrkjøring – se hva som ville skjedd uten å gjøre endringer
bash scripts/bygg_ordbank.sh --dry-run

# Hopp over Ordbøkene (hvis ord allerede er hentet)
bash scripts/bygg_ordbank.sh --skip-ordbokene

# Enkeltskript
python scripts/hent_ordbokene.py          # Bokmålsord
python scripts/hent_wikidata.py           # Egennavn fra Wikidata
python scripts/hent_synonymer.py          # Synonympar
```

Logger lagres i `scripts/logs/`.

---

## API

| Endepunkt | Beskrivelse |
|---|---|
| `GET /api/kryssord/daglig` | Dagens kryssord |
| `GET /api/kryssord/arkiv` | Paginert liste over publiserte kryssord |
| `GET /api/kryssord/{id}` | Hent spesifikt kryssord |
| `POST /api/kryssord/generer` | Generer nytt kryssord (krever `X-Admin-Key`) |
| `GET /api/ord` | Søk i orddatabasen |
| `GET /api/synonymer/{ord}` | Synonymer for et ord |
