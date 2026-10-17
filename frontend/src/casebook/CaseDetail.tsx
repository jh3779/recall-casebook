import { Fragment } from "react";
import { fmtDate } from "../recalls";
import { highlight } from "../search/highlight";
import { hasCauseText, type Card, type SearchResponse } from "../search/types";
import { causeBadge, causeLine, langOf, productionItem, supplierView, type ReportSource } from "./sources";

function Report({ source }: { source: ReportSource & { text_basis?: string } }) {
  return <dl className="cb-src">
    <dt>Report file</dt><dd>{source.file}</dd>
    <dt>pdf_sha256</dt><dd className="cb-mono">{source.pdf_sha256}</dd>
    <dt>Submitted</dt><dd>{fmtDate(source.submission_date)}</dd>
    {source.text_basis !== undefined && <><dt>Text basis</dt><dd>{source.text_basis}</dd></>}
  </dl>;
}

/** 체크한 선례 한 건 — 원문은 글자 그대로, 말한 주체와 출처는 접지 않고 항상 보인다(서비스 원칙 2) */
export function CaseDetail({ card, response, onRemove, on3d }: { card: Card; response: SearchResponse; onRemove: () => void; on3d?: (button: HTMLElement) => void }) {
  const cause = card.cause;
  const supplier = supplierView(card);
  const production = productionItem(card);
  const badge = causeBadge(card);
  return <article className="cb-case" aria-label={`Recall ${card.campno}`}>
    <header className="cb-case-head">
      <div><h3 className="cb-id">{card.campno}</h3><span className="cb-who">{card.maker}{card.maker_group && card.maker_group !== card.maker ? ` (${card.maker_group})` : ""}</span><span className="cb-muted"> · received {fmtDate(card.received_date)}</span></div>
      <span className="cb-case-actions">{on3d && <button type="button" className="cb-link" onClick={(e) => on3d(e.currentTarget)} aria-label={`Show part category of ${card.campno} in 3D`}>Show in 3D</button>}<button type="button" className="cb-link" onClick={onRemove} aria-label={`Remove ${card.campno}`}>Remove</button></span>
    </header>
    <div className="cb-parts">{card.components.map((part, i) => <span key={i}>{part}</span>)}</div>

    <section className="cb-block">
      <h4>Defect · Consequence · Remedy <small>NHTSA recall summary, verbatim</small></h4>
      <p className="cb-byline">Said by <b lang={langOf(card.source.speaker)}>{card.source.speaker}</b> · {card.campno} · {card.source.dataset} snapshot {card.source.snapshot_date}</p>
      {([["Defect", card.defect], ["Consequence", card.consequence], ["Remedy", card.remedy]] as const).map(([label, text]) => <div key={label}><h5>{label}</h5><p className="cb-src-text" lang="en">{text}</p></div>)}
    </section>

    <section className={`cb-block cb-cause ${badge.level}`}>
      <h4>Cause <small>Part 573 report</small><span className={`cb-badge ${badge.level}`}>{badge.label}</span></h4>
      {hasCauseText(cause) && <>
        <p className="cb-byline">Said by <b lang={langOf(cause.speaker)}>{cause.speaker}</b> · campaign <span className="cb-mono">{cause.source.campaign}</span></p>
        <p className="cb-src-text" lang="en">{highlight(cause.text, cause.flags).map((part, i) => part.kind
          ? <span key={i} className={`cb-flag ${part.kind}`} title={part.kind === "unknown_expression" ? "Not-reported / under-investigation expression" : "Hedging expression"}>{part.text}</span>
          : <Fragment key={i}>{part.text}</Fragment>)}</p>
        {cause.flags.length > 0 && <p className="cb-muted">Underlines mark expressions found in the text; they are not a judgement.</p>}
        <Report source={cause.source} />
      </>}
      <p className="cb-status">{causeLine(card)}</p>
    </section>

    {(production || supplier) && <section className="cb-block">
      <h4>Items to check <small>evidence side by side; this tool does not say same or different</small></h4>
      {production && <div className="cb-check-item">
        <h5>Production period</h5>
        {production.evidence.map((e, i) => <p key={i} className="cb-src-text" lang="en">{e.text}</p>)}
        {production.omitted > 0 && <p className="cb-muted">{production.omitted} more block(s) are not shown — see the report.</p>}
        {production.unread > 0 && <p className="cb-muted">{production.unread} block(s) without a readable date are not shown — see the report.</p>}
        <Report source={production.source} />
      </div>}
      {supplier && <div className="cb-check-item">
        <h5>Supplier</h5>
        {supplier.names.map((name, i) => <p key={i} className="cb-src-text" lang="en">{name}</p>)}
        <Report source={supplier.source} />
      </div>}
    </section>}
    {card.investigations.length > 0 && <section className="cb-block">
      <h4>NHTSA defect investigation <small>{card.investigations.length} linked, summary verbatim</small></h4>
      {card.investigations.map((inv) => <div key={inv.action} className="cb-check-item">
        <h5><span className="cb-mono">{inv.action}</span> · <span lang="en">{inv.subject}</span></h5>
        <p className="cb-byline">Said by <b lang={langOf(inv.speaker)}>{inv.speaker}</b> · {inv.action} · opened {inv.open_date ? fmtDate(inv.open_date) : "no record"} · closed {inv.close_date ? fmtDate(inv.close_date) : "no record"}</p>
        <p className="cb-src-text" lang="en">{inv.summary}</p>
      </div>)}
    </section>}
    <p className="cb-muted cb-prov">build {response.build_id} · snapshot {response.snapshot_date}{response.bundle_sha256 ? ` · bundle ${response.bundle_sha256.slice(0, 12)}…` : ""}</p>
  </article>;
}
