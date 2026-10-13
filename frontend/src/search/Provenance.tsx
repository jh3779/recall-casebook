import { useRef, useState } from "react";
import type { ProvenanceData } from "./types";

function FullBundle({ buildId, sha }: { buildId: string; sha: string }) {
  const [msg, setMsg] = useState("");
  const full = useRef<HTMLElement>(null);
  const fail = () => {
    setMsg("복사하지 못했습니다 — 위 글자를 눌러 선택한 뒤 복사해 주세요");
    const node = full.current;
    const selection = window.getSelection();
    if (node && selection) { const range = document.createRange(); range.selectNodeContents(node); selection.removeAllRanges(); selection.addRange(range); }
  };
  const copy = () => {
    if (!navigator.clipboard) return fail();
    navigator.clipboard.writeText(sha).then(() => setMsg("복사했습니다"), fail);
  };
  return <details className="prov-more">
    <summary>판본 자세히</summary>
    <div>build {buildId}</div>
    <code ref={full} className="prov-sha">{sha}</code>
    <button type="button" className="btn ghost small" onClick={copy}>복사</button>
    <span role="status" className="note">{msg}</span>
  </details>;
}

export function Provenance({ data, question }: { data: ProvenanceData; question?: string }) {
  return <footer className="prov" aria-label="응답 출처">
    <span>build {data.build_id}</span>
    <span title={data.bundle_sha256 ?? undefined}>{data.bundle_sha256 ? `묶음 ${data.bundle_sha256.slice(0, 12)}…` : "묶음 없음(로컬 파일로 띄운 서버)"}</span>
    <span>스냅샷 {data.snapshot_date}</span><span>모델 {data.model}</span>
    {question !== undefined && <span>질문 <span lang="en">{question}</span></span>}
    {data.bundle_sha256 && <FullBundle buildId={data.build_id} sha={data.bundle_sha256} />}
  </footer>;
}
