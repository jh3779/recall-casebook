import { useEffect, useRef, useState } from "react";
import { ApiError, search } from "../api";
import { Feedback } from "./Feedback";
import { PrecedentDetail } from "./PrecedentDetail";
import { Provenance } from "./Provenance";
import { ResultList } from "./ResultList";
import { SearchInput } from "./SearchInput";
import { Welcome } from "./Welcome";
import { RetrievalDashboard } from "./dashboard/RetrievalDashboard";
import type { Card, HealthState, SearchResponse } from "./types";

export default function SearchView({ health, draft, onShowroom }: { health: HealthState; draft: { question: string } | null; onShowroom: () => void }) {
  const [question, setQuestion] = useState(draft?.question ?? "");
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [selected, setSelected] = useState<Card>();
  const [error, setError] = useState<ApiError>();
  const [delayed, setDelayed] = useState(false);
  const [mobileDetail, setMobileDetail] = useState(false);
  const [resultMode, setResultMode] = useState<"precedents" | "dashboard">("precedents");
  const [executedQuestion, setExecutedQuestion] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const requestRef = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  function cancel() {
    requestRef.current?.abort();
    requestRef.current = null;
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }
  useEffect(() => () => cancel(), []);
  useEffect(() => {
    if (!draft) return;
    inputRef.current?.focus();
  }, [draft]);

  async function run(value: string) {
    if (!value.trim() || !/[A-Za-z]/.test(value) || value.length > 4000) return;
    cancel();
    const controller = new AbortController();
    requestRef.current = controller;
    setQuestion(value);
    setExecutedQuestion(value.trim());
    setState("loading");
    setResponse(null);
    setError(undefined);
    setDelayed(false);
    setMobileDetail(false);
    setResultMode("precedents");
    timersRef.current = [setTimeout(() => setDelayed(true), 3000), setTimeout(() => controller.abort(), 60_000)];
    try {
      const result = await search(value, controller.signal);
      if (requestRef.current !== controller) return;
      setResponse(result);
      setSelected(result.customer_precedents[0] ?? result.precedents[0]);
      setState("done");
    } catch (e) {
      if (requestRef.current !== controller) return;
      setError(e instanceof ApiError ? e : new ApiError("network", "서버에 연결하지 못했습니다"));
      setState("error");
    } finally {
      if (requestRef.current === controller) {
        timersRef.current.forEach(clearTimeout);
        timersRef.current = [];
        requestRef.current = null;
      }
    }
  }
  useEffect(() => {
    if (state !== "done") return;
    const panel = resultRef.current?.querySelector<HTMLElement>(".detail");
    if (panel) panel.scrollTop = 0;
    if (mobileDetail && matchMedia("(max-width: 767px)").matches) {
      resultRef.current?.querySelector<HTMLElement>("#detail-heading")?.focus();
    }
  }, [selected, mobileDetail, state]);

  function back() {
    setMobileDetail(false);
    requestAnimationFrame(() => resultRef.current?.querySelector<HTMLElement>(".item[aria-pressed=true]")?.focus());
  }
  return <main className="view-search">
    <h1 className="sr-only">선례 검색</h1>
    <SearchInput question={question} onChange={setQuestion} onSearch={run} loading={state === "loading"} inputRef={inputRef} />
    {state === "idle" && <Welcome health={health} onExample={run} onShowroom={onShowroom} />}
    <Feedback loading={state === "loading"} delayed={delayed} error={state === "error" ? error : undefined} onRetry={() => run(question)} />
    {state === "done" && response && <>
      <p className="sr-only" role="status">선례 {response.customer_precedents.length + response.precedents.length}건을 찾았습니다</p>
      <nav className="result-mode" aria-label="검색 결과 보기"><span>현재 검색 응답 · 검색 버튼을 누르면 갱신</span><button className={resultMode === "precedents" ? "on" : ""} aria-pressed={resultMode === "precedents"} onClick={() => setResultMode("precedents")}>선례 상세</button><button className={resultMode === "dashboard" ? "on" : ""} aria-pressed={resultMode === "dashboard"} onClick={() => setResultMode("dashboard")}>분석 대시보드</button></nav>
      {resultMode === "dashboard" ? <RetrievalDashboard response={response} question={executedQuestion} /> : <div ref={resultRef} className={`split${mobileDetail ? " mobile-detail" : ""}${selected ? "" : " empty"}`}>
        <ResultList response={response} selected={selected} onSelect={(card) => { setSelected(card); setMobileDetail(true); }} />
        {selected ? <PrecedentDetail key={selected.campno} card={selected} response={response} onBack={back} /> : <div className="detail"><p>선례를 찾지 못했습니다. 부품 이름이나 고장 모습을 바꿔 다시 써 보세요.</p><Provenance data={response} question={response.question} /></div>}
      </div>}
    </>}
  </main>;
}
