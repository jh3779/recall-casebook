import type { Card, SearchResponse } from "../search/types";

/** 체크한 선례를 8D 작성 화면으로 넘기는 줄 — 체크한 선례가 있을 때만 그린다(선례 검색의 "담기 → 8D 작성" 흐름, DEC-075) */
export function Write8dBar({ checked, response, onWrite8d }: { checked: readonly Card[]; response: SearchResponse; onWrite8d: (cards: readonly Card[], response: SearchResponse) => void }) {
  if (!checked.length) return null;
  return <div className="cb-stack-bar">
    <button type="button" className="cb-btn" onClick={() => onWrite8d(checked, response)}>Write 8D from checked ({checked.length}) →</button>
    <span className="cb-muted">Opens the 8D form with these precedents available as references.</span>
  </div>;
}
