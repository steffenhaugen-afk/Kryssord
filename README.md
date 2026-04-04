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
