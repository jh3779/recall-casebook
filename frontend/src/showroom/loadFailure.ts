import type { LoaderState } from "../components/Loader";
import { MODELS } from "../config";
import type { ModelKey } from "../types";

/** 쇼룸 데모 JSON(`data/hyundai-kia-*.json`)을 받지 못했거나 읽지 못했다 — 3D 모델 파일 문제와 안내가 달라야 한다 */
export class DemoDataError extends Error {}

// 모델 파일은 커밋하지 않으므로(용량) 받아 두지 않았으면 여기서 멈추고 안내한다
export const loadFailed = (key: ModelKey): LoaderState => ({
  text: `3D 모델을 불러오지 못했습니다 (public/${MODELS[key].glb}). frontend/README.md의 "3D 모델 파일"을 보세요.`,
  active: true,
  failed: true,
});

const demoDataFailed: LoaderState = { text: "쇼룸 데모 데이터를 받지 못했습니다 (data/hyundai-kia-*.json). 네트워크 연결을 확인하고 다시 열어 보세요.", active: true, failed: true };
const webglFailed: LoaderState = { text: "3D 화면을 시작하지 못했습니다. 이 브라우저에서 WebGL을 사용할 수 없습니다.", active: true, failed: true };

/** 첫 화면을 준비하다 실패했을 때의 안내 — 데이터 오류는 데이터 안내, 무대(WebGL)를 못 만들었으면 WebGL 안내, 그 밖에는 모델 파일 안내 */
export function startFailure(error: unknown, sceneCreated: boolean, key: ModelKey): LoaderState {
  if (error instanceof DemoDataError) return demoDataFailed;
  return sceneCreated ? loadFailed(key) : webglFailed;
}
