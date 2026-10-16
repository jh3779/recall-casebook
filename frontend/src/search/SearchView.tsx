import { useEffect, useRef, useState } from "react";
import { ApiError, search } from "../api";
import { Feedback } from "./Feedback";
import { PickBar } from "./PickBar";
import { isPicked, togglePick } from "./picks";
import { PrecedentDetail } from "./PrecedentDetail";
import { Provenance } from "./Provenance";
import { ResultList } from "./ResultList";
import { SearchInput } from "./SearchInput";
import { Welcome } from "./Welcome";
import type { Card, HealthState, SearchResponse } from "./types";

export default function SearchView({ health, draft, onShowroom, onWrite8d }: { health: HealthState; draft: { question: string } | null; onShowroom: () => void; onWrite8d?: (cards: readonly Card[], response: SearchResponse | null, fresh?: { question: string }) => void }) {
  const [question, setQuestion] = useState(draft?.question ?? "");
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [selected, setSelected] = useState<Card>();
  const [picked, setPicked] = useState<Card[]>([]);
  const [error, setError] = useState<ApiError>();
  const [delayed, setDelayed] = useState(false);
  const [mobileDetail, setMobileDetail] = useState(false);
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
    setState("loading");
    setResponse(null);
    setPicked([]);
    setError(undefined);
    setDelayed(false);
    setMobileDetail(false);
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
  const canPick = !!onWrite8d;
  return <main className={`view-search${canPick && state === "done" && picked.length ? " has-picks" : ""}`}>
    <h1 className="sr-only">선례 검색</h1>
    <SearchInput question={question} onChange={setQuestion} onSearch={run} loading={state === "loading"} inputRef={inputRef} extra={onWrite8d && <button type="button" className="write-plain" onClick={() => onWrite8d([], response, { question })}>선례 없이 8D 작성하기 →</button>} />
    {state === "idle" && <Welcome health={health} onExample={run} onShowroom={onShowroom} />}
    <Feedback loading={state === "loading"} delayed={delayed} error={state === "error" ? error : undefined} onRetry={() => run(question)} />
    {state === "done" && response && <>
      <p className="sr-only" role="status">선례 {response.customer_precedents.length + response.precedents.length}건을 찾았습니다</p>
      <div ref={resultRef} className={`split${mobileDetail ? " mobile-detail" : ""}${selected ? "" : " empty"}`}>
        <ResultList response={response} selected={selected} onSelect={(card) => { setSelected(card); setMobileDetail(true); }} picked={picked} onPick={canPick ? (card) => setPicked((list) => togglePick(list, card)) : undefined} />
        {selected ? <PrecedentDetail key={selected.campno} card={selected} response={response} onBack={back} picked={isPicked(picked, selected)} onPick={canPick ? () => setPicked((list) => togglePick(list, selected)) : undefined} /> : <div className="detail"><p>선례를 찾지 못했습니다. 부품 이름이나 고장 모습을 바꿔 다시 써 보세요.</p><Provenance data={response} question={response.question} /></div>}
      </div>
      {onWrite8d && picked.length > 0 && <PickBar picked={picked} onRemove={(card) => setPicked((list) => togglePick(list, card))} onWrite={() => onWrite8d(picked, response)} />}
    </>}
  </main>;
}
