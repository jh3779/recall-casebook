import { afterEach, beforeEach, expect, it, vi } from "vitest";

// vitest에는 브라우저가 없다 — 테마 규칙(저장값 > 기기 설정 > 어두움, 전환 동작)이 쓰는 전역을 가짜로 세워 시험한다.
type Store = Record<string, string>;
type Env = { store: Store; light: boolean; reduced: boolean; viewTransition: boolean; legacyMedia: boolean; mediaThrows: boolean; changeListeners: Array<() => void>; windowHandlers: Record<string, Array<(e: unknown) => void>>; timers: Array<() => void>; calls: string[]; classes: Set<string>; dataset: Record<string, string> };

function setup(over: Partial<Env> = {}): Env {
  const env: Env = { store: {}, light: false, reduced: false, viewTransition: true, legacyMedia: false, mediaThrows: false, changeListeners: [], windowHandlers: {}, timers: [], calls: [], classes: new Set(), dataset: {}, ...over };
  const doc: Record<string, unknown> = { documentElement: { dataset: env.dataset, classList: { add: (c: string) => env.classes.add(c), remove: (c: string) => env.classes.delete(c) } } };
  if (env.viewTransition) doc.startViewTransition = (update: () => void) => { env.calls.push("vt"); update(); };
  vi.stubGlobal("document", doc);
  vi.stubGlobal("localStorage", { getItem: (k: string) => env.store[k] ?? null, setItem: (k: string, v: string) => { env.store[k] = v; } });
  // legacyMedia: Safari 14 미만처럼 addEventListener 없이 addListener만 있는 MediaQueryList
  const media = (q: string) => {
    if (env.mediaThrows) throw new Error("matchMedia blocked");
    const list = { matches: q.includes("reduced-motion") ? env.reduced : q.includes("prefers-color-scheme: light") ? env.light : false };
    const add = (fn: () => void) => { env.changeListeners.push(fn); };
    return env.legacyMedia ? { ...list, addListener: add } : { ...list, addEventListener: (_: string, fn: () => void) => add(fn) };
  };
  vi.stubGlobal("window", {
    matchMedia: media,
    addEventListener: (type: string, fn: (e: unknown) => void) => { (env.windowHandlers[type] ??= []).push(fn); },
    setTimeout: (fn: () => void) => { env.timers.push(fn); return 0; },
  });
  return env;
}
// 이번 방문의 직접 선택(`chosen`)은 모듈 안에 남으므로 시험마다 모듈을 새로 불러온다.
async function load() { vi.resetModules(); return await import("./theme"); }
beforeEach(() => { vi.unstubAllGlobals(); });
afterEach(() => { vi.unstubAllGlobals(); });

