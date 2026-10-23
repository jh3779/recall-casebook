// 화면 테마 — 기본은 어두운 화면(랜딩과 같음), 밝은 화면은 기존 흰 화면. 선택은 이 브라우저에만 저장한다.
export type Theme = "dark" | "light";
const KEY = "theme";

let chosen: Theme | null = null; // 이번 방문에 직접 고른 값 — 저장소가 막혀 저장이 실패해도 기기 설정이 이 선택을 덮지 않게 한다
function saved(): Theme | null {
  try { const v = localStorage.getItem(KEY); if (v === "light" || v === "dark") return v; } catch { /* 읽을 수 없으면 아래 메모리 값 */ }
  return chosen;
}
// 사용자가 고른 적이 없으면 기기·브라우저의 화면 모드 설정을 따른다(알 수 없으면 랜딩과 같은 어두운 화면).
export function systemTheme(): Theme {
  try { // index.html의 첫 화면 스크립트와 같게 — matchMedia가 예외를 던지면 어두운 화면
    return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
  } catch { return "dark"; }
}
export function readTheme(): Theme {
  return saved() ?? systemTheme();
}
// 고른 적이 없을 때 기기 설정이 바뀌면 따라간다. 고른 값이 있으면 그대로 둔다. 다른 탭이 고른 값(storage 이벤트)도 따라간다.
export function followSystemTheme() {
  let query: MediaQueryList | undefined;
  try { query = window.matchMedia?.("(prefers-color-scheme: light)"); } catch { /* 읽을 수 없으면 기기 설정은 따라가지 않는다 */ }
  const onSystemChange = () => { if (!saved()) setTheme(systemTheme()); };
  if (query?.addEventListener) query.addEventListener("change", onSystemChange);
  else query?.addListener?.(onSystemChange); // Safari 14 미만은 addEventListener가 없다
  window.addEventListener?.("storage", (e: StorageEvent) => {
    if (e.key !== KEY || (e.newValue !== "light" && e.newValue !== "dark")) return;
    chosen = e.newValue; // 다른 탭의 선택도 직접 고른 값이다 — 이후 기기 설정이 덮지 않게
    setTheme(e.newValue);
  });
}
const listeners = new Set<(theme: Theme) => void>();
export function subscribeTheme(listener: (theme: Theme) => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
function setTheme(theme: Theme) { switchWithMotion(theme); listeners.forEach((l) => l(theme)); }
export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}
export function currentTheme(): Theme {
  return typeof document !== "undefined" && document.documentElement.dataset.theme === "light" ? "light" : "dark";
}
// 전환하는 동안만 화면이 부드럽게 바뀌게 한다(처음 열 때는 번쩍이지 않게 평소에는 붙이지 않는다). 움직임을 줄이는 설정이면 곧바로 바꾼다.
// 글자까지 한꺼번에 매끄럽게 섞이도록 브라우저의 화면 전환(View Transitions)을 쓰고, 지원하지 않으면 색 전환(transition)으로 대신한다.
function switchWithMotion(theme: Theme) {
  const root = document.documentElement;
  let reduce = false;
  try { reduce = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches; } catch { reduce = true; /* 움직임 설정을 읽지 못하면 움직임 없이 바로 적용한다 */ }
  if (reduce) { applyTheme(theme); return; }
  const start = (document as Document & { startViewTransition?: (update: () => void) => unknown }).startViewTransition;
  if (start) { start.call(document, () => applyTheme(theme)); return; }
  root.classList.add("theme-anim");
  applyTheme(theme);
  window.setTimeout(() => root.classList.remove("theme-anim"), 500);
}
export function saveTheme(theme: Theme) {
  chosen = theme;
  switchWithMotion(theme);
  try { localStorage.setItem(KEY, theme); } catch { /* 저장이 막혀도 이번 방문에는 적용된다 */ }
  listeners.forEach((l) => l(theme)); // 앱 바가 둘 이상이어도 스위치가 함께 바뀌게
}
