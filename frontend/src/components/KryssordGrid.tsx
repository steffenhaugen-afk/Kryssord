"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
import type { GridJson, LedetradJson } from "@/types/kryssord";

// ─── Colours ────────────────────────────────────────────────────────────────
const C = {
  bg:             "#F5F0E8",
  svart:          "#2C2C2C",
  hvit:           "#FFFFFF",
  border:         "#C8BFA8",
  ledetradBg:     "#EDE8DC",
  ledetradBorder: "#A09070",
  highlight:      "rgba(240,208,128,0.35)",
  active:         "rgba(240,208,128,0.90)",
  ok:             "#4A7C59",
  feil:           "#B05252",
};

// ─── Types ───────────────────────────────────────────────────────────────────
export type Retning = "across" | "down";

interface CellePos { rad: number; kol: number }

/** Word position derived by scanning the grid – NOT from ledetrad_json */
interface OrdPosisjon { rad: number; kol: number; lengde: number }

type OrdPosisjonMap = { across: Record<number, OrdPosisjon>; down: Record<number, OrdPosisjon> };

interface BehandletCelle {
  type:              "bokstav" | "ledetrad" | "svart";
  bokstav?:          string;
  ledetradVannrett?: string;
  ledetradLoddrett?: string;
  acrossNr?:         number;
  downNr?:           number;
}

interface State {
  brukerGrid:   string[][];
  sjekket:      boolean[][];
  korrekt:      boolean[][];
  valgtCelle:   CellePos | null;
  valgtRetning: Retning;
  ferdig:       boolean;
}

type Action =
  | { type: "VELG_CELLE";    celle: CellePos; retning?: Retning }
  | { type: "SKRIV_BOKSTAV"; bokstav: string }
  | { type: "SLETT" }
  | { type: "SJEKK" }
  | { type: "NESTE_CELLE" }
  | { type: "FORRIGE_CELLE" };

// ─── Grid computation ────────────────────────────────────────────────────────

function lagTomGrid(n: number): string[][]  { return Array.from({ length: n }, () => Array(n).fill("")) }
function lagBoolGrid(n: number): boolean[][] { return Array.from({ length: n }, () => Array(n).fill(false)) }

/**
 * Scans celler[][] to derive word start positions and lengths using standard
 * crossword numbering (left-to-right, top-to-bottom, same number for across
 * and down words sharing the same start cell).
 */
function byggOrdPosisjoner(celler: string[][]): OrdPosisjonMap {
  const n = celler.length;
  const across: Record<number, OrdPosisjon> = {};
  const down: Record<number, OrdPosisjon> = {};
  let nr = 1;

  for (let r = 0; r < n; r++) {
    const rad = celler[r] ?? [];
    for (let k = 0; k < rad.length; k++) {
      if (rad[k] === "#") continue;

      const starterAcross =
        (k === 0 || rad[k - 1] === "#") &&
        k + 1 < rad.length && rad[k + 1] !== "#";
      const starterDown =
        (r === 0 || (celler[r - 1]?.[k] ?? "#") === "#") &&
        r + 1 < n && (celler[r + 1]?.[k] ?? "#") !== "#";

      if (starterAcross || starterDown) {
        if (starterAcross) {
          let lengde = 0;
          while (k + lengde < rad.length && rad[k + lengde] !== "#") lengde++;
          across[nr] = { rad: r, kol: k, lengde };
        }
        if (starterDown) {
          let lengde = 0;
          while (r + lengde < n && (celler[r + lengde]?.[k] ?? "#") !== "#") lengde++;
          down[nr] = { rad: r, kol: k, lengde };
        }
        nr++;
      }
    }
  }

  return { across, down };
}

/**
 * Builds the processed cell grid.
 * Rule: ANY black cell with a letter immediately to its right OR immediately
 * below becomes a ledetrad-celle (not a plain black cell).
 * Uses a reverse-position lookup to attach the correct clue text and word nr.
 */
