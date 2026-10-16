import { useEffect, useRef, useState } from "react";
import { ApiError, draft } from "../api";
import type { Card } from "../search/types";
import { sameBuild, type DraftResponse, type DraftStep } from "./draft";
import { DraftResult } from "./DraftResult";

const MAX_CARDS = 6; // 서버가 한 번에 받는 선례 수

/** D2·D4의 "선례 근거 묶음 초안" — 담은 선례 원문을 LLM이 묶고 제목을 붙이게 한다(DEC-065). 누르기 전에는 아무것도 부르지 않는다 */
export function DraftPanel({ step, question, build, cards, inserted, onToggle }: { step: DraftStep; question: string; build: { build_id: string; bundle_sha256: string | null }; cards: readonly Card[]; inserted: Record<string, string>; onToggle: (id: string, block: string) => void }) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = useState<DraftResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const used = cards.slice(0, MAX_CARDS);

  async function run() {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    const timer = setTimeout(() => c.abort(), 60_000);
    setState("loading"); setError(null);
    try {
      const r = await draft(question, used.map((x) => x.campno), step, c.signal);
      if (controller.current !== c) return;
      if (!sameBuild(r, build)) { setResult(null); setError(new ApiError("server", "서버의 데이터 판본이 검색할 때와 달라졌습니다. 질문을 다시 검색한 뒤 선례를 담아 다시 시도해 주세요.")); setState("error"); return; }
      setResult(r); setState("done");
    } catch (e) {
      if (controller.current !== c) return;
      setError(e instanceof ApiError ? e : new ApiError("network", "서버에 연결하지 못했습니다")); setState("error");
    } finally { clearTimeout(timer); }
  }
  return <div className="dp">
    <div className="dp-head">
      <b>선례 근거 묶음 초안</b><span className="tag">LLM 보조 · 문장을 쓰지 않고 원문만 묶음</span>
      <button type="button" className="btn" onClick={run} disabled={state === "loading"}>{state === "loading" ? "묶는 중…" : state === "done" ? "다시 묶기" : "묶음 초안 만들기"}</button>
    </div>
    <p className="note">담은 선례 {used.length}건의 {step === "d2" ? "결함·결과" : "원인"} 원문을 비슷한 것끼리 묶고 제목을 붙입니다. 인용은 서버가 원문에서 잘라 낸 글자이고, 제목은 도구가 붙인 문장이라 원문이 아닙니다. 같다·다르다를 판정하지 않으며 자사 원인을 쓰지 않습니다.{cards.length > MAX_CARDS ? ` 담은 선례가 ${cards.length}건이라 앞 ${MAX_CARDS}건만 보냅니다.` : ""}</p>
    {state === "loading" && <p className="note" role="status">묶는 중입니다…</p>}
    {state === "error" && error && <p className="ed-err" role="alert">{error.message}</p>}
    {state === "done" && result && <DraftResult result={result} cards={cards} inserted={inserted} onToggle={onToggle} />}
  </div>;
}
