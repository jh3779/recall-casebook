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
  });
  it("화면으로 정한 해시는 다시 그 화면으로 읽힌다(왕복)", () => {
    for (const view of ["landing", "showroom", "8d", "casebook"] as View[]) expect(viewOfHash(`#${hashOfView(view)}`)).toBe(view); // location.hash = x 뒤에 읽으면 "#x"다
  });
  it("옛 #search와 모르는 해시는 케이스북이다(선례 검색 화면을 케이스북에 합쳤다, DEC-075)", () => {
    expect(viewOfHash("#search")).toBe("casebook");
    expect(viewOfHash("#landing")).toBe("casebook");
    expect(viewOfHash("#foo")).toBe("casebook");
  });
});
