import { CATEGORIES } from "../config";
import type { CategoryKey } from "../types";

interface Props {
  items: { key: CategoryKey; count: number }[];
  category: CategoryKey | null;
  onSelect: (cat: CategoryKey) => void;
  /** 위치는 3D 무대가 매 프레임 직접 옮긴다 (Showroom.bindHotspot) */
  bind: (cat: CategoryKey, el: HTMLElement | null) => void;
}

export function Hotspots({ items, category, onSelect, bind }: Props) {
  return (
    <div className="hotspots">
      {items.map(({ key, count }) => (
        <button
          key={key}
          type="button"
          ref={(el) => {
            bind(key, el);
            return () => bind(key, null);
          }}
          className={"hs" + (category === key ? " on" : "") + (category && category !== key ? " hidden" : "")}
          onClick={() => onSelect(key)}
        >
          <span className="hs-dot">+</span>
          <span className="hs-label">
            {CATEGORIES[key].name} · {count}건 · 추정 위치
          </span>
        </button>
      ))}
    </div>
  );
}
