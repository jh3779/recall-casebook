/**
 * 검색 오류 안내. 호출 상한(429)이면 남은 초를 세는 동안 Retry를 막는다(DEC-057 ⑤ — 선례 검색 화면의 `RateLimited`를 옮겼다).
 * 알림(role="alert")에는 바뀌지 않는 문구만 둔다 — 1초마다 바뀌는 남은 초가 알림 안에 있으면 화면 낭독기가 매초 다시 읽는다.
 * 끝났다는 말은 처음부터 비어 있는 role="status" 영역에 글자만 채운다(이미 있는 live 영역의 변화만 읽힌다).
 */
export function SearchError({ message, limited, wait, onRetry }: { message: string; limited: boolean; wait: number; onRetry: () => void }) {
  const done = limited && wait === 0;
  return <div className="cb-error">
    <p role="alert">{message}</p>
    {wait > 0 && <p aria-hidden="true">{wait}s left</p>}
    <p role="status" className={done ? "cb-muted" : "sr-only"}>{done ? "You can search again." : ""}</p>
    <button type="button" className="cb-link" disabled={wait > 0} onClick={onRetry}>Retry{wait > 0 && <span aria-hidden="true"> ({wait})</span>}</button>
  </div>;
}
