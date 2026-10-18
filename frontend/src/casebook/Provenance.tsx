import type { SearchResponse } from "../search/types";

/** 응답이 어느 서버 판본에서 나왔는지 — 묶음 sha256 전체까지 되짚을 수 있게 둔다(AGENTS.md 2절 4번) */
export function Provenance({ data }: { data: SearchResponse }) {
  return <footer className="cb-prov" aria-label="Response source">
    <span>build {data.build_id}</span>
    <span title={data.bundle_sha256 ?? undefined}>{data.bundle_sha256 ? `bundle ${data.bundle_sha256.slice(0, 12)}…` : "no bundle (server started from local files)"}</span>
    <span>snapshot {data.snapshot_date}</span><span>model {data.model}</span>
    <span>question <span lang="en">{data.question}</span></span>
    {data.bundle_sha256 && <details><summary>Full version</summary><code className="cb-sha">{data.bundle_sha256}</code></details>}
  </footer>;
}
