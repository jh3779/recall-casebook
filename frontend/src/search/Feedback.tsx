import { ApiError } from "../api";
export function Feedback({ loading, delayed, error, onRetry }: { loading?: boolean; delayed?: boolean; error?: ApiError; onRetry?: () => void }) {
  if (loading) return <div className="feedback" role="status" aria-live="polite">
    <span className="sr-only">선례를 찾고 있습니다</span>
    {delayed && <p className="wake">서버가 깨어나는 중일 수 있습니다. 첫 요청은 13~16초쯤 걸립니다.</p>}
    <div className="loading-split"><div className="skeleton" aria-hidden="true">{[0, 1, 2, 3].map((i) => <div className="sk" key={i} />)}</div></div>
  </div>;
  if (!error) return null;
  const title = {
    validation: "질문을 다시 확인해 주세요 (422)", network: "서버에 연결하지 못했습니다",
    timeout: "응답이 60초 안에 오지 않았습니다", shape: "응답 형식이 예상과 다릅니다", server: `서버 오류가 났습니다 (${error.status})`,
  }[error.kind];
  const message = error.kind === "timeout" ? "서버가 깨어나는 중일 수 있습니다. 한 번 더 보내 주세요."
    : error.kind === "shape" ? `화면이 아는 응답 모양과 달라 결과를 그리지 않았습니다. build_id ${error.buildId ?? "받지 못함"}` : error.message;
  return <div className="feedback"><div className="err" role="alert"><h2>{title}</h2><p>{message}</p>
    {["network", "timeout", "server"].includes(error.kind) && <div className="act"><button className="btn ghost small" onClick={onRetry}>다시 시도</button></div>}
  </div></div>;
}
