import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, search } from "../api";
import type { Card, HealthState, SearchResponse } from "../search/types";
import { adoptDraft } from "./adoptDraft";
import { errorText } from "./errors";
import { Intro } from "./Intro";
import { OverlayBoundary, OverlayLoading } from "./OverlayBoundary";
import { pickedFor, toggleChecked } from "./questions";
import { Results } from "./Results";
import { SearchError } from "./SearchError";
import { useCountdown } from "./useCountdown";
import { Write8dPlain } from "./Write8dBar";
import { adoptNotes, applyNote, browserStorage, clearNotes, isUnsaved, losesNotesOnSwitch, nextUnsaved, normalizeCaseName, notesText, storageProblem } from "./notes";

const ModelOverlay = lazy(() => import("./ModelOverlay")); // three.js는 3D 창을 열 때만 받는다

/**
 * Recall Casebook. for Engineer (DEC-067) — 선례를 체크하면 원인 원문이 근거로 쌓이고, 선례별 메모와 원인 묶기를 오른쪽에 둔다.
 * 판정하지 않는다: 같다·다르다·해당한다를 표시하지 않고 자사 원인을 제안하지 않는다. 메모는 서버·LLM으로 보내지 않는다.
 */
export default function CasebookView({ health, draft = null, onWrite8d }: { health: HealthState; draft?: { question: string; key: number } | null; onWrite8d?: (cards: readonly Card[], response: SearchResponse | null, fresh?: { question: string }) => void }) {
  const [question, setQuestion] = useState(draft?.question ?? "");
  const [draftKey, setDraftKey] = useState(draft?.key ?? 0);
  const questionInput = useRef<HTMLInputElement>(null);
  useEffect(() => { if (draft) questionInput.current?.focus(); }, [draft]);
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [checked, setChecked] = useState<Card[]>([]);
  const [error, setError] = useState("");
  const [retryAt, setRetryAt] = useState<number | null>(null); // 호출 상한(429) 뒤 다시 보낼 수 있는 시각 — 그때까지 검색 단추를 막는다
  const [slow, setSlow] = useState(false); // 3초가 지나도 응답이 없으면 서버가 깨어나는 중일 수 있다고 알린다
  const wait = useCountdown(retryAt);
  const [caseInput, setCaseInput] = useState("");
  const [caseName, setCaseName] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [copyMessage, setCopyMessage] = useState("");
  const [view3d, setView3d] = useState<{ card: Card; opener: HTMLElement } | null>(null); // opener = 클릭한 Show in 3D 버튼(닫을 때 초점을 돌려줄 곳)
  const [picked, setPicked] = useState<{ key: string; ids: string[] } | null>(null); // 묶기에서 모델이 고른 확인 질문 번호 — 체크한 선례가 바뀌면 걷어 낸다
  const [storeMessage, setStoreMessage] = useState(""); // 저장·삭제 실패 안내 — D4 구역에서도 보인다
  const [unsavedNotes, setUnsavedNotes] = useState<ReadonlySet<string>>(new Set()); // 저장소에 쓰지 못한 메모의 리콜 번호 — 하나라도 있으면 저장됐다고 말하지 않는다
  const saveFailed = unsavedNotes.size > 0;
  const storage = useMemo(() => browserStorage(), []);
  const request = useRef<AbortController | null>(null);
  const caseRef = useRef(caseName); // 검색이 오래 걸리는 동안 사건 이름이 붙으면 낡은 이름으로 화면 메모를 비우지 않게
  useEffect(() => { caseRef.current = caseName; }, [caseName]);
  const adopted = adoptDraft(draftKey, draft, question);
  if (adopted.key !== draftKey) { // 3D 쇼룸에서 넘어온 새 질문 — 입력창을 채우고(자동 검색은 하지 않는다) 이전 질문의 결과를 비운다
    setDraftKey(adopted.key); setQuestion(adopted.question);
    if (adopted.reset) { setState("idle"); setResponse(null); setChecked([]); setPicked(null); setError(""); setRetryAt(null); setSlow(false); }
  }
  const slowTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { request.current?.abort(); if (slowTimer.current) clearTimeout(slowTimer.current); }, []);
  useEffect(() => { if (draft) { request.current?.abort(); request.current = null; } }, [draft]); // 새 질문이 오면 진행 중이던 이전 요청은 취소하고 그 응답은 버린다

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
  async function run(example?: string) { // example: 예시 질문 버튼 — 입력창에도 채우고 바로 검색한다
    const value = (example ?? question).trim();
    if (example !== undefined) setQuestion(example);
    if (!value || !/[A-Za-z]/.test(value) || value.length > 4000) return;
    if (!caseName && unsaved && !confirm("Notes and D4 text without a case name will be discarded when you search again. Continue?")) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const timer = setTimeout(() => controller.abort(), 60_000);
    setState("loading"); setError(""); setRetryAt(null); setResponse(null); setChecked([]); setPicked(null); setSlow(false);
    if (slowTimer.current) clearTimeout(slowTimer.current);
    slowTimer.current = setTimeout(() => setSlow(true), 3000);
    try {
      const result = await search(value, controller.signal);
      if (request.current !== controller) return;
      if (!caseRef.current) setNotes({}); // 이름 없는 메모는 새 결과가 실제로 온 뒤에 비운다(검색이 실패하면 메모를 잃지 않게)
      setResponse(result); setState("done");
    } catch (e) {
      if (request.current !== controller) return;
      setError(errorText(e, "search")); setRetryAt(e instanceof ApiError ? e.retryAt ?? null : null); setState("error");
    } finally { clearTimeout(timer); if (request.current === controller && slowTimer.current) clearTimeout(slowTimer.current); }
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
      <input id="cb-question" ref={questionInput} lang="en" value={question} maxLength={4000} onChange={(e) => setQuestion(e.target.value)} placeholder="Describe the defect in English — e.g. brake fluid leaking from front caliper" aria-invalid={noEnglish} />
      <button type="submit" className="cb-btn" disabled={state === "loading" || wait > 0 || !question.trim() || noEnglish}>{state === "loading" ? "Searching…" : "Find precedents"}</button>
      <span className={`cb-muted${noEnglish ? " warn" : ""}`} aria-live="polite">{noEnglish ? "Needs English words." : "English questions only. NHTSA public recalls and Part 573 reports."}</span>
      {onWrite8d && <Write8dPlain question={question} response={response} onWrite8d={onWrite8d} />}
    </form>
    {state === "error" && <SearchError message={error} limited={retryAt !== null} wait={wait} onRetry={() => void run()} />}
    {state === "idle" && <><p className="cb-empty">Describe a defect to see precedents from other manufacturers, with the cause text each one wrote and who said it.</p><Intro health={health} onExample={(q) => void run(q)} /></>}
    {state === "loading" && <p className="cb-empty" role="status">Searching…{slow && " The server may be waking up — the first request can take 13–16 seconds."}</p>}

    {state === "done" && response && <Results response={response} checked={checked} checkedKey={checkedKey} onToggle={togglePicked} on3d={(card, button) => setView3d({ card, opener: button })}
      notes={notes} onNoteChange={changeNote} caseName={caseName} persistent={persistent} storageBlocked={storageProblem(caseName, !!storage, saveFailed)} onCopy={() => void copyAll()} onClear={clearCase}
      copyMessage={copyMessage} storeMessage={storeMessage} onGroupPicked={(ids) => setPicked({ key: checkedKey, ids })} picked={pickedFor(picked, checkedKey)} onWrite8d={onWrite8d} />}
    {view3d && <OverlayBoundary onClose={() => setView3d(null)} opener={view3d.opener}><Suspense fallback={<OverlayLoading onClose={() => setView3d(null)} opener={view3d.opener} />}><ModelOverlay card={view3d.card} opener={view3d.opener} onClose={() => setView3d(null)} /></Suspense></OverlayBoundary>}
  </main>;
}
