import { describe, expect, it } from "vitest";
import parts from "../../public/data/sorento_parts.json";
import { CATEGORIES } from "../config";
import {
  CATEGORY_LAYER, PEEL_BONES, PEEL_LABELS, PEEL_MAX, PEEL_MOVES, boneOfTitle, clampPeel, peelControls, peelFraming, peelShift, smootherstep,
} from "./peel";

const titles = Object.values(parts as Record<string, { title: string }>).map((p) => boneOfTitle(p.title));

describe("걷어내기 층 표", () => {
  it("층은 0(완성)부터 4까지이고 이름이 층 수보다 하나 많다", () => {
    expect(PEEL_MAX).toBe(4);
    expect(PEEL_LABELS).toHaveLength(PEEL_MOVES.length + 1);
  });
  it("한 뼈대는 한 층에서만 움직인다(층끼리 이동이 겹쳐 더해지지 않는다)", () => {
    const all = PEEL_MOVES.flatMap((layer) => Object.keys(layer));
    expect(new Set(all).size).toBe(all.length);
    expect(PEEL_BONES).toHaveLength(all.length);
  });
  it("표의 뼈대는 모두 쏘렌토 부품 데이터(메시 제목의 뼈대 이름)에 실제로 있다 — 모델 파일은 커밋하지 않으므로 이 데이터로 대조한다", () => {
    for (const bone of PEEL_BONES) expect(titles, bone).toContain(bone);
  });
  it("이동량은 모두 유한한 값이고 뼈대마다 한 방향 이상으로 움직인다", () => {
    for (const layer of PEEL_MOVES) {
      for (const [bone, move] of Object.entries(layer)) {
        expect(move.every(Number.isFinite), bone).toBe(true);
        expect(move.some((v) => v !== 0), bone).toBe(true);
      }
    }
  });
  it("차체 껍데기(4층)는 시트·핸들(3층)보다 훨씬 높이 올라가 서로 뚫고 지나가지 않는다", () => {
    const shell = PEEL_MOVES[3].bodyshell_030[1];
    for (const bone of Object.keys(PEEL_MOVES[2])) expect(shell).toBeGreaterThan(PEEL_MOVES[2][bone][1] + 1.5);
  });
  it("모든 부품 분류가 드러나는 층을 가지고 0~4 안이다", () => {
    for (const cat of Object.keys(CATEGORIES)) {
      const layer = CATEGORY_LAYER[cat as keyof typeof CATEGORY_LAYER];
      expect(Number.isInteger(layer), cat).toBe(true);
      expect(layer).toBeGreaterThanOrEqual(0);
      expect(layer).toBeLessThanOrEqual(PEEL_MAX);
    }
  });
});

describe("분류→층 표와 뼈대 층의 일치", () => {
  it("실제 메시가 있는 분류는 그 뼈대가 움직이는 층(또는 껍데기 아래 = 4층)에서 드러난다고 적혀 있다", () => {
    const layerOfBone = (bone: string) => PEEL_MOVES.findIndex((layer) => bone in layer) + 1; // 표에 없으면 0
    const seen = new Map<string, Set<string>>();
    for (const p of Object.values(parts as Record<string, { title: string; defect: string | null }>)) {
      if (!p.defect) continue;
      (seen.get(p.defect) ?? seen.set(p.defect, new Set()).get(p.defect)!).add(boneOfTitle(p.title));
    }
    expect(seen.size).toBeGreaterThan(0);
    for (const [cat, bones] of seen) {
      const layers = [...bones].map((b) => layerOfBone(b) || PEEL_MAX); // 움직이지 않는 뼈대는 차체 껍데기 아래(4층에서 드러남)
      expect(CATEGORY_LAYER[cat as keyof typeof CATEGORY_LAYER], `${cat}: ${[...bones].join(", ")}`).toBe(Math.min(...layers));
    }
  });
});

describe("걷어낸 정도에 따른 이동", () => {
  it("0에서는 아무것도 움직이지 않고, 층이 끝나면 표의 이동량 그대로이며, 그 뒤로는 더 움직이지 않는다", () => {
    for (const bone of PEEL_BONES) expect(peelShift(bone, 0)).toEqual([0, 0, 0]);
    expect(peelShift("door_dside_f_056", 1)).toEqual([0.5, 0.3, -2.3]);
    expect(peelShift("door_dside_f_056", 4)).toEqual([0.5, 0.3, -2.3]);
    expect(peelShift("bodyshell_030", 3)).toEqual([0, 0, 0]);
    expect(peelShift("bodyshell_030", 4)).toEqual([0, 3.2, 0]);
  });
  it("표에 없는 뼈대는 움직이지 않는다", () => {
    expect(peelShift("chassis_02", 4)).toEqual([0, 0, 0]);
    expect(peelShift("motor_010", 2.5)).toEqual([0, 0, 0]);
  });
  it("소수 단계에서는 이동이 층 사이에서 단조롭게 늘어난다", () => {
    let prev = -1;
    for (let l = 0; l <= 1.0001; l += 0.1) {
      const y = peelShift("bonnet_040", l)[1];
      expect(y).toBeGreaterThanOrEqual(prev);
      prev = y;
    }
    expect(peelShift("bonnet_040", 0.5)[1]).toBeCloseTo(0.5, 6); // 보간은 중간에서 정확히 절반
  });
  it("범위 밖·잘못된 값은 0~4로 고정하거나 0으로 처리한다", () => {
    expect(clampPeel(-3)).toBe(0);
    expect(clampPeel(9)).toBe(4);
    expect(clampPeel(Number.NaN)).toBe(0);
    expect(peelShift("bodyshell_030", Number.NaN)).toEqual([0, 0, 0]);
    expect(smootherstep(-1)).toBe(0);
    expect(smootherstep(2)).toBe(1);
  });
  it("카메라는 걷어낼수록 뒤로 빠지고 시선이 올라가며, 완성 상태는 원래 시점이다", () => {
    expect(peelFraming(0)).toEqual({ scale: 1, lift: 0 });
    expect(peelFraming(4).scale).toBeGreaterThan(peelFraming(2).scale);
    expect(peelFraming(4).lift).toBeGreaterThan(peelFraming(2).lift);
  });
});

describe("층 버튼 상태", () => {
  it("완성 상태에서는 되돌릴 수 없고 4층에서는 더 걷어낼 수 없다", () => {
    expect(peelControls(0, null)).toMatchObject({ canPutBack: false, canPeel: true });
    expect(peelControls(4, null)).toMatchObject({ canPutBack: true, canPeel: false });
    expect(peelControls(2, null)).toMatchObject({ canPutBack: true, canPeel: true });
  });
  it("분류가 없으면 드러내기를 쓸 수 없고, 분류가 있으면 그 층으로 가며 이미 그 층이면 쓸 수 없다", () => {
    expect(peelControls(0, null)).toMatchObject({ revealTo: null, canReveal: false });
    expect(peelControls(0, "engine")).toMatchObject({ revealTo: 4, canReveal: true });
    expect(peelControls(4, "engine")).toMatchObject({ revealTo: 4, canReveal: false });
    expect(peelControls(2, "seat")).toMatchObject({ revealTo: 3, canReveal: true });
  });
});
