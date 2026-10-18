import { describe, expect, it } from "vitest";
import { hashOfView, viewOfHash, type View } from "./views";

describe("viewOfHash", () => {
  it("해시가 없으면 랜딩이다", () => {
    expect(viewOfHash("")).toBe("landing");
    expect(viewOfHash("#")).toBe("landing");
  });
  it("기존 주소는 그대로 그 화면이다", () => {
    expect(viewOfHash("#casebook")).toBe("casebook");
    expect(viewOfHash("#8d")).toBe("8d");
    expect(viewOfHash("#showroom")).toBe("showroom");
    expect(viewOfHash("#search")).toBe("search");
  });
  it("화면으로 정한 해시는 다시 그 화면으로 읽힌다(왕복)", () => {
    for (const view of ["landing", "search", "showroom", "8d", "casebook"] as View[]) expect(viewOfHash(`#${hashOfView(view)}`)).toBe(view); // location.hash = x 뒤에 읽으면 "#x"다
  });
  it("모르는 해시는 예전처럼 검색 화면이다", () => {
    expect(viewOfHash("#landing")).toBe("search");
    expect(viewOfHash("#foo")).toBe("search");
  });
});
