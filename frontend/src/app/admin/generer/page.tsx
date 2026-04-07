"use client";

import { useState } from "react";
import type { Kryssord } from "@/types/kryssord";
import KryssordSpill from "@/components/KryssordSpill";
import { adminApi } from "@/lib/adminApi";

const STORRELSE_OPTS = [
  { value: 9,  label: "9×9 (lett)" },
  { value: 13, label: "13×13 (middels)" },
  { value: 17, label: "17×17 (vanskelig)" },
];

const TEMA_OPTS = [
  { value: "generell",  label: "Generell" },
  { value: "geografi",  label: "Geografi" },
  { value: "politikk",  label: "Politikk" },
  { value: "natur",     label: "Natur" },
  { value: "sport",     label: "Sport" },
];

type Status = "idle" | "genererer" | "klar" | "lagret" | "forkastet" | "feil";

export default function GenererPage() {
  const [storrelse, setStorrelse] = useState(13);
  const [tema, setTema] = useState("generell");
  const [tvangOrd, setTvangOrd] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [feil, setFeil] = useState("");
  const [kryssord, setKryssord] = useState<Kryssord | null>(null);
  const [lagretMelding, setLagretMelding] = useState("");

  async function generer() {
    setStatus("genererer");
    setFeil("");
    setKryssord(null);
    try {
      const tvangListe = tvangOrd
        .split(",")
        .map((o) => o.trim().toLowerCase())
        .filter(Boolean);

      const data = await adminApi.generer({ storrelse, tema, tvang_ord: tvangListe });
      setKryssord(data as unknown as Kryssord);
      setStatus("klar");
    } catch (e) {
      setFeil(e instanceof Error ? e.message : "Generering feilet");
      setStatus("feil");
    }
  }

  async function lagreSomUtkast() {
    if (!kryssord) return;
    // Kryssordet er allerede lagret i DB som utkast — bare meld fra
    setLagretMelding(`Lagret som utkast (${kryssord.tittel})`);
    setStatus("lagret");
  }

  async function forkast() {
    if (!kryssord) return;
    try {
      await adminApi.slett(kryssord.id);
      setKryssord(null);
      setStatus("forkastet");
      setLagretMelding("Utkast forkastet og slettet.");
    } catch {
      setFeil("Kunne ikke slette utkast.");
    }
  }

  const kjoreTid = storrelse === 9 ? "~10 sek" : storrelse === 13 ? "~20 sek" : "~60 sek";

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Generer kryssord</h1>
        <p className="text-sm text-gray-500 mt-1">
          Generering tar {kjoreTid} inkl. ledetråder.
        </p>
      </div>

      {/* Konfig */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Størrelse</label>
            <div className="flex gap-2 flex-wrap">
              {STORRELSE_OPTS.map((o) => (
                <button
                  key={o.value}
                  onClick={() => setStorrelse(o.value)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    storrelse === o.value
                      ? "bg-gray-900 text-white border-gray-900"
                      : "bg-white text-gray-700 border-gray-300 hover:border-gray-400"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tema</label>
            <select
              value={tema}
              onChange={(e) => setTema(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-gray-400"
            >
              {TEMA_OPTS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Tving inn ord{" "}
            <span className="font-normal text-gray-400">(kommaseparert, valgfritt)</span>
          </label>
          <input
            type="text"
            value={tvangOrd}
            onChange={(e) => setTvangOrd(e.target.value)}
            placeholder="oslo, fjord, skog"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
          />
          <p className="text-xs text-gray-400 mt-1">
            Ord legges øverst i ordpoolen — ingen garanti for at de brukes.
          </p>
        </div>

        <button
          onClick={generer}
          disabled={status === "genererer"}
          className="bg-gray-900 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-60 transition-colors flex items-center gap-2"
        >
          {status === "genererer" ? (
            <>
              <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              Genererer…
            </>
          ) : "Generer"}
        </button>

        {feil && (
          <p className="text-red-600 text-sm bg-red-50 px-3 py-2 rounded-lg">{feil}</p>
        )}
      </div>

      {/* Forhåndsvis */}
      {kryssord && status === "klar" && (
        <div className="space-y-4">
          <LedetradKvalitet kryssord={kryssord} />
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Forhåndsvisning</h2>
            <KryssordSpill kryssord={kryssord} />
          </div>
          <div className="flex gap-3">
            <button
              onClick={lagreSomUtkast}
              className="bg-amber-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-amber-700 transition-colors"
            >
              Lagre som utkast
            </button>
            <button
              onClick={forkast}
              className="bg-white text-red-600 border border-red-300 px-5 py-2 rounded-lg text-sm font-medium hover:bg-red-50 transition-colors"
            >
              Forkast
            </button>
          </div>
        </div>
      )}

      {(status === "lagret" || status === "forkastet") && lagretMelding && (
        <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
          {lagretMelding}
          {status === "lagret" && (
            <a href="/admin/kryssord" className="ml-2 underline font-medium">
              Gå til kryssord-listen →
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function LedetradKvalitet({ kryssord }: { kryssord: Kryssord }) {
  const alle = [
    ...Object.values(kryssord.ledetrad_json.across),
    ...Object.values(kryssord.ledetrad_json.down),
  ];
  const kildeTeller: Record<string, number> = {};
  for (const o of alle) {
    const k = (o as { kilde?: string }).kilde ?? "ukjent";
    kildeTeller[k] = (kildeTeller[k] ?? 0) + 1;
  }
  const mangler = kildeTeller["mangler"] ?? 0;

  return (
    <div className={`rounded-xl border px-5 py-4 ${mangler > 0 ? "bg-red-50 border-red-200" : "bg-green-50 border-green-200"}`}>
      <h3 className={`text-sm font-semibold mb-2 ${mangler > 0 ? "text-red-800" : "text-green-800"}`}>
        Ledetråd-kvalitet — {alle.length} ord totalt
      </h3>
      <div className="flex flex-wrap gap-3">
        {Object.entries(kildeTeller).map(([kilde, antall]) => (
          <span
            key={kilde}
            className={`text-xs px-2 py-1 rounded font-medium ${
              kilde === "mangler"
                ? "bg-red-100 text-red-700"
                : kilde === "kryssordkongen"
                ? "bg-blue-100 text-blue-700"
                : "bg-gray-100 text-gray-700"
            }`}
          >
            {kilde}: {antall}
          </span>
        ))}
      </div>
    </div>
  );
}
