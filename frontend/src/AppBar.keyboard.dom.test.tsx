// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it } from "vitest";
import { AppBar } from "./AppBar";

// AppBar.dom.test.tsx의 "기기 설정을 따라가는" 시험은 theme.ts의 모듈 상태(직접 고른 값)가 비어 있어야 해서 파일을 나눴다 —
// 이 파일의 시험은 스위치를 눌러 직접 고른 값을 만든다.
const user = () => userEvent.setup();
const root = document.documentElement;
const toggle = () => screen.getByRole("switch", { name: "어두운 화면" });
const bar = () => render(<AppBar view="casebook" onView={() => {}} health="loading" />);

beforeEach(() => {
  localStorage.clear();
  root.dataset.theme = "dark";
});
afterEach(() => { cleanup(); localStorage.clear(); delete root.dataset.theme; root.classList.remove("theme-anim"); });

it("스위치는 키보드(Enter·Space)로도 바뀌고 제목이 다음 동작을 알린다", async () => {
  const u = user();
  bar();
  toggle().focus();
  expect(toggle().title).toBe("밝은 화면으로 전환");
  await u.keyboard("{Enter}");
  expect(toggle().getAttribute("aria-checked")).toBe("false");
  expect(toggle().title).toBe("어두운 화면으로 전환");
  expect(root.dataset.theme).toBe("light");
  await u.keyboard(" ");
  expect(toggle().getAttribute("aria-checked")).toBe("true");
  expect(toggle().title).toBe("밝은 화면으로 전환");
  expect(localStorage.getItem("theme")).toBe("dark");
});
