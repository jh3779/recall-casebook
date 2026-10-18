import { describe, expect, it } from "vitest";
import parts from "../../public/data/sorento_parts.json";
import { CATEGORIES } from "../config";
import { GUIDE_LAST, GUIDE_STEPS, clampGuide, guideMoves, guideView } from "./guide";
import { MODEL_PART_BONES, TYPICAL_COMPONENTS, displayName } from "./partNames";
import { CATEGORY_LAYER, PEEL_MAX, boneOfTitle } from "./peel";

describe("안내 보기 단계", () => {
  it("5단계: 완성 → 투시 → 풀림 → 확대 → 부품 이름", () => {
    expect(GUIDE_STEPS.map((s) => s.id)).toEqual(["assembled", "seethrough", "unfold", "zoom", "parts"]);
    expect(GUIDE_LAST).toBe(4);
  });
  it("단계별 화면 상태: 처음은 완성 Exterior, 두 번째부터 투시, 3단계에 걷어내고, 4단계에 확대, 마지막에만 마커", () => {
    expect(guideView(0, "engine")).toEqual({ mode: "exterior", layer: 0, zoom: false, markers: false });
    expect(guideView(1, "engine")).toEqual({ mode: "xray", layer: 0, zoom: false, markers: false });
    expect(guideView(2, "engine")).toEqual({ mode: "xray", layer: CATEGORY_LAYER.engine, zoom: false, markers: false });
    expect(guideView(3, "engine")).toEqual({ mode: "xray", layer: CATEGORY_LAYER.engine, zoom: true, markers: false });
    expect(guideView(4, "engine")).toEqual({ mode: "xray", layer: CATEGORY_LAYER.engine, zoom: true, markers: true });
  });
  it("걷어내는 층은 선택한 분류가 드러나는 층이고 0~4 안이다 — 분류가 없으면 걷어내지 않는다", () => {
    for (const cat of Object.keys(CATEGORIES) as (keyof typeof CATEGORIES)[]) {
      for (let s = 0; s <= GUIDE_LAST; s++) {
        const v = guideView(s, cat);
        expect(v.layer).toBeGreaterThanOrEqual(0);
        expect(v.layer).toBeLessThanOrEqual(PEEL_MAX);
        if (s >= 2) expect(v.layer).toBe(CATEGORY_LAYER[cat]);
      }
    }
    expect(guideView(4, null).layer).toBe(0);
  });
  it("범위 밖·잘못된 단계는 0~4로 고정한다", () => {
    expect(clampGuide(-2)).toBe(0);
    expect(clampGuide(9)).toBe(4);
    expect(clampGuide(Number.NaN)).toBe(0);
    expect(guideView(99, "seat")).toEqual(guideView(4, "seat"));
  });
  it("Back은 첫 단계에서, Next는 마지막 단계에서 쓸 수 없다", () => {
    expect(guideMoves(0)).toEqual({ canBack: false, canNext: true });
    expect(guideMoves(2)).toEqual({ canBack: true, canNext: true });
    expect(guideMoves(4)).toEqual({ canBack: true, canNext: false });
  });
  it("안내 문구에 판정·단정 표현이 없다", () => {
    for (const s of GUIDE_STEPS) expect(s.text).not.toMatch(/applies|verdict|recall is required|caused by|the cause is/i); // principle-ok: 문구에 판정 표현이 없는지 검사
  });
});

describe("부품 이름 표", () => {
  const defectBones = new Set(
    Object.values(parts as Record<string, { title: string; defect: string | null }>).filter((p) => p.defect).map((p) => boneOfTitle(p.title)),
  );
  it("분류가 붙은 쏘렌토 실제 부품(뼈대)은 모두 이름이 있고, 이름 표의 뼈대는 모두 그런 부품이다", () => {
    for (const bone of defectBones) expect(MODEL_PART_BONES, bone).toContain(bone);
    for (const bone of MODEL_PART_BONES) expect(defectBones.has(bone), bone).toBe(true);
  });
  it("실제 부품·설명용 도형 이름을 영어로 돌려주고, 표에 없으면 null이다(이름을 지어내지 않는다)", () => {
    expect(displayName({ title: "seats_09 / 2021kiasorento" }, false)).toBe("Seats");
    expect(displayName({ title: "코일 스프링 (추정 형상)" }, true)).toBe("Coil spring");
    expect(displayName({ title: "코일 스프링" }, true)).toBe("Coil spring");
    expect(displayName({ title: "bodyshell_030 / xromat" }, false)).toBeNull();
    expect(displayName({ title: "알 수 없는 도형 (추정 형상)" }, true)).toBeNull();
  });
  it("모든 부품 분류에 일반 구성 목록이 있고, 이름은 영어 표의 이름과 겹친다", () => {
    for (const cat of Object.keys(CATEGORIES)) expect(Array.isArray(TYPICAL_COMPONENTS[cat as keyof typeof TYPICAL_COMPONENTS]), cat).toBe(true);
    for (const name of ["Engine block", "Oil pan", "Brake disc", "Door latch", "Coil spring"]) {
      expect(Object.values(TYPICAL_COMPONENTS).flat()).toContain(name);
    }
  });
});
