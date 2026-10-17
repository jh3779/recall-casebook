import { useEffect, useRef, useState } from "react";
import { CATEGORIES, MODELS } from "../config";
import { Showroom } from "../showroom/Showroom";
import type { Card } from "../search/types";
import type { CategoryKey, Mode } from "../types";
import { partCategories } from "./partCategory";
import { useModal } from "./useModal";

type Stage = "loading" | "ready" | "failed" | "nowebgl";

/**
 * 선례의 부품 분류를 3D 차량 위에 보여 주는 설명용 큰 창(DEC-070). 차량은 기아 쏘렌토 모델 하나이고 부품 위치는 추정 도형이다 —
 * 이 선례의 실제 차량·실제 위치가 아니다. 결함·원인·적용 여부를 판정하지 않는다. three.js는 이 창을 열 때만 받는다(lazy).
 */
export default function ModelOverlay({ card, onClose, opener }: { card: Card; onClose: () => void; opener: HTMLElement | null }) {
  const stageRef = useRef<HTMLDivElement>(null);
  const showroomRef = useRef<Showroom | null>(null);
  const [stage, setStage] = useState<Stage>("loading");
  const [cats3d, setCats3d] = useState<ReadonlySet<CategoryKey>>(new Set());
  const [category, setCategory] = useState<CategoryKey | null>(null);
  const [mode, setMode] = useState<Mode>("xray");
  const cardCats = partCategories(card.components);
  const shown = cardCats.filter((c) => cats3d.has(c));

  useEffect(() => {
    let alive = true;
    let showroom: Showroom | undefined;
    (async () => {
      try {
        showroom = new Showroom(stageRef.current!, { panelShift: 0 }); // 설명 패널이 무대와 다른 열이라 차를 옆으로 밀지 않는다
        showroomRef.current = showroom;
      } catch {
        if (alive) setStage("nowebgl");
        return;
      }
      try {
        const cats = await showroom.load("sorento");
        if (!alive) return;
        showroom.show("sorento");
        setCats3d(cats);
        setCategory(partCategories(card.components).find((c) => cats.has(c)) ?? null);
        setStage("ready");
      } catch {
        if (alive) setStage("failed");
      }
    })();
    return () => { alive = false; showroomRef.current = null; showroom?.dispose(); };
  }, [card]);

  useEffect(() => {
    const showroom = showroomRef.current;
    if (stage !== "ready" || !showroom) return;
    showroom.setLook(mode, category, new Set(category ? [category] : []));
    showroom.focus(mode === "xray" ? category : null);
  }, [stage, mode, category]);

  const dialogRef = useRef<HTMLDivElement>(null);
  const close = useModal(dialogRef, onClose, opener);

  const model = MODELS.sorento;
  return <div className="cb-3d" ref={dialogRef} role="dialog" aria-modal="true" aria-label={`3D illustration for recall ${card.campno}`}>
    <div className="cb-3d-bar">
      <div><b className="cb-id">{card.campno}</b> · {card.maker} <span className="cb-muted">— where this part category sits on a vehicle (illustration)</span></div>
      <button type="button" className="cb-btn" onClick={close} autoFocus>Close</button>
    </div>
    <div className="cb-3d-body">
      <div className="cb-3d-stage" ref={stageRef} />
      {stage === "loading" && <p className="cb-3d-msg" role="status">Loading the 3D model…</p>}
      {stage === "failed" && <p className="cb-3d-msg" role="alert">The 3D model file could not be loaded (public/{model.glb}). It is not committed to the repository — see frontend/README.md, “3D 모델 파일”.</p>}
      {stage === "nowebgl" && <p className="cb-3d-msg" role="alert">This browser cannot start WebGL, so the 3D view is not available.</p>}
    </div>
    <div className="cb-3d-side">
      <h2>Part category</h2>
      <p className="cb-muted">Component text of this recall (NHTSA, verbatim):</p>
      <ul className="cb-3d-comp" lang="en">{card.components.map((c, i) => <li key={i}>{c}</li>)}</ul>
      {stage === "ready" && <>
        <div className="cb-3d-chips" role="group" aria-label="Part category to show">
          {cardCats.map((c) => <button key={c} type="button" aria-pressed={category === c} className={category === c ? "on" : ""} disabled={!cats3d.has(c)} title={cats3d.has(c) ? undefined : "No 3D position for this category"} onClick={() => setCategory(c)}>{CATEGORIES[c].en}</button>)}
        </div>
        {shown.length === 0 && <p className="cb-muted">None of this recall’s part categories has a position in the 3D model, so only the vehicle is shown.</p>}
        <div className="cb-3d-mode" role="group" aria-label="View mode">
          <button type="button" aria-pressed={mode === "xray"} className={mode === "xray" ? "on" : ""} onClick={() => setMode("xray")}>See-through</button>
          <button type="button" aria-pressed={mode === "exterior"} className={mode === "exterior" ? "on" : ""} onClick={() => setMode("exterior")}>Exterior</button>
        </div>
      </>}
      <p className="cb-3d-note">Illustration only: a Kia Sorento model with <b>estimated</b> part shapes and positions. It is not the vehicle or the exact location in this recall, and it says nothing about your case.</p>
      <p className="cb-muted">3D: <a href={model.source} target="_blank" rel="noreferrer">{model.credit}</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a> · size and materials adjusted</p>
    </div>
  </div>;
}
