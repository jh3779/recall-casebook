import { fmtDate } from "../recalls";
import { CauseBlock } from "./CauseBlock";
import { Checklist } from "./Checklist";
import { InvestigationBlock } from "./InvestigationBlock";
import { PickToggle } from "./PickToggle";
import { Provenance } from "./Provenance";
import type { Card, SearchResponse } from "./types";
export function PrecedentDetail({ card, response, onBack, picked, onPick }: { card: Card; response: SearchResponse; onBack?: () => void; picked?: boolean; onPick?: () => void }) {
  return <article className="detail" aria-label={`리콜 ${card.campno} 상세`}>
    <button className="btn ghost mobile-back" onClick={onBack}>← 목록</button>
    <header className="d-head" tabIndex={-1} id="detail-heading">
      <div className="row"><span className="tag">전체 순위 {card.rank}</span><h2 className="campno">{card.campno}</h2>{onPick && <PickToggle card={card} picked={!!picked} onToggle={onPick} />}</div>
      <div className="row"><span className="who">{card.maker}{card.maker_group && card.maker_group !== card.maker && ` (${card.maker_group})`}</span><span className="note">접수 {fmtDate(card.received_date)}</span></div>
      <div className="parts">{card.components.map((part, i) => <span className="chip-part" key={i}>{part}</span>)}</div>
    </header>
    <section className="block">
      <h3>결함 · 결과 · 시정 (NHTSA 원문)</h3>
      <p className="byline">말한 주체 <b>{card.source.speaker}</b> · {card.campno} · {card.source.dataset} 스냅샷 {card.source.snapshot_date}</p>
      {([ ["defect", "결함"], ["consequence", "결과"], ["remedy", "시정"] ] as const).map(([field, label]) => <div className="src-field" key={field}>
        <h4 className="lbl">{label}</h4><p className="source-text" lang="en">{card[field]}</p>
      </div>)}
    </section>
    <CauseBlock cause={card.cause} />
    <InvestigationBlock investigations={card.investigations} />
    <Checklist items={card.checklist} />
    <Provenance data={response} question={response.question} />
  </article>;
}
