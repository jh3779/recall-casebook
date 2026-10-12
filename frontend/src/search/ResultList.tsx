import { ListItem } from "./ListItem";
import type { Card, SearchResponse } from "./types";
export function ResultList({ response, selected, onSelect }: { response: SearchResponse; selected?: Card; onSelect: (card: Card) => void }) {
  return <aside className="list" aria-label="검색 결과 목록">
    <section className="list-group"><header className="list-head"><h2>고객사 선례 · 현대·기아</h2><span>합친 순위 상위 100 안에서 최대 5건</span></header>
      {!response.customer_precedents.length && <p className="empty-customers note">검색 상위 100건 안에 현대·기아 리콜이 없습니다.</p>}
      {response.customer_precedents.map((card) => <ListItem key={card.campno} card={card} selected={selected === card} onSelect={() => onSelect(card)} />)}
    </section>
    <section className="list-group"><header className="list-head"><h2>다른 회사 선례</h2><span>합친 순위 상위 10건</span></header>
      {response.precedents.map((card) => <ListItem key={card.campno} card={card} selected={selected === card} onSelect={() => onSelect(card)} />)}
    </section>
  </aside>;
}
