import { expect, it } from "vitest";
import { highlight } from "./highlight";
import type { Flag } from "./types";
import fixture from "./__fixtures__/search_airbag.json";
const flag = (start: number, end: number, text: string): Flag => ({ kind: "unknown_expression", label: "원인 미확인 표현 있음", spans: [{ start, end, text }] });
it.each([...fixture.customer_precedents, ...fixture.precedents].filter((c) => "text" in c.cause))("$campno의 원문은 강조 전후 같다", ({ cause }) => {
  if (!("text" in cause)) throw new Error("시험 원문 없음");
  expect(highlight(cause.text!, cause.flags as Flag[]).map((p) => p.text).join("")).toBe(cause.text);
});
it("비-BMP·제어 문자 앞뒤에서 코드포인트 위치를 지킨다", () => {
  const text = "😀\u0092 Unknown cause.";
  expect(highlight(text, [flag(3, 10, "Unknown")])).toEqual([{ text: "😀\u0092 " }, { text: "Unknown", kind: "unknown_expression", label: "원인 미확인 표현 있음" }, { text: " cause." }]);
});
it("틀린 글자·범위·분수 좌표는 강조하지 않는다", () => {
  const text = "Unknown cause";
  expect(highlight(text, [flag(0, 7, "unknown"), flag(-1, 7, "Unknown"), flag(0, 99, text), flag(0.5, 7, "Unknown")])).toEqual([{ text }]);
});
it("겹치면 입력 순서상 먼저 온 구간을 유지하고 나중에 정렬한다", () => {
  const text = "Unknown cause";
  const result = highlight(text, [flag(8, 13, "cause"), flag(0, 13, text), flag(0, 7, "Unknown")]);
  expect(result.filter((p) => p.kind).map((p) => p.text)).toEqual(["Unknown", "cause"]);
  expect(result.map((p) => p.text).join("")).toBe(text);
});
it("빈 원문도 보존한다", () => expect(highlight("", [])).toEqual([{ text: "" }]));