function byggBehandletGrid(
  grid: GridJson,
  ledetrad: LedetradJson,
  posMap: OrdPosisjonMap,
): BehandletCelle[][] {
  const { celler } = grid;
  const n = celler.length;

  console.log("[KryssordGrid] celler[0]:", JSON.stringify(celler[0]));
  console.log("[KryssordGrid] celler[1]:", JSON.stringify(celler[1]));

  // Reverse lookup: "rad-kol" → word number, for each direction
  const acrossStart: Record<string, number> = {};
  const downStart:   Record<string, number> = {};
  for (const [nrStr, pos] of Object.entries(posMap.across))
    acrossStart[`${pos.rad}-${pos.kol}`] = Number(nrStr);
  for (const [nrStr, pos] of Object.entries(posMap.down))
    downStart[`${pos.rad}-${pos.kol}`] = Number(nrStr);

  const ut: BehandletCelle[][] = celler.map((rad) =>
    rad.map((c) =>
      c === "#" ? { type: "svart" } : { type: "bokstav", bokstav: c }
    )
  );

  const debugLog: string[] = [];

  for (let r = 0; r < n; r++) {
    const rad = celler[r] ?? [];
    const kolLengde = rad.length;
    for (let k = 0; k < kolLengde; k++) {
      if (rad[k] !== "#") continue;

      // → only if the cell to the right is the START of an across word
      const harHøyre =
        k + 1 < kolLengde &&
        rad[k + 1] !== "#" &&
        acrossStart[`${r}-${k + 1}`] != null;
      // ↓ only if the cell below is the START of a down word
      const nedenfor = celler[r + 1]?.[k];
      const harUnder =
        r + 1 < n &&
        nedenfor !== undefined &&
        nedenfor !== "#" &&
        downStart[`${r + 1}-${k}`] != null;

      if (!harHøyre && !harUnder) continue;

      let celle: BehandletCelle = { type: "ledetrad" };
      const info: string[] = [];

      if (harHøyre) {
        const nrAcross = acrossStart[`${r}-${k + 1}`];
        const tekst = nrAcross != null ? (ledetrad.across[String(nrAcross)]?.ledetrad ?? "") : "";
        celle = { ...celle, ledetradVannrett: tekst, acrossNr: nrAcross };
        info.push(`→ nr${nrAcross ?? "?"} "${tekst.slice(0, 20)}"`);
      }
      if (harUnder) {
        const nrDown = downStart[`${r + 1}-${k}`];
        const tekst = nrDown != null ? (ledetrad.down[String(nrDown)]?.ledetrad ?? "") : "";
        celle = { ...celle, ledetradLoddrett: tekst, downNr: nrDown };
        info.push(`↓ nr${nrDown ?? "?"} "${tekst.slice(0, 20)}"`);
      }

      ut[r][k] = celle;
      debugLog.push(`(${r},${k}): ${info.join(" | ")}`);
    }
  }

  console.log(`[KryssordGrid] Ledetråd-celler (${debugLog.length} stk):`);
  debugLog.forEach((l) => console.log(" ", l));
  return ut;
}

// ─── Word helpers ─────────────────────────────────────────────────────────────

function ordCeller(pos: OrdPosisjon, retning: Retning): CellePos[] {
  return Array.from({ length: pos.lengde }, (_, i) =>
    retning === "across"
      ? { rad: pos.rad, kol: pos.kol + i }
      : { rad: pos.rad + i, kol: pos.kol }
  );
}

function finnOrd(
  celle: CellePos,
  posMap: OrdPosisjonMap,
  preferertRetning: Retning,
): { nr: number; retning: Retning } | null {
  const retninger: Retning[] = [preferertRetning, preferertRetning === "across" ? "down" : "across"];
  for (const ret of retninger) {
    for (const [nrStr, pos] of Object.entries(posMap[ret])) {
      if (ordCeller(pos, ret).some((c) => c.rad === celle.rad && c.kol === celle.kol))
        return { nr: Number(nrStr), retning: ret };
    }
  }
  return null;
}

