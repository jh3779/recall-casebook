import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { Loader } from "./Loader";

it("준비가 끝나면 로딩 덮개를 제거한다", () => {
  expect(renderToStaticMarkup(<Loader text="모델 불러오는 중" active={false} />)).toBe("");
});

it("모델 실패 때 검색으로 돌아가는 버튼을 제공한다", () => {
  const markup = renderToStaticMarkup(<Loader text="모델을 불러오지 못했습니다" active failed />);
  expect(markup).toContain('role="alert"');
  expect(markup).toContain("케이스북으로");
});
