import { hentArkiv } from "@/lib/api";
import type { KryssordListeElement } from "@/types/kryssord";
import Link from "next/link";

export const revalidate = 300;

const STORRELSE_VALG = [
  { label: "Alle", value: undefined },
  { label: "9×9 (lett)", value: 9 },
  { label: "13×13 (middels)", value: 13 },
  { label: "17×17 (vanskelig)", value: 17 },
];

interface PageProps {
  searchParams: Promise<{ side?: string; storrelse?: string }>;
}

function formaterDato(iso: string): string {
  return new Date(iso).toLocaleDateString("nb-NO", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

const vanskelighetsfarger: Record<string, string> = {
  lett: "bg-green-100 text-green-700",
  middels: "bg-yellow-100 text-yellow-700",
  vanskelig: "bg-red-100 text-red-700",
};

export default async function ArkivSide({ searchParams }: PageProps) {
  const params = await searchParams;
  const side = Math.max(1, parseInt(params.side ?? "1", 10));
  const storrelse = params.storrelse ? parseInt(params.storrelse, 10) : undefined;

  let arkiv;
  try {
    arkiv = await hentArkiv(side, storrelse);
  } catch {
    return (
      <main className="max-w-3xl mx-auto px-4 py-16 text-center">
        <p className="text-gray-500">Kunne ikke laste arkivet. Prøv igjen senere.</p>
      </main>
    );
  }

  const antallSider = Math.ceil(arkiv.totalt / arkiv.per_side);

  function paginertUrl(s: number) {
    const p = new URLSearchParams();
    p.set("side", String(s));
    if (storrelse) p.set("storrelse", String(storrelse));
    return `/arkiv?${p}`;
  }

  function storrelseUrl(st?: number) {
    const p = new URLSearchParams();
    if (st) p.set("storrelse", String(st));
    return `/arkiv?${p}`;
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-6">
      <nav className="mb-6 flex items-center gap-2 text-sm text-gray-500">
        <Link href="/" className="hover:text-gray-800">
          Kryssord Norge
        </Link>
        <span>/</span>
        <span className="text-gray-800 font-medium">Arkiv</span>
      </nav>

      <h1 className="text-2xl font-bold mb-4">Kryssordarkiv</h1>

      {/* Størrelsesfilter */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {STORRELSE_VALG.map((v) => (
          <Link
            key={v.label}
            href={storrelseUrl(v.value)}
            className={`px-3 py-1 rounded-full text-sm border transition-colors ${
              storrelse === v.value
                ? "bg-blue-600 text-white border-blue-600"
                : "border-gray-300 text-gray-700 hover:border-blue-400"
            }`}
          >
            {v.label}
          </Link>
        ))}
      </div>

      {/* Liste */}
      <p className="text-sm text-gray-500 mb-3">{arkiv.totalt} kryssord totalt</p>

      {arkiv.kryssord.length === 0 ? (
        <p className="text-gray-500">Ingen kryssord funnet.</p>
      ) : (
        <ul className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden">
          {arkiv.kryssord.map((k: KryssordListeElement) => (
            <li key={k.id}>
              <Link
                href={`/kryssord/${k.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
              >
                <div>
                  <span className="font-medium text-gray-900">{k.tittel}</span>
                  <span className="ml-2 text-xs text-gray-400">
                    {k.grid_storrelse}×{k.grid_storrelse}
                  </span>
                  <span
                    className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${
                      vanskelighetsfarger[k.vanskelighetsgrad] ?? ""
                    }`}
                  >
                    {k.vanskelighetsgrad}
                  </span>
                </div>
                <div className="text-right shrink-0 ml-4">
                  <div className="text-xs text-gray-400">{formaterDato(k.opprettet_dato)}</div>
                  {k.antall_fullfort > 0 && (
                    <div className="text-xs text-gray-400">
                      {k.antall_fullfort} fullført
                    </div>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {/* Paginering */}
      {antallSider > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          {side > 1 && (
            <Link
              href={paginertUrl(side - 1)}
              className="px-3 py-1 text-sm border border-gray-300 rounded hover:border-blue-400"
            >
              ← Forrige
            </Link>
          )}
          <span className="text-sm text-gray-500">
            Side {side} av {antallSider}
          </span>
          {side < antallSider && (
            <Link
              href={paginertUrl(side + 1)}
              className="px-3 py-1 text-sm border border-gray-300 rounded hover:border-blue-400"
            >
              Neste →
            </Link>
          )}
        </div>
      )}
    </main>
  );
}
