import { fmtDate } from "../recalls";
import type { Investigation } from "./types";
export function InvestigationBlock({ investigations }: { investigations: Investigation[] }) {
  if (!investigations.length) return null;
  return <section className="block">
    <div className="block-title"><h3>NHTSA 결함 조사</h3><span className="inv-mark">{investigations.length}건 연결</span></div>
    {investigations.map((inv) => <div className="inv" key={inv.action}>
      <div className="item-top"><b className="mono">{inv.action}</b><b lang="en">{inv.subject}</b></div>
      <p className="note">개시 {fmtDate(inv.open_date)} / 종결 {inv.close_date ? fmtDate(inv.close_date) : "기록 없음"}</p>
      <p className="byline">말한 주체 <b>{inv.speaker}</b> · {inv.action}</p>
      <details className="more"><summary>조사 요약 원문</summary><p className="source-text" lang="en">{inv.summary}</p></details>
    </div>)}
  </section>;
}
