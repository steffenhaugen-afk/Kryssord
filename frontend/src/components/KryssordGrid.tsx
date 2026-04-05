"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
import type { GridJson, LedetradJson, LedetradOppslag } from "@/types/kryssord";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export type Retning = "across" | "down";

interface CellePos {
  rad: number;
  kol: number;
}

interface State {
  brukerGrid: string[][];      // brukerens bokstaver
  sjekket: boolean[][];        // om cellen er sjekket
  korrekt: boolean[][];        // korrekthet per celle
  valgtCelle: CellePos | null;
  valgtRetning: Retning;
  ferdig: boolean;
}

type Action =
  | { type: "VELG_CELLE"; celle: CellePos; retning?: Retning }
  | { type: "SKRIV_BOKSTAV"; bokstav: string }
  | { type: "SLETT" }
  | { type: "SJEKK" }
  | { type: "NESTE_CELLE" }
  | { type: "FORRIGE_CELLE" };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function lagTomGrid(storrelse: number): string[][] {
  return Array.from({ length: storrelse }, () => Array(storrelse).fill(""));
}

function lagBoolGrid(storrelse: number, verdi = false): boolean[][] {
  return Array.from({ length: storrelse }, () => Array(storrelse).fill(verdi));
}

/** Finn alle celler som tilhører et ord (fra ledetrad_json) */
function ordCeller(oppslag: LedetradOppslag, retning: Retning): CellePos[] {
  const celler: CellePos[] = [];
  for (let i = 0; i < oppslag.lengde; i++) {
    celler.push(
      retning === "across"
        ? { rad: oppslag.rad, kol: oppslag.kol + i }
        : { rad: oppslag.rad + i, kol: oppslag.kol }
    );
  }
  return celler;
}

/** Finn hvilket ord (nr + retning) en celle tilhører */
function finnOrd(
  celle: CellePos,
  ledetrad: LedetradJson,
  preferertRetning: Retning
): { nr: number; retning: Retning } | null {
  const retninger: Retning[] = [preferertRetning, preferertRetning === "across" ? "down" : "across"];
  for (const retning of retninger) {
    for (const [nrStr, oppslag] of Object.entries(ledetrad[retning])) {
      const celler = ordCeller(oppslag, retning);
      if (celler.some((c) => c.rad === celle.rad && c.kol === celle.kol)) {
        return { nr: Number(nrStr), retning };
      }
    }
  }
  return null;
}

/** Neste tomme celle i samme ord, eller neste celle */
function nesteCelle(
  celle: CellePos,
  nr: number,
  retning: Retning,
  ledetrad: LedetradJson,
  brukerGrid: string[][]
): CellePos {
  const oppslag = ledetrad[retning][String(nr)];
  if (!oppslag) return celle;
  const celler = ordCeller(oppslag, retning);
  const idx = celler.findIndex((c) => c.rad === celle.rad && c.kol === celle.kol);
  // Søk frem etter tom celle
  for (let i = idx + 1; i < celler.length; i++) {
    if (!brukerGrid[celler[i].rad][celler[i].kol]) return celler[i];
  }
  // Ellers bare neste
  if (idx + 1 < celler.length) return celler[idx + 1];
  return celle;
}

function forrigeCelle(
  celle: CellePos,
  nr: number,
  retning: Retning,
  ledetrad: LedetradJson
): CellePos {
  const oppslag = ledetrad[retning][String(nr)];
  if (!oppslag) return celle;
  const celler = ordCeller(oppslag, retning);
  const idx = celler.findIndex((c) => c.rad === celle.rad && c.kol === celle.kol);
  if (idx > 0) return celler[idx - 1];
  return celle;
}

/** Er kryssordet ferdig løst? */
function erFerdig(brukerGrid: string[][], fasitGrid: string[][]): boolean {
  for (let r = 0; r < fasitGrid.length; r++) {
    for (let k = 0; k < fasitGrid[r].length; k++) {
      if (fasitGrid[r][k] === "#") continue;
      if (brukerGrid[r][k].toLowerCase() !== fasitGrid[r][k].toLowerCase()) return false;
    }
  }
  return true;
}

