import { Fragment } from "react";
import { fmtDate } from "../recalls";
import { CauseBadge } from "./CauseBadge";
import { causeStatus } from "./causeStatus";
import { highlight } from "./highlight";
import { hasCauseText, type Cause } from "./types";

export function CauseBlock({ cause }: { cause: Cause }) {
  const status = causeStatus(cause);
  return <section className={`block cause ${status.level}`} aria-label="원인 (Part 573)">
    <div className="block-title"><h3>원인 (Part 573)</h3><CauseBadge cause={cause} /></div>
    {hasCauseText(cause) && <>
      <p className="byline">말한 주체 <b>{cause.speaker}</b> · 캠페인 <span className="mono">{cause.source.campaign}</span></p>
      {cause.flags.length > 0 && <div className="flag-list">
        <div className="item-bottom">{cause.flags.map((flag, i) => <span key={i} className={`flagtag ${flag.kind}`} title={flag.kind === "unknown_expression" ? "원인 미확인 표현" : "추정 표현"}><i aria-hidden="true" />{flag.label}</span>)}</div>
        <p className="flaghint">글에 이 표현이 있다는 표시이며 판단이 아닙니다</p>
      </div>}
      <p lang="en" className="source-text cause-text">{highlight(cause.text, cause.flags).map((part, i) => part.kind
        ? <span key={i} className={`flag ${part.kind}`} title={part.kind === "unknown_expression" ? "원인 미확인 표현" : "추정 표현"}>{part.text}</span>
        : <Fragment key={i}>{part.text}</Fragment>)}</p>
    </>}
    <p className="status-line">{status.message}</p>
    {hasCauseText(cause) && <details className="more">
      <summary>출처 자세히</summary>
      <dl className="kv">
        <dt>파일</dt><dd>{cause.source.file}</dd>
        <dt>pdf_sha256</dt><dd>{cause.source.pdf_sha256}</dd>
        <dt>제출일</dt><dd>{fmtDate(cause.source.submission_date)}</dd>
        <dt>글 정리 방식</dt><dd>{cause.source.text_basis}</dd>
      </dl>
    </details>}
  </section>;
}
