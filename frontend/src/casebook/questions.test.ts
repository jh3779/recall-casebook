import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";
import { D4_QUESTIONS, MAX_PICK, QUESTION_POOL, QUESTION_UNKNOWN, d4Questions, pickedFor, pickedIdsOf, pickedQuestions, toggleChecked } from "./questions";

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

const poolBlock = /QUESTION_POOL = \{([\s\S]*?)\n\}/.exec(python)?.[1];
const serverPool = Object.fromEntries([...(poolBlock ?? "").matchAll(/"(P\d+)": "((?:[^"\\]|\\.)*)"/g)].map((m) => [m[1], JSON.parse(`"${m[2]}"`) as string]));

it("확인 질문 풀 10개는 서버 `QUESTION_POOL`과 번호·문장이 글자까지 같다(LLM은 번호만 고르고 문장은 화면과 서버의 고정 풀에서 나온다)", () => {
  expect(poolBlock).toBeDefined();
  expect(Object.keys(serverPool)).toHaveLength(10);
  expect({ ...QUESTION_POOL }).toEqual(serverPool);
  expect(/MAX_PICK = (\d+)/.exec(python)?.[1]).toBe(String(MAX_PICK));
});
it("풀 문장은 질문형이고 판정하지 않는다", () => {
  for (const [id, q] of Object.entries(QUESTION_POOL)) {
    expect(q, id).toMatch(/습니까\?$/);
    expect(q, id).not.toMatch(/원인은|원인입니다|적용|다릅니다|같습니다/);
  }
});
it("고른 번호는 풀 안의 것만, 중복 없이 준 순서대로 최대 3개 — 응답이 문장을 들고 와도 화면은 풀의 문장을 쓴다", () => {
  expect(pickedQuestions(["P3", "P3", "P99", "P1", "x", "P2", "P5"]).map((q) => q.id)).toEqual(["P3", "P1", "P2"]);
  expect(pickedQuestions(undefined)).toEqual([]);
  expect(pickedQuestions(["P2"])[0].text).toBe(QUESTION_POOL.P2);
  const forged = { picked_questions: [{ id: "P2", text: "우리 건의 원인은 용접 불량입니다." }, { id: "P42", text: "x" }] };
  expect(pickedIdsOf(forged)).toEqual(["P2"]);
  expect(pickedIdsOf({})).toEqual([]);
  expect(pickedIdsOf({ picked_questions: undefined })).toEqual([]);
});
it("모델이 고른 번호는 같은 선례 조합에서만 보이고, 응답 모양이 이상해도 화면이 깨지지 않는다", () => {
  const picked = { key: "24V412000,24V422000", ids: ["P5", "P7"] };
  expect(pickedFor(picked, "24V412000,24V422000")).toEqual(["P5", "P7"]);
  expect(pickedFor(picked, "24V412000")).toEqual([]); // 다른 조합
  expect(pickedFor(picked, "")).toEqual([]);
  expect(pickedFor(null, "24V412000")).toEqual([]);
  expect(pickedQuestions(["P1", "P1", "P2", "P3", "P4"]).map((q) => q.id)).toEqual(["P1", "P2", "P3"]); // 상한 3
  expect(pickedQuestions([1 as never, null as never, "P4"]).map((q) => q.id)).toEqual(["P4"]); // 문자열이 아닌 항목은 쓰지 않는다
});
it("선례 체크를 바꾸면 모델이 고른 질문은 항상 걷히고, 같은 조합으로 돌아와도 되살아나지 않는다", () => {
  const a = { campno: "24V412000" } as never;
  const b = { campno: "24V422000" } as never;
  const picked = { key: "24V412000", ids: ["P5", "P7"] };
  const on = toggleChecked({ checked: [], picked: null }, a); // A 체크
  expect(on.checked).toEqual([a]);
  expect(pickedFor(picked, "24V412000")).toEqual(["P5", "P7"]); // A만 체크한 상태에서 묶기를 눌러 고른 질문
  const off = toggleChecked({ checked: on.checked, picked }, a); // A 해제
  expect(off).toEqual({ checked: [], picked: null });
  const again = toggleChecked({ checked: off.checked, picked: off.picked }, a); // A 다시 체크 — 같은 조합
  expect(again.checked).toEqual([a]);
  expect(pickedFor(again.picked, "24V412000")).toEqual([]); // 되살아나지 않는다
  expect(toggleChecked({ checked: [a], picked }, b).picked).toBeNull(); // 다른 선례를 더해도 걷힌다
});
