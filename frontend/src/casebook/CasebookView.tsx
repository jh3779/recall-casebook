import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { search } from "../api";
import type { Card, HealthState, SearchResponse } from "../search/types";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import { D4Panel } from "./D4Panel";
import { errorText } from "./errors";
import { GroupPanel } from "./GroupPanel";
import { NotesPanel } from "./NotesPanel";
import { OverlayBoundary } from "./OverlayBoundary";
import { pickedFor, toggleChecked } from "./questions";
import { adoptNotes, applyNote, browserStorage, clearNotes, isUnsaved, losesNotesOnSwitch, nextUnsaved, normalizeCaseName, notesText, storageProblem } from "./notes";

const ModelOverlay = lazy(() => import("./ModelOverlay")); // three.js는 3D 창을 열 때만 받는다

/**
 * Recall Casebook. for Engineer (DEC-067) — 선례를 체크하면 원인 원문이 근거로 쌓이고, 선례별 메모와 원인 묶기를 오른쪽에 둔다.
 * 판정하지 않는다: 같다·다르다·해당한다를 표시하지 않고 자사 원인을 제안하지 않는다. 메모는 서버·LLM으로 보내지 않는다.
 */
export default function CasebookView({ health }: { health: HealthState }) {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [checked, setChecked] = useState<Card[]>([]);
  const [error, setError] = useState("");
  const [caseInput, setCaseInput] = useState("");
  const [caseName, setCaseName] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [copyMessage, setCopyMessage] = useState("");
  const [view3d, setView3d] = useState<Card | null>(null);
  const [picked, setPicked] = useState<{ key: string; ids: string[] } | null>(null); // 묶기에서 모델이 고른 확인 질문 번호 — 체크한 선례가 바뀌면 걷어 낸다
  const [storeMessage, setStoreMessage] = useState(""); // 저장·삭제 실패 안내 — D4 구역에서도 보인다
  const [unsavedNotes, setUnsavedNotes] = useState<ReadonlySet<string>>(new Set()); // 저장소에 쓰지 못한 메모의 리콜 번호 — 하나라도 있으면 저장됐다고 말하지 않는다
  const saveFailed = unsavedNotes.size > 0;
  const storage = useMemo(() => browserStorage(), []);
  const request = useRef<AbortController | null>(null);
  const caseRef = useRef(caseName); // 검색이 오래 걸리는 동안 사건 이름이 붙으면 낡은 이름으로 화면 메모를 비우지 않게
  useEffect(() => { caseRef.current = caseName; }, [caseName]);
  useEffect(() => () => request.current?.abort(), []);

  // 사건 이름 없이 적은 메모가 있으면 새로고침·탭 닫기 전에 잃는다고 알린다
  const unsaved = isUnsaved(caseName, notes, saveFailed, !!storage);
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    addEventListener("beforeunload", warn);
    return () => removeEventListener("beforeunload", warn);
  }, [unsaved]);

  function commitCase() {
    const name = normalizeCaseName(caseInput);
    setCaseInput(name);
    if (name === caseName) return;
    if (losesNotesOnSwitch(caseName, notes, saveFailed, !!storage) && !confirm("Notes and D4 text that are not saved in this browser will be lost if you switch cases. Switch anyway?")) { setCaseInput(caseName); return; }
    setCaseName(name);
    // 이름 없이 적은 메모만 첫 사건 이름으로 옮긴다 — 다른 사건 이름이 붙어 있던 메모가 새 사건에 섞이지 않게
    const next = name ? adoptNotes(storage, name, caseName ? {} : notes) : { notes: {}, saved: true, failed: [] as string[] };
    setNotes(next.notes);
    setUnsavedNotes(!!storage && !!name ? new Set(next.failed) : new Set());
  }
  useEffect(() => { // 3D 창을 연 채 다른 화면으로 가면(뒤로 가기·주소창 해시) 숨은 창이 남지 않게 닫는다
    const left = () => { if (location.hash !== "#casebook") setView3d(null); };
    addEventListener("hashchange", left);
    return () => removeEventListener("hashchange", left);
  }, []);
  function togglePicked(card: Card) { // 체크한 선례가 바뀌면 모델이 고른 질문을 걷어 낸다 — 같은 조합으로 돌아와도 되살아나지 않게(DEC-071)
    const next = toggleChecked({ checked, picked }, card);
    setChecked(next.checked); setPicked(next.picked);
  }
  async function run() {
    const value = question.trim();
    if (!value || !/[A-Za-z]/.test(value) || value.length > 4000) return;
    if (!caseName && unsaved && !confirm("Notes and D4 text without a case name will be discarded when you search again. Continue?")) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const timer = setTimeout(() => controller.abort(), 60_000);
    setState("loading"); setError(""); setResponse(null); setChecked([]); setPicked(null);
    try {
      const result = await search(value, controller.signal);
      if (request.current !== controller) return;
      if (!caseRef.current) setNotes({}); // 이름 없는 메모는 새 결과가 실제로 온 뒤에 비운다(검색이 실패하면 메모를 잃지 않게)
      setResponse(result); setState("done");
    } catch (e) {
      if (request.current !== controller) return;
      setError(errorText(e, "search")); setState("error");
    } finally { clearTimeout(timer); }
  }
  function changeNote(campno: string, text: string) {
    const r = applyNote(storage, caseName, notes, campno, text);
    setNotes(r.notes);
    if (caseName && storage && !r.deleteFailed) setUnsavedNotes((prev) => nextUnsaved(prev, campno, r.saved)); // 삭제 실패는 저장 실패가 아니다 — 옛 글이 저장소에 남아 있으므로 "잃는다" 경고를 켜지 않고 삭제 실패만 알린다
    const failed = r.deleteFailed ? "Could not delete the saved note — it may remain in this browser." : "";
    setCopyMessage(failed); setStoreMessage(failed);
  }
  async function copyAll() {
    try { await navigator.clipboard.writeText(notesText(checked, notes)); setCopyMessage("Copied."); }
    catch { setCopyMessage("Could not copy — select the text in the boxes instead."); }
  }
  function clearCase() {
    if (!confirm(caseName ? `Delete all notes and D4 text saved under “${caseName}”?` : "Delete all notes and D4 text in this tab?")) return;
    if (caseName && storage && !clearNotes(storage, caseName)) { const failed = "Could not delete the saved notes — they may remain in this browser."; setCopyMessage(failed); setStoreMessage(failed); return; } // 지우지 못했으면 화면도 그대로 둔다
    setNotes({}); setCopyMessage(""); setStoreMessage(""); setUnsavedNotes(new Set());
  }
  const checkedKey = checked.map((x) => x.campno).join(",");
  const noEnglish = !!question.trim() && !/[A-Za-z]/.test(question);
  const persistent = !!caseName && !!storage;

  return <main className="view-casebook" lang="en">
    <header className="cb-top">
      <div className="cb-brand"><span className="cb-brand-mark" aria-hidden="true" /><h1>Recall Casebook.<small> for Engineer</small></h1></div>
      <div className="cb-case-name">
        <label htmlFor="cb-case">Case name</label>
        <input id="cb-case" value={caseInput} maxLength={80} onChange={(e) => setCaseInput(e.target.value)} onBlur={commitCase} onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing && e.keyCode !== 229) commitCase(); }} placeholder="e.g. Sorento rear camera, Oct" aria-describedby="cb-case-hint" />
        <small id="cb-case-hint" className="cb-muted">Changing the name switches to that case's notes. The name is also stored in this browser — avoid real project names.</small>
      </div>
      <span className="cb-health" role="status">{typeof health === "object" ? `build ${health.build_id} · snapshot ${health.snapshot_date}` : health === "loading" ? "Checking server…" : "Server version unavailable"}</span>
    </header>

    <form className="cb-search" onSubmit={(e) => { e.preventDefault(); void run(); }}>
      <label htmlFor="cb-question" className="sr-only">Defect description in English</label>
      <input id="cb-question" lang="en" value={question} maxLength={4000} onChange={(e) => setQuestion(e.target.value)} placeholder="Describe the defect in English — e.g. brake fluid leaking from front caliper" aria-invalid={noEnglish} />
      <button type="submit" className="cb-btn" disabled={state === "loading" || !question.trim() || noEnglish}>{state === "loading" ? "Searching…" : "Find precedents"}</button>
      <span className={`cb-muted${noEnglish ? " warn" : ""}`} aria-live="polite">{noEnglish ? "Needs English words." : "English questions only. NHTSA public recalls and Part 573 reports."}</span>
    </form>
    {state === "error" && <p className="cb-error" role="alert">{error} <button type="button" className="cb-link" onClick={() => void run()}>Retry</button></p>}
    {state === "idle" && <p className="cb-empty">Describe a defect to see precedents from other manufacturers, with the cause text each one wrote and who said it.</p>}
    {state === "loading" && <p className="cb-empty" role="status">Searching…</p>}

    {state === "done" && response && <>
    <div className="cb-grid">
      <CaseList response={response} checked={checked} onToggle={togglePicked} />
      <section className="cb-stack" aria-label="Checked precedents">
        <h2 className="sr-only">Checked precedents</h2>
        {!checked.length && <p className="cb-empty">Check precedents on the left. Each one stacks here with its original wording, who said it, and the report it came from.</p>}
        {checked.map((card) => <CaseDetail key={card.campno} card={card} response={response} onRemove={() => togglePicked(card)} on3d={() => setView3d(card)} />)}
      </section>
      <div className="cb-side">
        <NotesPanel cards={checked} notes={notes} onChange={changeNote} caseName={caseName} persistent={persistent} storageBlocked={storageProblem(caseName, !!storage, saveFailed)} onCopy={() => void copyAll()} onClear={clearCase} copyMessage={copyMessage} />
        <GroupPanel key={checkedKey} question={response.question} build={response} cards={checked} onPicked={(ids) => setPicked({ key: checkedKey, ids })} />
      </div>
    </div>
    <D4Panel cards={checked} response={response} notes={notes} onChange={changeNote} caseName={caseName} persistent={persistent} storageBlocked={storageProblem(caseName, !!storage, saveFailed)} storeMessage={storeMessage} picked={pickedFor(picked, checkedKey)} />
    </>}
    {view3d && <OverlayBoundary onClose={() => setView3d(null)}><Suspense fallback={<p className="cb-3d-msg" role="status">Loading the 3D view…</p>}><ModelOverlay card={view3d} onClose={() => setView3d(null)} /></Suspense></OverlayBoundary>}
  </main>;
}
