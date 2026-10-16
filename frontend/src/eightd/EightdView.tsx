import { useState } from "react";
import type { Card, SearchResponse } from "../search/types";
import { ALL_STEPS, composeDocument, CORE_STEPS, evidenceFooter, insertBlock, insertedFor, removeBlock, sameSteps, STEPS, stepParagraphs, TARGET, toggleStep } from "./document";
import { DocxError, inspectDocx, patchDocx, type Inspection, type Place } from "./docxPatch";
import { DraftPanel } from "./DraftPanel";
import { EvidenceCard } from "./EvidenceCard";
import { FileMap } from "./FileMap";
import { FormPreview } from "./FormPreview";
import { resultsBlock, type EvidenceStep } from "./evidenceText";

const HINT: Record<string, string> = {
  "2": "타사 선례가 쓴 결함·결과 원문입니다.",
  "3": "선례 차량의 573 생산 기간입니다(우리 로트가 아님).",
  "4": "타사 선례의 공개된 원인 원문입니다. 자사 원인이 아닙니다.",
  "5": "타사 선례 리콜의 시정 원문입니다(설계·공정 변경이 아닐 수 있음).",
  "7": "같은 부품 검색 결과와 공급사 표시입니다.",
};
const stepLabel = (n: number[]) => n.map((x) => `D${x}`).join("·");
function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const rowsFor = (value: string) => Math.min(40, Math.max(3, value.split("\n").reduce((n, line) => n + Math.max(1, Math.ceil(line.length / 90)), 0) + 1));

