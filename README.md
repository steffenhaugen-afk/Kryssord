# Kryssord Norge

Fullstack-applikasjon for norske kryssord.

## Struktur

```
kryssord-norge/
├── backend/        # Python FastAPI
├── frontend/       # Next.js med TypeScript
├── database/       # SQL-migrasjoner
└── scripts/        # Python-skript for datainnhenting
```

## Kom i gang

### Krav
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+

### Oppsett

1. Kopier `.env.example` til `.env` og fyll inn verdiene:
   ```bash
   cp .env.example .env
   ```

2. Start backend:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

3. Start frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## API

API-dokumentasjon tilgjengelig på `http://localhost:8000/docs` når backend kjører.

## GitHub Actions

To workflows er satt opp:

| Workflow | Trigger | Beskrivelse |
|---|---|---|
| `generer_kryssord.yml` | Hver mandag 06:00 UTC | Genererer og publiserer 9×9, 13×13 og 17×17 kryssord |
| `deploy.yml` | Push til `main` | Bygger og deployer frontend (Vercel) og backend (Railway) |

### Sett opp GitHub Secrets

Gå til **Settings → Secrets and variables → Actions** i GitHub-repoet og legg til følgende secrets:

#### Påkrevd

| Secret | Beskrivelse | Eksempel |
|---|---|---|
| `PROD_DATABASE_URL` | PostgreSQL connection string til produksjonsdatabasen | `postgresql://user:pass@host:5432/kryssord` |

#### Frontend (Vercel)

| Secret | Hvor finner du den | Beskrivelse |
|---|---|---|
| `VERCEL_TOKEN` | vercel.com → Settings → Tokens | API-token for deploy |
| `VERCEL_ORG_ID` | `vercel project ls --json` eller `.vercel/project.json` | Organisasjons-ID |
| `VERCEL_PROJECT_ID` | `.vercel/project.json` etter `vercel link` | Prosjekt-ID |
| `NEXT_PUBLIC_API_URL` | Din backend URL | `https://api.kryssord.no` |

#### Backend (Railway)

| Secret | Hvor finner du den | Beskrivelse |
|---|---|---|
| `RAILWAY_TOKEN` | railway.app → Account Settings → Tokens | API-token for deploy |

#### Sett opp Vercel (én gang)

```bash
cd frontend
npx vercel link        # Kobler prosjektet til Vercel
cat .vercel/project.json  # Viser orgId og projectId
```

#### Sett opp Railway (én gang)

```bash
npm install -g @railway/cli
railway login
railway link           # Kobler til eksisterende prosjekt
```

### Manuell kjøring

Workflows kan også kjøres manuelt fra GitHub UI:
**Actions → velg workflow → Run workflow**

## Datahenting (scripts)

```bash
source backend/.venv/bin/activate

# Hent ord fra Bokmålsordboka (~70 000 artikler, ~15 min)
python scripts/hent_ordbokene.py

# Hent egennavn fra Wikidata
python scripts/hent_wikidata.py

# Hent synonympar
python scripts/hent_synonymer.py

# Generer kryssord lokalt
python scripts/generer_kryssord.py --storrelse 9 13 17
```
