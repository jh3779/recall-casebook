import { MODEL_KEYS, MODELS } from "../config";
import type { ModelKey } from "../types";

export function TopBar({ model, onSelect }: { model: ModelKey; onSelect: (key: ModelKey) => void }) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" />
        <div>
          <div className="brand-title">결함 선례 쇼룸</div>
          <div className="brand-sub">NHTSA 리콜 × 실차 역설계 3D 모델</div>
        </div>
      </div>
      <nav className="model-tabs">
        {MODEL_KEYS.map((k) => (
          <button key={k} type="button" className={k === model ? "on" : ""} onClick={() => onSelect(k)}>
            {MODELS[k].label}
          </button>
        ))}
      </nav>
    </header>
  );
}
