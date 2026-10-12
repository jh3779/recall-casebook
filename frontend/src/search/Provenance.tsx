import type { ProvenanceData } from "./types";
export function Provenance({ data, question }: { data: ProvenanceData; question?: string }) {
  return <footer className="prov" aria-label="응답 출처">
    <span>build {data.build_id}</span>
    <span title={data.bundle_sha256 ?? undefined}>{data.bundle_sha256 ? `묶음 ${data.bundle_sha256.slice(0, 12)}…` : "묶음 없음(로컬 파일로 띄운 서버)"}</span>
    <span>스냅샷 {data.snapshot_date}</span><span>모델 {data.model}</span>
    {question !== undefined && <span>질문 <span lang="en">{question}</span></span>}
  </footer>;
}
