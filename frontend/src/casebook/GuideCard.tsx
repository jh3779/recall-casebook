import type { RefObject } from "react";
import { GUIDE_STEPS, type GuideMarker, guideMoves } from "../showroom/guide";

/**
 * 3D 창 "안내 보기" 카드(DEC-073): 단계·단계 문구·Back/Next/Play, 마지막 단계에서는 부품 이름 목록.
 * 부품 이름 목록(4단계)에는 추정 표시와 "단순화한 일반 설명용이며 이 리콜 차량의 실제 구조·결함 위치가 아니다" 안내가 항상 함께 나온다 —
 * 이름이 보이는데 안내가 없는 경로가 없도록 한 묶음으로 그린다.
 */
export function GuideCard({ step, showParts, markers, typical, isPlaying, reducedMotion, onBack, onNext, onPlay, backRef, nextRef }: {
  step: number;
  showParts: boolean;
  markers: readonly GuideMarker[];
  typical: readonly string[];
  isPlaying: boolean;
  reducedMotion: boolean;
  onBack: () => void;
  onNext: () => void;
  onPlay: () => void;
  backRef?: RefObject<HTMLButtonElement | null>;
  nextRef?: RefObject<HTMLButtonElement | null>;
}) {
  const moves = guideMoves(step);
  return <section className="cb-3d-guide" aria-label="Guided view">
    <h3>Guided view <small>Step {step + 1} of {GUIDE_STEPS.length}</small></h3>
    <ol className="cb-3d-steps">{GUIDE_STEPS.map((s, i) => <li key={s.id} aria-current={i === step ? "step" : undefined}>{s.title}</li>)}</ol>
    <p role="status">{GUIDE_STEPS[step].text}</p>
    <div className="cb-3d-layer-btns">
      <button type="button" ref={backRef} disabled={!moves.canBack} onClick={onBack}>Back</button>
      <button type="button" ref={nextRef} disabled={!moves.canNext} onClick={onNext}>Next</button>
      <button type="button" aria-pressed={isPlaying} disabled={reducedMotion || !moves.canNext} title={reducedMotion ? "Auto-play is off because your system asks for reduced motion" : undefined} onClick={onPlay}>{isPlaying ? "Pause" : "Play"}</button>
    </div>
    {showParts && <div className="cb-3d-parts">
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
  </section>;
}
