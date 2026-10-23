// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLayoutEffect } from "react";
import { afterEach, beforeEach, expect, it } from "vitest";
import { AppBar } from "./AppBar";
import { followSystemTheme } from "./theme";

// 이슈 #173 후속: 스위치가 여럿이어도 함께 바뀌고, 다른 탭의 선택을 따라가며, 앱 바 높이는 그리기 전에 알린다.
// theme 모듈은 `chosen`을 안에 들고 있으므로(저장소가 막혀도 지키려는 값) 시험마다 저장소·문서 테마를 비운다.
beforeEach(() => { localStorage.clear(); delete document.documentElement.dataset.theme; });
afterEach(() => { cleanup(); document.documentElement.style.removeProperty("--app-bar-height"); });

const bar = () => <AppBar view="casebook" onView={() => {}} health="loading" />;

it("앱 바가 둘이어도 한쪽 스위치를 누르면 다른 쪽 스위치도 함께 바뀐다 (saveTheme이 구독자에게 알린다)", async () => {
  const user = userEvent.setup();
  render(<>{bar()}{bar()}</>);
  const [first, second] = screen.getAllByRole("switch", { name: "어두운 화면" });
  expect(first.getAttribute("aria-checked")).toBe("true");
  expect(second.getAttribute("aria-checked")).toBe("true");

  await user.click(first);
  expect(first.getAttribute("aria-checked")).toBe("false");
  expect(second.getAttribute("aria-checked")).toBe("false");
  expect(document.documentElement.dataset.theme).toBe("light");
});

it("다른 탭이 고른 값(storage 이벤트)을 따라 문서 테마와 스위치가 바뀐다", () => {
  followSystemTheme();
  render(bar());
  const toggle = screen.getByRole("switch", { name: "어두운 화면" });
  act(() => { window.dispatchEvent(new StorageEvent("storage", { key: "theme", newValue: "light" })); });
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(toggle.getAttribute("aria-checked")).toBe("false");
  act(() => { window.dispatchEvent(new StorageEvent("storage", { key: "unrelated", newValue: "dark" })); });
  expect(toggle.getAttribute("aria-checked")).toBe("false"); // 다른 키는 무시한다
  act(() => { window.dispatchEvent(new StorageEvent("storage", { key: "theme", newValue: "dark" })); });
  expect(toggle.getAttribute("aria-checked")).toBe("true");
});

it("앱 바 높이는 첫 화면이 그려지기 전(같은 커밋의 레이아웃 효과)에 이미 알려져 있다", () => {
  let seen: string | null = null;
  function Probe() { // 앱 바 다음 형제의 레이아웃 효과 — 앱 바가 레이아웃 효과로 높이를 알렸다면 이 시점에 값이 있다
    useLayoutEffect(() => { seen = document.documentElement.style.getPropertyValue("--app-bar-height"); }, []);
    return null;
  }
  render(<>{bar()}<Probe /></>);
  expect(seen).toMatch(/^\d+px$/);
});
