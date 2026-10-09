import { useState } from "react";
import { CATEGORIES, MODELS } from "../config";
import { categoryRows, fmtDate, otherModel, recallsFor, yearLabel } from "../recalls";
import type { CategoryKey, ModelKey, Recall, RecallsByModel } from "../types";

interface Props {
  recalls: RecallsByModel;
  model: ModelKey;
  category: CategoryKey | null;
  cats3d: ReadonlySet<CategoryKey>;
  onSelect: (cat: CategoryKey | null) => void;
  /** 같은 부품을 다른 차종에서 보기 */
  onCross: (model: ModelKey, cat: CategoryKey) => void;
}

export function Panel({ recalls, model, category, cats3d, onSelect, onCross }: Props) {
  const list = category && recallsFor(recalls, model, category);
  const title = category && list ? `${CATEGORIES[category].name} · ${list.length}건` : "결함이 기록된 부품";
  return (
    <aside className="panel">
      <div className="panel-head">
        <div className="panel-eyebrow">결함 부품</div>
        <div className="panel-title">{title}</div>
      </div>
      {/* 목록이 바뀌면 스크롤·펼침 상태를 처음으로 */}
      <div className="panel-body" key={`${model}-${category}`}>
        {category && list ? (
          <RecallList recalls={recalls} model={model} category={category} list={list} onSelect={onSelect} onCross={onCross} />
        ) : (
          <CategoryList recalls={recalls} model={model} cats3d={cats3d} onSelect={onSelect} />
        )}
      </div>
    </aside>
  );
}

function CategoryList({ recalls, model, cats3d, onSelect }: Pick<Props, "recalls" | "model" | "cats3d" | "onSelect">) {
  const none = recallsFor(recalls, model, null).length;
  return (
    <>
      {categoryRows(recalls, model, cats3d).map((r) => (
        <button
          key={r.key}
          type="button"
          className={"cat" + (r.has3d ? "" : " disabled")}
          disabled={!r.has3d}
          onClick={() => onSelect(r.key)}
        >
          <span className="cat-dot" />
          <span className="cat-name">
            {r.name}
            <span className="cat-sub">{r.sub}</span>
          </span>
          <span className="cat-count">{r.count}</span>
        </button>
      ))}
      {none > 0 && (
        <div className="cat disabled">
          <span className="cat-dot" />
          <span className="cat-name">
            전기 · 후방카메라 · 기타
            <span className="cat-sub">3D 형상이 없는 부품</span>
          </span>
          <span className="cat-count">{none}</span>
        </div>
      )}
    </>
  );
}

function RecallList({
  recalls,
  model,
  category,
  list,
  onSelect,
  onCross,
}: Pick<Props, "recalls" | "model" | "onSelect" | "onCross"> & { category: CategoryKey; list: Recall[] }) {
  const c = CATEGORIES[category];
  const o = otherModel(model);
  const crossN = recallsFor(recalls, o, category).length;
  return (
    <>
      <button type="button" className="back" onClick={() => onSelect(null)}>
        ← 전체 부품
      </button>
      {crossN > 0 && (
        <button type="button" className="cross" onClick={() => onCross(o, category)}>
          같은 부품, 다른 회사 선례 → {MODELS[o].label} {crossN}건
          <small>
            {MODELS[o].maker} · {MODELS[o].gen}
          </small>
        </button>
      )}
      {c.sub.includes("위치로 표시") && (
        <div className="note">해석 모델에 해당 부품의 형상이 없어, {c.sub.replace(" 위치로 표시", "")} 위치로 표시합니다.</div>
      )}
      {list.map((r) => (
        <RecallCard key={r.campno} r={r} />
      ))}
    </>
  );
}

// 결함·결과·조치는 NHTSA 원문 그대로 보여 준다 (AGENTS.md 2절: 원문을 바꾸지 않고 리콜 번호와 함께)
function RecallCard({ r }: { r: Recall }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="recall">
      <div className="recall-top">
        <span className="campno">{r.campno}</span>
        <span className="recall-date">{fmtDate(r.received)}</span>
      </div>
      <div className="recall-meta">
        {r.maker} · {yearLabel(r.years)}년식 · {r.potaff.toLocaleString()}대{r.mfr_part && ` · 부품명: ${r.mfr_part}`}
      </div>
      <div className="recall-comp">
        {r.components.map((comp, i) => (
          <div key={i}>{comp}</div>
        ))}
      </div>
      <div className="recall-label">결함 (원문)</div>
      <div className={"recall-text" + (open ? "" : " clamp")}>{r.defect}</div>
      {open && (
        <>
          <div className="recall-label">결과</div>
          <div className="recall-text">{r.consequence}</div>
          <div className="recall-label">조치</div>
          <div className="recall-text">{r.remedy}</div>
        </>
      )}
      <button type="button" className="more" onClick={() => setOpen(!open)}>
        {open ? "접기" : "더 보기"}
      </button>
    </div>
  );
}
