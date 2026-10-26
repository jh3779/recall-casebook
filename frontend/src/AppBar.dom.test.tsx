// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it } from "vitest";
import { AppBar } from "./AppBar";
import { followSystemTheme } from "./theme";

const user = () => userEvent.setup();
const root = document.documentElement;
const toggle = () => screen.getByRole("switch", { name: "어두운 화면" });
const bar = () => render(<AppBar view="casebook" onView={() => {}} health="loading" />);

let light = false;
const changeListeners = new Set<() => void>();
beforeEach(() => {
  light = false;
  changeListeners.clear();
  localStorage.clear();
  root.dataset.theme = "dark";
  Object.defineProperty(window, "matchMedia", {
    configurable: true, writable: true,
    value: (query: string) => ({ matches: query.includes("prefers-color-scheme: light") && light, media: query, addEventListener: (_: string, fn: () => void) => { changeListeners.add(fn); }, removeEventListener: () => {} }),
  });
});
afterEach(() => { cleanup(); Reflect.deleteProperty(window, "matchMedia"); localStorage.clear(); delete root.dataset.theme; root.classList.remove("theme-anim"); });

// 이 시험은 직접 고른 값이 생기기 전이어야 해서(theme.ts 모듈 안의 chosen) 이 파일에는 이 시험 하나만 둔다 — 다른 시험(AppBar.keyboard.dom.test.tsx)은 파일을 나눠, 실행 순서를 섞어도(--sequence.shuffle) 서로의 선택이 새지 않게 한다
it("고른 적이 없으면 기기 설정이 바뀔 때 스위치도 따라가고, 직접 고르면 그 뒤의 기기 설정 변화는 무시한다", async () => {
  const u = user();
  bar();
  followSystemTheme();
  expect(toggle().getAttribute("aria-checked")).toBe("true");

  light = true; // 기기가 밝은 화면으로 바뀐다
  act(() => { changeListeners.forEach((fn) => fn()); });
  expect(root.dataset.theme).toBe("light");
  expect(toggle().getAttribute("aria-checked")).toBe("false");
  expect(localStorage.getItem("theme")).toBeNull(); // 따라간 것은 저장하지 않는다

  await u.click(toggle()); // 사용자가 어두운 화면을 고른다
  expect(root.dataset.theme).toBe("dark");
  expect(localStorage.getItem("theme")).toBe("dark");
  light = false;
  act(() => { changeListeners.forEach((fn) => fn()); });
  light = true; // 기기 설정이 다시 밝게 바뀌어도
  act(() => { changeListeners.forEach((fn) => fn()); });
  expect(root.dataset.theme).toBe("dark");
  expect(toggle().getAttribute("aria-checked")).toBe("true");
});