function nesteCelle(
  celle: CellePos, nr: number, retning: Retning,
  posMap: OrdPosisjonMap, brukerGrid: string[][],
): CellePos {
  const pos = posMap[retning][nr];
  if (!pos) return celle;
  const celler = ordCeller(pos, retning);
  const idx = celler.findIndex((c) => c.rad === celle.rad && c.kol === celle.kol);
  for (let i = idx + 1; i < celler.length; i++)
    if (!brukerGrid[celler[i].rad]?.[celler[i].kol]) return celler[i];
  return idx + 1 < celler.length ? celler[idx + 1] : celle;
}

function forrigeCelle(
  celle: CellePos, nr: number, retning: Retning, posMap: OrdPosisjonMap,
): CellePos {
  const pos = posMap[retning][nr];
  if (!pos) return celle;
  const celler = ordCeller(pos, retning);
  const idx = celler.findIndex((c) => c.rad === celle.rad && c.kol === celle.kol);
  return idx > 0 ? celler[idx - 1] : celle;
}

function erFerdig(bruker: string[][], fasit: string[][]): boolean {
  return fasit.every((rad, r) =>
    rad.every((f, k) => f === "#" || bruker[r]?.[k]?.toLowerCase() === f.toLowerCase())
  );
}

// ─── Reducer ──────────────────────────────────────────────────────────────────

function lagInitState(grid: GridJson): State {
  return {
    brukerGrid:   lagTomGrid(grid.storrelse),
    sjekket:      lagBoolGrid(grid.storrelse),
    korrekt:      lagBoolGrid(grid.storrelse),
    valgtCelle:   null,
    valgtRetning: "across",
    ferdig:       false,
  };
}

function reducer(
  s: State, a: Action, grid: GridJson, posMap: OrdPosisjonMap,
): State {
  switch (a.type) {

    case "VELG_CELLE": {
      const { celle, retning } = a;
      if (grid.celler[celle.rad]?.[celle.kol] === "#") return s;
      const sammePos = s.valgtCelle?.rad === celle.rad && s.valgtCelle?.kol === celle.kol;
      const ønsketRetning = retning
        ? retning
        : sammePos
          ? (s.valgtRetning === "across" ? "down" : "across")
          : s.valgtRetning;
      const ord = finnOrd(celle, posMap, ønsketRetning);
      return { ...s, valgtCelle: celle, valgtRetning: ord?.retning ?? ønsketRetning };
    }

    case "SKRIV_BOKSTAV": {
      if (!s.valgtCelle || s.ferdig) return s;
      const { rad, kol } = s.valgtCelle;
      if (grid.celler[rad]?.[kol] === "#") return s;
      const nyGrid = s.brukerGrid.map((r) => [...r]);
      nyGrid[rad][kol] = a.bokstav.toLowerCase();
      const ord = finnOrd(s.valgtCelle, posMap, s.valgtRetning);
      const nyPos = ord ? nesteCelle(s.valgtCelle, ord.nr, ord.retning, posMap, nyGrid) : s.valgtCelle;
      return {
        ...s,
        brukerGrid: nyGrid,
        valgtCelle: nyPos,
        ferdig: erFerdig(nyGrid, grid.celler),
        sjekket: s.sjekket.map((r, ri) => r.map((v, ki) => ri === rad && ki === kol ? false : v)),
      };
    }

    case "SLETT": {
      if (!s.valgtCelle) return s;
      const { rad, kol } = s.valgtCelle;
      const nyGrid = s.brukerGrid.map((r) => [...r]);
      if (nyGrid[rad]?.[kol]) {
        nyGrid[rad][kol] = "";
        return { ...s, brukerGrid: nyGrid };
      }
      const ord = finnOrd(s.valgtCelle, posMap, s.valgtRetning);
      const forrige = ord ? forrigeCelle(s.valgtCelle, ord.nr, ord.retning, posMap) : s.valgtCelle;
      if (nyGrid[forrige.rad]) nyGrid[forrige.rad][forrige.kol] = "";
      return { ...s, brukerGrid: nyGrid, valgtCelle: forrige };
    }

    case "SJEKK": {
      const nyKorrekt = grid.celler.map((rad, r) =>
        rad.map((f, k) => f !== "#" && !!s.brukerGrid[r]?.[k] && s.brukerGrid[r][k].toLowerCase() === f.toLowerCase())
      );
      const nySjekket = grid.celler.map((rad, r) =>
        rad.map((f, k) => f !== "#" && !!s.brukerGrid[r]?.[k])
      );
      return { ...s, korrekt: nyKorrekt, sjekket: nySjekket };
    }

    case "NESTE_CELLE": {
      if (!s.valgtCelle) return s;
      const ord = finnOrd(s.valgtCelle, posMap, s.valgtRetning);
      if (!ord) return s;
      return { ...s, valgtCelle: nesteCelle(s.valgtCelle, ord.nr, ord.retning, posMap, s.brukerGrid) };
    }

    case "FORRIGE_CELLE": {
      if (!s.valgtCelle) return s;
      const ord = finnOrd(s.valgtCelle, posMap, s.valgtRetning);
      if (!ord) return s;
      return { ...s, valgtCelle: forrigeCelle(s.valgtCelle, ord.nr, ord.retning, posMap) };
    }

    default: return s;
  }
}

