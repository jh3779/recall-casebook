import { useEffect, useMemo, useRef, useState } from "react";
import { CATEGORIES, MODELS } from "../config";
import { Showroom } from "../showroom/Showroom";
import type { Card } from "../search/types";
import type { CategoryKey, Mode } from "../types";
import { GUIDE_LAST, GUIDE_PLAY_MS, GUIDE_STEPS, guideMoves, guideView } from "../showroom/guide";
import { TYPICAL_COMPONENTS } from "../showroom/partNames";
import { PEEL_LABELS, PEEL_MAX, peelControls } from "../showroom/peel";
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
  /** 부품 이름 마커를 그릴 때 쓰는 인스턴스(모델을 올린 뒤에만 있다) */
  const [readyShowroom, setReadyShowroom] = useState<Showroom | null>(null);
  const [stage, setStage] = useState<Stage>("loading");
  const [cats3d, setCats3d] = useState<ReadonlySet<CategoryKey>>(new Set());
  const [category, setCategory] = useState<CategoryKey | null>(null);
  const [mode, setMode] = useState<Mode>("exterior");
  const [layer, setLayer] = useState(0);
  /** 안내 보기의 단계(0~4). null이면 직접 조작 중이다 */
  const [step, setStep] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [reducedMotion] = useState(() => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
  const sliderRef = useRef<HTMLInputElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const lastLayer = useRef(0);
  const cardCats = partCategories(card.components);
  /** 직접 조작하면 안내 보기를 멈춘다(보던 화면은 그대로 둔다) */
  const manual = () => {
    if (view) { setMode(view.mode); setLayer(view.layer); } // 안내가 보여 주던 화면을 직접 조작의 시작점으로 넘긴다
    setStep(null);
    setPlaying(false);
  };
  /** 층을 바꾼다. 누른 버튼이 끝에 닿아 비활성이 되면 초점이 사라지지 않게 슬라이더로 옮긴다 */
  const moveLayer = (to: number, keepFocus = false) => {
    manual();
    setLayer(to);
    if (keepFocus || to === 0 || to === PEEL_MAX) sliderRef.current?.focus();
  };
  const shown = cardCats.filter((c) => cats3d.has(c));
  const view = step === null ? null : guideView(step, category);
  const effMode = view ? view.mode : mode;
  const effLayer = view ? view.layer : layer;
  const zoom = view ? view.zoom : mode === "xray";
  const peel = peelControls(effLayer, category);
  const markers = useMemo(() => readyShowroom?.markersOf(category) ?? [], [readyShowroom, category]);
  const isPlaying = playing && step !== null && step < GUIDE_LAST;
  const typical = category ? TYPICAL_COMPONENTS[category].filter((n) => !markers.some((m) => m.label === n)) : [];
  const goStep = (to: number) => {
    setPlaying(false);
    setStep(to);
    const m = guideMoves(to);
    if (!m.canNext) backRef.current?.focus();
    else if (!m.canBack) nextRef.current?.focus();
  };

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
        const first = partCategories(card.components).find((c) => cats.has(c)) ?? null;
        setCategory(first);
        setStep(first ? 0 : null); // 3D 위치가 있는 분류가 있으면 안내 보기 1단계(완성 모델)에서 시작한다
        setReadyShowroom(showroom);
        setStage("ready");
      } catch {
        if (alive) setStage("failed");
      }
    })();
    return () => { alive = false; showroomRef.current = null; setReadyShowroom(null); showroom?.dispose(); };
  }, [card]);

  useEffect(() => {
    const showroom = showroomRef.current;
    if (stage !== "ready" || !showroom) return;
    showroom.setLook(effMode, category, new Set(category ? [category] : []));
    showroom.focus(zoom ? category : null, step !== null); // 안내 보기의 확대는 부품 가까이
  }, [stage, effMode, category, zoom, step]);

  useEffect(() => {
    if (stage !== "ready") return;
    // 여러 층을 한 번에 풀 때는 층당 0.35초(최소 0.7초)
    showroomRef.current?.setPeel(effLayer, Math.max(700, 350 * Math.abs(effLayer - lastLayer.current)));
    lastLayer.current = effLayer;
  }, [stage, effLayer]);

  useEffect(() => {
    // 자동 재생: 3초마다 다음 단계로, 마지막 단계에서 멈춘다. 모션 감소 설정에서는 쓰지 않는다
    if (!isPlaying) return;
    const id = setTimeout(() => setStep((s) => (s === null ? s : Math.min(GUIDE_LAST, s + 1))), GUIDE_PLAY_MS);
    return () => clearTimeout(id);
  }, [isPlaying, step]);

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
      {view?.markers && markers.map((m, i) => <span key={m.id} className="cb-3d-marker" ref={(el) => showroomRef.current?.bindMarker(m.id, el)} title={m.label}>{i + 1}</span>)}
      {stage === "loading" && <p className="cb-3d-msg" role="status">Loading the 3D model…</p>}
      {stage === "failed" && <p className="cb-3d-msg" role="alert">The 3D model file could not be loaded (public/{model.glb}). It is not committed to the repository — see frontend/README.md, “3D 모델 파일”.</p>}
      {stage === "nowebgl" && <p className="cb-3d-msg" role="alert">This browser cannot start WebGL, so the 3D view is not available.</p>}
    </div>
    <div className="cb-3d-side">
      <h2>Part category</h2>
      <p className="cb-muted">Component text of this recall (NHTSA, verbatim):</p>
      <ul className="cb-3d-comp" lang="en">{card.components.map((c, i) => <li key={i}>{c}</li>)}</ul>
      <p className="cb-3d-note">Illustration only: a Kia Sorento model with <b>estimated</b> part shapes and positions. It is not the vehicle or the exact location in this recall, and it says nothing about your case. The peeling order is only an illustration — not a repair or disassembly procedure, and not the real structure of that vehicle.</p>
      {stage === "ready" && <>
        <div className="cb-3d-chips" role="group" aria-label="Part category to show">
          {cardCats.map((c) => <button key={c} type="button" aria-pressed={category === c} className={category === c ? "on" : ""} disabled={!cats3d.has(c)} title={cats3d.has(c) ? undefined : "No 3D position for this category"} onClick={() => setCategory(c)}>{CATEGORIES[c].en}</button>)}
        </div>
        {shown.length === 0 && <p className="cb-muted">None of this recall’s part categories has a position in the 3D model, so only the vehicle is shown.</p>}
        {shown.length > 0 && (step === null
          ? <div className="cb-3d-guide"><button type="button" onClick={() => setStep(0)}>Start guided view</button></div>
          : <section className="cb-3d-guide" aria-label="Guided view">
            <h3>Guided view <small>Step {step + 1} of {GUIDE_STEPS.length}</small></h3>
            <ol className="cb-3d-steps">{GUIDE_STEPS.map((s, i) => <li key={s.id} aria-current={i === step ? "step" : undefined}>{s.title}</li>)}</ol>
            <p role="status">{GUIDE_STEPS[step].text}</p>
            <div className="cb-3d-layer-btns">
              <button type="button" ref={backRef} disabled={!guideMoves(step).canBack} onClick={() => goStep(step - 1)}>Back</button>
              <button type="button" ref={nextRef} disabled={!guideMoves(step).canNext} onClick={() => goStep(step + 1)}>Next</button>
              <button type="button" aria-pressed={isPlaying} disabled={reducedMotion || !guideMoves(step).canNext} title={reducedMotion ? "Auto-play is off because your system asks for reduced motion" : undefined} onClick={() => setPlaying(!isPlaying)}>{isPlaying ? "Pause" : "Play"}</button>
            </div>
            {view?.markers && <div className="cb-3d-parts">
              <h4>Parts of this category</h4>
              {markers.length > 0
                ? <ol>{markers.map((m) => <li key={m.id}>{m.label}{m.estimated && <span className="cb-muted"> (estimated shape)</span>}</li>)}</ol>
                : <p className="cb-muted">No named parts of this category are drawn in the 3D model.</p>}
              {typical.length > 0 && <>
                <h4>Typical components of this system</h4>
                <ul>{typical.map((n) => <li key={n}>{n}</li>)}</ul>
                <p className="cb-muted">Typical components are a general list, not specific to this vehicle, and are not all drawn in the model.</p>
              </>}
              <p className="cb-muted">The parts and their layout are a simplified general illustration — not the structure of the vehicle in this recall and not where a defect is.</p>
            </div>}
          </section>)}
        <div className="cb-3d-layers">
          <label htmlFor="cb-3d-layer">Layers <b>{effLayer} · {PEEL_LABELS[effLayer]}</b></label>
          <input id="cb-3d-layer" ref={sliderRef} type="range" min={0} max={PEEL_MAX} step={1} value={effLayer} aria-valuetext={`${effLayer}, ${PEEL_LABELS[effLayer]}`} onChange={(e) => { manual(); setLayer(Number(e.target.value)); }} />
          <div className="cb-3d-layer-btns">
            <button type="button" disabled={!peel.canPutBack} onClick={() => moveLayer(effLayer - 1)}>Put back one layer</button>
            <button type="button" disabled={!peel.canPeel} onClick={() => moveLayer(effLayer + 1)}>Peel next layer</button>
            <button type="button" disabled={!peel.canReveal} onClick={() => peel.revealTo !== null && moveLayer(peel.revealTo, true)} title={category ? undefined : "Pick a part category first"}>Reveal this category</button>
          </div>
        </div>
        <div className="cb-3d-mode" role="group" aria-label="View mode">
          <button type="button" aria-pressed={effMode === "xray"} className={effMode === "xray" ? "on" : ""} onClick={() => { manual(); setMode("xray"); }}>See-through</button>
          <button type="button" aria-pressed={effMode === "exterior"} className={effMode === "exterior" ? "on" : ""} onClick={() => { manual(); setMode("exterior"); }}>Exterior</button>
        </div>
      </>}
      <p className="cb-muted">3D: <a href={model.source} target="_blank" rel="noreferrer">{model.credit}</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a> · size and materials adjusted</p>
    </div>
  </div>;
}
