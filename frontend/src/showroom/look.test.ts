import { describe, expect, it } from "vitest";
import { meshLook, type Look } from "./look";

const base = (over: Partial<Look> = {}): Look => ({ mode: "exterior", category: "engine", activeCats: new Set(["engine"]), highlight: false, ...over });
const real = { cat: "seat" as const, estimated: false };
const estimatedEngine = { cat: "engine" as const, estimated: true };
const estimatedBrake = { cat: "brakes" as const, estimated: true };

describe("부품 표시(meshLook)", () => {
  it("외관은 설명용 추정 도형을 숨기고 모든 부품이 원래 재질이다", () => {
    expect(meshLook(base(), real)).toEqual({ visible: true, material: "base" });
    expect(meshLook(base(), estimatedEngine)).toEqual({ visible: false, material: "base" });
  });
  it("외관 + highlight: 선택한 분류만 보이고 주황이다 — 추정 도형도 드러나고 다른 분류의 추정 도형은 숨은 채다(차체는 투명하지 않다)", () => {
    expect(meshLook(base({ highlight: true }), estimatedEngine)).toEqual({ visible: true, material: "hot" });
    expect(meshLook(base({ highlight: true }), estimatedBrake)).toEqual({ visible: false, material: "base" });
    expect(meshLook(base({ highlight: true }), real)).toEqual({ visible: true, material: "base" }); // 차체·다른 실제 부품은 불투명 원래 재질
    expect(meshLook(base({ highlight: true, category: "seat" }), real)).toEqual({ visible: true, material: "hot" }); // 선택한 분류가 실제 부품이면 그것이 주황
  });
  it("분류가 없으면 highlight여도 아무것도 강조하지 않는다", () => {
    expect(meshLook(base({ highlight: true, category: null }), estimatedEngine)).toEqual({ visible: false, material: "base" });
  });
  it("결함 투시(xray)는 이전과 같다 — 고른 부품 주황·나머지 결함 부품 회색·그 밖 반투명, highlight는 영향이 없다", () => {
    const xray = base({ mode: "xray" });
    expect(meshLook(xray, estimatedEngine)).toEqual({ visible: true, material: "hot" });
    expect(meshLook(xray, estimatedBrake)).toEqual({ visible: false, material: "ghost" });
    expect(meshLook(xray, real)).toEqual({ visible: true, material: "ghost" });
    expect(meshLook({ ...xray, category: null, activeCats: new Set(["engine", "brakes"]) }, estimatedBrake)).toEqual({ visible: true, material: "defect" });
    expect(meshLook({ ...xray, highlight: true }, real)).toEqual(meshLook(xray, real));
  });
});
