import { describe, expect, it } from "vitest";
import { CATEGORY_KEYS } from "./config";
import { categoryRows, fmtDate, heroStats, otherModel, recallsFor, yearLabel } from "./recalls";
import type { PartsMap, Recall, RecallsByModel } from "./types";
import recallsJson from "../public/data/recalls.json";
import ramParts from "../public/data/ram_parts.json";
import silveradoParts from "../public/data/silverado_parts.json";

function recall(campno: string, categories: Recall["categories"], potaff = 1000): Recall {
  return {
    campno,
    maker: "Maker",
    received: "20260924",
    potaff,
    defect: "d",
    consequence: "c",
    remedy: "r",
    years: [2016],
    components: [],
    categories,
    mfr_part: "",
  };
}

const sample: RecallsByModel = {
  silverado: [
    recall("A1", ["airbag"], 1_000_000),
    recall("A2", ["airbag", "seat"], 500_000),
    recall("B1", ["brakes"], 100_000),
    recall("X1", [], 30_000),
  ],
  ram: [recall("R1", ["brakes"])],
};

describe("recallsFor", () => {
  it("부품 분류가 들어 있는 리콜만 고른다", () => {
    expect(recallsFor(sample, "silverado", "airbag").map((r) => r.campno)).toEqual(["A1", "A2"]);
    expect(recallsFor(sample, "silverado", "seat").map((r) => r.campno)).toEqual(["A2"]);
  });

  it("분류가 null이면 3D 형상이 없는(분류가 빈) 리콜만 고른다", () => {
    expect(recallsFor(sample, "silverado", null).map((r) => r.campno)).toEqual(["X1"]);
  });
});

describe("categoryRows", () => {
  it("0건 분류는 빼고 건수 내림차순, 같으면 CATEGORIES 순서로 둔다", () => {
    const rows = categoryRows(sample, "silverado", new Set(["airbag", "brakes"]));
    expect(rows.map((r) => [r.key, r.count])).toEqual([
      ["airbag", 2],
      ["brakes", 1],
      ["seat", 1],
    ]);
  });

  it("3D 위치가 있는 분류만 고를 수 있게 표시한다", () => {
    const rows = categoryRows(sample, "silverado", new Set(["airbag", "brakes"]));
    expect(Object.fromEntries(rows.map((r) => [r.key, r.has3d]))).toEqual({ airbag: true, brakes: true, seat: false });
  });
});

describe("heroStats", () => {
  it("리콜 건수 · 3D로 보이는 리콜 건수 · 대상 대수 합계(백만)", () => {
    expect(heroStats(sample.silverado)).toEqual({ total: 4, in3d: 3, unitsM: "1.6" });
  });
});

describe("표시 형식", () => {
  it("접수일 YYYYMMDD → YYYY.MM.DD", () => {
    expect(fmtDate("20260924")).toBe("2026.09.24");
  });

  it("연식은 한 해면 그대로, 여러 해면 처음–끝", () => {
    expect(yearLabel([2018])).toBe("2018");
    expect(yearLabel([2016, 2017, 2018])).toBe("2016–2018");
  });

  it("다른 차종", () => {
    expect(otherModel("silverado")).toBe("ram");
    expect(otherModel("ram")).toBe("silverado");
  });
});

// 화면이 기대하는 데이터 모양을 실제 파일로 확인한다 (artifact에서 받은 데모 스냅샷)
describe("public/data 약속", () => {
  const data = recallsJson as RecallsByModel;

  it.each(["silverado", "ram"] as const)("%s 리콜마다 리콜 번호가 있고 서로 다르며, 분류는 CATEGORIES 안에 있다", (model) => {
    const list = data[model];
    expect(list.length).toBeGreaterThan(0);
    for (const r of list) {
      // NHTSA 리콜 번호: 연도 2자리 + 종류(V 차량 · E 장비 · T 타이어 · C 유아용 시트) + 6자리
      expect(r.campno).toMatch(/^\d{2}[VETC]\d{6}$/);
      expect(r.received).toMatch(/^\d{8}$/);
      expect(r.years.length).toBeGreaterThan(0);
      for (const c of r.categories) expect(CATEGORY_KEYS).toContain(c);
    }
    expect(new Set(list.map((r) => r.campno)).size).toBe(list.length);
  });

  it.each([
    ["silverado", silveradoParts],
    ["ram", ramParts],
  ])("%s 부품 분류는 CATEGORIES 안에 있다", (_, parts) => {
    for (const p of Object.values(parts as PartsMap)) {
      if (p.defect) expect(CATEGORY_KEYS).toContain(p.defect);
    }
  });
});
