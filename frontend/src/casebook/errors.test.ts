import { expect, it } from "vitest";
import { ApiError } from "../api";
import { errorText } from "./errors";

it("묶기가 배포되지 않은 서버(404)는 영어 안내로 알린다", () => {
  expect(errorText(new ApiError("server", "서버 오류가 났습니다 (404)", 404), "grouping")).toBe("Grouping is not available on this server.");
});
it("호출 상한은 기다릴 초를 영어로 알리고 한국어 문구를 내지 않는다", () => {
  const text = errorText(new ApiError("rate_limit", "호출이 너무 잦습니다", 429, undefined, 12), "search");
  expect(text).toContain("12 seconds");
  expect(text).not.toMatch(/[가-힣]/);
});
it("종류별 문구에 한국어가 섞이지 않는다", () => {
  for (const kind of ["validation", "timeout", "network", "shape", "server"] as const) {
    for (const what of ["search", "grouping"] as const) expect(errorText(new ApiError(kind, "한국어"), what)).not.toMatch(/[가-힣]/);
  }
  expect(errorText(new Error("x"), "search")).toBe("Could not reach the server.");
});
