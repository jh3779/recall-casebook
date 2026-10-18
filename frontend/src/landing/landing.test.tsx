import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppBar } from "../AppBar";
import Landing from "./Landing";

describe("랜딩", () => {
  it("서비스 이름·한 문장·Open casebook 버튼을 보인다", () => {
    const html = renderToStaticMarkup(<Landing onEnter={() => {}} />);
    expect(html).toContain("Recall Casebook");
    expect(html).toContain("quoted word for word from NHTSA records");
    expect(html).toMatch(/<button[^>]*>Open casebook<\/button>/);
  });
  it("판정·원인 단정 문구가 없다", () => {
    const html = renderToStaticMarkup(<Landing onEnter={() => {}} />);
    expect(html).not.toMatch(/applies|verdict|the cause is|recall is required/i); // principle-ok: 문구에 판정 표현이 없는지 검사
  });
  it("배경 영상은 상대 경로로 부르고 소리가 없다(영상 파일은 저장소에 없다)", () => {
    const html = renderToStaticMarkup(<Landing onEnter={() => {}} />);
    expect(html).toContain('src="landing/roadster.mp4"');
    expect(html).toContain("muted");
  });
});

describe("상단 바의 시작 화면 버튼", () => {
  it("onHome이 있을 때만 그린다", () => {
    const base = { view: "casebook", onView: () => {}, health: "loading" as const };
    expect(renderToStaticMarkup(<AppBar {...base} onHome={() => {}} />)).toContain('aria-label="시작 화면으로"');
    expect(renderToStaticMarkup(<AppBar {...base} />)).not.toContain("시작 화면으로");
  });
});
