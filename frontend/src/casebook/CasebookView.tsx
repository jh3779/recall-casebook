import { useEffect, useMemo, useRef, useState } from "react";
import { search } from "../api";
import { togglePick } from "../search/picks";
import type { Card, HealthState, SearchResponse } from "../search/types";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import { errorText } from "./errors";
import { GroupPanel } from "./GroupPanel";
import { NotesPanel } from "./NotesPanel";
import { adoptNotes, browserStorage, clearNotes, normalizeCaseName, notesText, saveNote } from "./notes";

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
  const [saveFailed, setSaveFailed] = useState(false); // 사건 이름이 있는데 저장소에 쓰지 못한 적이 있다 — 저장됐다고 말하지 않는다
  const storage = useMemo(() => browserStorage(), []);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  // 사건 이름 없이 적은 메모가 있으면 새로고침·탭 닫기 전에 잃는다고 알린다
  const unsaved = (!caseName || !storage || saveFailed) && Object.values(notes).some((t) => t.trim());
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
    setCaseName(name);
    // 이름 없이 적은 메모만 첫 사건 이름으로 옮긴다 — 다른 사건 이름이 붙어 있던 메모가 새 사건에 섞이지 않게
    const next = name ? adoptNotes(storage, name, caseName ? {} : notes) : { notes: {}, saved: true };
    setNotes(next.notes);
    setSaveFailed(!!storage && !!name && !next.saved);
  }
  async function run() {
    const value = question.trim();
    if (!value || !/[A-Za-z]/.test(value) || value.length > 4000) return;
    if (!caseName && unsaved && !confirm("Notes without a case name will be discarded when you search again. Continue?")) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const timer = setTimeout(() => controller.abort(), 60_000);
    setState("loading"); setError(""); setResponse(null); setChecked([]);
    try {
      const result = await search(value, controller.signal);
      if (request.current !== controller) return;
      if (!caseName) setNotes({}); // 이름 없는 메모는 새 결과가 실제로 온 뒤에 비운다(검색이 실패하면 메모를 잃지 않게)
      setResponse(result); setState("done");
    } catch (e) {
      if (request.current !== controller) return;
      setError(errorText(e, "search")); setState("error");
    } finally { clearTimeout(timer); }
  }
  function changeNote(campno: string, text: string) {
    setNotes((memory) => {
      const next = { ...memory };
      if (text) next[campno] = text; else delete next[campno];
      return next;
    });
    const saved = saveNote(storage, caseName, campno, text);
    if (caseName && storage) setSaveFailed(!saved);
  }
  async function copyAll() {
    try { await navigator.clipboard.writeText(notesText(checked, notes)); setCopyMessage("Copied."); }
    catch { setCopyMessage("Could not copy — select the text in the boxes instead."); }
  }
  function clearCase() {
    if (!confirm(caseName ? `Delete all notes saved under “${caseName}”?` : "Delete all notes in this tab?")) return;
    const cleared = clearNotes(storage, caseName);
    setNotes({}); setCopyMessage("");
    if (caseName && storage) setSaveFailed(!cleared);
  }
  const noEnglish = !!question.trim() && !/[A-Za-z]/.test(question);
  const persistent = !!caseName && !!storage;

  return <main className="view-casebook" lang="en">
    <header className="cb-top">
      <div className="cb-brand"><span className="cb-brand-mark" aria-hidden="true" /><h1>Recall Casebook.<small> for Engineer</small></h1></div>
      <label className="cb-case-name">
        <span>Case name</span>
        <input value={caseInput} maxLength={80} onChange={(e) => setCaseInput(e.target.value)} onBlur={commitCase} onKeyDown={(e) => { if (e.key === "Enter") commitCase(); }} placeholder="e.g. Sorento rear camera, Oct" aria-describedby="cb-case-hint" />
        <small id="cb-case-hint" className="cb-muted">Changing the name switches to that case's notes.</small>
      </label>
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

    {state === "done" && response && <div className="cb-grid">
      <CaseList response={response} checked={checked} onToggle={(card) => setChecked((list) => togglePick(list, card))} />
      <section className="cb-stack" aria-label="Checked precedents">
        <h2 className="sr-only">Checked precedents</h2>
        {!checked.length && <p className="cb-empty">Check precedents on the left. Each one stacks here with its original wording, who said it, and the report it came from.</p>}
        {checked.map((card) => <CaseDetail key={card.campno} card={card} response={response} onRemove={() => setChecked((list) => togglePick(list, card))} />)}
      </section>
      <div className="cb-side">
        <NotesPanel cards={checked} notes={notes} onChange={changeNote} caseName={caseName} persistent={persistent} storageBlocked={(!!caseName && !storage) || saveFailed} onCopy={() => void copyAll()} onClear={clearCase} copyMessage={copyMessage} />
        <GroupPanel key={checked.map((c) => c.campno).join(",")} question={response.question} build={response} cards={checked} />
      </div>
    </div>}
  </main>;
}
