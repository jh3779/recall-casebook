import { expect, it } from "vitest";
import { MODELS } from "../config";
import { DemoDataError, loadFailed, startFailure } from "./loadFailure";

// 이슈 #110: 데모 JSON을 못 받았는데 "3D 모델을 불러오지 못했습니다(public/models/…)"라고 안내하면 엉뚱한 파일을 찾게 된다
it("데모 데이터 오류는 데이터 안내이고 모델 파일 경로를 말하지 않는다", () => {
  const state = startFailure(new DemoDataError("data/hyundai-kia-recalls.json 404"), true, "sonata");
  expect(state).toMatchObject({ active: true, failed: true });
  expect(state.text).toContain("쇼룸 데모 데이터를 받지 못했습니다");
  expect(state.text).toContain("data/hyundai-kia-*.json");
  expect(state.text).not.toContain(MODELS.sonata.glb);
});
it("무대(WebGL)를 만들지 못했으면 WebGL 안내이고, 무대는 있는데 모델 파일이 없으면 모델 파일 안내다", () => {
  expect(startFailure(new Error("webgl"), false, "sonata").text).toContain("WebGL을 사용할 수 없습니다");
  const missing = startFailure(new Error("404"), true, "sonata");
  expect(missing).toEqual(loadFailed("sonata"));
  expect(missing.text).toContain(`public/${MODELS.sonata.glb}`);
});
it("무대가 없으면 데이터 오류도 데이터 안내가 먼저다(원인을 숨기지 않는다)", () => {
  expect(startFailure(new DemoDataError("x"), false, "sonata").text).toContain("쇼룸 데모 데이터");
});
