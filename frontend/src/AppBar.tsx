import { useEffect, useRef, useState } from "react";
import type { HealthState } from "./search/types";
import { currentTheme, saveTheme, subscribeTheme, type Theme } from "./theme";
export function AppBar({ view, onView, onHome, health }: { view: string; onView: (view: "showroom" | "casebook") => void; onHome?: () => void; health: HealthState }) {
  const bar = useRef<HTMLElement>(null);
  useEffect(() => { // 좁은 화면에서 앱 바가 여러 줄로 늘어나도 아래 화면이 앱 바 뒤로 가려지지 않게 실제 높이를 알린다
    const el = bar.current;
    if (!el) return;
    const root = document.documentElement;
    const update = () => root.style.setProperty("--app-bar-height", `${Math.ceil(el.getBoundingClientRect().height)}px`);
    update();
    if (typeof ResizeObserver === "undefined") return () => { root.style.removeProperty("--app-bar-height"); };
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => { observer.disconnect(); root.style.removeProperty("--app-bar-height"); };
  }, []);
  return <header className="app-top" ref={bar}>
    {onHome && <button type="button" className="app-home" aria-label="시작 화면으로" title="시작 화면으로" onClick={onHome}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12 4.5-5.5 5.5 5.5 5.5" /></svg></button>}
    <div className="app-brand"><span className="app-brand-mark" aria-hidden="true" /><div>결함 선례 찾기<small>NHTSA 공개 리콜 · Part 573 원문</small></div></div>
    <nav className="view-tabs" data-view={view} aria-label="화면 전환"><button aria-pressed={view === "casebook"} className={view === "casebook" ? "on" : ""} onClick={() => onView("casebook")}>케이스북</button><button aria-pressed={view === "showroom"} className={view === "showroom" ? "on" : ""} onClick={() => onView("showroom")}>3D 쇼룸<span className="demo">(데모)</span></button></nav>
    <div className="spacer" />
    <ThemeToggle />
    <div className="health" role="status" title={typeof health === "object" ? `build ${health.build_id} · 묶음 ${health.bundle_sha256 ?? "없음"}` : undefined}>
      <span className={`dot${typeof health === "string" ? " wait" : ""}`} aria-hidden="true" />
      {typeof health === "object" ? `카드 ${health.cards.toLocaleString("ko-KR")}장 · 스냅샷 ${health.snapshot_date}` : health === "loading" ? "서버 확인 중…" : "서버 판본을 받지 못했습니다"}
    </div>
  </header>;
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  useEffect(() => subscribeTheme(setTheme), []); // 기기 설정을 따라 바뀔 때도 스위치가 맞게
  const dark = theme === "dark";
  return <button type="button" role="switch" aria-checked={dark} aria-label="어두운 화면" title={dark ? "밝은 화면으로 전환" : "어두운 화면으로 전환"} className="theme-switch" onClick={() => { const next: Theme = dark ? "light" : "dark"; saveTheme(next); setTheme(next); }}>
    <span className="ts-thumb" aria-hidden="true">
      <svg className="ts-sun" viewBox="0 0 20 20"><circle cx="10" cy="10" r="3.4" /><path d="M10 2.4v2M10 15.6v2M2.4 10h2M15.6 10h2M4.6 4.6l1.4 1.4M14 14l1.4 1.4M4.6 15.4 6 14M14 6l1.4-1.4" /></svg>
      <svg className="ts-moon" viewBox="0 0 20 20"><path d="M16.4 11.9A6.7 6.7 0 0 1 8.1 3.6a6.7 6.7 0 1 0 8.3 8.3Z" /></svg>
    </span>
  </button>;
}
