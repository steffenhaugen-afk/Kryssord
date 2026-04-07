/**
 * Klientside-API-kall til Next.js admin-proxy-ruter.
 * Ingen admin-nøkkel trengs her — serveren håndterer auth.
 */

export type KryssordStatus = "utkast" | "godkjent" | "publisert";

export interface AdminKryssordElement {
  id: string;
  tittel: string;
  vanskelighetsgrad: string;
  grid_storrelse: number;
  opprettet_dato: string;
  publisert: boolean;
  godkjent: boolean;
  antall_ord: number;
}

export interface OrdResultat {
  id: string;
  tekst: string;
  ordklasse: string | null;
  bokstavlengde: number;
  kryssordkongen: string[];
  synonymer: string[];
  kategorier: string[];
}

async function adminFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`/api/admin${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Ukjent feil");
  }
  return res.json() as Promise<T>;
}

export const adminApi = {
  // Kryssord-liste
  hentAlle: () =>
    adminFetch<{ totalt: number; kryssord: AdminKryssordElement[] }>("/kryssord"),

  // Enkelt kryssord (fullt)
  hentKryssord: (id: string) =>
    adminFetch<Record<string, unknown>>(`/kryssord/${id}`),

  // Generer nytt
  generer: (body: { storrelse: number; tema: string; tvang_ord: string[] }) =>
    adminFetch<Record<string, unknown>>("/kryssord/generer", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Oppdater status
  oppdaterStatus: (id: string, body: { godkjent?: boolean; publisert?: boolean; tittel?: string }) =>
    adminFetch<{ ok: boolean }>(`/kryssord/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // Rediger ledetråd
  oppdaterLedetrad: (id: string, retning: string, nr: string, ledetrad: string) =>
    adminFetch<{ ok: boolean }>(`/kryssord/${id}/ledetrad`, {
      method: "PATCH",
      body: JSON.stringify({ retning, nr, ledetrad }),
    }),

  // Slett kryssord
  slett: (id: string) =>
    adminFetch<{ ok: boolean }>(`/kryssord/${id}`, { method: "DELETE" }),

  // Ordbank-søk
  sokOrd: (q: string) =>
    adminFetch<{ totalt: number; resultater: OrdResultat[] }>(`/ord?q=${encodeURIComponent(q)}`),

  // Legg til ledetråd manuelt
  leggTilLedetrad: (tekst: string, ledetrad: string) =>
    adminFetch<{ ok: boolean }>(`/ord/${encodeURIComponent(tekst)}/ledetrad`, {
      method: "POST",
      body: JSON.stringify({ ledetrad }),
    }),
};