// ─── Sub-components ──────────────────────────────────────────────────────────

/** Font size for single-clue cell: scales 11→7px by text length */
function enkeltFs(tekst: string): number {
  if (tekst.length <= 15) return 11;
  if (tekst.length <= 25) return 9;
  if (tekst.length <= 40) return 8;
  return 7;
}

/** Slightly smaller for dual-clue cells (less space per triangle) */
function dobbeltFs(tekst: string): number {
  if (tekst.length <= 12) return 10;
  if (tekst.length <= 20) return 8;
  if (tekst.length <= 30) return 7;
  return 6;
}

interface LedetradCelleProps {
  celle:   BehandletCelle;
  strl:    number;
  onClick: (retning: Retning) => void;
}

function LedetradCelleView({ celle, strl, onClick }: LedetradCelleProps) {
  const harBegge = !!(celle.ledetradVannrett != null && celle.ledetradLoddrett != null);

  const baseCss: React.CSSProperties = {
    width:           strl,
    height:          strl,
    backgroundColor: C.ledetradBg,
    border:          `1px solid ${C.ledetradBorder}`,
    borderRadius:    3,
    position:        "relative",
    overflow:        "hidden",
    cursor:          "pointer",
    flexShrink:      0,
  };

  // ── Single clue ──────────────────────────────────────────────────────────────
  if (!harBegge) {
    const erVannrett = celle.ledetradVannrett != null;
    const tekst = (celle.ledetradVannrett ?? celle.ledetradLoddrett) ?? "";
    const fs = enkeltFs(tekst);
    return (
      <div
        style={baseCss}
        onClick={() => onClick(erVannrett ? "across" : "down")}
        title={`${erVannrett ? "→" : "↓"} ${tekst}`}
      >
        <div
          style={{
            position:       "absolute",
            inset:          2,
            display:        "flex",
            flexDirection:  "column",
            justifyContent: "flex-end",
            alignItems:     erVannrett ? "flex-end" : "flex-start",
          }}
        >
          <span
            style={{
              fontSize:        fs,
              lineHeight:      1.2,
              color:           "#3A3028",
              fontFamily:      "system-ui, sans-serif",
              fontWeight:      600,
              overflow:        "hidden",
              display:         "-webkit-box",
              WebkitLineClamp: 3,
              WebkitBoxOrient: "vertical",
              textAlign:       erVannrett ? "right" : "left",
              wordBreak:       "break-word",
            }}
          >
            {erVannrett ? "→ " : "↓ "}{tekst}
          </span>
        </div>
      </div>
    );
  }

  // ── Dual clue – diagonal split ───────────────────────────────────────────────
  // Diagonal goes top-left → bottom-right.
  // Across (→) lives in the top-right triangle.
  // Down   (↓) lives in the bottom-left triangle.
  // Each triangle is half the cell; we clip text content to avoid the stroke.
  const fsV = dobbeltFs(celle.ledetradVannrett!);
  const fsL = dobbeltFs(celle.ledetradLoddrett!);
  // Triangle width: a bit less than half cell to stay clear of diagonal
  const triW = Math.floor(strl * 0.54);
  const pad  = 2;

  return (
    <div style={baseCss} title={`→ ${celle.ledetradVannrett}\n↓ ${celle.ledetradLoddrett}`}>
      {/* Diagonal divider */}
      <svg
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
        width={strl}
        height={strl}
        aria-hidden
      >
        <line
          x1={0} y1={0} x2={strl} y2={strl}
          stroke={C.ledetradBorder}
          strokeWidth={1.5}
        />
      </svg>

      {/* Top-right triangle – across clue */}
      <div
        onClick={() => onClick("across")}
        style={{
          position:  "absolute",
          top:        pad,
          right:      pad,
          width:      triW,
          maxHeight:  "52%",
          overflow:   "hidden",
          textAlign:  "right",
        }}
      >
        <span
          style={{
            fontSize:        fsV,
            lineHeight:      1.2,
            color:           "#3A3028",
            fontFamily:      "system-ui, sans-serif",
            fontWeight:      600,
            display:         "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow:        "hidden",
            wordBreak:       "break-word",
          }}
        >
          →&nbsp;{celle.ledetradVannrett}
        </span>
      </div>

      {/* Bottom-left triangle – down clue */}
      <div
        onClick={() => onClick("down")}
        style={{
          position:  "absolute",
          bottom:     pad,
          left:       pad,
          width:      triW,
          maxHeight:  "52%",
          overflow:   "hidden",
          textAlign:  "left",
        }}
      >
        <span
          style={{
            fontSize:        fsL,
            lineHeight:      1.2,
            color:           "#3A3028",
            fontFamily:      "system-ui, sans-serif",
            fontWeight:      600,
            display:         "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow:        "hidden",
            wordBreak:       "break-word",
          }}
        >
          ↓&nbsp;{celle.ledetradLoddrett}
        </span>
      </div>
    </div>
  );
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface KryssordGridProps {
  grid_json:             GridJson;
  ledetrad_json:         LedetradJson;
  onOrdValgt?:           (nr: number, retning: Retning) => void;
  valgtNr?:              number | null;
  valgtRetningEksternt?: Retning;
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function KryssordGrid({
  grid_json,
  ledetrad_json,
  onOrdValgt,
  valgtNr,
  valgtRetningEksternt,
}: KryssordGridProps) {
  // Derive word positions by scanning the grid (API does not provide rad/kol/lengde)
  const posMap = useMemo(
    () => byggOrdPosisjoner(grid_json.celler),
    [grid_json],
  );

  const [state, dispatch] = useReducer(
    (s: State, a: Action) => reducer(s, a, grid_json, posMap),
    grid_json,
    lagInitState,
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const gridWrapRef  = useRef<HTMLDivElement>(null);

  const pan   = useRef({ x: 0, y: 0 });
  const zoom  = useRef(1);
  const drag  = useRef<{ active: boolean; sx: number; sy: number; tx: number; ty: number }>({ active: false, sx: 0, sy: 0, tx: 0, ty: 0 });
  const pinch = useRef<number | null>(null);

  function applyTransform() {
    if (!gridWrapRef.current) return;
    gridWrapRef.current.style.transform =
      `translate(${pan.current.x}px, ${pan.current.y}px) scale(${zoom.current})`;
  }

  // ── Processed grid ───────────────────────────────────────────────────────────
  const behandletGrid = useMemo(
    () => byggBehandletGrid(grid_json, ledetrad_json, posMap),
    [grid_json, ledetrad_json, posMap],
  );

  // ── Highlighted cells for active word ────────────────────────────────────────
  const valgtOrdCeller = useMemo((): Set<string> => {
    if (!state.valgtCelle) return new Set();
    const ord = finnOrd(state.valgtCelle, posMap, state.valgtRetning);
    if (!ord) return new Set();
    const pos = posMap[ord.retning][ord.nr];
    if (!pos) return new Set();
    return new Set(ordCeller(pos, ord.retning).map((c) => `${c.rad}-${c.kol}`));
  }, [state.valgtCelle, state.valgtRetning, posMap]);

  // ── Active header clue ────────────────────────────────────────────────────────
  const aktivLedetrad = useMemo((): string => {
    if (!state.valgtCelle) return "";
    const ord = finnOrd(state.valgtCelle, posMap, state.valgtRetning);
    if (!ord) return "";
    const opp = ledetrad_json[ord.retning][String(ord.nr)];
    if (!opp) return "";
    return `${ord.retning === "across" ? "→" : "↓"} ${opp.ledetrad}`;
  }, [state.valgtCelle, state.valgtRetning, posMap, ledetrad_json]);

  // ── Sync external selection ───────────────────────────────────────────────────
  useEffect(() => {
    if (valgtNr == null || !valgtRetningEksternt) return;
    const pos = posMap[valgtRetningEksternt][valgtNr];
    if (!pos) return;
    dispatch({ type: "VELG_CELLE", celle: { rad: pos.rad, kol: pos.kol }, retning: valgtRetningEksternt });
  }, [valgtNr, valgtRetningEksternt, posMap]);

  // ── Notify parent ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!state.valgtCelle) return;
    const ord = finnOrd(state.valgtCelle, posMap, state.valgtRetning);
    if (ord) onOrdValgt?.(ord.nr, ord.retning);
  }, [state.valgtCelle, state.valgtRetning, posMap, onOrdValgt]);

  // ── Keyboard ──────────────────────────────────────────────────────────────────
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (/^[a-zA-ZæøåÆØÅ]$/.test(e.key)) {
        e.preventDefault();
        dispatch({ type: "SKRIV_BOKSTAV", bokstav: e.key });
      } else if (e.key === "Backspace" || e.key === "Delete") {
        e.preventDefault();
        dispatch({ type: "SLETT" });
      } else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        if (state.valgtRetning !== "across" && state.valgtCelle)
          dispatch({ type: "VELG_CELLE", celle: state.valgtCelle, retning: "across" });
        else
          dispatch({ type: e.key === "ArrowRight" ? "NESTE_CELLE" : "FORRIGE_CELLE" });
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (state.valgtRetning !== "down" && state.valgtCelle)
          dispatch({ type: "VELG_CELLE", celle: state.valgtCelle, retning: "down" });
        else
          dispatch({ type: e.key === "ArrowDown" ? "NESTE_CELLE" : "FORRIGE_CELLE" });
      }
    },
    [state.valgtRetning, state.valgtCelle],
  );

  // ── Pan – pointer events ───────────────────────────────────────────────────────
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (e.pointerType === "mouse" && e.button !== 1) return;
    if (e.pointerType === "touch") return;
    drag.current = { active: true, sx: e.clientX, sy: e.clientY, tx: pan.current.x, ty: pan.current.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!drag.current.active) return;
    pan.current = {
      x: drag.current.tx + e.clientX - drag.current.sx,
      y: drag.current.ty + e.clientY - drag.current.sy,
    };
    applyTransform();
  }, []);

  const onPointerUp = useCallback(() => { drag.current.active = false; }, []);

  // ── Touch events ───────────────────────────────────────────────────────────────
  const onTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      pinch.current = Math.hypot(dx, dy);
    } else if (e.touches.length === 1) {
      drag.current = {
        active: true,
        sx: e.touches[0].clientX,
        sy: e.touches[0].clientY,
        tx: pan.current.x,
        ty: pan.current.y,
      };
    }
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    e.preventDefault();
    if (e.touches.length === 2 && pinch.current !== null) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const dist = Math.hypot(dx, dy);
      zoom.current = Math.min(3, Math.max(0.5, zoom.current * (dist / pinch.current)));
      pinch.current = dist;
      applyTransform();
    } else if (e.touches.length === 1 && drag.current.active) {
      pan.current = {
        x: drag.current.tx + e.touches[0].clientX - drag.current.sx,
        y: drag.current.ty + e.touches[0].clientY - drag.current.sy,
      };
      applyTransform();
    }
  }, []);

  const onTouchEnd = useCallback(() => {
    drag.current.active = false;
    pinch.current = null;
  }, []);

  // ── Wheel zoom ─────────────────────────────────────────────────────────────────
  // Normalize deltaY to pixels (mode 0=px, 1=lines≈16px, 2=page≈400px),
  // then use Math.pow(0.999, Δpx) for smooth exponential scaling.
  // At 0.999 per pixel: 50px scroll → ×0.951, 100px → ×0.905. Feels precise.
  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    const deltaPx =
      e.deltaMode === 1 ? e.deltaY * 16 :
      e.deltaMode === 2 ? e.deltaY * 400 :
      e.deltaY;
    const factor = Math.pow(0.999, deltaPx);
    zoom.current = Math.min(3, Math.max(0.5, zoom.current * factor));
    applyTransform();
  }, []);

  // ── Cell size ──────────────────────────────────────────────────────────────────
  const { storrelse } = grid_json;
  const celleStrl = storrelse <= 9 ? 56 : storrelse <= 13 ? 46 : 38;
  const GAP = 2;

  // ─── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col items-center gap-3 select-none">

      {/* Header strip – shows active clue */}
      <div
        style={{
          width:           storrelse * (celleStrl + GAP),
          minHeight:       44,
          backgroundColor: "#EDE8DC",
          border:          `1px solid ${C.ledetradBorder}`,
          borderRadius:    8,
          padding:         "8px 14px",
          display:         "flex",
          alignItems:      "center",
        }}
      >
        {aktivLedetrad ? (
          <span style={{ fontFamily: "system-ui, sans-serif", fontSize: 15, color: "#2C2018", fontWeight: 500 }}>
            {aktivLedetrad}
          </span>
        ) : (
          <span style={{ fontFamily: "system-ui, sans-serif", fontSize: 13, color: "#A09070", fontStyle: "italic" }}>
            Velg en rute for å se ledetråden
          </span>
        )}
      </div>

      {/* Scrollable grid viewport */}
      <div
        ref={containerRef}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onWheel={onWheel}
        style={{
          outline:     "none",
          overflow:    "hidden",
          cursor:      "default",
          touchAction: "none",
          padding:     8,
          backgroundColor: C.bg,
          borderRadius: 12,
          border:      `1px solid ${C.border}`,
        }}
      >
        <div
          ref={gridWrapRef}
          style={{ display: "inline-block", transformOrigin: "top left", willChange: "transform" }}
        >
          <div
            style={{
              display:             "grid",
              gridTemplateColumns: `repeat(${storrelse}, ${celleStrl}px)`,
              gridTemplateRows:    `repeat(${storrelse}, ${celleStrl}px)`,
              gap:                 GAP,
            }}
          >
            {behandletGrid.map((rad, r) =>
              rad.map((celle, k) => {
                const posKey = `${r}-${k}`;

                // ── Svart celle ─────────────────────────────────────────────────
                if (celle.type === "svart") {
                  return (
                    <div
                      key={posKey}
                      style={{
                        width:           celleStrl,
                        height:          celleStrl,
                        backgroundColor: C.svart,
                        borderRadius:    2,
                        flexShrink:      0,
                      }}
                    />
                  );
                }

                // ── Ledetråd-celle ──────────────────────────────────────────────
                if (celle.type === "ledetrad") {
                  return (
                    <LedetradCelleView
                      key={posKey}
                      celle={celle}
                      strl={celleStrl}
                      onClick={(retning) => {
                        const nr = retning === "across" ? celle.acrossNr : celle.downNr;
                        if (nr == null) return;
                        const pos = posMap[retning][nr];
                        if (!pos) return;
                        dispatch({ type: "VELG_CELLE", celle: { rad: pos.rad, kol: pos.kol }, retning });
                      }}
                    />
                  );
                }

                // ── Bokstavrute ─────────────────────────────────────────────────
                const erValgt      = state.valgtCelle?.rad === r && state.valgtCelle?.kol === k;
                const erIValgtOrd  = valgtOrdCeller.has(posKey);
                const brukerBokstav = state.brukerGrid[r]?.[k] ?? "";
                const erSjekket    = state.sjekket[r]?.[k] ?? false;
                const erKorrekt    = state.korrekt[r]?.[k] ?? false;

                let bokstavFarge = "#1A1008";
                if (erSjekket) bokstavFarge = erKorrekt ? C.ok : C.feil;

                let bgFarge = C.hvit;
                if (erValgt)         bgFarge = C.active;
                else if (erIValgtOrd) bgFarge = C.highlight;

                return (
                  <div
                    key={posKey}
                    onClick={() => dispatch({ type: "VELG_CELLE", celle: { rad: r, kol: k } })}
                    style={{
                      width:           celleStrl,
                      height:          celleStrl,
                      backgroundColor: bgFarge,
                      border:          `1px solid ${C.border}`,
                      borderRadius:    3,
                      cursor:          "pointer",
                      position:        "relative",
                      display:         "flex",
                      alignItems:      "center",
                      justifyContent:  "center",
                      flexShrink:      0,
                      transition:      "background-color 0.1s ease",
                    }}
                  >
                    <span
                      style={{
                        fontFamily:    "var(--font-playfair), 'Playfair Display', Georgia, serif",
                        fontSize:      celleStrl <= 38 ? 18 : celleStrl <= 46 ? 22 : 26,
                        fontWeight:    700,
                        color:         bokstavFarge,
                        lineHeight:    1,
                        userSelect:    "none",
                        textTransform: "uppercase",
                      }}
                    >
                      {brukerBokstav}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Sjekk-knapp */}
      <div className="flex gap-3 mt-1">
        <button
          onClick={() => dispatch({ type: "SJEKK" })}
          style={{
            padding:       "8px 20px",
            backgroundColor: "#5C4A2A",
            color:         "#F5F0E8",
            border:        "none",
            borderRadius:  8,
            fontSize:      14,
            fontWeight:    600,
            fontFamily:    "system-ui, sans-serif",
            cursor:        "pointer",
            letterSpacing: "0.02em",
          }}
        >
          Sjekk svar
        </button>
      </div>

      {/* Ferdig-melding */}
      {state.ferdig && (
        <div
          style={{
            padding:       "12px 24px",
            backgroundColor: "#E8F0E4",
            border:        "1px solid #7AAD6B",
            borderRadius:  10,
            color:         "#2D5A20",
            fontFamily:    "var(--font-playfair), Georgia, serif",
            fontSize:      18,
            fontWeight:    600,
          }}
        >
          Gratulerer, kryssordet er løst!
        </div>
      )}
    </div>
  );
}