/** 8D 작성 화면 — 선례는 기본으로 어디에도 들어가지 않고, 사용자가 "본문에 텍스트로 넣기"를 누른 인용만 해당 칸에 평문으로 들어간다(DEC-064) */
export default function EightdView({ cards, response, onBack }: { cards: readonly Card[]; response: SearchResponse | null; onBack: () => void }) {
  const [subjectInput, setSubjectInput] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [inserted, setInserted] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [previewMode, setPreviewMode] = useState<"form" | "text">("form");
  const [docx, setDocx] = useState<{ file: File; view: Inspection } | null>(null);
  const [choice, setChoice] = useState<Record<number, Place>>({});
  const [docxError, setDocxError] = useState("");
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState<ReadonlySet<number>>(ALL_STEPS);
  const subject = subjectInput ?? response?.question ?? "";
  const customers = new Set(response?.customer_precedents.map((c) => c.campno));
  const insertedCount = (step: string) => Object.keys(inserted).filter((k) => k.startsWith(`${step}|`)).length;
  const appliedInserted = Object.keys(inserted).filter((k) => applied.has(Number(k.split("|")[0]))).length;
  const fileText = composeDocument({ subject, values, withEvidence: appliedInserted > 0, prov: response, only: applied });

  function toggle(step: string, id: string, block: string) {
    const key = `${step}|${id}`;
    const field = TARGET[step];
    setMessage("");
    if (inserted[key] === undefined) {
      setValues((v) => ({ ...v, [field]: insertBlock(v[field] ?? "", block) }));
      setInserted((i) => ({ ...i, [key]: block }));
      return;
    }
    const next = removeBlock(values[field] ?? "", inserted[key]);
    if (next === null) { setMessage("본문에서 직접 고친 글이라 자동으로 뺄 수 없습니다. 칸에서 직접 지워 주세요."); return; }
    setValues((v) => ({ ...v, [field]: next }));
    setInserted((i) => { const rest = { ...i }; delete rest[key]; return rest; });
  }
  async function copy() {
    try { await navigator.clipboard.writeText(fileText); setMessage("파일에 들어갈 글을 클립보드에 복사했습니다."); }
    catch { setMessage("복사하지 못했습니다. 아래 미리보기에서 직접 선택해 복사해 주세요."); }
  }
  async function onFile(file: File | undefined) {
    setDocxError(""); setMessage(""); setChoice({});
    if (!file) { setDocx(null); return; }
    try { setDocx({ file, view: await inspectDocx(file) }); }
    catch (e) { setDocx(null); setDocxError(e instanceof DocxError ? e.message : "파일을 읽지 못했습니다"); }
  }
  async function exportDocx() {
    if (!docx) return;
    setBusy(true); setMessage("");
    try {
      const steps = Object.fromEntries(STEPS.filter((step) => applied.has(step.n)).map((step) => [step.n, stepParagraphs(step, values)]));
      const r = await patchDocx(docx.file, { subject, steps, footer: appliedInserted && response ? evidenceFooter(response) : null, cells: choice });
      const name = `${docx.file.name.replace(/\.docx$/i, "")}_${appliedInserted ? "선례삽입" : "작성"}.docx`;
      download(r.blob, name);
      setMessage(`${name} 파일을 내려받았습니다. 적용한 단계: ${stepLabel([...applied].sort((a, b) => a - b))}. 칸에 넣은 단계: ${r.filled.length ? stepLabel(r.filled) : "없음(쓴 글이 없습니다)"}.${r.missing.length ? ` 파일에서 칸을 찾지 못해 넣지 못한 단계: ${stepLabel(r.missing)} — 칸을 고르거나 "파일 글 복사"로 직접 붙여 넣어 주세요.` : ""}${r.ambiguous.length ? ` 후보 칸이 여럿이라 넣지 않은 단계: ${stepLabel(r.ambiguous)} — 위 표에서 칸을 고른 뒤 다시 내려받아 주세요.` : ""}${r.conflict.length ? ` 다른 단계와 같은 칸을 골라 넣지 않은 단계: ${stepLabel(r.conflict)} — 단계마다 다른 칸을 골라 주세요.` : ""}`);
    } catch (e) { setMessage(e instanceof DocxError ? e.message : "파일을 만들지 못했습니다"); }
    finally { setBusy(false); }
  }
  const reference = (step: string) => {
    if (step === "7") {
      if (!response) return null;
      const block = resultsBlock(response);
      const on = inserted["7|table"] !== undefined;
      return <details className="ed-ref"><summary><span>선례 참고 열기 <span className="ed-opt">선택</span></span><span className={`ed-cnt${on ? " on" : ""}`}>넣음 {insertedCount("7")}건</span></summary>
        <p className="note">{HINT["7"]} 넣기를 누르기 전에는 본문에 아무것도 들어가지 않습니다.</p>
        <article className={`ev-card${on ? " on" : ""}`}><header className="ev-head"><span className="tag">검색 결과 표 · 자사 사실 아님</span>
          <button type="button" className={`pick${on ? " on" : ""}`} aria-pressed={on} onClick={() => toggle("7", "table", block)}>{on ? "본문에 넣음 ✓ (다시 누르면 뺌)" : "표를 텍스트로 본문에 넣기"}</button></header><pre className="ev-text">{block}</pre></article></details>;
    }
    if (!(step in HINT) || !cards.length) return null;
    return <details className="ed-ref"><summary><span>선례 참고 열기 <span className="ed-opt">선택</span></span><span className={`ed-cnt${insertedCount(step) ? " on" : ""}`}>넣음 {insertedCount(step)}건</span></summary>
      <p className="note">{HINT[step]} 넣기를 누르기 전에는 본문에 아무것도 들어가지 않습니다.</p>
      {response && (step === "2" || step === "4") && <DraftPanel key={`${step}|${response.question}|${cards.map((c) => c.campno).join(",")}`} step={step === "2" ? "d2" : "d4"} question={response.question} cards={cards} inserted={insertedFor(inserted, step)} onToggle={(id, block) => toggle(step, id, block)} />}
      {cards.map((card) => <EvidenceCard key={card.campno} step={step as EvidenceStep} card={card} customer={customers.has(card.campno)} inserted={inserted[`${step}|${card.campno}`] !== undefined} onToggle={(block) => toggle(step, card.campno, block)} />)}
    </details>;
  };
  const total = appliedInserted;
  return <main className="view-eightd">
    <h1>8D 작성</h1>
    <div className="ed-picked">
      <button type="button" className="btn ghost" onClick={onBack}>← 선례 찾기로</button>
      {cards.length ? <><span className="note">8D 근거로 담은 선례 {cards.length}건</span>{cards.map((c) => <span className="ed-chip campno" key={c.campno}>{c.campno}</span>)}</> : <span className="note">담은 선례 없음 — 선례 없이 작성합니다</span>}
    </div>
    <p className="ed-intro"><b>기본은 선례 없이 작성하는 빈 양식입니다.</b> {cards.length ? <>칸 아래 "선례 참고 열기"에는 앞 화면에서 담은 선례만 나오고, <b>"본문에 텍스트로 넣기"를 누른 인용만</b> 그 칸에 평문으로 들어갑니다. 들어간 글은 일반 문서 글처럼 고치거나 지울 수 있고, </> : <>선례를 참고하려면 "← 선례 찾기로" 돌아가 선례를 담고 다시 오면 됩니다. </>}서비스는 어떤 칸도 스스로 채우지 않습니다.</p>
    <section className="ed-file" aria-label="내 8D 파일">
      <div className="ed-file-head"><b>내 8D 파일(.docx)</b><span className="ed-opt">선택</span><span className="note">올리면 그 파일의 칸 끝에 쓴 글을 덧붙인 새 파일로 내려받습니다. 파일은 이 기기 밖으로 나가지 않고 원본은 바뀌지 않습니다.</span></div>
      <input type="file" aria-label="8D 양식 파일 선택" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => onFile(e.target.files?.[0])} />
      {docxError && <p className="ed-err" role="alert">{docxError}</p>}
      {docx && <><p className="note"><span className="ed-fn">{docx.file.name}</span> — 라벨로 칸을 인식한 단계 {Object.keys(docx.view.matches).length}개. 내려받기 전에 각 단계의 칸이 맞는지 확인하고, 틀렸거나 후보가 여럿이면 직접 고릅니다.</p>
        <FileMap view={docx.view} choice={choice} applied={applied} onChoose={(step, place) => { setMessage(""); setChoice((c) => { const rest = { ...c }; if (place) rest[step] = place; else delete rest[step]; return rest; }); }} /></>}
    </section>
    <section className="ed-apply" aria-label="적용할 단계">
      <div className="ed-apply-head"><b>적용할 단계</b><span className="note">체크한 단계만 미리보기·복사·내려받기 파일에 들어갑니다. 빼도 써 둔 글은 지워지지 않고, 파일의 그 칸은 손대지 않습니다.</span></div>
      <div className="ed-apply-row">
        <div className="ed-chips" role="group" aria-label="8D 단계 선택">{STEPS.map((st) => <button type="button" key={st.n} aria-pressed={applied.has(st.n)} className={applied.has(st.n) ? "on" : ""} title={st.name} onClick={() => setApplied(toggleStep(applied, st.n))}>D{st.n}</button>)}</div>
        <div className="ed-presets"><button type="button" aria-pressed={sameSteps(applied, ALL_STEPS)} className={sameSteps(applied, ALL_STEPS) ? "on" : ""} onClick={() => setApplied(ALL_STEPS)}>전체</button><button type="button" aria-pressed={sameSteps(applied, CORE_STEPS)} className={sameSteps(applied, CORE_STEPS) ? "on" : ""} onClick={() => setApplied(CORE_STEPS)}>D2·D4만</button></div>
      </div>
    </section>
    <div className="ed-form">
      <label className="ed-subject"><span>SUBJECT</span><input type="text" lang="en" value={subject} onChange={(e) => setSubjectInput(e.target.value)} /></label>
      {STEPS.map((step) => !applied.has(step.n) ? <section className="ed-step off" key={step.n} aria-labelledby={`ed-h-${step.n}`}>
        <h2 id={`ed-h-${step.n}`}><span className="ed-n">DISCIPLINE {step.n}</span>{step.name}</h2>
        <p className="note ed-off">적용 안 함 — 미리보기·파일에서 빠집니다. 써 둔 글은 그대로 남아 있습니다. <button type="button" className="ed-link" onClick={() => setApplied(toggleStep(applied, step.n))}>적용하기</button></p>
      </section> : <section className="ed-step" key={step.n} aria-labelledby={`ed-h-${step.n}`}>
        <h2 id={`ed-h-${step.n}`}><span className="ed-n">DISCIPLINE {step.n}</span>{step.name}</h2>
        <div className={`ed-fields${step.fields.length > 1 ? ` n${step.fields.length}` : ""}`}>
          {step.fields.map((f) => <label key={f.key} className="ed-field"><span>{f.label} <em className="ed-own">작성자 기입</em></span>
            <textarea value={values[f.key] ?? ""} rows={rowsFor(values[f.key] ?? "")} placeholder={f.hint} onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} /></label>)}
        </div>
        {reference(String(step.n))}
      </section>)}
    </div>
    <section className="ed-bar" aria-label="파일 만들기">
      <div className="ed-bar-main"><b>본문에 넣은 선례 {total}건</b><span className="note">{total ? "— 칸의 글이 그대로 파일에 들어갑니다" : "— 선례 없이 만들어집니다"}</span></div>
      <div className="ed-bar-actions"><button type="button" className="btn" onClick={copy}>파일 글 복사</button><button type="button" className="btn primary" disabled={!docx || !docx.view.cells.length || busy} title={docx ? undefined : "위에서 내 8D 파일(.docx)을 올리면 켜집니다"} onClick={exportDocx}>{busy ? "만드는 중…" : "원본 서식 그대로 내려받기 (.docx)"}</button></div>
      <p className="note" role="status">{message || (total ? "넣은 인용에는 머리줄 “[타사 선례 번호 · 회사 · 접수일]”과 꼬리줄 “— 말한 주체 · 출처 파일 · sha256”이 평문으로 붙어 있습니다. 출처 표시라 지우지 않는 것을 권장합니다." : "")}</p>
    </section>
    <section className="ed-preview" aria-label="미리보기">
      <div className="ed-preview-head"><b>파일 미리보기</b><span className="note">칸에 쓴 글이 양식 어디에 앉는지, 자동 갱신</span>
        <div className="ed-tabs" role="group" aria-label="미리보기 보기 방식"><button type="button" aria-pressed={previewMode === "form"} className={previewMode === "form" ? "on" : ""} onClick={() => setPreviewMode("form")}>양식 미리보기</button><button type="button" aria-pressed={previewMode === "text"} className={previewMode === "text" ? "on" : ""} onClick={() => setPreviewMode("text")}>텍스트</button></div></div>
      {previewMode === "form" ? <FormPreview subject={subject} values={values} only={applied} evidenceNote={total && response ? evidenceFooter(response) : null} /> : <pre className="ev-text paper">{fileText}</pre>}
    </section>
  </main>;
}
