import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { MODELS, MODEL_KEYS } from "../config";

describe("현대·기아 쇼룸 데이터 범위", () => {
  it("manifest가 커밋된 리콜 JSON과 입력 판본을 가리킨다", () => {
    const recalls = readFileSync(new URL("../../public/data/hyundai-kia-recalls.json", import.meta.url));
    const manifest = JSON.parse(readFileSync(new URL("../../public/data/hyundai-kia-manifest.json", import.meta.url), "utf8"));
    expect(manifest.recalls_json_sha256).toBe(createHash("sha256").update(recalls).digest("hex"));
    for (const key of ["snapshot_date", "raw_manifest_sha256", "flat_sha256", "cards_sha256"]) expect(manifest[key]).toEqual(expect.any(String));
  });
  it("쏘나타·쏘렌토 모델과 출처를 연결한다", () => {
    expect(MODEL_KEYS).toEqual(["sonata", "sorento"]);
    for (const key of MODEL_KEYS) {
      expect(MODELS[key].glb).toBe(`models/${key}.glb`);
    }
  });
  it("쏘나타 2011–2014·쏘렌토 2021–2023 범위와 원문을 보존한다", () => {
    const data = JSON.parse(readFileSync(new URL("../../public/data/hyundai-kia-recalls.json", import.meta.url), "utf8"));
    expect(Object.keys(data)).toEqual(["sonata", "sorento"]);
    expect(data.sonata).toHaveLength(18);
    expect(data.sorento).toHaveLength(8);
    const campaign = (id: string) => data.sonata.find((r: { campno: string }) => r.campno === id);
    expect(campaign("10V426000").categories).toEqual(["steering"]);
    expect(campaign("13V113000").categories).toEqual(["lighting"]);
    expect(campaign("18V137000").categories).toEqual(["airbag", "seat"]);
    expect(data.sonata.map((r: { campno: string }) => r.campno)).toContain("10V426000");
    expect(data.sonata.map((r: { campno: string }) => r.campno)).not.toContain("21V127000"); // 코나 전기차
    for (const [key, list] of Object.entries(data) as [string, { years: number[]; maker: string; campno: string; source: string }[]][]) {
      for (const r of list) {
        expect(r.years.every(y => key === "sonata" ? y >= 2011 && y <= 2014 : y >= 2021 && y <= 2023)).toBe(true);
        expect(r.maker).toMatch(key === "sonata" ? /Hyundai/i : /Kia/i);
        expect(r.source).toBe(`https://www.nhtsa.gov/recalls?nhtsaId=${r.campno}`);
      }
    }
  });
});
