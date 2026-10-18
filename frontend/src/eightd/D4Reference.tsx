import type { Card, SearchResponse } from "../search/types";
import { insertedFor } from "./document";
import { DraftPanel } from "./DraftPanel";
import { EvidenceCard } from "./EvidenceCard";

const HINT = "타사 선례의 공개된 원인 원문입니다. 자사 원인이 아니라서 '타사 선례' 머리줄과 출처 줄이 붙고, D4 칸 본문(엔지니어가 쓴 글 뒤) 또는 아래 '선례 근거 부록'(8D 표 뒤 별도 문단)에 넣을 수 있습니다.";

/**
 * D4의 "선례 참고 열기" — 선례 내용은 D4에만 넣는다(DEC-076). 선례마다 본문(`"4"`)·부록(`"4a"`) 버튼이 있고 눌러야만 들어간다.
 * 어느 버튼이 어느 곳으로 가는지가 서비스 원칙(타사 원문을 어디에 넣는가)이라 화면 조립에서 떼어 시험한다.
 */
export function D4Reference({ cards, response, customers, inserted, onToggle }: { cards: readonly Card[]; response: SearchResponse | null; customers: ReadonlySet<string>; inserted: Readonly<Record<string, string>>; onToggle: (step: "4" | "4a", id: string, block: string) => void }) {
  if (!cards.length) return null;
  const count = Object.keys(inserted).filter((k) => k.startsWith("4|") || k.startsWith("4a|")).length;
  return <details className="ed-ref"><summary><span>선례 참고 열기 <span className="ed-opt">선택</span></span><span className={`ed-cnt${count ? " on" : ""}`}>넣음 {count}건</span></summary>
    <p className="note">{HINT} 넣기를 누르기 전에는 아무것도 들어가지 않습니다.</p>
    {response && <DraftPanel key={`4|${response.question}|${cards.map((c) => c.campno).join(",")}`} step="d4" question={response.question} build={response} cards={cards} inserted={insertedFor(inserted, "4")} onToggle={(id, block) => onToggle("4", id, block)} />}
    {cards.map((card) => <EvidenceCard key={card.campno} card={card} customer={customers.has(card.campno)} inBody={inserted[`4|${card.campno}`] !== undefined} inAppendix={inserted[`4a|${card.campno}`] !== undefined} onToggleBody={(block) => onToggle("4", card.campno, block)} onToggleAppendix={(block) => onToggle("4a", card.campno, block)} />)}
  </details>;
}
