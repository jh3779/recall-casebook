import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";
import { D4_QUESTIONS, QUESTION_UNKNOWN, d4Questions } from "./questions";

const python = readFileSync(fileURLToPath(new URL("../../../server/rag/draft.py", import.meta.url)), "utf8");
const strings = (block: string) => [...block.matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => JSON.parse(`"${m[1]}"`) as string);

it("D4 확인 질문 문장은 서버 `server/rag/draft.py`의 고정 문장과 글자까지 같다(한 곳에서 나온 문장만 보인다)", () => {
  const block = /"d4": \[([\s\S]*?)\n    \],/.exec(python)?.[1];
  expect(block).toBeDefined();
  expect([...D4_QUESTIONS]).toEqual(strings(block!));
  const unknown = /QUESTION_UNKNOWN = "((?:[^"\\]|\\.)*)"/.exec(python)?.[1];
  expect(unknown).toBeDefined();
  expect(QUESTION_UNKNOWN).toBe(JSON.parse(`"${unknown}"`));
});
it("서버 `questions_for`와 같은 규칙: 미보고·조사 중 표현의 원인 글이 있을 때만 확인 문장이 더해진다", () => {
  const filled = { cause: { status: "filled" as const } };
  const unknown = { cause: { status: "stated_unknown" as const } };
  expect(d4Questions([])).toEqual([...D4_QUESTIONS]);
  expect(d4Questions([filled] as never)).toEqual([...D4_QUESTIONS]);
  expect(d4Questions([filled, unknown] as never)).toEqual([...D4_QUESTIONS, QUESTION_UNKNOWN]);
  expect(python).toMatch(/cause_status"\) == "stated_unknown"/); // 서버 규칙의 조건이 그대로인지(규칙이 바뀌면 이 시험이 알린다)
});
it("확인 질문은 선례의 원인을 우리 건의 원인으로 단정하지 않는다", () => {
  for (const q of D4_QUESTIONS) expect(q).not.toMatch(/원인은\s.{0,30}입니다/);
  expect(D4_QUESTIONS[0]).toContain("우리 건의 원인이 아닙니다");
});
