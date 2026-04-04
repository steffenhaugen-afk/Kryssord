# Database

SQL-migrasjoner administreres med Alembic.

## Kjør migrasjoner

```bash
cd backend
alembic upgrade head
```

## Lag ny migrasjon

```bash
alembic revision --autogenerate -m "beskrivelse"
```
