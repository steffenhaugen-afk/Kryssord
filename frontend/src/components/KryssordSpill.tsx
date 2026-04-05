"use client";

import { useCallback, useState } from "react";
import type { Kryssord } from "@/types/kryssord";
import type { Retning } from "./KryssordGrid";
import KryssordGrid from "./KryssordGrid";
import Ledetrad from "./Ledetrad";
import Timer from "./Timer";

interface KryssordSpillProps {
  kryssord: Kryssord;
}

export default function KryssordSpill({ kryssord }: KryssordSpillProps) {
  const [valgtNr, setValgtNr] = useState<number | null>(null);
  const [valgtRetning, setValgtRetning] = useState<Retning>("across");
  const [timerKjorer, setTimerKjorer] = useState(true);

  const handleOrdValgt = useCallback((nr: number, retning: Retning) => {
    setValgtNr(nr);
    setValgtRetning(retning);
  }, []);

  const handleLedetradKlikk = useCallback((nr: number, retning: Retning) => {
    setValgtNr(nr);
    setValgtRetning(retning);
  }, []);

  const vanskelighetsfarger: Record<string, string> = {
    lett: "bg-green-100 text-green-800",
    middels: "bg-yellow-100 text-yellow-800",
    vanskelig: "bg-red-100 text-red-800",
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      {/* Topplinje */}
      <div className="flex items-start justify-between mb-4 gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{kryssord.tittel}</h1>
          <div className="flex items-center gap-2 mt-1">
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                vanskelighetsfarger[kryssord.vanskelighetsgrad] ?? ""
              }`}
            >
              {kryssord.vanskelighetsgrad}
            </span>
            <span className="text-xs text-gray-500">
              {kryssord.grid_storrelse}×{kryssord.grid_storrelse}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Timer running={timerKjorer} />
          <button
            onClick={() => setTimerKjorer((v) => !v)}
            className="text-xs text-gray-500 hover:text-gray-700 underline"
          >
            {timerKjorer ? "Pause" : "Start"}
          </button>
        </div>
      </div>

      {/* Grid + ledetråder */}
      <div className="flex flex-col lg:flex-row gap-8 items-start">
        <KryssordGrid
          grid_json={kryssord.grid_json}
          ledetrad_json={kryssord.ledetrad_json}
          onOrdValgt={handleOrdValgt}
          valgtNr={valgtNr}
          valgtRetningEksternt={valgtRetning}
        />
        <div className="flex-1 min-w-0">
          <Ledetrad
            ledetrad_json={kryssord.ledetrad_json}
            valgtNr={valgtNr}
            valgtRetning={valgtRetning}
            onVelg={handleLedetradKlikk}
          />
        </div>
      </div>
    </div>
  );
}
