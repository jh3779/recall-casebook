import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { Card, SearchResponse } from "../search/types";
import { deriveDashboard, type Distribution } from "./dashboard";

const response = fixture as SearchResponse;
const all = [...response.customer_precedents, ...response.precedents];
const data = deriveDashboard(response);
const campnosOf = (d: Distribution) => Object.fromEntries(d.rows.map((r) => [r.label, r.campnos]));
const countsOf = (d: Distribution) => Object.fromEntries(d.rows.map((r) => [r.label, r.count]));
const card = (extra: Partial<Card> & { campno: string }): Card => ({ ...all[0], components: [], investigations: [], checklist: [], ...extra });

it("선례 수: 고객사 구역과 그 밖 구역을 나누고 리콜 번호를 붙인다", () => {
  expect(data.precedents.all.count).toBe(12);
  expect(data.precedents.customer.campnos).toEqual(["26V307000", "11V179000"]);
  expect(data.precedents.other.count).toBe(10);
  expect(data.precedents.all.campnos).toEqual(all.map((c) => c.campno));
});

it("회사 분포: 응답의 maker 글자 그대로, 많은 순 → 이름순", () => {
  expect(data.makers.rows[0]).toMatchObject({ label: "Takata Corporation", count: 4, campnos: ["13E017000", "16E009000", "14E073000", "15E041000"] });
  expect(data.makers.rows[1]).toMatchObject({ label: "Mazda North American Operations", count: 2, campnos: ["17V806000", "17V807000"] });
  expect(data.makers.rows).toHaveLength(8);
  expect(data.makers.missing).toEqual([]);
});

it("부품 분류 분포: 분류 문자열 그대로, 카드 하나가 같은 값을 여러 번 내도 한 번만 센다", () => {
  expect(countsOf(data.components)).toEqual({
    "AIR BAGS": 3,
    "AIR BAGS:FRONTAL:DRIVER SIDE:INFLATOR MODULE": 3,
    "AIR BAGS:SIDE/WINDOW": 2,
    "AIR BAGS:FRONTAL:PASSENGER SIDE:INFLATOR MODULE": 2,
    "AIR BAGS:FRONTAL:SENSOR/CONTROL MODULE-INACTIVE": 1,
    "AIR BAGS:FRONTAL": 1,
  });
  const twice = deriveDashboard({ precedents: [card({ campno: "A1", components: ["X", "X", "Y"] })] });
  expect(countsOf(twice.components)).toEqual({ X: 1, Y: 1 });
});

it("접수 연도 분포: 오래된 해부터, 날짜가 없으면 라벨을 지어내지 않고 missing에 둔다", () => {
  expect(data.years.rows.map((r) => r.label)).toEqual(["2000", "2010", "2011", "2013", "2014", "2015", "2016", "2017", "2026"]);
  expect(campnosOf(data.years)["2017"]).toEqual(["17V787000", "17V806000", "17V807000"]);
  expect(data.years.missing).toEqual([]);
  const odd = deriveDashboard({ precedents: [card({ campno: "B1", received_date: "" }), card({ campno: "B2", received_date: "20200102" }), card({ campno: "B3", received_date: "n/a" })] });
  expect(odd.years.rows).toEqual([{ label: "2020", count: 1, campnos: ["B2"] }]);
  expect(odd.years.missing).toEqual(["B1", "B3"]);
});

it("원인 칸: 글 있음·미보고 표현·원문 없음 세 묶음과 상태 원본 분포", () => {
  expect(data.causeLevels.text.count).toBe(5);
  expect(data.causeLevels.stated.campnos).toEqual(["17V787000"]);
  expect(data.causeLevels.none.count).toBe(6);
  const { text, stated, none } = data.causeLevels;
  expect(text.count + stated.count + none.count).toBe(data.precedents.all.count);
  expect(countsOf(data.causeStatuses)).toEqual({ filled: 5, no_573_report: 5, stated_unknown: 1, report_unreadable: 1 });
  expect(campnosOf(data.causeStatuses).report_unreadable).toEqual(["15E041000"]);
});

it("모르는 원인 상태도 원문 없음으로 센다(원인 불명으로 단정하지 않는다)", () => {
  const d = deriveDashboard({ precedents: [card({ campno: "C1", cause: { status: "brand_new_status" } })] });
  expect(d.causeLevels.none.campnos).toEqual(["C1"]);
  expect(countsOf(d.causeStatuses)).toEqual({ brand_new_status: 1 });
});