// ---------------------------------------------------------------------------
// Nummerering: bygg et kart {rad-kol: nr} fra ledetrad_json
// ---------------------------------------------------------------------------
function byggNummerKart(ledetrad: LedetradJson): Map<string, number> {
  const kart = new Map<string, number>();
  for (const retning of ["across", "down"] as Retning[]) {
    for (const [nrStr, oppslag] of Object.entries(ledetrad[retning])) {
      kart.set(`${oppslag.rad}-${oppslag.kol}`, Number(nrStr));
    }
  }
  return kart;
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------
function lagInitState(grid: GridJson): State {
  return {
    brukerGrid: lagTomGrid(grid.storrelse),
    sjekket: lagBoolGrid(grid.storrelse),
    korrekt: lagBoolGrid(grid.storrelse),
    valgtCelle: null,
    valgtRetning: "across",
    ferdig: false,
  };
}

function reducer(
  state: State,
  action: Action,
  grid: GridJson,
  ledetrad: LedetradJson
): State {
  switch (action.type) {
    case "VELG_CELLE": {
      const { celle, retning } = action;
      if (grid.celler[celle.rad][celle.kol] === "#") return state;

      // Klikk på samme celle → bytt retning
      const sammePos =
        state.valgtCelle?.rad === celle.rad && state.valgtCelle?.kol === celle.kol;
      const nyRetning = retning
        ? retning
        : sammePos
        ? state.valgtRetning === "across" ? "down" : "across"
        : state.valgtRetning;

      // Sjekk om retning er gyldig for denne cellen
      const ord = finnOrd(celle, ledetrad, nyRetning);
      const faktiskRetning = ord?.retning ?? nyRetning;

      return { ...state, valgtCelle: celle, valgtRetning: faktiskRetning };
    }

    case "SKRIV_BOKSTAV": {
      if (!state.valgtCelle || state.ferdig) return state;
      const { rad, kol } = state.valgtCelle;
      if (grid.celler[rad][kol] === "#") return state;

      const nyGrid = state.brukerGrid.map((r) => [...r]);
      nyGrid[rad][kol] = action.bokstav.toLowerCase();

      const ord = finnOrd(state.valgtCelle, ledetrad, state.valgtRetning);
      const nyPos = ord
        ? nesteCelle(state.valgtCelle, ord.nr, ord.retning, ledetrad, nyGrid)
        : state.valgtCelle;

      const ferdig = erFerdig(nyGrid, grid.celler);
      return {
        ...state,
        brukerGrid: nyGrid,
        valgtCelle: nyPos,
        ferdig,
        // Nullstill sjekk-markering for denne cellen
        sjekket: state.sjekket.map((r, ri) =>
          r.map((v, ki) => (ri === rad && ki === kol ? false : v))
        ),
      };
    }

    case "SLETT": {
      if (!state.valgtCelle) return state;
      const { rad, kol } = state.valgtCelle;
      const nyGrid = state.brukerGrid.map((r) => [...r]);

      if (nyGrid[rad][kol]) {
        // Slett gjeldende celle
        nyGrid[rad][kol] = "";
        return { ...state, brukerGrid: nyGrid };
      } else {
        // Gå tilbake og slett forrige
        const ord = finnOrd(state.valgtCelle, ledetrad, state.valgtRetning);
        const forrige = ord
          ? forrigeCelle(state.valgtCelle, ord.nr, ord.retning, ledetrad)
          : state.valgtCelle;
        nyGrid[forrige.rad][forrige.kol] = "";
        return { ...state, brukerGrid: nyGrid, valgtCelle: forrige };
      }
    }

    case "SJEKK": {
      const nyKorrekt = grid.celler.map((rad, r) =>
        rad.map((fasit, k) => {
          if (fasit === "#") return false;
          return (
            !!state.brukerGrid[r][k] &&
            state.brukerGrid[r][k].toLowerCase() === fasit.toLowerCase()
          );
        })
      );
      const nySjekket = grid.celler.map((rad, r) =>
        rad.map((fasit, k) => fasit !== "#" && !!state.brukerGrid[r][k])
      );
      return { ...state, korrekt: nyKorrekt, sjekket: nySjekket };
    }

    case "NESTE_CELLE": {
      if (!state.valgtCelle) return state;
      const ord = finnOrd(state.valgtCelle, ledetrad, state.valgtRetning);
      if (!ord) return state;
      const neste = nesteCelle(
        state.valgtCelle, ord.nr, ord.retning, ledetrad, state.brukerGrid
      );
      return { ...state, valgtCelle: neste };
    }

    case "FORRIGE_CELLE": {
      if (!state.valgtCelle) return state;
      const ord = finnOrd(state.valgtCelle, ledetrad, state.valgtRetning);
      if (!ord) return state;
      const forrige = forrigeCelle(state.valgtCelle, ord.nr, ord.retning, ledetrad);
      return { ...state, valgtCelle: forrige };
    }

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface KryssordGridProps {
  grid_json: GridJson;
  ledetrad_json: LedetradJson;
  onOrdValgt?: (nr: number, retning: Retning) => void;
  valgtNr?: number | null;
  valgtRetningEksternt?: Retning;
}

// ---------------------------------------------------------------------------
// Komponent
// ---------------------------------------------------------------------------
export default function KryssordGrid({
  grid_json,
  ledetrad_json,
  onOrdValgt,
  valgtNr,
  valgtRetningEksternt,
}: KryssordGridProps) {
  const [state, dispatch] = useReducer(
    (s: State, a: Action) => reducer(s, a, grid_json, ledetrad_json),
    grid_json,
    lagInitState
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const nummerKart = useMemo(() => byggNummerKart(ledetrad_json), [ledetrad_json]);

  // Synkroniser eksternt valgt ord → oppdater valgtCelle
  useEffect(() => {
    if (valgtNr == null || !valgtRetningEksternt) return;
    const oppslag = ledetrad_json[valgtRetningEksternt][String(valgtNr)];
    if (!oppslag) return;
    dispatch({
      type: "VELG_CELLE",
      celle: { rad: oppslag.rad, kol: oppslag.kol },
      retning: valgtRetningEksternt,
    });
  }, [valgtNr, valgtRetningEksternt, ledetrad_json]);

  // Fortell foreldre om valgt ord
  useEffect(() => {
    if (!state.valgtCelle) return;
    const ord = finnOrd(state.valgtCelle, ledetrad_json, state.valgtRetning);
    if (ord) onOrdValgt?.(ord.nr, ord.retning);
  }, [state.valgtCelle, state.valgtRetning, ledetrad_json, onOrdValgt]);

  // Finn hvilke celler som tilhører valgt ord
  const valgtOrdCeller = useMemo((): Set<string> => {
    if (!state.valgtCelle) return new Set();
    const ord = finnOrd(state.valgtCelle, ledetrad_json, state.valgtRetning);
    if (!ord) return new Set();
    const oppslag = ledetrad_json[ord.retning][String(ord.nr)];
    return new Set(ordCeller(oppslag, ord.retning).map((c) => `${c.rad}-${c.kol}`));
  }, [state.valgtCelle, state.valgtRetning, ledetrad_json]);

  // Tastaturhåndtering
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key.match(/^[a-zA-ZæøåÆØÅ]$/) && e.key.length === 1) {
        e.preventDefault();
        dispatch({ type: "SKRIV_BOKSTAV", bokstav: e.key });
      } else if (e.key === "Backspace" || e.key === "Delete") {
        e.preventDefault();
        dispatch({ type: "SLETT" });
      } else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        if (state.valgtRetning !== "across") {
          if (state.valgtCelle)
            dispatch({ type: "VELG_CELLE", celle: state.valgtCelle, retning: "across" });
        } else {
          dispatch({ type: e.key === "ArrowRight" ? "NESTE_CELLE" : "FORRIGE_CELLE" });
        }
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (state.valgtRetning !== "down") {
          if (state.valgtCelle)
            dispatch({ type: "VELG_CELLE", celle: state.valgtCelle, retning: "down" });
        } else {
          dispatch({ type: e.key === "ArrowDown" ? "NESTE_CELLE" : "FORRIGE_CELLE" });
        }
      }
    },
    [state.valgtRetning, state.valgtCelle]
  );

  const { celler, storrelse } = grid_json;
  // Beregn cellestørrelse basert på grid-størrelse
  const celleStrl = storrelse <= 9 ? 52 : storrelse <= 13 ? 42 : 34;

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Grid */}
      <div
        ref={containerRef}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        className="outline-none focus:ring-2 focus:ring-blue-400 rounded"
        style={{ display: "inline-block" }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${storrelse}, ${celleStrl}px)`,
            gridTemplateRows: `repeat(${storrelse}, ${celleStrl}px)`,
            gap: 2,
          }}
        >
          {celler.map((rad, r) =>
            rad.map((celle, k) => {
              const erSvart = celle === "#";
              const posKey = `${r}-${k}`;
              const erValgt =
                state.valgtCelle?.rad === r && state.valgtCelle?.kol === k;
              const erIValgtOrd = valgtOrdCeller.has(posKey);
              const nummer = nummerKart.get(posKey);
              const brukerBokstav = state.brukerGrid[r][k];
              const erSjekket = state.sjekket[r][k];
              const erKorrekt = state.korrekt[r][k];

              if (erSvart) {
                return (
                  <div
                    key={posKey}
                    className="bg-gray-900"
                    style={{ width: celleStrl, height: celleStrl }}
                  />
                );
              }

              let bgFarge = "bg-white";
              if (erValgt) bgFarge = "bg-blue-300";
              else if (erIValgtOrd) bgFarge = "bg-blue-100";

              let tekstFarge = "text-gray-900";
              if (erSjekket) {
                tekstFarge = erKorrekt ? "text-green-600" : "text-red-600";
              }

              return (
                <div
                  key={posKey}
                  onClick={() =>
                    dispatch({ type: "VELG_CELLE", celle: { rad: r, kol: k } })
                  }
                  className={`relative border border-gray-300 cursor-pointer select-none flex items-center justify-center ${bgFarge}`}
                  style={{ width: celleStrl, height: celleStrl }}
                >
                  {nummer != null && (
                    <span
                      className="absolute top-0 left-0.5 text-gray-600 leading-none"
                      style={{ fontSize: celleStrl <= 34 ? 8 : 10 }}
                    >
                      {nummer}
                    </span>
                  )}
                  <span
                    className={`font-bold uppercase ${tekstFarge}`}
                    style={{ fontSize: celleStrl <= 34 ? 14 : 18 }}
                  >
                    {brukerBokstav}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Knapper */}
      <div className="flex gap-3">
        <button
          onClick={() => dispatch({ type: "SJEKK" })}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          Sjekk svar
        </button>
      </div>

      {/* Ferdig-melding */}
      {state.ferdig && (
        <div className="mt-2 px-6 py-3 bg-green-100 border border-green-400 text-green-800 rounded-lg font-semibold text-lg">
          Gratulerer, kryssordet er løst!
        </div>
      )}
    </div>
  );
}
