"use client";

import { useState, useCallback, useRef } from "react";
import { adminApi, type OrdResultat } from "@/lib/adminApi";

const KILDE_FARGE: Record<string, string> = {
  kryssordkongen: "bg-blue-100 text-blue-700",
  synonymer:      "bg-teal-100 text-teal-700",
  kategorier:     "bg-orange-100 text-orange-700",
};

export default function OrdbankPage() {
  const [query, setQuery] = useState("");
  const [resultater, setResultater] = useState<OrdResultat[]>([]);
  const [totalt, setTotalt] = useState(0);
  const [laster, setLaster] = useState(false);
  const [utvidet, setUtvidet] = useState<string | null>(null);
  const [nyLedetrad, setNyLedetrad] = useState<Record<string, string>>({});
  const [lagrer, setLagrer] = useState<string | null>(null);
  const [melding, setMelding] = useState<Record<string, string>>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sok = useCallback(async (q: string) => {
    if (q.length < 1) { setResultater([]); setTotalt(0); return; }
    setLaster(true);
    try {
      const data = await adminApi.sokOrd(q);
      setResultater(data.resultater);
      setTotalt(data.totalt);
    } finally {
      setLaster(false);
    }
  }, []);

  function handleInput(v: string) {
    setQuery(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => sok(v), 350);
  }

  async function leggTilLedetrad(tekst: string) {
    const ny = nyLedetrad[tekst]?.trim();
    if (!ny) return;
    setLagrer(tekst);
    try {
      await adminApi.leggTilLedetrad(tekst, ny);
      setNyLedetrad({ ...nyLedetrad, [tekst]: "" });
      setMelding({ ...melding, [tekst]: "Ledetråd lagt til!" });
      // Oppdater søk for å reflektere endring
      await sok(query);
    } catch (e) {
      setMelding({ ...melding, [tekst]: e instanceof Error ? e.message : "Feil" });
    } finally {
      setLagrer(null);
    }
  }

  const harLedetrad = (o: OrdResultat) =>
    o.kryssordkongen.length > 0 || o.synonymer.length > 0 || o.kategorier.length > 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Ordbank</h1>
        <p className="text-sm text-gray-500 mt-1">
          Søk etter ord, se ledetråd-kilder og legg til manuelle ledetråder.
        </p>
      </div>

      {/* Søk */}
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          placeholder="Søk etter ord…"
          className="w-full border border-gray-300 rounded-xl px-4 py-3 text-base bg-white focus:outline-none focus:ring-2 focus:ring-gray-400 shadow-sm"
          autoFocus
        />
        {laster && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full" />
          </div>
        )}
      </div>

      {totalt > 0 && (
        <p className="text-xs text-gray-400">{totalt} treff</p>
      )}

      {/* Resultater */}
      <div className="space-y-2">
        {resultater.map((ord) => {
          const erUtvidet = utvidet === ord.tekst;
          const harData = harLedetrad(ord);
          return (
            <div
              key={ord.id}
              className="bg-white rounded-xl border border-gray-200 overflow-hidden"
            >
              <button
                onClick={() => setUtvidet(erUtvidet ? null : ord.tekst)}
                className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="font-semibold text-gray-900">{ord.tekst}</span>
                  <span className="text-xs text-gray-400">
                    {ord.ordklasse} · {ord.bokstavlengde} bokstaver
                  </span>
                  {!harData && (
                    <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded font-medium">
                      ingen ledetråd
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {harData && (
                    <div className="flex gap-1">
                      {ord.kryssordkongen.length > 0 && (
                        <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                          kk:{ord.kryssordkongen.length}
                        </span>
                      )}
                      {ord.synonymer.length > 0 && (
                        <span className="text-xs bg-teal-100 text-teal-700 px-1.5 py-0.5 rounded">
                          syn:{ord.synonymer.length}
                        </span>
                      )}
                      {ord.kategorier.length > 0 && (
                        <span className="text-xs bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded">
                          kat:{ord.kategorier.length}
                        </span>
                      )}
                    </div>
                  )}
                  <span className="text-gray-400 text-sm">{erUtvidet ? "▲" : "▼"}</span>
                </div>
              </button>

              {erUtvidet && (
                <div className="border-t border-gray-100 px-4 py-4 space-y-4 bg-gray-50">
                  {/* Kryssordkongen */}
                  {ord.kryssordkongen.length > 0 && (
                    <Gruppe label="Kryssordkongen" farge={KILDE_FARGE.kryssordkongen}>
                      {ord.kryssordkongen.map((l, i) => (
                        <LedetradPill key={i}>{l}</LedetradPill>
                      ))}
                    </Gruppe>
                  )}

                  {/* Synonymer */}
                  {ord.synonymer.length > 0 && (
                    <Gruppe label="Synonymer" farge={KILDE_FARGE.synonymer}>
                      {ord.synonymer.map((s, i) => (
                        <LedetradPill key={i}>{s}</LedetradPill>
                      ))}
                    </Gruppe>
                  )}

                  {/* Kategorier */}
                  {ord.kategorier.length > 0 && (
                    <Gruppe label="Wikidata-kategorier" farge={KILDE_FARGE.kategorier}>
                      {ord.kategorier.map((k, i) => (
                        <LedetradPill key={i}>{k}</LedetradPill>
                      ))}
                    </Gruppe>
                  )}

                  {/* Legg til manuell */}
                  <div>
                    <p className="text-xs font-medium text-gray-600 mb-2">Legg til ledetråd manuelt</p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={nyLedetrad[ord.tekst] ?? ""}
                        onChange={(e) =>
                          setNyLedetrad({ ...nyLedetrad, [ord.tekst]: e.target.value })
                        }
                        placeholder={`Ledetråd for "${ord.tekst}"…`}
                        className="flex-1 border border-gray-300 rounded-lg px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-gray-400"
                        onKeyDown={(e) => {
                          if (e.key === "Enter") leggTilLedetrad(ord.tekst);
                        }}
                      />
                      <button
                        onClick={() => leggTilLedetrad(ord.tekst)}
                        disabled={lagrer === ord.tekst || !nyLedetrad[ord.tekst]?.trim()}
                        className="bg-gray-900 text-white px-3 py-1.5 rounded-lg text-sm hover:bg-gray-800 disabled:opacity-50 transition-colors"
                      >
                        {lagrer === ord.tekst ? "…" : "Legg til"}
                      </button>
                    </div>
                    {melding[ord.tekst] && (
                      <p className="text-xs text-green-700 mt-1">{melding[ord.tekst]}</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {!laster && query.length > 0 && resultater.length === 0 && (
        <p className="text-center text-gray-400 py-8">Ingen ord funnet for "{query}".</p>
      )}
    </div>
  );
}

function Gruppe({
  label, farge, children,
}: {
  label: string; farge: string; children: React.ReactNode;
}) {
  return (
    <div>
      <p className={`text-xs font-semibold mb-1.5 inline-block px-1.5 py-0.5 rounded ${farge}`}>
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function LedetradPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-xs bg-white border border-gray-200 text-gray-700 px-2 py-0.5 rounded-full">
      {children}
    </span>
  );
}
