import type { CategoryKey } from "../types";

/**
 * NHTSA 부품 분류 문자열 → 3D 쇼룸의 부품 분류. `scripts/build_showroom_demo.py`의 `categories()`를 그대로 옮긴 것이다 —
 * `partCategory.test.ts`가 쇼룸 데모 데이터(`public/data/hyundai-kia-recalls.json`)의 26건과 같은 결과가 나오는지 대조한다.
 * 이 분류는 "3D에서 어디를 보여 줄지" 고르는 용도일 뿐이고 결함의 위치를 확정하지 않는다.
 */
export function partCategories(components: readonly string[]): CategoryKey[] {
  const out = new Set<CategoryKey>();
  for (const c of components) {
    if (c.startsWith("SERVICE BRAKES") || c.startsWith("PARKING BRAKE")) out.add("brakes");
    else if (c.startsWith("ELECTRICAL SYSTEM")) out.add("electrical");
    else if (c.startsWith("ENGINE")) out.add("engine");
    else if (c.startsWith("FUEL SYSTEM")) out.add("fuel");
    else if (c.startsWith("POWER TRAIN:AUTOMATIC TRANSMISSION")) out.add("transmission");
    else if (c.startsWith("STEERING")) out.add("steering");
    else if (c.startsWith("SUSPENSION")) out.add("suspension");
    else if (c.startsWith("AIR BAGS")) out.add("airbag");
    else if (c.startsWith("SEATS") || c.startsWith("SEAT BELTS")) out.add("seat");
    else if (c.startsWith("EXTERIOR LIGHTING:BRAKE LIGHTS:SWITCH")) out.add("lighting");
    else if (c.startsWith("LATCHES/LOCKS/LINKAGES:DOORS")) out.add("latches");
    else out.add("other");
  }
  return out.size ? [...out].sort() : ["other"];
}
