"use client";

import { useEffect, useRef, useState } from "react";

interface TimerProps {
  running: boolean;
  onTick?: (sekunder: number) => void;
}

function formater(sekunder: number): string {
  const m = Math.floor(sekunder / 60)
    .toString()
    .padStart(2, "0");
  const s = (sekunder % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export default function Timer({ running, onTick }: TimerProps) {
  const [sekunder, setSekunder] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (running) {
      intervalRef.current = setInterval(() => {
        setSekunder((s) => {
          const neste = s + 1;
          onTick?.(neste);
          return neste;
        });
      }, 1000);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [running, onTick]);

  return (
    <div className="font-mono text-lg tabular-nums text-gray-600">
      {formater(sekunder)}
    </div>
  );
}
