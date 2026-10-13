import { fmtDate } from "../recalls";
import { CauseBadge } from "./CauseBadge";
import type { Card } from "./types";
export function ListItem({ card, selected, onSelect }: { card: Card; selected: boolean; onSelect: () => void }) {
  return <button type="button" className={`item${selected ? " on" : ""}`} aria-pressed={selected} onClick={onSelect} data-campno={card.campno}>
    <span className="item-top"><span className="rank">#{card.rank}</span><span className="campno">{card.campno}</span><span className="date">{fmtDate(card.received_date)}</span></span>
    <span className="who">{card.maker}{card.maker_group && card.maker_group !== card.maker && ` · ${card.maker_group}`}</span>
    <span className="snip source-text" lang="en">{card.defect}</span>
    <span className="item-bottom">{card.components.slice(0, 2).map((part, i) => <span className="chip-part" key={i}>{part}</span>)}{card.components.length > 2 && <span className="chip-part">+{card.components.length - 2}</span>}</span>
    <span className="item-bottom"><CauseBadge cause={card.cause} />{card.investigations.length > 0 && <span className="inv-mark">NHTSA 조사 {card.investigations.length}</span>}</span>
  </button>;
}
