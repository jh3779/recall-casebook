import { fieldLabel } from "./fieldLabels";
import type { CheckItem } from "./types";
export function Checklist({ items }: { items: CheckItem[] }) {
  if (!items.length) return null;
  return <section className="block">
    <h3>확인 항목</h3>
    <p className="note">근거 원문을 나란히 보여 줄 뿐, 같다·다르다를 표시하지 않습니다</p>
    <div className="check">{items.map((item, i) => <div className="check-item" key={i}>
      <span className="lbl">{item.label}</span>
      <div className="ev">{item.evidence.map((e, j) => <div className="ev-row" key={j}>
        <span className="f">{fieldLabel(e.field)}</span><span className="t source-text" lang="en" title={e.text}>{e.text}</span>
      </div>)}</div>
    </div>)}</div>
  </section>;
}
