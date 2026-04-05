-- Migrasjon 002: Ekstra kolonner på ord-tabellen
-- - har_bindestrek / har_mellomrom / kort_ord
-- - Fiks bokstavlengde til å utelate bindestrek og mellomrom

-- ---- Nye flagg-kolonner ----
ALTER TABLE ord ADD COLUMN IF NOT EXISTS har_bindestrek BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE ord ADD COLUMN IF NOT EXISTS har_mellomrom  BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE ord ADD COLUMN IF NOT EXISTS kort_ord       BOOLEAN NOT NULL DEFAULT false;

-- ---- Fiks bokstavlengde-beregningen ----
-- Den gamle genererte kolonnen teller bindestrek og mellomrom som bokstaver.
-- Den nye teller kun faktiske bokstaver (a-å, A-Å).

DROP INDEX  IF EXISTS idx_ord_bokstavlengde;
ALTER TABLE ord DROP   COLUMN bokstavlengde;
ALTER TABLE ord ADD    COLUMN bokstavlengde INTEGER NOT NULL
    GENERATED ALWAYS AS (length(regexp_replace(tekst, '[- ]', '', 'g'))) STORED;
CREATE INDEX IF NOT EXISTS idx_ord_bokstavlengde ON ord (bokstavlengde);
