// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { AppBar } from "./AppBar";

// DOM 시험 환경 스모크 — 실제 DOM에 그리고 사용자 이벤트(클릭)로 상태가 바뀌는지 본다.
it("화면 모드 스위치를 누르면 aria-checked·문서 테마·저장값이 함께 바뀐다", async () => {
  const user = userEvent.setup();
  render(<AppBar view="casebook" onView={() => {}} health="loading" />);
  const toggle = screen.getByRole("switch", { name: "어두운 화면" });
  expect(toggle.getAttribute("aria-checked")).toBe("true"); // 기본은 어두운 화면

  await user.click(toggle);
  expect(toggle.getAttribute("aria-checked")).toBe("false");
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(localStorage.getItem("theme")).toBe("light");

  await user.click(toggle);
  expect(toggle.getAttribute("aria-checked")).toBe("true");
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem("theme")).toBe("dark");
});
