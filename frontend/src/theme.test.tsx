import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { AppBar } from "./AppBar";
import { currentTheme, readTheme } from "./theme";

// 서버 렌더링 시험에는 브라우저가 없다 — 저장소를 못 읽으면 기본(어두운 화면)이어야 하고, 앱 바에는 전환 단추가 있다.
it("저장소를 읽을 수 없으면 어두운 화면이 기본이다", () => {
  expect(readTheme()).toBe("dark");
  expect(currentTheme()).toBe("dark");
});
it("앱 바에 밝은 화면으로 전환하는 슬라이드 스위치가 있다", () => {
  const html = renderToStaticMarkup(<AppBar view="casebook" onView={() => {}} health="loading" />);
  expect(html).toContain('role="switch"');
  expect(html).toContain('aria-checked="true"');
  expect(html).toContain("밝은 화면으로 전환");
});
