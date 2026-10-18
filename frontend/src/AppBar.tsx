import type { HealthState } from "./search/types";
export function AppBar({ view, onView, onHome, health }: { view: string; onView: (view: "search" | "showroom" | "casebook") => void; onHome?: () => void; health: HealthState }) {
  return <header className="app-top">
    {onHome && <button type="button" className="app-home" aria-label="시작 화면으로" title="시작 화면으로" onClick={onHome}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12 4.5-5.5 5.5 5.5 5.5" /></svg></button>}
    <div className="app-brand"><span className="app-brand-mark" aria-hidden="true" /><div>결함 선례 찾기<small>NHTSA 공개 리콜 · Part 573 원문</small></div></div>
    <nav className="view-tabs" aria-label="화면 전환"><button aria-pressed={view === "search"} className={view === "search" ? "on" : ""} onClick={() => onView("search")}>선례 검색</button><button aria-pressed={view === "casebook"} className={view === "casebook" ? "on" : ""} onClick={() => onView("casebook")}>케이스북</button><button aria-pressed={view === "showroom"} className={view === "showroom" ? "on" : ""} onClick={() => onView("showroom")}>3D 쇼룸<span className="demo">(데모)</span></button></nav>
    <div className="spacer" />
    <div className="health" role="status" title={typeof health === "object" ? `build ${health.build_id} · 묶음 ${health.bundle_sha256 ?? "없음"}` : undefined}>
      <span className={`dot${typeof health === "string" ? " wait" : ""}`} aria-hidden="true" />
      {typeof health === "object" ? `카드 ${health.cards.toLocaleString("ko-KR")}장 · 스냅샷 ${health.snapshot_date}` : health === "loading" ? "서버 확인 중…" : "서버 판본을 받지 못했습니다"}
    </div>
  </header>;
}