it("출처 종류: 결함 조사·573 원인 글·생산 기간을 리콜 번호와 함께 센다", () => {
  expect(data.sources.investigation.campnos).toEqual(["14E073000"]);
  expect(data.investigationActions.rows).toEqual([{ label: "PE14016", count: 1, campnos: ["14E073000"] }]);
  expect(data.sources.part573.count).toBe(6); // 원인 글 5 + 미보고 표현 1
  expect(data.sources.productionPeriod.count).toBe(0); // 이 응답에는 생산 기간 항목이 없다
  const source = { campaign: "X", file: "p.pdf", pdf_sha256: "a".repeat(64), submission_date: "20200101" };
  const production = { item: "production_period" as const, label: "p", evidence: [], omitted: 0, unread: 0, source };
  const d = deriveDashboard({ precedents: [card({ campno: "D1", cause: { status: "no_573_report" }, checklist: [production] })] });
  expect(d.sources.productionPeriod.campnos).toEqual(["D1"]);
  expect(d.sources.part573.campnos).toEqual(["D1"]);
  expect(d.matrix[0]).toMatchObject({ cause: "none", hasProductionPeriod: true, hasInvestigation: false });
});

it("본문 묶음 분포: 같은 묶음의 리콜 번호를 함께 돌려 준다", () => {
  expect(data.dupGroups.rows).toHaveLength(10);
  expect(campnosOf(data.dupGroups).c2875d75c9ba).toEqual(["17V787000", "17V807000"]);
});

it("근거 매트릭스: 선례마다 한 줄, 응답 순서 그대로", () => {
  expect(data.matrix.map((r) => r.campno)).toEqual(all.map((c) => c.campno));
  expect(data.matrix[0]).toEqual({ campno: "26V307000", maker: "Hyundai Motor America", received_date: "20260514", cause: "text", hasInvestigation: false, hasProductionPeriod: false });
  expect(data.matrix.find((r) => r.campno === "14E073000")).toMatchObject({ cause: "text", hasInvestigation: true });
});

it("모든 집계 항목은 이번 응답에 있는 리콜 번호만 근거로 단다(응답 밖 번호 없음)", () => {
  const known = new Set(all.map((c) => c.campno));
  const buckets = [
    ...Object.values(data.precedents), ...Object.values(data.causeLevels), ...Object.values(data.sources),
    ...[data.makers, data.components, data.years, data.causeStatuses, data.investigationActions, data.dupGroups].flatMap((d) => d.rows),
  ];
  for (const b of buckets) {
    expect(b.count).toBe(b.campnos.length);
    for (const c of b.campnos) expect(known.has(c), c).toBe(true);
  }
});

it("공급사는 집계하지 않는다(DEC-059 ⑤) — 키도 값도 결과에 없다", () => {
  const supplierNames = all.flatMap((c) => c.checklist.filter((i) => i.item === "supplier").flatMap((i) => i.evidence.map((e) => e.text))).filter(Boolean);
  expect(supplierNames.length).toBeGreaterThan(0);
  const json = JSON.stringify(data);
  expect(json).not.toMatch(/supplier/i);
  for (const name of supplierNames) expect(json).not.toContain(name);
});

it("판정 필드·문구가 결과에 없고, 입력을 바꾸지 않는다", () => {
  const forbidden = /applies|verdict|is_?applicable|recall[_\s-]?required/i; // principle-ok: 판정 필드가 결과 키에 없는지 검사하는 금지 패턴
  expect(JSON.stringify(data).match(forbidden)).toBeNull();
  const before = structuredClone(response);
  deriveDashboard(response);
  expect(response).toEqual(before);
});

it("빈 입력·누락 필드에도 빈 집계를 돌려 준다", () => {
  for (const input of [null, undefined, {}, { customer_precedents: [], precedents: [] }, { precedents: undefined }]) {
    const d = deriveDashboard(input);
    expect(d.precedents.all).toEqual({ count: 0, campnos: [] });
    expect(d.makers).toEqual({ rows: [], missing: [] });
    expect(d.causeLevels.none.count).toBe(0);
    expect(d.matrix).toEqual([]);
  }
  const bare = { campno: "E1" } as Card; // 칸이 거의 없는 카드도 죽지 않는다
  const d = deriveDashboard({ precedents: [bare] });
  expect(d.precedents.all.campnos).toEqual(["E1"]);
  expect(d.makers.missing).toEqual(["E1"]);
  expect(d.components.missing).toEqual(["E1"]);
  expect(d.causeLevels.none.campnos).toEqual(["E1"]);
  expect(d.matrix[0]).toEqual({ campno: "E1", maker: "", received_date: "", cause: "none", hasInvestigation: false, hasProductionPeriod: false });
});

it("같은 리콜 번호가 두 구역에 있으면 고객사 구역에서만 한 번 센다", () => {
  const dup = deriveDashboard({ customer_precedents: [card({ campno: "F1" })], precedents: [card({ campno: "F1" }), card({ campno: "F2" })] });
  expect(dup.precedents.all.campnos).toEqual(["F1", "F2"]);
  expect(dup.precedents.customer.campnos).toEqual(["F1"]);
  expect(dup.precedents.other.campnos).toEqual(["F2"]);
});
