"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
import type { GridJson, LedetradJson, LedetradOppslag } from "@/types/kryssord";

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

interface BehandletCelle {
  type:              "bokstav" | "ledetrad" | "svart";
  bokstav?:          string;
  ledetradVannrett?: string;   // full clue text for across word
  ledetradLoddrett?: string;   // full clue text for down word
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
 * Derives the processed grid from the raw grid + ledetrad data.
 *
 * Strategy: for each word in ledetrad_json, the cell immediately before its
 * start position (left for across, above for down) is a black cell that
 * should be rendered as a ledetrad-celle instead.  A cell can hold clues for
 * both directions (diagonal split).
 */
function byggBehandletGrid(
  grid: GridJson,
  ledetrad: LedetradJson,
): BehandletCelle[][] {
  const { celler } = grid;

  const ut: BehandletCelle[][] = celler.map((rad) =>
    rad.map((c) =>
      c === "#" ? { type: "svart" } : { type: "bokstav", bokstav: c }
    )
  );

  for (const retning of ["across", "down"] as Retning[]) {
    for (const [nrStr, oppslag] of Object.entries(ledetrad[retning])) {
      const nr = Number(nrStr);
      const { rad, kol, ledetrad: tekst } = oppslag;

      if (retning === "across" && kol > 0 && celler[rad][kol - 1] === "#") {
        const c = ut[rad][kol - 1];
        ut[rad][kol - 1] = c.type === "ledetrad"
          ? { ...c, ledetradVannrett: tekst, acrossNr: nr }
          : { type: "ledetrad", ledetradVannrett: tekst, acrossNr: nr };
      }

      if (retning === "down" && rad > 0 && celler[rad - 1][kol] === "#") {
        const c = ut[rad - 1][kol];
        ut[rad - 1][kol] = c.type === "ledetrad"
          ? { ...c, ledetradLoddrett: tekst, downNr: nr }
          : { type: "ledetrad", ledetradLoddrett: tekst, downNr: nr };
      }
    }
  }

  return ut;
}

// ─── Word helpers ─────────────────────────────────────────────────────────────

function ordCeller(oppslag: LedetradOppslag, retning: Retning): CellePos[] {
  return Array.from({ length: oppslag.lengde }, (_, i) =>
    retning === "across"
      ? { rad: oppslag.rad, kol: oppslag.kol + i }
      : { rad: oppslag.rad + i, kol: oppslag.kol }
  );
}

function finnOrd(
  celle: CellePos,
  ledetrad: LedetradJson,
  preferertRetning: Retning,
): { nr: number; retning: Retning } | null {
  const retninger: Retning[] = [preferertRetning, preferertRetning === "across" ? "down" : "across"];
  for (const ret of retninger) {
    for (const [nrStr, opp] of Object.entries(ledetrad[ret])) {
      if (ordCeller(opp, ret).some((c) => c.rad === celle.rad && c.kol === celle.kol))
        return { nr: Number(nrStr), retning: ret };
    }
  }
  return null;
}

function nesteCelle(
  celle: CellePos, nr: number, retning: Retning,
  ledetrad: LedetradJson, brukerGrid: string[][],
): CellePos {
  const opp = ledetrad[retning][String(nr)];
  if (!opp) return celle;
  const celler = ordCeller(opp, retning);
  const idx = celler.findIndex((c) => c.rad === celle.rad && c.kol === celle.kol);
  for (let i = idx + 1; i < celler.length; i++)
    if (!brukerGrid[celler[i].rad][celler[i].kol]) return celler[i];
  return idx + 1 < celler.length ? celler[idx + 1] : celle;
}

function forrigeCelle(
  celle: CellePos, nr: number, retning: Retning, ledetrad: LedetradJson,
): CellePos {
  const opp = ledetrad[retning][String(nr)];
  if (!opp) return celle;
  const celler = ordCeller(opp, retning);
  const idx = celler.findIndex((c) => c.rad === celle.rad && c.kol === celle.kol);
  return idx > 0 ? celler[idx - 1] : celle;
}

function erFerdig(bruker: string[][], fasit: string[][]): boolean {
  return fasit.every((rad, r) =>
    rad.every((f, k) => f === "#" || bruker[r][k].toLowerCase() === f.toLowerCase())
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

function reducer(s: State, a: Action, grid: GridJson, ledetrad: LedetradJson): State {
  switch (a.type) {

    case "VELG_CELLE": {
      const { celle, retning } = a;
      if (grid.celler[celle.rad][celle.kol] === "#") return s;
      const sammePos = s.valgtCelle?.rad === celle.rad && s.valgtCelle?.kol === celle.kol;
      const ønsketRetning = retning
        ? retning
        : sammePos
          ? (s.valgtRetning === "across" ? "down" : "across")
          : s.valgtRetning;
      const ord = finnOrd(celle, ledetrad, ønsketRetning);
      return { ...s, valgtCelle: celle, valgtRetning: ord?.retning ?? ønsketRetning };
    }

    case "SKRIV_BOKSTAV": {
      if (!s.valgtCelle || s.ferdig) return s;
      const { rad, kol } = s.valgtCelle;
      if (grid.celler[rad][kol] === "#") return s;
      const nyGrid = s.brukerGrid.map((r) => [...r]);
      nyGrid[rad][kol] = a.bokstav.toLowerCase();
      const ord = finnOrd(s.valgtCelle, ledetrad, s.valgtRetning);
      const nyPos = ord ? nesteCelle(s.valgtCelle, ord.nr, ord.retning, ledetrad, nyGrid) : s.valgtCelle;
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
      if (nyGrid[rad][kol]) {
        nyGrid[rad][kol] = "";
        return { ...s, brukerGrid: nyGrid };
      }
      const ord = finnOrd(s.valgtCelle, ledetrad, s.valgtRetning);
      const forrige = ord ? forrigeCelle(s.valgtCelle, ord.nr, ord.retning, ledetrad) : s.valgtCelle;
      nyGrid[forrige.rad][forrige.kol] = "";
      return { ...s, brukerGrid: nyGrid, valgtCelle: forrige };
    }

    case "SJEKK": {
      const nyKorrekt = grid.celler.map((rad, r) =>
        rad.map((f, k) => f !== "#" && !!s.brukerGrid[r][k] && s.brukerGrid[r][k].toLowerCase() === f.toLowerCase())
      );
      const nySjekket = grid.celler.map((rad, r) =>
        rad.map((f, k) => f !== "#" && !!s.brukerGrid[r][k])
      );
      return { ...s, korrekt: nyKorrekt, sjekket: nySjekket };
    }

    case "NESTE_CELLE": {
      if (!s.valgtCelle) return s;
      const ord = finnOrd(s.valgtCelle, ledetrad, s.valgtRetning);
      if (!ord) return s;
      return { ...s, valgtCelle: nesteCelle(s.valgtCelle, ord.nr, ord.retning, ledetrad, s.brukerGrid) };
    }

    case "FORRIGE_CELLE": {
      if (!s.valgtCelle) return s;
      const ord = finnOrd(s.valgtCelle, ledetrad, s.valgtRetning);
      if (!ord) return s;
      return { ...s, valgtCelle: forrigeCelle(s.valgtCelle, ord.nr, ord.retning, ledetrad) };
    }

    default: return s;
  }
}

// ─── Sub-components ──────────────────────────────────────────────────────────

/** Scales font size based on text length, clamped to 8–13 px */
function ledetradFontSize(tekst: string): number {
  if (tekst.length <= 12) return 13;
  if (tekst.length <= 20) return 11;
  if (tekst.length <= 30) return 9;
  return 8;
}

interface LedetradCelleProps {
  celle:       BehandletCelle;
  strl:        number;
  onClick:     (retning: Retning) => void;
}

function LedetradCelleView({ celle, strl, onClick }: LedetradCelleProps) {
  const harBegge = !!(celle.ledetradVannrett && celle.ledetradLoddrett);

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

  if (!harBegge) {
    // Single clue – full cell
    const erVannrett = !!celle.ledetradVannrett;
    const tekst = (celle.ledetradVannrett ?? celle.ledetradLoddrett) || "";
    const fs = ledetradFontSize(tekst);
    return (
      <div
        style={baseCss}
        onClick={() => onClick(erVannrett ? "across" : "down")}
        title={tekst}
      >
        <div
          style={{
            position:   "absolute",
            inset:      2,
            display:    "flex",
            flexDirection: "column",
            justifyContent: "flex-end",
            alignItems: erVannrett ? "flex-end" : "flex-start",
          }}
        >
          <span
            style={{
              fontSize:   fs,
              lineHeight: 1.15,
              color:      "#3A3028",
              fontFamily: "system-ui, sans-serif",
              fontWeight: 500,
              overflow:   "hidden",
              display:    "-webkit-box",
              WebkitLineClamp: 3,
              WebkitBoxOrient: "vertical",
              textAlign:  erVannrett ? "right" : "left",
            }}
          >
            {erVannrett ? "→ " : "↓ "}{tekst}
          </span>
        </div>
      </div>
    );
  }

  // Dual clue – diagonal split
  const fsV = ledetradFontSize(celle.ledetradVannrett!);
  const fsL = ledetradFontSize(celle.ledetradLoddrett!);

  return (
    <div style={baseCss} title={`→ ${celle.ledetradVannrett}\n↓ ${celle.ledetradLoddrett}`}>
      {/* SVG diagonal divider */}
      <svg
        style={{ position: "absolute", inset: 0 }}
        width={strl}
        height={strl}
        aria-hidden
      >
        <line
          x1={0} y1={0} x2={strl} y2={strl}
          stroke={C.ledetradBorder}
          strokeWidth={1}
        />
      </svg>

      {/* Top-right triangle – across clue */}
      <div
        onClick={() => onClick("across")}
        style={{
          position:   "absolute",
          top:        2,
          right:      2,
          width:      "55%",
          textAlign:  "right",
        }}
      >
        <span style={{ fontSize: fsV, lineHeight: 1.15, color: "#3A3028", fontFamily: "system-ui, sans-serif", fontWeight: 500 }}>
          →&nbsp;{celle.ledetradVannrett}
        </span>
      </div>

      {/* Bottom-left triangle – down clue */}
      <div
        onClick={() => onClick("down")}
        style={{
          position: "absolute",
          bottom:   2,
          left:     2,
          width:    "55%",
          textAlign: "left",
        }}
      >
        <span style={{ fontSize: fsL, lineHeight: 1.15, color: "#3A3028", fontFamily: "system-ui, sans-serif", fontWeight: 500 }}>
          ↓&nbsp;{celle.ledetradLoddrett}
        </span>
      </div>
    </div>
  );
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface KryssordGridProps {
  grid_json:              GridJson;
  ledetrad_json:          LedetradJson;
  onOrdValgt?:            (nr: number, retning: Retning) => void;
  valgtNr?:               number | null;
  valgtRetningEksternt?:  Retning;
}

// ─── Main component ───────────────────────────────────────────────────────────

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
    lagInitState,
  );

  const containerRef  = useRef<HTMLDivElement>(null);
  const gridWrapRef   = useRef<HTMLDivElement>(null);

  // Pan/zoom via refs (avoids re-renders during drag)
  const pan    = useRef({ x: 0, y: 0 });
  const zoom   = useRef(1);
  const drag   = useRef<{ active: boolean; sx: number; sy: number; tx: number; ty: number }>({ active: false, sx: 0, sy: 0, tx: 0, ty: 0 });
  const pinch  = useRef<number | null>(null);

  function applyTransform() {
    if (!gridWrapRef.current) return;
    gridWrapRef.current.style.transform =
      `translate(${pan.current.x}px, ${pan.current.y}px) scale(${zoom.current})`;
  }

  // ── Processed grid ──────────────────────────────────────────────────────────
  const behandletGrid = useMemo(
    () => byggBehandletGrid(grid_json, ledetrad_json),
    [grid_json, ledetrad_json],
  );

  // ── Highlighted cells for active word ───────────────────────────────────────
  const valgtOrdCeller = useMemo((): Set<string> => {
    if (!state.valgtCelle) return new Set();
    const ord = finnOrd(state.valgtCelle, ledetrad_json, state.valgtRetning);
    if (!ord) return new Set();
    const opp = ledetrad_json[ord.retning][String(ord.nr)];
    return new Set(ordCeller(opp, ord.retning).map((c) => `${c.rad}-${c.kol}`));
  }, [state.valgtCelle, state.valgtRetning, ledetrad_json]);

  // ── Active header clue ───────────────────────────────────────────────────────
  const aktivLedetrad = useMemo((): string => {
    if (!state.valgtCelle) return "";
    const ord = finnOrd(state.valgtCelle, ledetrad_json, state.valgtRetning);
    if (!ord) return "";
    const opp = ledetrad_json[ord.retning][String(ord.nr)];
    return `${ord.retning === "across" ? "→" : "↓"} ${opp.ledetrad}`;
  }, [state.valgtCelle, state.valgtRetning, ledetrad_json]);

  // ── Sync external selection ──────────────────────────────────────────────────
  useEffect(() => {
    if (valgtNr == null || !valgtRetningEksternt) return;
    const opp = ledetrad_json[valgtRetningEksternt][String(valgtNr)];
    if (!opp) return;
    dispatch({ type: "VELG_CELLE", celle: { rad: opp.rad, kol: opp.kol }, retning: valgtRetningEksternt });
  }, [valgtNr, valgtRetningEksternt, ledetrad_json]);

  // ── Notify parent ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!state.valgtCelle) return;
    const ord = finnOrd(state.valgtCelle, ledetrad_json, state.valgtRetning);
    if (ord) onOrdValgt?.(ord.nr, ord.retning);
  }, [state.valgtCelle, state.valgtRetning, ledetrad_json, onOrdValgt]);

