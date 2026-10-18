import { useState } from "react";
import type { Card, SearchResponse } from "../search/types";
import { ALL_STEPS, APPENDIX_KEY, appendixParagraphs, composeDocument, CORE_STEPS, D4_EVIDENCE_KEY, d4EvidenceVisible, evidenceFooter, insertedCount, pruneInserted, sameSteps, STEPS, stepParagraphs, toggleEvidence, toggleStep } from "./document";
import { freshQuestionChanged, workChanged } from "./session";
import { DocxError, inspectDocx, patchDocx, type Inspection, type Place } from "./docxPatch";
import { D4Reference } from "./D4Reference";
import { FileMap } from "./FileMap";
import { FormPreview } from "./FormPreview";

const stepLabel = (n: number[]) => n.map((x) => `D${x}`).join("·");
function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const rowsFor = (value: string) => Math.min(40, Math.max(3, value.split("\n").reduce((n, line) => n + Math.max(1, Math.ceil(line.length / 90)), 0) + 1));

/** 8D 작성 화면 — 선례는 기본으로 어디에도 들어가지 않고, 사용자가 D4에서 "D4 본문·부록에 넣기"를 누른 인용만 평문으로 들어간다(본문에 넣으면 부록에도 같이 들어간다). 선례 내용은 D4에만 넣는다(DEC-064·076) */
export default function EightdView({ cards, response, fresh = 0, freshQuestion, onBack }: { cards: readonly Card[]; response: SearchResponse | null; fresh?: number; freshQuestion?: string; onBack: () => void }) {
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
  // 선례 목록·검색 결과가 바뀌어 돌아오면 더는 담지 않은 선례의 인용을 본문에서 걷어 낸다. 질문·판본까지 바뀌었으면 확인 질문도 걷어 내고,
  // 사용자가 쓴 글·올린 파일은 지우지 않고 비울지 묻는다(session.ts). props가 바뀔 때 렌더 중에 상태를 맞추는 React 권장 방식
  const [seen, setSeen] = useState({ cards, response });
  const [anchor, setAnchor] = useState(response); // 마지막으로 본 검색 결과(검색 실패로 null이 와도 기억)
  const [stale, setStale] = useState<"question" | "fresh" | null>(null);
  const [seenFresh, setSeenFresh] = useState(fresh);
  let valuesNow = values; // 이 렌더에서 걷어 낸 뒤의 글 — "이전에 쓴 글이 남았나" 판단은 걷어 낸 뒤 값으로 한다
  let insertedNow = inserted; // 글과 짝인 "넣은 블록" 목록도 같은 시점 것으로 맞춘다(옛 목록으로 다시 걷으면 이미 지운 글을 못 뺀 것으로 잘못 알린다)
  const notes: string[] = [];
  if (seen.cards !== cards || seen.response !== response) {
    const changed = workChanged(anchor, response);
    setSeen({ cards, response });
    if (response) setAnchor(response);
    const r = pruneInserted(values, inserted, new Set(cards.map((c) => c.campno)), changed);
    if (r.removed.length || r.blocked.length) {
      setValues(r.values); setInserted(r.inserted); valuesNow = r.values; insertedNow = r.inserted;
      notes.push(`담지 않은 선례의 인용 ${r.removed.length}건을 본문에서 뺐습니다.${r.blocked.length ? ` 직접 고친 글이라 자동으로 못 뺀 ${r.blocked.length}건은 칸에서 직접 지워 주세요(타사 원문이면 출처 줄이 붙지 않으니 지우는 것을 권장합니다).` : ""}`);
    }
    if (changed && (Object.values(r.values).some((v) => v.trim()) || docx)) setStale("question");
  }
  // "선례 없이 8D 작성하기"를 새로 눌렀으면, 이전에 쓴 글·올린 파일이 있을 때 비울지 묻는다
  if (seenFresh !== fresh) {
    setSeenFresh(fresh);
    // 검색창 질문만 바꿨다면 이전 질문의 확인 질문은 걷어 낸다(사용자가 쓴 글은 남긴다)
    if (freshQuestionChanged(anchor, freshQuestion)) {
      const r = pruneInserted(valuesNow, insertedNow, new Set(cards.map((c) => c.campno)), true);
      if (r.removed.length || r.blocked.length) {
        setValues(r.values); setInserted(r.inserted); valuesNow = r.values; insertedNow = r.inserted;
        notes.push(`이전 질문의 인용·확인 질문 ${r.removed.length}건을 뺐습니다.${r.blocked.length ? ` 직접 고친 글이라 자동으로 못 뺀 ${r.blocked.length}건은 칸에서 직접 지워 주세요.` : ""}`);
      }
    }
    if (Object.values(valuesNow).some((v) => v.trim()) || docx || subjectInput !== null) setStale("fresh");
  }
  if (notes.length) setMessage(notes.join(" "));
  function startOver() {
    setValues({}); setInserted({}); setDocx(null); setChoice({}); setApplied(ALL_STEPS); setSubjectInput(null); setDocxError(""); setStale(null);
    setMessage("이전 작업을 비우고 새로 시작했습니다.");
  }
  const subject = subjectInput ?? freshQuestion ?? response?.question ?? "";
  const customers = new Set(response?.customer_precedents.map((c) => c.campno));
    const appliedInserted = insertedCount(inserted, applied); // 키는 "4|번호"(D4 본문)·"4a|번호"(부록)
  const fileText = composeDocument({ subject, values, withEvidence: appliedInserted > 0, prov: response, only: applied });

  function toggleBoth(id: string, block: string) {
    const r = toggleEvidence(values, inserted, id, block);
    setValues(r.values); setInserted(r.inserted);
    setMessage(r.blocked ? "직접 고친 글이라 자동으로 뺄 수 없는 곳이 있습니다. 그 칸에서 직접 지워 주세요." : "");
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
      const r = await patchDocx(docx.file, { subject, steps, footer: appliedInserted && response ? evidenceFooter(response) : null, cells: choice, appendix: applied.has(4) ? appendixParagraphs(values) : [] });
      const name = `${docx.file.name.replace(/\.docx$/i, "")}_${appliedInserted ? "선례삽입" : "작성"}.docx`;
      download(r.blob, name);
      setMessage(`${name} 파일을 내려받았습니다. 적용한 단계: ${stepLabel([...applied].sort((a, b) => a - b))}. 칸에 넣은 단계: ${r.filled.length ? stepLabel(r.filled) : "없음(쓴 글이 없습니다)"}.${r.missing.length ? ` 파일에서 칸을 찾지 못해 넣지 못한 단계: ${stepLabel(r.missing)} — 칸을 고르거나 "파일 글 복사"로 직접 붙여 넣어 주세요.` : ""}${r.ambiguous.length ? ` 후보 칸이 여럿이라 넣지 않은 단계: ${stepLabel(r.ambiguous)} — 위 표에서 칸을 고른 뒤 다시 내려받아 주세요.` : ""}${r.conflict.length ? ` 다른 단계와 같은 칸을 골라 넣지 않은 단계: ${stepLabel(r.conflict)} — 단계마다 다른 칸을 골라 주세요.` : ""}${r.appendixPlaced === false ? " 파일에 표가 없어 선례 근거 부록을 넣지 못했습니다 — \"파일 글 복사\"로 직접 붙여 넣어 주세요." : r.appendixPlaced ? " 선례 근거 부록은 8D 단계 칸(인식했거나 직접 고른 칸)이 든 마지막 표 뒤에 별도 문단으로 붙였습니다(양식에 따라 위치가 다를 수 있으니 파일에서 확인해 주세요)." : ""}`);
    } catch (e) { setMessage(e instanceof DocxError ? e.message : "파일을 만들지 못했습니다"); }
    finally { setBusy(false); }
  }
  const reference = (step: string) => step === "4" ? <D4Reference cards={cards} response={response} customers={customers} inserted={inserted} onToggle={toggleBoth} /> : null;
  const total = appliedInserted;
  return <main className="view-eightd">
    <h1>8D 작성</h1>
    <div className="ed-picked">
      <button type="button" className="btn ghost" onClick={onBack}>← 케이스북으로</button>
      {cards.length ? <><span className="note">8D 근거로 담은 선례 {cards.length}건</span>{cards.map((c) => <span className="ed-chip campno" key={c.campno}>{c.campno}</span>)}</> : <span className="note">담은 선례 없음 — 선례 없이 작성합니다</span>}
    </div>
    {stale && <p className="ed-err" role="alert">{stale === "fresh" ? "새로 시작했지만" : "질문이 바뀌었습니다. 이전 질문의 선례 인용은 뺐지만,"} 이전에 쓴 글{docx ? "과 올린 파일" : ""}은 남아 있습니다 — SUBJECT 칸도 확인해 주세요. <button type="button" className="ed-link" onClick={startOver}>이전 작업 비우고 새로 시작</button> · <button type="button" className="ed-link" onClick={() => setStale(null)}>이어서 쓰기</button></p>}
    <p className="ed-intro"><b>기본은 선례 없이 작성하는 빈 양식입니다.</b> {cards.length ? <>선례 내용은 <b>D4에만</b> 넣습니다 — D4 칸 아래 "선례 참고 열기"에는 앞 화면에서 담은 선례만 나오고, <b>"D4 본문·부록에 넣기"를 누른 인용만</b> D4 칸 본문과 8D 표 뒤 부록에 함께 평문으로 들어갑니다. 나머지 단계는 선례 없이 직접 씁니다. 들어간 글은 일반 문서 글처럼 고치거나 지울 수 있고, </> : <>선례를 참고하려면 "← 케이스북으로" 돌아가 선례를 체크하고 "Write 8D from checked"로 다시 오면 됩니다. </>}서비스는 어떤 칸도 스스로 채우지 않습니다.</p>
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
        <div className="ed-presets"><button type="button" aria-pressed={sameSteps(applied, ALL_STEPS)} className={sameSteps(applied, ALL_STEPS) ? "on" : ""} onClick={() => setApplied(ALL_STEPS)}>전체</button><button type="button" aria-pressed={sameSteps(applied, CORE_STEPS)} className={sameSteps(applied, CORE_STEPS) ? "on" : ""} onClick={() => setApplied(CORE_STEPS)}>D4만</button></div>
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
        {step.n === 4 && d4EvidenceVisible(cards.length, values) && <div className="ed-fields"><label className="ed-field"><span>선례 근거 — D4 칸에 들어가는 타사 원문 <em className="ed-own">D4 "본문·부록에 넣기"를 누른 인용만 — 자사 글은 위 Escape·Root Cause 칸에 쓰세요</em></span>
          <textarea value={values[D4_EVIDENCE_KEY] ?? ""} rows={rowsFor(values[D4_EVIDENCE_KEY] ?? "")} placeholder="D4 선례 참고에서 본문에 넣은 타사 원인 원문이 여기 들어갑니다 — 엔지니어가 쓴 Escape·Root Cause 글 뒤에 '타사 선례' 제목과 함께 붙습니다" onChange={(e) => setValues((v) => ({ ...v, [D4_EVIDENCE_KEY]: e.target.value }))} /></label></div>}
      </section>)}
      {applied.has(4) && <section className="ed-step" aria-labelledby="ed-h-appendix">
        <h2 id="ed-h-appendix"><span className="ed-n">부록</span>선례 근거 부록 — D4 타사 원인</h2>
        <div className="ed-fields"><label className="ed-field"><span>D4 인용 <em className="ed-own">D4 "본문·부록에 넣기"를 누른 인용도 여기 한 번 더 들어갑니다</em></span>
          <textarea value={values[APPENDIX_KEY] ?? ""} rows={rowsFor(values[APPENDIX_KEY] ?? "")} placeholder="D4 선례 참고에서 부록에 넣은 타사 원인 원문이 여기 들어갑니다 — 8D 표 뒤 별도 문단이라 자사 근본 원인과 섞이지 않습니다" onChange={(e) => setValues((v) => ({ ...v, [APPENDIX_KEY]: e.target.value }))} /></label></div>
      </section>}
    </div>
    <section className="ed-bar" aria-label="파일 만들기">
      <div className="ed-bar-main"><b>D4에 넣은 선례 항목 {total}건</b><span className="note">{total ? "— 칸의 글이 그대로 파일에 들어갑니다" : "— 선례 없이 만들어집니다"}</span></div>
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
