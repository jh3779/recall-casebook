// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readTheme } from "./theme";

// index.html의 인라인 스크립트는 첫 화면이 그려지기 전에 테마를 정한다(깜빡임 방지). theme.ts의 readTheme과 같은 규칙이어야 하므로
// 파일에서 스크립트를 꺼내 같은 조건에서 돌리고 두 결과를 견준다. (jsdom 환경에서는 file: URL로 읽을 수 없어 경로로 읽는다)
const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");
const inline = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
const runInline = () => new Function(inline!)();
const root = document.documentElement;

function deviceSetting(light: boolean | "unknown") {
  Object.defineProperty(window, "matchMedia", {
    configurable: true, writable: true,
    value: light === "unknown" ? undefined : (query: string) => ({ matches: query.includes("prefers-color-scheme: light") && light, media: query }),
  });
}
beforeEach(() => { localStorage.clear(); delete root.dataset.theme; });
afterEach(() => { vi.restoreAllMocks(); Reflect.deleteProperty(window, "matchMedia"); localStorage.clear(); delete root.dataset.theme; });

it("인라인 스크립트는 <head>에서 모듈 스크립트보다 먼저 실행된다", () => {
  expect(inline).toBeTruthy();
  expect(html.indexOf("<script>")).toBeGreaterThan(html.indexOf("<head>"));
  expect(html.indexOf("<script>")).toBeLessThan(html.indexOf("</head>"));
  expect(html.indexOf("<script>")).toBeLessThan(html.indexOf('<script type="module"'));
});

it.each([
  { name: "고른 밝은 화면이 기기의 어두운 설정보다 우선", stored: "light", device: false, expected: "light" },
  { name: "고른 어두운 화면이 기기의 밝은 설정보다 우선", stored: "dark", device: true, expected: "dark" },
  { name: "고른 적이 없으면 기기의 밝은 설정을 따른다", stored: null, device: true, expected: "light" },
  { name: "고른 적이 없고 기기가 어두우면 어둡다", stored: null, device: false, expected: "dark" },
  { name: "기기 설정을 알 수 없으면 어둡다", stored: null, device: "unknown", expected: "dark" },
  { name: "저장값이 light·dark가 아니면 기기 설정을 따른다", stored: "sepia", device: true, expected: "light" },
  { name: "저장소를 읽을 수 없으면 기기 설정으로 정한다", stored: "throw", device: true, expected: "light" },
  { name: "저장소도 기기 설정도 알 수 없으면 어둡다", stored: "throw", device: "unknown", expected: "dark" },
] as const)("$name — 인라인 스크립트와 readTheme이 같은 결과($expected)를 낸다", ({ stored, device, expected }) => {
  deviceSetting(device);
  if (stored === "throw") vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  else if (stored !== null) localStorage.setItem("theme", stored);

  runInline();
  expect(root.dataset.theme).toBe(expected);
  expect(readTheme()).toBe(expected);
});

it("기기 설정을 묻다가 예외가 나도 어두운 화면으로 시작한다", () => {
  Object.defineProperty(window, "matchMedia", { configurable: true, writable: true, value: () => { throw new Error("broken"); } });
  runInline();
  expect(root.dataset.theme).toBe("dark");
});