  // ── Keyboard ─────────────────────────────────────────────────────────────────
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

  // ── Pan – pointer events ──────────────────────────────────────────────────────
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    // Only initiate pan on non-cell middle-area (or two-finger touch)
    if (e.pointerType === "mouse" && e.button !== 1) return;
    if (e.pointerType === "touch") return; // handled by touch events
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

  // ── Touch events (pan + pinch-to-zoom) ───────────────────────────────────────
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

  // ── Wheel zoom ────────────────────────────────────────────────────────────────
  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    zoom.current = Math.min(3, Math.max(0.5, zoom.current * (e.deltaY < 0 ? 1.1 : 0.9)));
    applyTransform();
  }, []);

  // ── Cell size ─────────────────────────────────────────────────────────────────
  const { celler, storrelse } = grid_json;
  const celleStrl = storrelse <= 9 ? 56 : storrelse <= 13 ? 46 : 38;
  const GAP = 2;

  // ─── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col items-center gap-3 select-none">

      {/* Header strip */}
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
          <span
            style={{
              fontFamily: "system-ui, sans-serif",
              fontSize:   15,
              color:      "#2C2018",
              fontWeight: 500,
            }}
          >
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
          outline:         "none",
          overflow:        "hidden",
          cursor:          "default",
          touchAction:     "none",
          padding:         8,
          backgroundColor: C.bg,
          borderRadius:    12,
          border:          `1px solid ${C.border}`,
        }}
      >
        {/* Transformable inner layer */}
        <div
          ref={gridWrapRef}
          style={{
            display:    "inline-block",
            transformOrigin: "top left",
            willChange: "transform",
          }}
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

                // ── Svart celle ───────────────────────────────────────────────
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

                // ── Ledetråd-celle ────────────────────────────────────────────
                if (celle.type === "ledetrad") {
                  return (
                    <LedetradCelleView
                      key={posKey}
                      celle={celle}
                      strl={celleStrl}
                      onClick={(retning) => {
                        const nr = retning === "across" ? celle.acrossNr : celle.downNr;
                        if (nr == null) return;
                        const opp = ledetrad_json[retning][String(nr)];
                        if (!opp) return;
                        dispatch({ type: "VELG_CELLE", celle: { rad: opp.rad, kol: opp.kol }, retning });
                      }}
                    />
                  );
                }

                // ── Bokstavrute ───────────────────────────────────────────────
                const erValgt    = state.valgtCelle?.rad === r && state.valgtCelle?.kol === k;
                const erIValgtOrd = valgtOrdCeller.has(posKey);
                const brukerBokstav = state.brukerGrid[r][k];
                const erSjekket  = state.sjekket[r][k];
                const erKorrekt  = state.korrekt[r][k];

                let bokstavFarge = "#1A1008";
                if (erSjekket) bokstavFarge = erKorrekt ? C.ok : C.feil;

                let bgFarge = C.hvit;
                if (erValgt)      bgFarge = C.active;
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
                        fontFamily: "var(--font-playfair), 'Playfair Display', Georgia, serif",
                        fontSize:   celleStrl <= 38 ? 18 : celleStrl <= 46 ? 22 : 26,
                        fontWeight: 700,
                        color:      bokstavFarge,
                        lineHeight: 1,
                        userSelect: "none",
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
            padding:         "8px 20px",
            backgroundColor: "#5C4A2A",
            color:           "#F5F0E8",
            border:          "none",
            borderRadius:    8,
            fontSize:        14,
            fontWeight:      600,
            fontFamily:      "system-ui, sans-serif",
            cursor:          "pointer",
            letterSpacing:   "0.02em",
          }}
        >
          Sjekk svar
        </button>
      </div>

      {/* Ferdig-melding */}
      {state.ferdig && (
        <div
          style={{
            padding:         "12px 24px",
            backgroundColor: "#E8F0E4",
            border:          "1px solid #7AAD6B",
            borderRadius:    10,
            color:           "#2D5A20",
            fontFamily:      "var(--font-playfair), Georgia, serif",
            fontSize:        18,
            fontWeight:      600,
          }}
        >
          Gratulerer, kryssordet er løst! 🎉
        </div>
      )}
    </div>
  );
}
