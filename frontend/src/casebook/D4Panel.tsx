import { useState } from "react";
import { DocxError, inspectDocx, patchDocx, type Inspection, type Place } from "../eightd/docxPatch";
import type { Card, SearchResponse } from "../search/types";
import { d4Export, D4_KEYS, d4Values, docxContent, exportMessage } from "./d4Doc";
import { SHARED_BROWSER_NOTE, storageState } from "./notes";
import { d4Questions, pickedQuestions } from "./questions";

const keyOf = (p: Place) => `${p.table}.${p.row}.${p.col}`;
const short = (text: string) => (text.length > 40 ? `${text.slice(0, 40)}…` : text);
function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  Object.assign(document.createElement("a"), { href: url, download: name }).click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * D4 작성 칸(DEC-069) — 확인 질문(도구가 만든 고정 문장), 엔지니어가 직접 쓰는 Escape Cause·Root Cause·검증 방법, 8D `.docx` 내보내기.
 * 서비스는 이 칸을 채우거나 제안하지 않는다. 쓴 글은 메모처럼 이 브라우저에만 저장하고 서버·LLM에 보내지 않는다. 검증 방법은 8D 양식에 칸이 없어 내보내지 않는다.
 */
export function D4Panel({ cards, response, notes, onChange, caseName, persistent, storageBlocked, storeMessage, picked }: { cards: readonly Card[]; response: SearchResponse; notes: Readonly<Record<string, string>>; onChange: (key: string, text: string) => void; caseName: string; persistent: boolean; storageBlocked: boolean; storeMessage: string; picked: readonly string[] }) {
  const values = d4Values(notes);
  const [body, setBody] = useState(false);
  const [appendix, setAppendix] = useState(false);
  const [docx, setDocx] = useState<{ file: File; view: Inspection } | null>(null);
  const [chosen, setChosen] = useState<Place | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const out = d4Export({ values, cards, includeBody: body, includeAppendix: appendix, prov: response });
  const questions = d4Questions(cards);
  const modelPicked = pickedQuestions(picked);
  const state = storageState(caseName, persistent, storageBlocked);
  const auto = docx?.view.matches[4] ?? [];
  const place = chosen ?? (auto.length === 1 ? auto[0] : null);
  const labelAt = (p: Place) => docx?.view.cells.find((c) => keyOf(c) === keyOf(p))?.label ?? "";

  async function onFile(file: File | undefined) {
    setMessage(""); setChosen(null);
    if (!file) { setDocx(null); return; }
    try { setDocx({ file, view: await inspectDocx(file) }); }
    catch (e) { setDocx(null); setMessage(e instanceof DocxError ? e.message : "Could not read the file."); }
  }
  async function exportDocx() {
    if (!docx) return;
    setBusy(true); setMessage("");
    try {
      const r = await patchDocx(docx.file, docxContent(out, place));
      const name = `${docx.file.name.replace(/\.docx$/i, "")}_D4.docx`;
      download(r.blob, name);
      setMessage(exportMessage(r, name, out.appendixCount, Object.keys(out.steps).length > 0, out.bodyCount));
    } catch (e) { setMessage(e instanceof DocxError ? e.message : "Could not make the file."); }
    finally { setBusy(false); }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(out.text); setMessage("Copied the D4 text."); }
    catch { setMessage("Could not copy — select the preview text instead."); }
  }
  const field = (label: string, key: keyof typeof D4_KEYS, hint: string, exported: boolean) => <label className="cb-d4-field">
    <span>{label} <em>{exported ? "goes into the file" : "stays here — the 8D form has no cell for it"}</em></span>
    <textarea maxLength={10000} rows={5} value={notes[D4_KEYS[key]] ?? ""} placeholder={hint} onChange={(e) => onChange(D4_KEYS[key], e.target.value)} />
  </label>;

  return <section className="cb-d4" aria-label="D4 — your cause analysis">
    <h2>D4 · Your cause analysis <span className="cb-tag">you write this — the tool never fills or suggests it</span></h2>
    <p className="cb-muted">The cause texts above are what other manufacturers wrote about their own recalls. They are not the cause of your case. Write your own Escape Cause and Root Cause here. Your text is saved like the notes and is never sent to the server or an LLM.</p>
    <p className={`cb-note-state${state.warn ? " warn" : ""}`} role="status">{state.text}</p>
    <p className="cb-muted">{SHARED_BROWSER_NOTE}</p>
    {storeMessage && <p className="cb-note-state warn" role="status">{storeMessage}</p>}

    <div className="cb-d4-grid">
      <div>
        <h3>Questions to check <small>fixed sentences made by the tool, in Korean</small></h3>
        <ol className="cb-questions" lang="ko">{questions.map((q) => <li key={q}>{q}</li>)}</ol>
        {modelPicked.length > 0 && <>
          <h4>Picked by the model <small>from a fixed list of sentences — the model wrote none of them</small></h4>
          <ol className="cb-questions cb-picked" lang="ko">{modelPicked.map((q) => <li key={q.id}><b className="cb-id">{q.id}</b> {q.text}</li>)}</ol>
        </>}
        <p className="cb-muted">These do not say whether anything is the same or different, and they are not exported.{modelPicked.length === 0 ? " “Group the checked causes” lets the model pick more questions from a fixed list (needs a server with the model switched on)." : ""}</p>
      </div>
      <div className="cb-d4-fields">
        {field("Escape Cause — why it was not detected", "escape", "Why the defect was not caught in your process", true)}
        {field("Root Cause — the root cause in your case", "root", "The service does not fill or suggest this", true)}
        {field("Verification method — how you will verify", "verify", "How you will verify the cause (kept here only)", false)}
      </div>
    </div>

    <div className="cb-d4-out">
      <h3>Output <small>.docx · the 8D form you upload is read in this browser and never leaves it; the original is not changed</small></h3>
      <label className="cb-d4-opt"><input type="checkbox" checked={body} onChange={(e) => setBody(e.target.checked)} />
        <span>Put the cause texts of the {cards.length} checked precedent(s) in the D4 cell too, after what you wrote <em>(off by default — nothing is added unless you tick this)</em></span></label>
      {body && <p className="cb-muted">They follow your Escape and Root Cause text under the line “[선례 근거 — 타사 공개 원문이며 자사 사실이 아닙니다]”. Each quote keeps its “[타사 선례 …]” header and its source line (who said it · report file · submitted date · sha256), so another manufacturer’s cause is not read as yours. Other D steps are never filled from precedents.{out.skipped.length > 0 ? ` No cause text for ${out.skipped.join(", ")} — left out, nothing is filled in.` : ""}</p>}
      <label className="cb-d4-opt"><input type="checkbox" checked={appendix} onChange={(e) => setAppendix(e.target.checked)} />
        <span>Add the cause texts of the {cards.length} checked precedent(s) as an appendix after the 8D table <em>(off by default — nothing is added unless you tick this)</em></span></label>
      {appendix && <p className="cb-muted">Each appendix quote keeps its header (recall number · maker · date) and its source line (who said it · report file · submitted date · sha256).{!body && out.skipped.length > 0 ? ` No cause text for ${out.skipped.join(", ")} — left out, nothing is filled in.` : ""}</p>}
      <div className="cb-d4-file">
        <label>8D form (.docx)<input type="file" aria-label="8D form file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => void onFile(e.target.files?.[0])} /></label>
        {docx && <label>D4 cell
          <select aria-label="D4 cell" value={chosen ? keyOf(chosen) : ""} onChange={(e) => { const c = docx.view.cells.find((x) => keyOf(x) === e.target.value); setChosen(c ? { table: c.table, row: c.row, col: c.col } : null); }}>
            <option value="">{auto.length === 1 ? `Detected: table ${auto[0].table}, row ${auto[0].row} — “${short(labelAt(auto[0]))}”` : auto.length > 1 ? `${auto.length} cells match — choose one` : "Not found — choose a cell"}</option>
            {[...docx.view.cells.filter((c) => c.guess === 4), ...docx.view.cells.filter((c) => c.guess !== 4)].map((c) => <option key={keyOf(c)} value={keyOf(c)}>Table {c.table} · row {c.row} · “{short(c.label)}”{c.guess === 4 ? " — label matches D4" : ""}</option>)}
          </select></label>}
      </div>
      <div className="cb-actions">
        <button type="button" className="cb-btn" disabled={!docx || !out.hasContent || busy} onClick={() => void exportDocx()} title={docx ? undefined : "Upload your 8D form (.docx) to enable"}>{busy ? "Making the file…" : "Download .docx"}</button>
        <button type="button" className="cb-btn ghost" disabled={!out.hasContent} onClick={() => void copy()}>Copy the D4 text</button>
        <span role="status" className="cb-muted">{message || (out.hasContent ? "" : "Write your Escape Cause or Root Cause, or tick a precedent option, to enable.")}</span>
      </div>
      <details className="cb-d4-preview"><summary>Preview of what goes into the file</summary><pre lang="ko">{out.text}</pre></details>
    </div>
  </section>;
}
