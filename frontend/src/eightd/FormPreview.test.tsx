import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { D4_EVIDENCE_KEY, D4_EVIDENCE_TITLE, STEPS } from "./document";
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
it("적용하지 않은 단계는 써 둔 글이 있어도 칸을 비워 두고 표시한다", () => {
  const markup = renderToStaticMarkup(<FormPreview subject="" values={{ d2: "문제", d3: "잠정" }} evidenceNote={null} only={new Set([2])} />);
  expect(markup).toContain("<p>문제</p>");
  expect(markup).not.toContain("잠정");
  expect(markup.match(/fp-cell off/g)).toHaveLength(7);
});

it("선례 근거 부록은 D4 적용 때만 표 아래 별도 영역에 보이고 D4 칸 안에는 섞이지 않는다", () => {
  const values = { d4_root: "자사 원인", appendix: "[타사 선례 20V000001]\n(원인 원문) \"원문\"" };
  const on = renderToStaticMarkup(<FormPreview subject="" values={values} evidenceNote={null} />);
  expect(on).toContain("선례 근거 부록");
  expect(on).toContain("(원인 원문) &quot;원문&quot;");
  const table = on.slice(on.indexOf("<table class=\"fp-table fp-body\""), on.indexOf("</table>", on.indexOf("fp-body")));
  expect(table).toContain("자사 원인");
  expect(table).not.toContain("타사 선례");
  expect(renderToStaticMarkup(<FormPreview subject="" values={values} evidenceNote={null} only={new Set([2])} />)).not.toContain("선례 근거 부록");
});

it("D4 칸 미리보기에는 엔지니어 글 뒤에 타사 원문 제목과 인용이 붙고, 다른 단계 칸에는 선례 글이 없다(DEC-076)", () => {
  const evidence = "[타사 선례 20V000001 · 회사 · 접수 2020-01-05]\n(원인 원문) \"원문 한 줄\"";
  const markup = renderToStaticMarkup(<FormPreview subject="s" values={{ d2: "불량 사실", d4_root: "자사 원인", [D4_EVIDENCE_KEY]: evidence }} evidenceNote={null} />);
  const rows = markup.split("<tr>").filter((r) => r.includes("fp-label"));
  const d4 = rows.find((r) => r.includes("DISCIPLINE 4"))!;
  expect(d4).toContain("자사 원인");
  expect(d4).toContain(D4_EVIDENCE_TITLE);
  expect(d4.indexOf(D4_EVIDENCE_TITLE)).toBeGreaterThan(d4.indexOf("자사 원인"));
  expect(d4).toContain("원문 한 줄");
  for (const r of rows.filter((x) => !x.includes("DISCIPLINE 4"))) expect(r).not.toContain("타사 선례");
  expect(renderToStaticMarkup(<FormPreview subject="s" values={{ d4_root: "자사 원인" }} evidenceNote={null} />)).not.toContain(D4_EVIDENCE_TITLE);
});
