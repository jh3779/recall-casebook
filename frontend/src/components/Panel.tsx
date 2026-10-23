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
  onSearch: (question: string) => void;
  /** 같은 부품을 다른 차종에서 보기 */
  onCross: (model: ModelKey, cat: CategoryKey) => void;
}

export function Panel({ recalls, model, category, cats3d, onSelect, onCross, onSearch }: Props) {
  const list = category && recallsFor(recalls, model, category);
  const title = category && list ? `${CATEGORIES[category].name} · ${list.length}건` : "리콜이 기록된 부품 분류";
  return (
    <aside className="panel">
      <div className="panel-head">
        <div className="panel-eyebrow">리콜이 기록된 부품 분류</div>
        <div className="panel-title">{title}</div>
        {category && <button className="search-category" onClick={() => onSearch(CATEGORIES[category].en)}>이 분류로 선례 검색</button>}
      </div>
      {/* 목록이 바뀌면 스크롤·펼침 상태를 처음으로 */}
      <div className="panel-body" key={`${model}-${category}`}>
        {category && list ? (
          <RecallList recalls={recalls} model={model} category={category} list={list} cats3d={cats3d} onSelect={onSelect} onCross={onCross} />
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
          className={"cat" + (r.has3d ? "" : " records-only")}
          onClick={() => onSelect(r.key)}
        >
          <span className="cat-dot" />
          <span className="cat-name">
            {r.name}
            <span className="cat-sub">{r.has3d ? "추정 위치 · " : "기록 보기 · "}{r.sub}</span>
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
  cats3d,
}: Pick<Props, "recalls" | "model" | "onSelect" | "onCross" | "cats3d"> & { category: CategoryKey; list: Recall[] }) {
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
          같은 분류({c.name})의 {MODELS[o].label} 리콜 {crossN}건 보기
          <small>
            {MODELS[o].maker} · {MODELS[o].gen}
          </small>
        </button>
      )}
      <div className="note">{cats3d.has(category)
        ? "추정 위치 · 설명용 표시입니다. 일반적인 부품 배치와 단순화한 형상을 사용하며, 실제 결함 위치나 정비 도면을 뜻하지 않습니다. 아래 리콜은 NHTSA 실제 기록입니다."
        : "이 모델에서 해당 부품의 3D 위치를 확인하지 못했습니다. 아래 원문에서 결함 부품을 확인하세요."}</div>
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
        {r.maker} · {yearLabel(r.years)}년식 · 신고 대상 대수 {r.potaff.toLocaleString()} (이 리콜 전체, 다른 차종 포함){r.mfr_part && ` · 부품명: ${r.mfr_part}`}
      </div>
      <div className="recall-comp">
        {r.components.map((comp, i) => (
          <div key={i}>{comp}</div>
        ))}
      </div>
      {/^\d{2}E/.test(r.campno) && <span className="equipment-badge">장비 리콜</span>}
      <div className="recall-meta">{r.source ? <a href={r.source} target="_blank" rel="noreferrer">NHTSA 원문 ↗</a> : "NHTSA 원문"}</div>
      <div className="recall-label">결함</div>
      <div lang="en" className={"recall-text" + (open ? "" : " clamp")}>{r.defect}</div>
      {open && (
        <>
          <div className="recall-label">결과</div>
          <div lang="en" className="recall-text">{r.consequence}</div>
          <div className="recall-label">시정</div>
          <div lang="en" className="recall-text">{r.remedy}</div>
        </>
      )}
      <button type="button" className="more" onClick={() => setOpen(!open)}>
        {open ? "접기" : "더 보기"}
      </button>
    </div>
  );
}
