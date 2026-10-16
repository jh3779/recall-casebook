import { fmtDate } from "../recalls";
import type { Card } from "../search/types";
import { groupBlock, groupId, questionsBlock, type DraftItem, type DraftResponse } from "./draft";

const FIELD = { defect: "결함", consequence: "결과", cause: "원인 원문" } as const;
const REJECTED: Record<string, string> = { not_in_source: "원문에 없어서", unknown_source: "출처가 맞지 않아서", duplicate_source: "겹쳐서", bad_title: "제목이 판정 표현에 걸려 제목만" };
const DEGRADED = { disabled: "묶음 초안 기능이 꺼져 있습니다.", llm_failed: "묶음을 만들지 못했습니다." } as const;

function Quote({ item, card }: { item: DraftItem; card: Card | undefined }) {
  return <li className="dq">
    <span className="campno">{item.campno}</span>{card && <span className="note">{card.maker} · 접수 {fmtDate(card.received_date)}</span>}
    <span className="dq-field">{FIELD[item.field]}</span>
    <q className="dq-text" lang="en">{item.quote}</q>
    <span className="note">말한 주체: {item.speaker}</span>
  </li>;
}

/** 서버가 돌려준 묶음 초안 — 인용은 서버가 원문에서 잘라 낸 글자이고, 제목만 도구가 붙인 문장이라 그렇게 표시한다 */
export function DraftResult({ result, cards, inserted, appendix = false, onToggle }: { result: DraftResponse; cards: readonly Card[]; inserted: Record<string, string>; appendix?: boolean; onToggle: (id: string, block: string) => void }) {
  const byId = new Map(cards.map((c) => [c.campno, c]));
  const toggleBtn = (id: string, block: string, label: string) => {
    const on = inserted[id] !== undefined;
    return <button type="button" className={`pick${on ? " on" : ""}`} aria-pressed={on} onClick={() => onToggle(id, block)}>{on ? `${appendix ? "부록" : "본문"}에 넣음 ✓ (다시 누르면 뺌)` : label}</button>;
  };
  const dropped = Object.entries(result.rejected).filter(([, n]) => n > 0);
  return <div className="dr">
    {result.degraded && <p className="note dr-degraded" role="status">{DEGRADED[result.degraded]} 묶음 없이 아래 "선례 참고"의 원문 카드를 쓰세요.</p>}
    {!result.degraded && !result.groups.length && !result.ungrouped.length && <p className="note">이 단계에 쓸 원문이 있는 선례가 없습니다{result.step === "d4" ? "(원인 원문이 있는 선례만 묶습니다)" : ""}.</p>}
    {result.groups.map((group, i) => {
      const id = groupId(group);
      return <article className="dg" key={id} aria-label={`묶음 ${i + 1}`}>
        <header className="dg-head"><b>묶음 {i + 1}</b><span className="note">{group.items.length}건</span>{toggleBtn(id, groupBlock(group, cards), appendix ? "이 묶음을 부록에 넣기" : "이 묶음을 본문에 넣기")}</header>
        <ul className="dg-list">{group.items.map((item) => <Quote key={`${item.campno}-${item.field}`} item={item} card={byId.get(item.campno)} />)}</ul>
      </article>;
    })}
    {result.groups.length > 0 && result.ungrouped.length > 0 && <p className="note">묶이지 않은 원문 {result.ungrouped.length}건은 위 "선례 참고"의 카드에서 직접 넣을 수 있습니다.</p>}
    {dropped.length > 0 && <p className="note">서버가 원문과 대조해 버린 항목: {dropped.map(([k, n]) => `${REJECTED[k] ?? k} ${n}건`).join(" · ")}.</p>}
    {result.questions.length > 0 && <article className="dg dq-box" aria-label="확인 질문">
      <header className="dg-head"><span className="tag">도구가 만든 고정 문장</span><b>확인 질문</b>{toggleBtn("draft:q", questionsBlock(result.questions), appendix ? "확인 질문을 부록에 넣기" : "확인 질문을 본문에 넣기")}</header>
      <ol className="dg-list">{result.questions.map((q) => <li key={q}>{q}</li>)}</ol>
    </article>}
    <p className="note">{result.model ? `묶음 모델 ${result.model} · ` : ""}build {result.build_id}</p>
  </div>;
}
