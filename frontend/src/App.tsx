import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { health } from "./api";
import { AppBar } from "./AppBar";
import CasebookView from "./casebook/CasebookView";
import EightdView from "./eightd/EightdView";
import { nextEightdInput, type EightdInput } from "./eightd/session";
import Landing from "./landing/Landing";
import SearchView from "./search/SearchView";
import type { HealthState } from "./search/types";
import { hashOfView, viewOfHash, type View } from "./views";

const ShowroomView = lazy(() => import("./showroom/ShowroomView"));
const currentView = (): View => viewOfHash(location.hash);

class ShowroomBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="showroom-fallback" role="alert"><p>3D 쇼룸을 불러오지 못했습니다.</p><button onClick={() => { location.hash = "search"; }}>검색 화면으로</button></div> : this.props.children;
  }
}
export default function App() {
  const [view, setView] = useState<View>(currentView);
  const [eightd, setEightd] = useState<EightdInput>({ cards: [], response: null, fresh: 0 });
  const [fromApp, setFromApp] = useState(false);
  const [server, setServer] = useState<HealthState>("loading");
  const [draft, setDraft] = useState<{ question: string; key: number } | null>(null);
  useEffect(() => {
    const changed = () => setView(currentView());
    addEventListener("hashchange", changed);
    return () => removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let alive = true;
    const timeout = setTimeout(() => controller.abort(), 60_000);
    health(controller.signal).then((data) => { if (alive) setServer(data); }).catch(() => { if (alive) setServer("error"); }).finally(() => clearTimeout(timeout));
    return () => { alive = false; clearTimeout(timeout); controller.abort(); };
  }, []);
  function navigate(next: View) { setFromApp(true); setView(next); location.hash = hashOfView(next); }
  return <div className="app-shell">
    {view === "landing" ? <Landing focusEnter={fromApp} onEnter={() => navigate("casebook")} /> : <AppBar view={view} onView={navigate} onHome={() => navigate("landing")} health={server} />}
    <div hidden={view !== "search"}><SearchView key={draft?.key ?? 0} health={server} draft={draft} onShowroom={() => navigate("showroom")} onWrite8d={(cards, response, fresh) => { setEightd((prev) => nextEightdInput(prev, cards, response, fresh)); navigate("8d"); }} /></div>
    <div hidden={view !== "casebook"}><CasebookView health={server} /></div>
    <div hidden={view !== "8d"}><EightdView fresh={eightd.fresh} freshQuestion={eightd.freshQuestion} cards={eightd.cards} response={eightd.response} onBack={() => navigate("search")} /></div>
    {view === "showroom" && <ShowroomBoundary><Suspense fallback={<div className="showroom-fallback" role="status">3D 쇼룸 불러오는 중…</div>}><ShowroomView onSearch={(question) => { setDraft((old) => ({ question, key: (old?.key ?? 0) + 1 })); navigate("search"); }} /></Suspense></ShowroomBoundary>}
  </div>;
}
