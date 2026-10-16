import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { ALL_STEPS } from "./document";
import type { Inspection } from "./docxPatch";
import { FileMap } from "./FileMap";

const view: Inspection = {
  cells: [
    { table: 1, row: 1, col: 2, label: "Supplier Problem Report No.", guess: 2 },
    { table: 1, row: 2, col: 2, label: "Problem Description", guess: 2 },
    { table: 1, row: 3, col: 2, label: "Root Cause", guess: 4 },
    { table: 1, row: 4, col: 2, label: "Part Name", guess: null },
  ],
  matches: { 2: [{ table: 1, row: 1, col: 2 }, { table: 1, row: 2, col: 2 }], 4: [{ table: 1, row: 3, col: 2 }] },
  subject: false,
};
const render = (choice = {}, applied: ReadonlySet<number> = ALL_STEPS) => renderToStaticMarkup(<FileMap view={view} choice={choice} applied={applied} onChoose={() => {}} />);

it("라벨이 맞은 칸이 하나면 자동 인식으로 보이고 그 칸의 라벨을 함께 보여 준다", () => {
  expect(render()).toContain("자동 인식 ✓ 표 1 · 3행 · 2열 — “Root Cause”");
});
it("후보가 여럿이면 짐작하지 않고 고르기 전에는 넣지 않는다고 알린다", () => {
  const markup = render();
  expect(markup).toContain("후보 2곳");
  expect(markup).toContain("넣지 않습니다");
});
it("못 찾은 단계도 문서의 아무 칸이나 고를 수 있고, 라벨이 맞은 칸에는 표시가 붙으며 먼저 나온다", () => {
  const markup = render();
  expect(markup).toContain("찾지 못함");
  expect(markup).toContain("“Part Name”"); // 라벨이 단계와 무관한 칸도 후보
  const d2 = markup.split("D2 칸 고르기")[1].split("</select>")[0];
  expect(d2).toContain("라벨이 맞음");
  expect(d2.indexOf("Problem Description")).toBeLessThan(d2.indexOf("Part Name"));
});
it("내가 고른 칸은 자동 인식보다 우선해 보인다", () => {
  const markup = render({ 2: { table: 1, row: 2, col: 2 } });
  expect(markup).toContain("내가 고른 칸 ✓ 표 1 · 2행 · 2열 — “Problem Description”");
  expect(markup).not.toContain("후보 2곳");
  expect(markup).toMatch(/<option value="1\.2\.2" selected="">/);
});
it("적용하지 않는 단계는 칸 고르기를 보이지 않는다", () => {
  const markup = render({}, new Set([4]));
  expect(markup).toContain("(적용 안 함)");
  expect(markup).not.toContain("D2 칸 고르기");
  expect(markup).toContain("D4 칸 고르기");
});
it("다른 단계가 이미 쓰는 칸은 고르지 못하게 막는다(두 단계가 한 칸에 겹쳐 파일이 깨지지 않게)", () => {
  const markup = render({ 2: { table: 1, row: 2, col: 2 } });
  const d4 = markup.split("D4 칸 고르기")[1].split("</select>")[0];
  expect(d4).toMatch(/<option value="1\.2\.2" disabled="">[^<]*다른 단계가 사용 중/); // D2가 고른 칸
  const d2 = markup.split("D2 칸 고르기")[1].split("</select>")[0];
  expect(d2).toMatch(/<option value="1\.3\.2" disabled="">[^<]*다른 단계가 사용 중/); // D4가 라벨로 자동 정해진 칸
});
it("적용하지 않는 단계가 쥔 칸은 다른 단계의 선택지를 막지 않는다", () => {
  const markup = render({ 2: { table: 1, row: 2, col: 2 } }, new Set([4])); // D2는 적용 안 함
  const d4 = markup.split("D4 칸 고르기")[1].split("</select>")[0];
  expect(d4).not.toMatch(/value="1\.2\.2" disabled/);
});
