import { afterEach, beforeEach, expect, it, vi } from "vitest";

// vitest에는 브라우저가 없다 — 테마 규칙(저장값 > 기기 설정 > 어두움, 전환 동작)이 쓰는 전역을 가짜로 세워 시험한다.
type Store = Record<string, string>;
type Env = { store: Store; light: boolean; reduced: boolean; viewTransition: boolean; changeListeners: Array<() => void>; timers: Array<() => void>; calls: string[]; classes: Set<string>; dataset: Record<string, string> };

function setup(over: Partial<Env> = {}): Env {
  const env: Env = { store: {}, light: false, reduced: false, viewTransition: true, changeListeners: [], timers: [], calls: [], classes: new Set(), dataset: {}, ...over };
  const doc: Record<string, unknown> = { documentElement: { dataset: env.dataset, classList: { add: (c: string) => env.classes.add(c), remove: (c: string) => env.classes.delete(c) } } };
  if (env.viewTransition) doc.startViewTransition = (update: () => void) => { env.calls.push("vt"); update(); };
  vi.stubGlobal("document", doc);
  vi.stubGlobal("localStorage", { getItem: (k: string) => env.store[k] ?? null, setItem: (k: string, v: string) => { env.store[k] = v; } });
  vi.stubGlobal("window", {
    matchMedia: (q: string) => ({ matches: q.includes("reduced-motion") ? env.reduced : q.includes("prefers-color-scheme: light") ? env.light : false, addEventListener: (_: string, fn: () => void) => { env.changeListeners.push(fn); } }),
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
  const env = setup({ light: false });
  vi.stubGlobal("localStorage", { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } });
  t.followSystemTheme();
  t.saveTheme("light");
  expect(env.dataset.theme).toBe("light");
  env.light = false; // 기기 설정이 어둡게 바뀌어도
  env.changeListeners.forEach((fn) => fn());
  expect(env.dataset.theme).toBe("light");
  expect(t.readTheme()).toBe("light");
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
