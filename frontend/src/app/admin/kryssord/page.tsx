"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { adminApi, type AdminKryssordElement } from "@/lib/adminApi";

const STATUS_BADGE: Record<string, string> = {
  publisert: "bg-green-100 text-green-800",
  godkjent:  "bg-amber-100 text-amber-800",
  utkast:    "bg-gray-100 text-gray-600",
};

function statusLabel(k: AdminKryssordElement): string {
  if (k.publisert) return "publisert";
  if (k.godkjent)  return "godkjent";
  return "utkast";
}

function formaterDato(iso: string) {
  return new Date(iso).toLocaleDateString("nb-NO", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export default function KryssordListePage() {
  const [kryssord, setKryssord] = useState<AdminKryssordElement[]>([]);
  const [laster, setLaster] = useState(true);
  const [filter, setFilter] = useState<"alle" | "utkast" | "godkjent" | "publisert">("alle");

  async function last() {
    setLaster(true);
    try {
      const data = await adminApi.hentAlle();
      setKryssord(data.kryssord);
    } finally {
      setLaster(false);
    }
  }

  useEffect(() => { last(); }, []);

  async function slett(id: string, tittel: string) {
    if (!confirm(`Slett "${tittel}"?`)) return;
    await adminApi.slett(id);
    await last();
  }

  const filtrert = kryssord.filter((k) => {
    if (filter === "alle") return true;
    return statusLabel(k) === filter;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Kryssord</h1>
          <p className="text-sm text-gray-500 mt-1">{kryssord.length} kryssord totalt</p>
        </div>
        <Link
          href="/admin/generer"
          className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-800 transition-colors"
        >
          + Generer nytt
        </Link>
      </div>

      {/* Filter */}
      <div className="flex gap-2 flex-wrap">
        {(["alle", "utkast", "godkjent", "publisert"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              filter === f ? "bg-gray-900 text-white" : "bg-white border border-gray-300 text-gray-600 hover:border-gray-400"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {laster ? (
        <div className="text-center py-12 text-gray-400">Laster…</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Tittel</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Størrelse</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Ord</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Opprettet</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtrert.map((k) => {
                const st = statusLabel(k);
                return (
                  <tr key={k.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <Link
                        href={`/admin/kryssord/${k.id}`}
                        className="font-medium text-gray-900 hover:underline"
                      >
                        {k.tittel}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {k.grid_storrelse}×{k.grid_storrelse}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{k.antall_ord}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[st]}`}>
                        {st}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {formaterDato(k.opprettet_dato)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => slett(k.id, k.tittel)}
                        className="text-xs text-red-500 hover:text-red-700"
                      >
                        Slett
                      </button>
                    </td>
                  </tr>
                );
              })}
              {filtrert.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                    Ingen kryssord.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
