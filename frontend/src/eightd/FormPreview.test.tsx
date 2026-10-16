import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { STEPS } from "./document";
import { FormPreview } from "./FormPreview";

it("양식 표 구조: 단계 8개와 제목·SUBJECT·머리글 띠가 있다", () => {
  const markup = renderToStaticMarkup(<FormPreview subject="airbag" values={{}} evidenceNote={null} />);
  expect(markup).toContain("CORRECTIVE ACTION REPORT");
  expect(markup).toContain("8-DISCIPLINE REPORT");
  for (const step of STEPS) expect(markup).toContain(`DISCIPLINE ${step.n}`);
  expect(markup).toMatch(/SUBJECT<\/th><td colSpan="3"[^>]*>airbag<\/td>/);
  expect(markup).not.toContain("선례 근거 데이터");
});
it("쓴 글은 해당 단계 칸에 그대로, 칸이 여럿인 단계는 칸 이름이 붙는다", () => {
  const markup = renderToStaticMarkup(<FormPreview subject="" values={{ d2: " 불량 6건 ", d4_root: "[타사 선례 X]\n(원인 원문) \"원문\"", d4_escape: "" }} evidenceNote={null} />);
  expect(markup).toContain("<p>불량 6건</p>");
  expect(markup).toContain("<b>Root Cause: </b>[타사 선례 X]");
  expect(markup).not.toContain("Escape Cause:");
  expect(markup).not.toContain("(미작성)");
});
it("선례를 넣었을 때의 근거 데이터 줄은 표 밖에 붙는다", () => {
  const markup = renderToStaticMarkup(<FormPreview subject="" values={{}} evidenceNote="※ 선례 근거 데이터: build x" />);
  expect(markup).toContain('<p class="fp-note">※ 선례 근거 데이터: build x</p>');
});
