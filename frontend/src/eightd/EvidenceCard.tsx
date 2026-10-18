import { fmtDate } from "../recalls";
import type { Card } from "../search/types";
import { evidenceBlock, missingReason } from "./evidenceText";

/** D4 선례 참고의 선례 한 건 — 미리 보이는 글이 그대로 D4 칸 본문 또는 부록에 들어간다(화면용 별도 가공이 없다). 둘 다 눌러야만 들어가고, 한쪽·양쪽 모두 고를 수 있다(DEC-076) */
export function EvidenceCard({ card, customer, inBody, inAppendix, onToggleBody, onToggleAppendix }: { card: Card; customer: boolean; inBody: boolean; inAppendix: boolean; onToggleBody: (block: string) => void; onToggleAppendix: (block: string) => void }) {
  const block = evidenceBlock(card);
  return <article className={`ev-card${inBody || inAppendix ? " on" : ""}${block ? "" : " empty"}`} aria-label={`선례 ${card.campno}`}>
    <header className="ev-head">
      <span className="tag">타사 선례 · 자사 사실 아님</span><span className="campno">{card.campno}</span><b>{card.maker}</b><span className="note">접수 {fmtDate(card.received_date)}</span>
      {customer && <span className="tag cust">고객사</span>}
      {block && <button type="button" className={`pick${inBody ? " on" : ""}`} aria-pressed={inBody} onClick={() => onToggleBody(block)}>{inBody ? "D4 본문에 넣음 ✓ (다시 누르면 뺌)" : "본문에 텍스트로 넣기"}</button>}
      {block && <button type="button" className={`pick${inAppendix ? " on" : ""}`} aria-pressed={inAppendix} onClick={() => onToggleAppendix(block)}>{inAppendix ? "부록에 넣음 ✓ (다시 누르면 뺌)" : "부록에 텍스트로 넣기"}</button>}
    </header>
    {block ? <pre className="ev-text">{block}</pre> : <p className="note">{missingReason(card)}</p>}
  </article>;
}
