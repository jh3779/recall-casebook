import type { CategoryKey } from "../types";

/**
 * 3D 창의 "걷어내기" 층(DEC-072). 쏘렌토 GLB는 부품이 뼈대(스켈레톤) 이름 단위로 나뉘어 있어서, 뼈대를 차량 바깥쪽으로 옮기면 그 부품만 빠진다.
 * 이동량은 정규화한 차량 좌표(미터)다: 앞 +x, 운전석 쪽 −z, 위 +y. 아래 표의 뼈대는 모두 `chassis_02`의 직접 자식이라(문·범퍼 등의 자식 뼈대는 부모를 따라간다)
 * 층끼리 이동이 겹쳐 더해지지 않는다. 차체 껍데기(4층)는 가장 높이 들려 올라가고, 시트·핸들(3층)은 그 아래에 머물러 서로 뚫고 지나가지 않게 했다.
 *
 * 설명용 연출일 뿐이다 — 정비·분해 순서나 이 차량(리콜 차종)의 실제 구조가 아니고, 결함 위치를 확정하지 않는다.
 * 출처: 단계별로 걷어내는 아이디어와 보간 방식은 `car-assembly-react`(팀 자료, 라이선스 파일 없음)를 참고했고 코드는 가져오지 않았다.
 */
export const PEEL_LABELS = ["Assembled", "Panels", "Glass & lamps", "Interior", "Body shell"] as const;
export const PEEL_MAX = PEEL_LABELS.length - 1;

export type Vec = readonly [number, number, number];

/** 층 i+1에서 움직이는 뼈대와 그 층이 끝났을 때의 이동량 */
export const PEEL_MOVES: readonly Readonly<Record<string, Vec>>[] = [
  {
    door_dside_f_056: [0.5, 0.3, -2.3], door_pside_f_061: [0.5, 0.3, 2.3],
    door_dside_r_066: [-0.5, 0.3, -2.3], door_pside_r_070: [-0.5, 0.3, 2.3],
    bonnet_040: [1.6, 1.0, 0], boot_080: [-1.6, 1.0, 0],
    bumper_f_038: [1.5, 0, 0], bumper_r_03: [-1.5, 0, 0], grill_07: [1.1, 0.3, 0],
  },
  {
    windscreen_089: [1.6, 1.0, 0], window_lm_088: [0, 0.3, -2.6], window_rm_087: [0, 0.3, 2.6],
    fara_08: [1.0, 0.6, 0], headlight_l_076: [1.0, 0.6, -0.4], headlight_r_077: [1.0, 0.6, 0.4],
    taillight_l_046: [-1.0, 0.6, -0.4], taillight_r_047: [-1.0, 0.6, 0.4],
    indicator_lr_078: [-1.0, 0.4, -0.6], indicator_rr_079: [-1.0, 0.4, 0.6],
  },
  { seats_09: [0, 1.0, 0], steeringwheel_053: [0.4, 1.0, 0] },
  { bodyshell_030: [0, 3.2, 0] },
];

export const PEEL_BONES: readonly string[] = [...new Set(PEEL_MOVES.flatMap((layer) => Object.keys(layer)))];

/** 부품 분류가 눈에 드러나는 층. 설명용 배치이고 결함 위치의 근거가 아니다. 0 = 걷어내지 않아도 보인다 */
export const CATEGORY_LAYER: Readonly<Record<CategoryKey, number>> = {
  tailgate: 1, latches: 1, seat: 3, airbag: 3, steering: 3,
  lighting: 4, engine: 4, transmission: 4, electrical: 4, fuel: 4, driveline: 4, suspension: 4, brakes: 4, other: 0,
};

const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
export const smootherstep = (v: number) => { const t = clamp(v); return t * t * t * (t * (t * 6 - 15) + 10); };
export const clampPeel = (level: number) => (Number.isFinite(level) ? clamp(level, 0, PEEL_MAX) : 0);

/** 걷어낸 정도 level(0~4, 소수 가능)에서 이 뼈대가 이동한 양. 표에 없는 뼈대는 움직이지 않는다 */
export function peelShift(bone: string, level: number): [number, number, number] {
  const out: [number, number, number] = [0, 0, 0];
  const l = clampPeel(level);
  PEEL_MOVES.forEach((layer, i) => {
    const move = layer[bone];
    if (!move) return;
    const u = smootherstep(l - i);
    for (let k = 0; k < 3; k++) out[k] += move[k] * u;
  });
  return out;
}

/** 부품이 바깥으로 나가면 카메라를 뒤로 빼고 시선을 올려 전부 보이게 한다 */
export function peelFraming(level: number): { scale: number; lift: number } {
  const l = clampPeel(level);
  return { scale: 1 + 0.09 * l, lift: 0.4 * l };
}

/** 데이터(`*_parts.json`)의 메시 제목은 "뼈대이름 / 재질"이다 */
export const boneOfTitle = (title: string) => title.split(" / ")[0];

/** 3D 창의 층 버튼 상태. 분류가 없으면 "이 분류 드러내기"는 쓸 수 없고, 이미 그 층이면 더 할 일이 없다 */
export function peelControls(layer: number, category: CategoryKey | null) {
  const target = category ? CATEGORY_LAYER[category] : null;
  return { canPutBack: layer > 0, canPeel: layer < PEEL_MAX, revealTo: target, canReveal: target !== null && target !== layer };
}
