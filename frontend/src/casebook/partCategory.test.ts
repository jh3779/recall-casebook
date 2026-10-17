import { expect, it } from "vitest";
import recalls from "../../public/data/hyundai-kia-recalls.json";
import { partCategories } from "./partCategory";

it("쇼룸 데모 데이터 26건의 부품 분류와 `build_showroom_demo.py`의 `categories()` 결과가 같다", () => {
  const all = [...recalls.sonata, ...recalls.sorento];
  expect(all).toHaveLength(26);
  for (const r of all) expect(partCategories(r.components), r.campno).toEqual(r.categories);
});
it("알려진 분류 규칙과 기타·빈 목록", () => {
  expect(partCategories(["AIR BAGS:FRONTAL:DRIVER SIDE:INFLATOR MODULE"])).toEqual(["airbag"]);
  expect(partCategories(["SEAT BELTS:FRONT", "SERVICE BRAKES, HYDRAULIC:FOUNDATION COMPONENTS"])).toEqual(["brakes", "seat"]);
  expect(partCategories(["POWER TRAIN:AUTOMATIC TRANSMISSION"])).toEqual(["transmission"]);
  expect(partCategories(["VISIBILITY:WIPER"])).toEqual(["other"]);
  expect(partCategories([])).toEqual(["other"]);
});
