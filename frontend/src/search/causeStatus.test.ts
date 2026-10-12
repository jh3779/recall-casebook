import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { causeStatus } from "./causeStatus";
import type { Cause } from "./types";
import fixture from "./__fixtures__/search_airbag.json";
import synthetic from "./__fixtures__/cause_statuses_synthetic.json";

const causes = [...fixture.customer_precedents, ...fixture.precedents].map((card) => card.cause).concat(synthetic as never[]);
const docs = readFileSync(new URL("../../../docs/design-system/copy/cause-status.md", import.meta.url), "utf8");
const rows = docs.split("\n").filter((line) => /^\| `|^\| \(모르는 값\)/.test(line));
it.each(rows)("설계 문구와 글자까지 일치: %s", (row) => {
  const [, raw, label, message] = row.split("|").map((s) => s.trim());
  const name = raw.startsWith("`") ? raw.slice(1, -1) : "future_status";
  const cause = causes.find((c) => c.status === name) as Cause;
  expect(cause).toBeDefined();
  const expected = message.replace("{campaign}", "campaign" in cause ? cause.campaign ?? "" : "")
    .replace("{reason}", "reason" in cause ? String(cause.reason) : "").replace("{status}", cause.status);
  expect(causeStatus(cause)).toEqual({ label, message: expected, level: name === "filled" ? "text" : name === "stated_unknown" ? "stated" : "none" });
});
it("객체의 내장 속성과 같은 모르는 값도 상태 글로 표시한다", () => {
  expect(causeStatus({ status: "constructor" }).message).toBe("원인 상태: constructor");
});
