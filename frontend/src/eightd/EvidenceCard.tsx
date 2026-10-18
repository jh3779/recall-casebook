import { fmtDate } from "../recalls";
import type { Card } from "../search/types";
import { evidenceBlock, missingReason } from "./evidenceText";

/** D4 선례 참고의 선례 한 건 — 미리 보이는 글이 그대로 D4 칸 본문과 8D 표 뒤 부록에 함께 들어간다(화면용 별도 가공이 없다). 눌러야만 들어간다(DEC-076) */
export function EvidenceCard({ card, customer, inserted, onToggle }: { card: Card; customer: boolean; inserted: boolean; onToggle: (block: string) => void }) {
  const block = evidenceBlock(card);
  return <article className={`ev-card${inserted ? " on" : ""}${block ? "" : " empty"}`} aria-label={`선례 ${card.campno}`}>
    <header className="ev-head">
      <span className="tag">타사 선례 · 자사 사실 아님</span><span className="campno">{card.campno}</span><b>{card.maker}</b><span className="note">접수 {fmtDate(card.received_date)}</span>
      {customer && <span className="tag cust">고객사</span>}
      {block && <button type="button" className={`pick${inserted ? " on" : ""}`} aria-pressed={inserted} onClick={() => onToggle(block)}>{inserted ? "D4 본문·부록에 넣음 ✓ (다시 누르면 뺌)" : "D4 본문·부록에 넣기"}</button>}
    </header>
    {block ? <pre className="ev-text">{block}</pre> : <p className="note">{missingReason(card)}</p>}
  </article>;
}
