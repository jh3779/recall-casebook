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
        </div>)}
        {item.item === "production_period" && item.omitted ? <div className="ev-more">외 {item.omitted}개 블록은 싣지 않았습니다 — 아래 출처 보고서 원문에서 확인하세요</div> : null}
        {item.item === "production_period" ? <div className="ev-row">
          <span className="f">출처 보고서</span>
          <span className="t source-text" lang="en" title={item.source.pdf_sha256}>{item.source.file} · 제출일 {item.source.submission_date} · sha256 {item.source.pdf_sha256}</span>
        </div> : null}
      </div>
    </div>)}</div>
  </section>;
}
