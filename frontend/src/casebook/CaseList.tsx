import { fmtDate } from "../recalls";
import { isPicked } from "../search/picks";
import type { Card, SearchResponse } from "../search/types";
import { causeBadge } from "./sources";

function Row({ card, on, onToggle }: { card: Card; on: boolean; onToggle: () => void }) {
  const badge = causeBadge(card);
  return <button type="button" className={`cb-row${on ? " on" : ""}`} aria-pressed={on} onClick={onToggle} data-campno={card.campno}>
    <span className="cb-check" aria-hidden="true">{on ? "✓" : ""}</span>
    <span className="cb-row-main">
      <span className="cb-row-top"><b className="cb-id">{card.campno}</b><span className="cb-muted">{fmtDate(card.received_date)}</span></span>
      <span className="cb-row-who">{card.maker}</span>
      <span className="cb-snip" lang="en">{card.defect}</span>
      <span className={`cb-badge ${badge.level}`}>{badge.label}</span>
    </span>
  </button>;
}

/** 검색 결과 — 체크한 선례만 가운데 칸에 쌓인다 */
export function CaseList({ response, checked, onToggle }: { response: SearchResponse; checked: readonly Card[]; onToggle: (card: Card) => void }) {
  const section = (title: string, hint: string, cards: Card[], empty?: string) => <section className="cb-list-group">
    <header><h2>{title}</h2><span>{hint}</span></header>
    {!cards.length && empty && <p className="cb-muted">{empty}</p>}
    {cards.map((card) => <Row key={card.campno} card={card} on={isPicked(checked, card)} onToggle={() => onToggle(card)} />)}
  </section>;
  return <aside className="cb-list" aria-label="Search results">
    {section("Customer precedents · Hyundai / Kia", "up to 5", response.customer_precedents, "No Hyundai / Kia recall in the top 100.")}
    {section("Other manufacturers", "top 10", response.precedents)}
  </aside>;
}
