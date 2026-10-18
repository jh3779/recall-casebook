import type { HealthState } from "../search/types";
import { EXAMPLES } from "./examples";

/** 처음 열었을 때(검색 전) 보이는 안내 — 예시 질문·하는 일/하지 않는 일·데이터 판본. 선례 검색 화면에 있던 것을 옮겼다(DEC-075) */

export function Intro({ health, onExample }: { health: HealthState; onExample: (question: string) => void }) {
  return <div className="cb-intro">
    <section className="cb-intro-ex"><h2>Example questions</h2><div className="cb-examples">{EXAMPLES.map((q) => <button type="button" className="cb-example" lang="en" key={q} onClick={() => onExample(q)}>{q}</button>)}</div></section>
    <div className="cb-does">
      <section><h2>What this tool does</h2><ul>
        <li>Finds recalls that may involve the same part from one English defect line — you compare the part chips and the items to check yourself.</li>
        <li>Shows the defect, consequence, remedy and the Part 573 cause field word for word.</li>
        <li>Labels every quote with who said it and where it comes from (recall number, Part 573 file, investigation number).</li>
      </ul></section>
      <section className="not"><h2>What it does not do</h2><ul>
        <li>It does not decide whether a recall is needed, or what the cause is.</li>
        <li>It does not translate or summarize the originals.</li>
        <li>It does not guess a cause or a supplier that is not in the source.</li>
      </ul></section>
    </div>
    <section className="cb-version"><h2>Data version</h2>
      {typeof health === "string" ? <p className="cb-muted">{health === "loading" ? "Checking server…" : "Server version unavailable"}</p>
        : <p className="cb-muted">{health.cards.toLocaleString("en-US")} cards · build {health.build_id} · {health.bundle_sha256 ? `bundle ${health.bundle_sha256.slice(0, 12)}…` : "no bundle (server started from local files)"} · snapshot {health.snapshot_date} · model {health.model}</p>}
    </section>
  </div>;
}
