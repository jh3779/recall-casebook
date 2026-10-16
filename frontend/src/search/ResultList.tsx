import { ListItem } from "./ListItem";
import { isPicked } from "./picks";
import { PickToggle } from "./PickToggle";
import type { Card, SearchResponse } from "./types";
export function ResultList({ response, selected, onSelect, picked, onPick }: { response: SearchResponse; selected?: Card; onSelect: (card: Card) => void; picked?: readonly Card[]; onPick?: (card: Card) => void }) {
  const row = (card: Card) => {
    const item = <ListItem key={card.campno} card={card} selected={selected === card} onSelect={() => onSelect(card)} />;
    if (!onPick) return item;
    const on = isPicked(picked ?? [], card);
    return <div className={`item-wrap${on ? " picked" : ""}`} key={card.campno}>{item}<PickToggle card={card} picked={on} onToggle={() => onPick(card)} /></div>;
  };
  return <aside className="list" aria-label="검색 결과 목록">
    <section className="list-group"><header className="list-head"><h2>고객사 선례 · 현대·기아</h2><span>합친 순위 상위 100 안에서 최대 5건</span></header>
      {!response.customer_precedents.length && <p className="empty-customers note">검색 상위 100건 안에 현대·기아 리콜이 없습니다.</p>}
      {response.customer_precedents.map(row)}
    </section>
    <section className="list-group"><header className="list-head"><h2>다른 회사 선례</h2><span>합친 순위 상위 10건</span></header>
      {response.precedents.map(row)}
    </section>
  </aside>;
}
