export interface KryssordStatistikk {
  antall_fullfort: number;
  antall_forsok: number;
}

export interface GridJson {
  celler: string[][];
  storrelse: number;
}

export interface LedetradOppslag {
  nr: number;
  tekst: string;
  ledetrad: string;
  kilde?: string;
  // Valgfrie posisjonsfelter – leveres ikke av API, avledet fra grid i frontend
  kol?: number;
  rad?: number;
  lengde?: number;
}

export interface LedetradJson {
  across: Record<string, LedetradOppslag>;
  down: Record<string, LedetradOppslag>;
}

export interface Kryssord {
  id: string;
  tittel: string;
  vanskelighetsgrad: "lett" | "middels" | "vanskelig";
  grid_storrelse: number;
  grid_json: GridJson;
  ledetrad_json: LedetradJson;
  opprettet_dato: string;
  publisert: boolean;
  statistikk: KryssordStatistikk | null;
}

export interface KryssordListeElement {
  id: string;
  tittel: string;
  vanskelighetsgrad: "lett" | "middels" | "vanskelig";
  grid_storrelse: number;
  opprettet_dato: string;
  antall_fullfort: number;
}

export interface KryssordArkiv {
  totalt: number;
  side: number;
  per_side: number;
  kryssord: KryssordListeElement[];
}
