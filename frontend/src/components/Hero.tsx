import { MODELS } from "../config";
import { heroStats } from "../recalls";
import type { ModelKey, Recall } from "../types";

export function Hero({ model, recalls }: { model: ModelKey; recalls: Recall[] }) {
  const cfg = MODELS[model];
  const s = heroStats(recalls);
  return (
    <section className="hero">
      <div className="hero-eyebrow">
        {cfg.maker} · {cfg.gen}
      </div>
      <h1 className="hero-title">{cfg.label}</h1>
      <div className="hero-stats">
        <Stat num={s.total} label="NHTSA 리콜" />
        <Stat num={s.in3d} label="3D로 보이는 부품" />
        <Stat num={`${s.unitsM}M`} label="리콜 대상 대수(합계)" />
      </div>
    </section>
  );
}

function Stat({ num, label }: { num: number | string; label: string }) {
  return (
    <div>
      <div className="stat-num">{num}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
