-- Migrasjon 001: Initialt databaseskjema
-- Kryssord Norge

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- ord
-- ============================================================
CREATE TABLE IF NOT EXISTS ord (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tekst           TEXT NOT NULL,
    ordklasse       TEXT,
    bokstavlengde   INTEGER NOT NULL GENERATED ALWAYS AS (length(tekst)) STORED,
    frekvens        NUMERIC(10, 6) DEFAULT 0.0,
    opprettet_dato  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ord_tekst       ON ord (tekst);
CREATE        INDEX IF NOT EXISTS idx_ord_bokstavlengde ON ord (bokstavlengde);

-- ============================================================
-- synonymer
-- ============================================================
CREATE TABLE IF NOT EXISTS synonymer (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ord_id        UUID NOT NULL REFERENCES ord (id) ON DELETE CASCADE,
    synonym_id    UUID NOT NULL REFERENCES ord (id) ON DELETE CASCADE,
    relasjon_type TEXT NOT NULL DEFAULT 'synonym',
    kilde         TEXT,
    CONSTRAINT uq_synonym_par UNIQUE (ord_id, synonym_id)
);

CREATE INDEX IF NOT EXISTS idx_synonymer_ord_id     ON synonymer (ord_id);
CREATE INDEX IF NOT EXISTS idx_synonymer_synonym_id ON synonymer (synonym_id);

-- ============================================================
-- kategorier
-- ============================================================
CREATE TABLE IF NOT EXISTS kategorier (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    navn        TEXT NOT NULL UNIQUE,
    beskrivelse TEXT
);

-- ============================================================
-- ord_kategorier  (mange-til-mange)
-- ============================================================
CREATE TABLE IF NOT EXISTS ord_kategorier (
    ord_id      UUID NOT NULL REFERENCES ord        (id) ON DELETE CASCADE,
    kategori_id UUID NOT NULL REFERENCES kategorier (id) ON DELETE CASCADE,
    PRIMARY KEY (ord_id, kategori_id)
);

CREATE INDEX IF NOT EXISTS idx_ord_kategorier_kategori ON ord_kategorier (kategori_id);

-- ============================================================
-- kryssord
-- ============================================================
CREATE TABLE IF NOT EXISTS kryssord (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tittel            TEXT NOT NULL,
    vanskelighetsgrad TEXT NOT NULL DEFAULT 'middels'
                          CHECK (vanskelighetsgrad IN ('lett', 'middels', 'vanskelig')),
    grid_storrelse    INTEGER NOT NULL,
    grid_json         JSONB NOT NULL DEFAULT '{}',
    ledetrad_json     JSONB NOT NULL DEFAULT '{}',
    opprettet_dato    TIMESTAMPTZ NOT NULL DEFAULT now(),
    publisert         BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_kryssord_publisert       ON kryssord (publisert);
CREATE INDEX IF NOT EXISTS idx_kryssord_vanskelighetsgrad ON kryssord (vanskelighetsgrad);

-- ============================================================
-- kryssord_statistikk
-- ============================================================
CREATE TABLE IF NOT EXISTS kryssord_statistikk (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kryssord_id      UUID NOT NULL REFERENCES kryssord (id) ON DELETE CASCADE UNIQUE,
    antall_fullfort  INTEGER NOT NULL DEFAULT 0,
    antall_forsok    INTEGER NOT NULL DEFAULT 0
);
