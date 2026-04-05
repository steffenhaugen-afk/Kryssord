"use client";

import type { LedetradJson, LedetradOppslag } from "@/types/kryssord";

interface LedetradProps {
  ledetrad_json: LedetradJson;
  valgtNr: number | null;
  valgtRetning: "across" | "down";
  onVelg: (nr: number, retning: "across" | "down") => void;
}

function LedetradListe({
  tittel,
  oppslag,
  valgtNr,
  retning,
  onVelg,
}: {
  tittel: string;
  oppslag: Record<string, LedetradOppslag>;
  valgtNr: number | null;
  retning: "across" | "down";
  onVelg: (nr: number, retning: "across" | "down") => void;
}) {
  const sortert = Object.values(oppslag).sort((a, b) => a.nr - b.nr);

  return (
    <div className="flex-1 min-w-0">
      <h3 className="font-semibold text-sm uppercase tracking-wide text-gray-500 mb-2">
        {tittel}
      </h3>
      <ul className="space-y-0.5">
        {sortert.map((o) => (
          <li key={o.nr}>
            <button
              onClick={() => onVelg(o.nr, retning)}
              className={`w-full text-left px-2 py-1 rounded text-sm transition-colors ${
                valgtNr === o.nr
                  ? "bg-blue-600 text-white"
                  : "hover:bg-gray-100 text-gray-800"
              }`}
            >
              <span className="font-medium mr-1.5">{o.nr}.</span>
              {o.ledetrad}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Ledetrad({
  ledetrad_json,
  valgtNr,
  valgtRetning,
  onVelg,
}: LedetradProps) {
  return (
    <div className="flex gap-6 mt-4">
      <LedetradListe
        tittel="Vannrett"
        oppslag={ledetrad_json.across}
        valgtNr={valgtRetning === "across" ? valgtNr : null}
        retning="across"
        onVelg={onVelg}
      />
      <LedetradListe
        tittel="Loddrett"
        oppslag={ledetrad_json.down}
        valgtNr={valgtRetning === "down" ? valgtNr : null}
        retning="down"
        onVelg={onVelg}
      />
    </div>
  );
}
