import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import demo from "../public/data/recalls.json";

describe("쇼룸 원문과 차종 범위", () => {
  it("잘못 재인코딩된 글자가 없다", () => {
    const text = readFileSync(new URL("../public/data/recalls.json", import.meta.url), "utf8");
    expect(text).not.toMatch(/Ã|Â[\u0080-\u00bf]/);
  });
  it("HD 전용 2건을 제외하고 장비 리콜은 남긴다", () => {
    expect(demo.silverado).toHaveLength(36);
    expect(demo.ram).toHaveLength(39);
    const ids = demo.silverado.map((card) => card.campno);
    expect(ids).not.toContain("13V544000");
    expect(ids).not.toContain("14V614000");
    const equipment = [...demo.silverado, ...demo.ram].filter((card) => /^\d{2}E/.test(card.campno)).map((card) => card.campno);
    expect(equipment).toEqual(["13E073000", "16E041000"]);
  });
});
