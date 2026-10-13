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
        <Stat num={"외관 참고"} label="3D 모델 용도" />
        <Stat num={s.receivedRange} label="접수일 범위" />
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
