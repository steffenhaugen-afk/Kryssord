import type { Kryssord, KryssordArkiv } from "@/types/kryssord";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export function hentDagligKryssord(): Promise<Kryssord> {
  return apiFetch<Kryssord>("/api/kryssord/daglig");
}

export function hentKryssord(id: string): Promise<Kryssord> {
  return apiFetch<Kryssord>(`/api/kryssord/${id}`);
}

export function hentArkiv(side = 1, storrelse?: number): Promise<KryssordArkiv> {
  const params = new URLSearchParams({ side: String(side) });
  if (storrelse) params.set("storrelse", String(storrelse));
  return apiFetch<KryssordArkiv>(`/api/kryssord/arkiv?${params}`);
}