it("저장된 선택이 기기 설정보다 우선한다", async () => {
  const t = await load();
  setup({ store: { theme: "light" }, light: false });
  expect(t.readTheme()).toBe("light");
  setup({ store: { theme: "dark" }, light: true });
  expect(t.readTheme()).toBe("dark");
});
it("저장된 값이 없거나 잘못됐으면 기기 설정을 따른다", async () => {
  const t = await load();
  setup({ store: {}, light: true });
  expect(t.readTheme()).toBe("light");
  setup({ store: { theme: "sepia" }, light: false });
  expect(t.readTheme()).toBe("dark");
});
it("저장소를 읽을 수 없어도 기기 설정으로 정한다", async () => {
  const t = await load();
  setup({ light: true });
  vi.stubGlobal("localStorage", { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } });
  expect(t.readTheme()).toBe("light");
  expect(() => t.saveTheme("dark")).not.toThrow();
});
it("고르면 저장하고 화면 전환(View Transitions)으로 적용한다", async () => {
  const t = await load();
  const env = setup();
  t.saveTheme("light");
  expect(env.store.theme).toBe("light");
  expect(env.dataset.theme).toBe("light");
  expect(env.calls).toEqual(["vt"]);
  expect(t.currentTheme()).toBe("light");
});
it("화면 전환을 지원하지 않으면 색 전환 표시를 잠깐 붙였다 뗀다", async () => {
  const t = await load();
  const env = setup({ viewTransition: false });
  t.saveTheme("light");
  expect(env.dataset.theme).toBe("light");
  expect(env.classes.has("theme-anim")).toBe(true);
  env.timers.forEach((fn) => fn());
  expect(env.classes.has("theme-anim")).toBe(false);
});
it("움직임 줄이기 설정이면 전환 효과 없이 곧바로 적용한다", async () => {
  const t = await load();
  const env = setup({ reduced: true });
  t.saveTheme("light");
  expect(env.dataset.theme).toBe("light");
  expect(env.calls).toEqual([]);
  expect(env.classes.size).toBe(0);
});
it("고른 적이 없으면 기기 설정이 바뀔 때 따라가고, 고른 값이 있으면 그대로 둔다", async () => {
  const t = await load();
  const env = setup({ light: false });
  const seen: string[] = [];
  const off = t.subscribeTheme((t) => seen.push(t));
  t.followSystemTheme();
  env.light = true;
  env.changeListeners.forEach((fn) => fn());
  expect(env.dataset.theme).toBe("light");
  expect(seen).toEqual(["light"]);
  env.store.theme = "dark";
  env.light = false;
  env.changeListeners.forEach((fn) => fn());
  expect(env.dataset.theme).toBe("light");
  expect(seen).toEqual(["light"]);
  off();
});
it("저장이 막혀도 이번 방문에 직접 고른 값은 기기 설정이 바뀌어도 지킨다", async () => {
  const t = await load();
  const env = setup({ light: false }); // 기기는 어둡다
  vi.stubGlobal("localStorage", { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } });
  t.followSystemTheme();
  t.saveTheme("light");
  expect(env.dataset.theme).toBe("light");
  env.light = true; // 기기 설정이 실제로 밝게 바뀌었다가
  env.changeListeners.forEach((fn) => fn());
  env.light = false; // 다시 어둡게 바뀌어도(저장소는 막혀 있다)
  env.changeListeners.forEach((fn) => fn());
  expect(env.dataset.theme).toBe("light"); // 직접 고른 값이 기기 설정을 이긴다
  expect(t.readTheme()).toBe("light");
});
it("MediaQueryList에 addEventListener가 없는 옛 브라우저(Safari 14 미만)는 addListener로 기기 설정을 따라간다", async () => {
  const t = await load();
  const env = setup({ light: false, legacyMedia: true });
  expect(() => t.followSystemTheme()).not.toThrow();
  expect(env.changeListeners).toHaveLength(1);
  env.light = true;
  env.changeListeners[0]();
  expect(env.dataset.theme).toBe("light");
});
it("matchMedia가 예외를 던져도 어두운 화면으로 시작하고 렌더가 멈추지 않는다(첫 화면 스크립트와 같은 규칙)", async () => {
  const t = await load();
  setup({ mediaThrows: true });
  expect(t.systemTheme()).toBe("dark");
  expect(t.readTheme()).toBe("dark");
  expect(() => t.followSystemTheme()).not.toThrow();
});
it("matchMedia가 예외를 던지는 환경에서도 스위치를 누르면 적용·저장·알림이 된다(움직임 설정 조회도 막혀 있다)", async () => {
  const t = await load();
  const env = setup({ mediaThrows: true });
  const seen: string[] = [];
  t.subscribeTheme((theme) => seen.push(theme));
  expect(() => t.saveTheme("light")).not.toThrow();
  expect(env.dataset.theme).toBe("light");
  expect(env.store.theme).toBe("light");
  expect(seen).toEqual(["light"]);
  // 움직임 설정을 읽지 못하면 애니메이션 없이 바로 적용한다 — 화면 전환도 색 전환 클래스도 쓰지 않는다
  expect(env.calls).not.toContain("vt");
  expect(env.classes.has("theme-anim")).toBe(false);
  expect(env.timers).toHaveLength(0);
});
it("고르면 구독자에게 알린다 — 앱 바가 여럿이어도 스위치가 함께 바뀐다", async () => {
  const t = await load();
  setup();
  const seen: string[] = [];
  const off = t.subscribeTheme((theme) => seen.push(theme));
  t.saveTheme("light");
  t.saveTheme("dark");
  off();
  t.saveTheme("light");
  expect(seen).toEqual(["light", "dark"]);
});
it("다른 탭이 고른 값(storage 이벤트)을 따라가고 직접 고른 값으로 지키며, 다른 키·잘못된 값은 무시한다", async () => {
  const t = await load();
  const env = setup({ light: false });
  const seen: string[] = [];
  t.subscribeTheme((theme) => seen.push(theme));
  t.followSystemTheme();
  const onStorage = (e: { key: string | null; newValue: string | null }) => env.windowHandlers.storage.forEach((fn) => fn(e));
  onStorage({ key: "other", newValue: "light" });
  onStorage({ key: "theme", newValue: "sepia" });
  onStorage({ key: "theme", newValue: null });
  expect(env.dataset.theme).toBeUndefined();
  expect(seen).toEqual([]);

  onStorage({ key: "theme", newValue: "light" });
  expect(env.dataset.theme).toBe("light");
  expect(seen).toEqual(["light"]);
  env.light = false; // 기기 설정이 바뀌어도 다른 탭에서 고른 값이 남는다
  vi.stubGlobal("localStorage", { getItem: () => { throw new Error("blocked"); }, setItem: () => {} });
  env.changeListeners.forEach((fn) => fn());
  expect(env.dataset.theme).toBe("light");
});
it("matchMedia가 없어도 어두운 화면으로 시작하고 오류가 나지 않는다", async () => {
  const t = await load();
  vi.stubGlobal("window", {});
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {} });
  expect(t.readTheme()).toBe("dark");
  expect(() => t.followSystemTheme()).not.toThrow();
  vi.stubGlobal("document", { documentElement: { dataset: {} } });
  t.applyTheme("light");
  expect(t.currentTheme()).toBe("light");
});
