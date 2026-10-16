import { fmtDate } from "../recalls";
import type { Card } from "../search/types";
import { evidenceBlock, missingReason, type EvidenceStep } from "./evidenceText";

/** 미리 보이는 글이 그대로 본문에 들어간다 — 화면용 별도 가공이 없다 */
export function EvidenceCard({ step, card, customer, inserted, onToggle }: { step: EvidenceStep; card: Card; customer: boolean; inserted: boolean; onToggle: (block: string) => void }) {
  const block = evidenceBlock(step, card);
  return <article className={`ev-card${inserted ? " on" : ""}${block ? "" : " empty"}`} aria-label={`선례 ${card.campno}`}>
    <header className="ev-head">
      <span className="tag">타사 선례 · 자사 사실 아님</span><span className="campno">{card.campno}</span><b>{card.maker}</b><span className="note">접수 {fmtDate(card.received_date)}</span>
      {customer && <span className="tag cust">고객사</span>}
      {block && <button type="button" className={`pick${inserted ? " on" : ""}`} aria-pressed={inserted} onClick={() => onToggle(block)}>{inserted ? "본문에 넣음 ✓ (다시 누르면 뺌)" : "본문에 텍스트로 넣기"}</button>}
    </header>
    {block ? <pre className="ev-text">{block}</pre> : <p className="note">{missingReason(step as "3" | "4", card)}</p>}
  </article>;
}
