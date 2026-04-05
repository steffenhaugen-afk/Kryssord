# Database

SQL-migrasjoner administreres med et enkelt Python-skript som kjører SQL-filer i rekkefølge.

## Kjør migrasjoner

```bash
pip install psycopg2-binary python-dotenv
python database/migrate.py
```

Skriptet holder styr på hvilke migrasjoner som er kjørt i tabellen `_migrasjoner`, og kjører bare nye filer.

## Lag ny migrasjon

Opprett en ny fil i `database/migrations/` med fortløpende nummer:

```bash
touch database/migrations/002_beskrivelse.sql
```

Navnekonvensjon: `NNN_beskrivelse.sql` — skriptet kjører dem i stigende alfabetisk rekkefølge.

## Tabeller

| Tabell | Beskrivelse |
|---|---|
| `ord` | Norske ord med ordklasse og bokstavlengde (computed) |
| `synonymer` | Synonympar mellom ord, med relasjonstype |
| `kategorier` | Kategorier som egennavn tilhører |
| `ord_kategorier` | Kobling mellom ord og kategorier |
| `kryssord` | Genererte kryssord med grid og ledetråder (JSONB) |
| `kryssord_statistikk` | Bruksstatistikk per kryssord |
