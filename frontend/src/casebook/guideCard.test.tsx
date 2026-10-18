import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GuideCard } from "./GuideCard";
import { GUIDE_STEPS, markerTitle } from "../showroom/guide";

const marks = [
  { id: "brakes:Brake disc", label: "Brake disc", estimated: true },
  { id: "steering:Steering wheel", label: "Steering wheel", estimated: false },
];
const props = { markers: marks, typical: ["Steering column", "Steering rack"], isPlaying: false, reducedMotion: false, onBack: () => {}, onNext: () => {}, onPlay: () => {} };
const NOT_STRUCTURE = "not the structure of the vehicle in this recall and not where a defect is";

describe("안내 보기 카드", () => {
  it("마지막(4) 단계는 부품 이름 목록과 함께 추정 표시·일반 구성 면책·고정 안내가 항상 나온다", () => {
    const html = renderToStaticMarkup(<GuideCard step={3} showParts {...props} />);
    expect(html).toContain("Step 4 of 4");
    expect(html).toContain("Parts of this category");
    expect(html).toContain("Brake disc");
    expect(html).toContain("(estimated shape)");
    expect(html).toContain("Typical components of this system");
    expect(html).toContain("not specific to this vehicle");
    expect(html).toContain(NOT_STRUCTURE);
  });
  it("일반 구성이 없어도 고정 안내는 나오고, 이름 목록이 비면 비었다고 알린다", () => {
    const html = renderToStaticMarkup(<GuideCard step={3} showParts {...props} markers={[]} typical={[]} />);
    expect(html).toContain("No named parts of this category are drawn in the 3D model.");
    expect(html).not.toContain("Typical components");
    expect(html).toContain(NOT_STRUCTURE);
  });
  it("1~3 단계에는 부품 이름 목록도 면책 문구도 없다(이름이 보이는 곳에서만 안내가 나온다)", () => {
    for (let s = 0; s <= 2; s++) {
      const html = renderToStaticMarkup(<GuideCard step={s} showParts={false} {...props} />);
      expect(html, `step ${s}`).not.toContain("Parts of this category");
      expect(html, `step ${s}`).not.toContain("Steering wheel");
      expect(html, `step ${s}`).not.toContain(NOT_STRUCTURE);
      expect(html, `step ${s}`).toContain(`Step ${s + 1} of 4`);
    }
  });
  it("Back은 첫 단계에서, Next·Play는 마지막 단계에서 비활성이고 현재 단계가 표시된다", () => {
    const first = renderToStaticMarkup(<GuideCard step={0} showParts={false} {...props} />);
    expect(first).toMatch(/<button[^>]*disabled=""[^>]*>Back<\/button>/);
    expect(first).toMatch(/<li aria-current="step">Assembled<\/li>/);
    const last = renderToStaticMarkup(<GuideCard step={3} showParts {...props} />);
    expect(last).toMatch(/<button[^>]*disabled=""[^>]*>Next<\/button>/);
    expect(last).toMatch(/<button[^>]*disabled=""[^>]*>Play<\/button>/);
  });
  it("단계 목록에는 투명화(See-through) 단계가 없다 — Assembled → Unfold → Zoom → Parts(DEC-078)", () => {
    const html = renderToStaticMarkup(<GuideCard step={0} showParts={false} {...props} />);
    for (const title of ["Assembled", "Unfold", "Zoom", "Parts"]) expect(html).toContain(`>${title}</li>`);
    expect(html).not.toContain("See-through");
    expect(html).not.toContain("transparent");
    for (const s of GUIDE_STEPS) expect(`${s.title} ${s.text}`).not.toMatch(/see-through|transparent|x-ray/i); // 단계 문구가 투명화를 다시 말하지 않는다
  });
  it("모션 감소 설정에서는 Play를 쓸 수 없고 이유를 알리며, 재생 중에는 Pause로 바뀐다", () => {
    const reduced = renderToStaticMarkup(<GuideCard step={1} showParts={false} {...props} reducedMotion />);
    expect(reduced).toMatch(/<button[^>]*disabled=""[^>]*>Play<\/button>/);
    expect(reduced).toContain("Auto-play is off because your system asks for reduced motion");
    const playing = renderToStaticMarkup(<GuideCard step={1} showParts={false} {...props} isPlaying />);
    expect(playing).toContain("Pause");
    expect(playing).toContain('aria-pressed="true"');
  });
  it("안내 문구에 판정·단정 표현이 없다", () => {
    for (let s = 0; s <= 3; s++) {
      const html = renderToStaticMarkup(<GuideCard step={s} showParts={s === 3} {...props} />);
      expect(html).not.toMatch(/applies|verdict|the cause is|recall is required/i); // principle-ok: 문구에 판정 표현이 없는지 검사
    }
  });
  it("마커의 이름 표기는 설명용 도형에 추정 표시를 붙인다(호버로 읽어도 같다)", () => {
    expect(markerTitle(marks[0])).toBe("Brake disc (estimated shape)");
    expect(markerTitle(marks[1])).toBe("Steering wheel");
  });
});
