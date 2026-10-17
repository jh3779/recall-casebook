import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { nextFocusIndex } from "./focusTrap";
import { OverlayBoundary, OverlayFailed } from "./OverlayBoundary";
import { DEFAULT_PANEL_SHIFT, panelOffset } from "../showroom/viewOffset";

it("3D 창 코드를 받지 못했을 때의 안내는 케이스북·메모가 그대로라고 알리고 닫기 버튼을 준다", () => {
  const html = renderToStaticMarkup(<OverlayFailed onClose={() => {}} />);
  expect(html).toContain('role="alertdialog"');
  expect(html).toContain("could not be loaded");
  expect(html).toContain("your notes are unchanged");
  expect(html).toContain("reload the page"); // 닫고 다시 열어도 같은 실패가 나므로 다시 시도하라고 안내하지 않는다
  expect(html).not.toContain("try again");
  expect(html).toMatch(/<button[^>]*>Close<\/button>/);
  expect(html).not.toMatch(/원인은|applies|verdict/i); // principle-ok: 안내 문구에 판정 표현이 없는지 검사
});
it("오류 경계는 로딩 실패(오류)를 받으면 안내 상태로 바뀌고, 아니면 자식을 그대로 그린다", () => {
  expect(OverlayBoundary.getDerivedStateFromError()).toEqual({ failed: true });
  expect(renderToStaticMarkup(<OverlayBoundary onClose={() => {}}><p>3D</p></OverlayBoundary>)).toBe("<p>3D</p>");
});
it("Tab·Shift+Tab은 창 안에서 순환하고 창 밖(−1)에서는 첫·마지막 요소로 들어온다", () => {
  expect(nextFocusIndex(3, 0, false)).toBe(1);
  expect(nextFocusIndex(3, 2, false)).toBe(0); // 마지막에서 Tab → 처음
  expect(nextFocusIndex(3, 0, true)).toBe(2); // 처음에서 Shift+Tab → 마지막
  expect(nextFocusIndex(3, 1, true)).toBe(0);
  expect(nextFocusIndex(3, -1, false)).toBe(0); // 초점이 창 밖에 있으면 안으로 끌어온다
  expect(nextFocusIndex(3, -1, true)).toBe(2);
  expect(nextFocusIndex(1, 0, false)).toBe(0); // 요소가 하나면 제자리
  expect(nextFocusIndex(0, -1, false)).toBe(-1); // 요소가 없으면 막지 않는다
});
it("차량 가로 보정: 기존 쇼룸은 넓은 화면에서 200px, 설명 패널이 다른 열인 3D 창은 0", () => {
  expect(DEFAULT_PANEL_SHIFT).toBe(200);
  expect(panelOffset(1440)).toBe(200);
  expect(panelOffset(900)).toBe(0); // 900px 이하는 보정하지 않는다(기존 동작)
  expect(panelOffset(1440, 0)).toBe(0);
  expect(panelOffset(1280, 0)).toBe(0);
});
