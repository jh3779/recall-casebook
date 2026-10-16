import type { Card } from "./types";
export function PickBar({ picked, onRemove, onWrite }: { picked: readonly Card[]; onRemove: (card: Card) => void; onWrite: () => void }) {
  return <section className="pickbar" aria-label="8D 근거로 담은 선례">
    <div className="pickbar-main">
      <b>8D 근거로 담은 선례 {picked.length}건</b>
      <ul className="pickbar-list">{picked.map((card) => <li key={card.campno}><span className="campno">{card.campno}</span><span className="who">{card.maker}</span><button type="button" aria-label={`${card.campno} 빼기`} onClick={() => onRemove(card)}>✕</button></li>)}</ul>
      <p className="note">담는 것은 사용자이며, 도구는 같은 부품인지·같은 원인인지 판단하지 않습니다. 담아도 서류에는 아무것도 들어가지 않고, 다음 화면에서 인용마다 직접 넣습니다.</p>
    </div>
    <button type="button" className="btn primary" onClick={onWrite}>선택한 선례로 8D 작성하기 →</button>
  </section>;
}
