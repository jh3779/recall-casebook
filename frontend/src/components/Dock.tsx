import { PAINTS } from "../config";
import type { Mode } from "../types";

const MODES: { mode: Mode; label: string }[] = [
  { mode: "exterior", label: "외관" },
  { mode: "xray", label: "부품 투시" },
];

interface Props {
  mode: Mode;
  onMode: (mode: Mode) => void;
  paint: string;
  onPaint: (color: string) => void;
  onReset: () => void;
}

export function Dock({ mode, onMode, paint, onPaint, onReset }: Props) {
  return (
    <footer className="dock">
      <div className="seg">
        {MODES.map((m) => (
          <button key={m.mode} type="button" className={m.mode === mode ? "on" : ""} onClick={() => onMode(m.mode)}>
            {m.label}
          </button>
        ))}
      </div>
      <div className="swatches">
        {PAINTS.map((p) => (
          <button
            key={p.color}
            type="button"
            className={"sw" + (p.color === paint ? " on" : "")}
            style={{ background: p.color }}
            title={p.name}
            aria-label={p.name}
            onClick={() => onPaint(p.color)}
          />
        ))}
      </div>
      <button type="button" className="ghost-btn" title="처음 시점으로" onClick={onReset}>
        ↺ 360°
      </button>
    </footer>
  );
}
