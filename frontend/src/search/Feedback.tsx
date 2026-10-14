import { useEffect, useState } from "react";
import { ApiError } from "../api";
export function Feedback({ loading, delayed, error, onRetry }: { loading?: boolean; delayed?: boolean; error?: ApiError; onRetry?: () => void }) {
  if (loading) return <div className="feedback" role="status" aria-live="polite">
    <span className="sr-only">선례를 찾고 있습니다</span>
    {delayed && <p className="wake">서버가 깨어나는 중일 수 있습니다. 첫 요청은 13~16초쯤 걸립니다.</p>}
    <div className="loading-split"><div className="skeleton" aria-hidden="true">{[0, 1, 2, 3].map((i) => <div className="sk" key={i} />)}</div></div>
  </div>;
  if (!error) return null;
  if (error.kind === "rate_limit") return <RateLimited error={error} onRetry={onRetry} />;
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

// 호출 상한(429, DEC-057): Retry-After 동안 [다시 시도]를 막고 남은 초를 보여 준다
function RateLimited({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  // 남은 초는 오류가 정한 마감(retryAt)에서 계산한다 — 다시 보낸 검색이 또 429면 새 오류의 마감으로 센다
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const left = Math.max(0, Math.ceil(((error.retryAt ?? now) - now) / 1000));
  return <div className="feedback"><div className="err" role="alert"><h2>호출이 너무 잦습니다 (429)</h2>
    <p>{left > 0 ? `같은 주소에서 1분에 보낼 수 있는 검색 수를 넘었습니다. ${left}초 뒤에 다시 시도할 수 있습니다.` : "이제 다시 시도할 수 있습니다."}</p>
    <div className="act"><button className="btn ghost small" disabled={left > 0} onClick={onRetry}>{left > 0 ? `다시 시도 (${left})` : "다시 시도"}</button></div>
  </div></div>;
}
