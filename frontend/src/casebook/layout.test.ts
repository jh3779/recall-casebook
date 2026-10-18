import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

// 케이스북 화면 맞춤(DEC-077) — 서버 렌더링 시험으로는 레이아웃을 못 재므로 CSS 구조와 색 값을 글자로 지킨다.
// 브라우저에서 잰 결과(1920~390px 8개 폭에서 가로 넘침 0)는 PR 본문에 있다.
const raw = readFileSync(new URL("./casebook.css", import.meta.url), "utf8");
const css = raw.replace(/\/\*[^]*?\*\//g, ""); // 주석은 규칙 읽기에서 뺀다
const rule = (selector: string) => {
  const found = [...css.matchAll(/(^|\n)([^{}\n@][^{}]*)\{([^{}]*)\}/g)].filter((m) => m[2].split(",").map((s) => s.trim()).includes(selector));
  return found.map((m) => m[3]).join(" ");
};

it("기존 색 팔레트(현대자동차 CI 색 8개와 글자·경고용 진한 값)가 그대로다", () => {
  const tokens = Object.fromEntries([...raw.slice(0, raw.indexOf("color: var(--cb-ink)")).matchAll(/--(cb-[a-z0-9-]+):\s*(#[0-9a-f]{3,6})/g)].map((m) => [m[1], m[2]]));
  expect(tokens).toEqual({
    "cb-blue": "#002c5f", "cb-active": "#00aad2", "cb-red": "#e63312", "cb-sand": "#e4dcd3", "cb-light": "#f6f3f2", "cb-sky": "#aacae6", "cb-gold": "#a36b4f",
    "cb-gold-text": "#8a563b", "cb-red-text": "#b32410", "cb-ink": "#000", "cb-ink-2": "#4d4d4d", "cb-ink-3": "#666",
  });
});
it("오른쪽 열은 안쪽 내용이 열 폭을 밀어내지 못한다 — 묶음의 긴 파일명·해시가 화면 밖으로 나가던 문제", () => {
  expect(rule(".cb-side")).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  for (const selector of [".cb-list", ".cb-side", ".cb-stack", ".cb-notes", ".cb-group", ".cb-groups", ".cb-grp"]) expect(rule(selector), selector).toMatch(/min-width:\s*0/);
  expect(rule(".cb-grp li")).toMatch(/overflow-wrap:\s*anywhere/);
});
it("넓은 화면에서 좌우 열은 스크롤하는 동안에도 보이고(고정 + 안쪽 스크롤), 좁은 화면(1100px 이하)은 한 줄로 쌓인다", () => {
  const sticky = css.match(/@media \(min-width: 1101px\) \{([^]*?)\n\}/)?.[1] ?? "";
  expect(sticky).toMatch(/\.cb-list, \.cb-side \{[^}]*position:\s*sticky/);
  expect(sticky).toMatch(/max-height:\s*calc\(100dvh/);
  expect(sticky).toMatch(/overflow-y:\s*auto/);
  expect(sticky).toMatch(/padding:\s*4px;\s*margin:\s*-4px/); // 안쪽 스크롤이 초점선(outline 3px)을 자르지 않게
  expect(css).toMatch(/@media \(max-width: 1100px\) \{\s*\.cb-grid \{ grid-template-columns: 1fr; \}/);
});
