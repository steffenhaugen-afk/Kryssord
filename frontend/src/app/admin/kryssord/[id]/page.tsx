"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Kryssord, LedetradOppslag } from "@/types/kryssord";
import { adminApi } from "@/lib/adminApi";

const KILDE_FARGE: Record<string, string> = {
  kryssordkongen: "bg-blue-100 text-blue-700",
  norwordnet:     "bg-purple-100 text-purple-700",
  synonym:        "bg-teal-100 text-teal-700",
  kategori:       "bg-orange-100 text-orange-700",
  manuell:        "bg-pink-100 text-pink-700",
  mangler:        "bg-red-100 text-red-700",
};

interface LedetradRad {
  retning: "across" | "down";
  nr: string;
  oppslag: LedetradOppslag & { kilde?: string };
}

export default function KryssordDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const router = useRouter();
  const [kryssord, setKryssord] = useState<Kryssord | null>(null);
  const [laster, setLaster] = useState(true);
  const [redigerer, setRedigerer] = useState<Record<string, string>>({});
  const [lagrer, setLagrer] = useState<string | null>(null);
  const [melding, setMelding] = useState("");
  const [statusLaster, setStatusLaster] = useState(false);

  async function last() {
    setLaster(true);
    try {
      const data = await adminApi.hentKryssord(id);
      setKryssord(data as unknown as Kryssord);
    } finally {
      setLaster(false);
    }
  }

  useEffect(() => { last(); }, [id]);

  if (laster) {
    return <div className="text-center py-16 text-gray-400">Laster…</div>;
  }
  if (!kryssord) {
    return <div className="text-center py-16 text-red-500">Kryssord ikke funnet.</div>;
  }

  const ledetradRader: LedetradRad[] = [
    ...Object.entries(kryssord.ledetrad_json.across).map(([nr, o]) => ({
      retning: "across" as const, nr, oppslag: o as LedetradOppslag & { kilde?: string },
    })),
    ...Object.entries(kryssord.ledetrad_json.down).map(([nr, o]) => ({
      retning: "down" as const, nr, oppslag: o as LedetradOppslag & { kilde?: string },
    })),
  ].sort((a, b) => Number(a.nr) - Number(b.nr));

  const nøkkel = (r: LedetradRad) => `${r.retning}-${r.nr}`;

  async function lagreLedetrad(rad: LedetradRad) {
    const key = nøkkel(rad);
    const ny = redigerer[key];
    if (!ny) return;
    setLagrer(key);
    try {
      await adminApi.oppdaterLedetrad(id, rad.retning, rad.nr, ny);
      await last();
      const oppdatert = { ...redigerer };
      delete oppdatert[key];
      setRedigerer(oppdatert);
      setMelding("Ledetråd lagret.");
    } finally {
      setLagrer(null);
    }
  }

  async function settStatus(felt: "godkjent" | "publisert", verdi: boolean) {
    setStatusLaster(true);
    try {
      await adminApi.oppdaterStatus(id, { [felt]: verdi });
      await last();
      setMelding(`Status oppdatert: ${felt} = ${verdi}`);
    } finally {
      setStatusLaster(false);
    }
  }

  async function slett() {
    if (!confirm("Slett dette kryssordet?")) return;
    await adminApi.slett(id);
    router.push("/admin/kryssord");
  }

  const er = kryssord as Kryssord & { godkjent?: boolean };
  const godkjent = er.godkjent ?? false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <button
            onClick={() => router.push("/admin/kryssord")}
            className="text-sm text-gray-500 hover:text-gray-700 mb-2 flex items-center gap-1"
          >
            ← Tilbake
          </button>
          <h1 className="text-2xl font-bold text-gray-900">{kryssord.tittel}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {kryssord.grid_storrelse}×{kryssord.grid_storrelse} · {kryssord.vanskelighetsgrad} ·{" "}
            {ledetradRader.length} ord
          </p>
        </div>

        {/* Status-knapper */}
        <div className="flex items-center gap-2 flex-wrap">
          {melding && (
            <span className="text-xs text-green-700 bg-green-50 px-2 py-1 rounded">
              {melding}
            </span>
          )}
          {!godkjent && !kryssord.publisert && (
            <button
              onClick={() => settStatus("godkjent", true)}
              disabled={statusLaster}
              className="bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-amber-700 disabled:opacity-60 transition-colors"
            >
              Godkjenn
            </button>
          )}
          {godkjent && !kryssord.publisert && (
            <button
              onClick={() => settStatus("publisert", true)}
              disabled={statusLaster}
              className="bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-800 disabled:opacity-60 transition-colors"
            >
              Publiser
            </button>
          )}
          {kryssord.publisert && (
            <button
              onClick={() => settStatus("publisert", false)}
              disabled={statusLaster}
              className="bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-60 transition-colors"
            >
              Avpubliser
            </button>
          )}
          <button
            onClick={slett}
            className="text-sm text-red-600 hover:text-red-800 px-3 py-2"
          >
            Slett
          </button>
        </div>
      </div>

      {/* Status-badges */}
      <div className="flex gap-2">
        <StatusBadge label="publisert" aktiv={kryssord.publisert} />
        <StatusBadge label="godkjent" aktiv={godkjent} />
        {!godkjent && !kryssord.publisert && <StatusBadge label="utkast" aktiv />}
      </div>

      {/* Grid ASCII */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 overflow-x-auto">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Grid</h2>
        <AsciiGrid grid={kryssord.grid_json.celler} />
      </div>

      {/* Ledetråd-editor */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <h2 className="text-sm font-semibold text-gray-700 px-4 py-3 border-b border-gray-100">
          Ledetråder
        </h2>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th className="text-left px-4 py-2 font-medium text-gray-500 w-12">Nr</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500 w-8">↔</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500 w-32">Ord</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">Ledetråd</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500 w-28">Kilde</th>
              <th className="px-4 py-2 w-20" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {ledetradRader.map((rad) => {
              const key = nøkkel(rad);
              const erRedigert = key in redigerer;
              const kilde = rad.oppslag.kilde ?? "ukjent";
              return (
                <tr key={key} className="hover:bg-gray-50">
                  <td className="px-4 py-2 text-gray-400 font-mono">{rad.nr}</td>
                  <td className="px-4 py-2 text-gray-400">
                    {rad.retning === "across" ? "→" : "↓"}
                  </td>
                  <td className="px-4 py-2 font-medium text-gray-800">{rad.oppslag.tekst}</td>
                  <td className="px-4 py-2">
                    {erRedigert ? (
                      <input
                        type="text"
                        value={redigerer[key]}
                        onChange={(e) =>
                          setRedigerer({ ...redigerer, [key]: e.target.value })
                        }
                        className="w-full border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
                        autoFocus
                      />
                    ) : (
                      <span
                        className={`${kilde === "mangler" ? "text-red-500 italic" : "text-gray-700"}`}
                      >
                        {rad.oppslag.ledetrad || "(mangler)"}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                        KILDE_FARGE[kilde] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {kilde}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    {erRedigert ? (
                      <div className="flex gap-1 justify-end">
                        <button
                          onClick={() => lagreLedetrad(rad)}
                          disabled={lagrer === key}
                          className="text-xs bg-gray-900 text-white px-2 py-1 rounded hover:bg-gray-800 disabled:opacity-60"
                        >
                          {lagrer === key ? "…" : "Lagre"}
                        </button>
                        <button
                          onClick={() => {
                            const o = { ...redigerer };
                            delete o[key];
                            setRedigerer(o);
                          }}
                          className="text-xs text-gray-500 px-2 py-1 hover:text-gray-700"
                        >
                          Avbryt
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() =>
                          setRedigerer({ ...redigerer, [key]: rad.oppslag.ledetrad ?? "" })
                        }
                        className="text-xs text-blue-600 hover:text-blue-800"
                      >
                        Rediger
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusBadge({ label, aktiv }: { label: string; aktiv: boolean }) {
  if (!aktiv) return null;
  const farge =
    label === "publisert" ? "bg-green-100 text-green-800" :
    label === "godkjent"  ? "bg-amber-100 text-amber-800" :
                            "bg-gray-100 text-gray-600";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${farge}`}>
      {label}
    </span>
  );
}

function AsciiGrid({ grid }: { grid: string[][] }) {
  const CELLE_STR = 28;
  return (
    <div
      className="font-mono text-xs leading-none inline-block border border-gray-300 rounded"
      style={{ fontSize: 11 }}
    >
      {grid.map((rad, r) => (
        <div key={r} className="flex">
          {rad.map((celle, k) => (
            <div
              key={k}
              className={`flex items-center justify-center border border-gray-200 font-bold uppercase ${
                celle === "#"
                  ? "bg-gray-800 text-transparent"
                  : "bg-white text-gray-800"
              }`}
              style={{ width: CELLE_STR, height: CELLE_STR, flexShrink: 0 }}
            >
              {celle !== "#" ? celle : ""}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
