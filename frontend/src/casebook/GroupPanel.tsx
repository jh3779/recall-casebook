import { useEffect, useRef, useState } from "react";
import { draft } from "../api";
import { sameBuild, type DraftResponse } from "../eightd/draft";
import type { Card } from "../search/types";
import { errorText } from "./errors";
import { groupCandidates, langOf } from "./sources";

const MAX_CARDS = 6; // 서버가 한 번에 받는 선례 수
const DEGRADED = { disabled: "Grouping is switched off on this server.", llm_failed: "Grouping failed." } as const;
const REJECTED: Record<string, string> = { not_in_source: "not in the source", unknown_source: "source mismatch", duplicate_source: "duplicate" };

/**
 * 원인 원문 묶기(DEC-065, LLM 보조). 문장을 새로 쓰지 않고, 화면에 나가는 글자는 서버가 출처 원문에서 잘라 낸 그 출처의 전체 원문이다.
 * 묶음 제목은 보이지 않는다("Group N"). 누르기 전에는 아무것도 부르지 않는다. 체크한 선례가 바뀌면 부모가 key를 바꿔 새로 시작한다(이전 묶음을 걷어 낸다).
 */
export function GroupPanel({ question, build, cards }: { question: string; build: { build_id: string; bundle_sha256: string | null }; cards: readonly Card[] }) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = useState<DraftResponse | null>(null);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const withCause = groupCandidates(cards, Infinity).length;
  const used = groupCandidates(cards, MAX_CARDS);
  const byId = new Map(cards.map((c) => [c.campno, c]));

  async function run() {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    const timer = setTimeout(() => c.abort(), 60_000);
    setState("loading"); setError("");
    try {
      const r = await draft(question, used.map((x) => x.campno), "d4", c.signal);
      if (controller.current !== c) return;
      if (!sameBuild(r, build)) { setResult(null); setError("The server data version changed since the search. Search again."); setState("error"); return; }
      setResult(r); setState("done");
    } catch (e) {
      if (controller.current !== c) return;
      setError(errorText(e, "grouping"));
      setState("error");
    } finally { clearTimeout(timer); }
  }
  return <section className="cb-group" aria-label="Group similar causes">
    <h2>Group similar causes <span className="cb-tag">LLM-assisted · writes no sentences</span></h2>
    <p className="cb-muted">Groups the cause texts of the checked precedents by similar wording. Each quote is the full original text of its source; the tool does not compare them with your case and does not write a cause.{cards.length > 0 && withCause === 0 ? " None of the checked precedents has a cause text." : ""}{withCause > MAX_CARDS ? ` ${withCause} have a cause text; only the first ${MAX_CARDS} are sent.` : ""}</p>
    <button type="button" className="cb-btn" onClick={run} disabled={!used.length || state === "loading"}>{state === "loading" ? "Grouping…" : state === "done" ? "Group again" : "Group the checked causes"}</button>
    {state === "error" && <p className="cb-error" role="alert">{error}</p>}
    {state === "done" && result && <div className="cb-groups">
      {result.degraded && <p className="cb-muted" role="status">{DEGRADED[result.degraded]} Read the cause texts in the middle column.</p>}
      {!result.degraded && !result.groups.length && !result.ungrouped.length && <p className="cb-muted">None of the checked precedents has a cause text to group.</p>}
      {!result.degraded && !result.groups.length && result.ungrouped.length > 0 && <p className="cb-muted">No similar wording found among the {result.ungrouped.length} cause text(s). Read them in the middle column.</p>}
      {result.groups.map((group, i) => <article key={i} className="cb-grp" aria-label={`Group ${i + 1}`}>
        <h3>Group {i + 1} <small>{group.items.length} quote(s)</small></h3>
        <ul>{group.items.map((item) => <li key={`${item.campno}-${item.field}`}>
          <b className="cb-id">{item.campno}</b>{byId.get(item.campno) && <span className="cb-muted"> · {byId.get(item.campno)!.maker}</span>}
          <q lang="en">{item.quote}</q>
          {item.cause_status === "stated_unknown" && <span className="cb-muted">Text opens with a not-reported / under-investigation expression; this does not mean the cause is unknown.</span>}
          <span className="cb-muted" lang={langOf(item.speaker)}>Said by {item.speaker}{item.cause_source ? ` · ${item.cause_source.file} · sha256 ${item.cause_source.pdf_sha256}` : ""}</span>
        </li>)}</ul>
      </article>)}
      {result.groups.length > 0 && result.ungrouped.length > 0 && <p className="cb-muted">{result.ungrouped.length} cause text(s) were not grouped; read them in the middle column.</p>}
      {Object.entries(result.rejected).some(([k, n]) => n > 0 && k !== "bad_title") && <p className="cb-muted">Dropped after checking against the source: {Object.entries(result.rejected).filter(([k, n]) => n > 0 && k !== "bad_title").map(([k, n]) => `${REJECTED[k] ?? k} ${n}`).join(" · ")}.</p>}
      <p className="cb-muted">{result.model ? `model ${result.model} · ` : ""}build {result.build_id}</p>
    </div>}
  </section>;
}
