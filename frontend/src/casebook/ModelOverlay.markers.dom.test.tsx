// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { SearchResponse } from "../search/types";
import { TYPICAL_COMPONENTS } from "../showroom/partNames";
import ModelOverlay from "./ModelOverlay";

// 3D 마커(`.cb-3d-marker`)가 안내의 마지막 단계에서만 그려지는지 — 쇼룸이 마커를 돌려주는 상태에서 본다(이슈 #163).
// WebGL(three.js)은 jsdom에서 쓸 수 없어 쇼룸은 가짜다: 마커 목록은 `markersOf`가 돌려주고, 화면이 `bindMarker`로 요소를 등록한다.
const MARKERS = [
  { id: "airbag:Driver air bag area", label: "Driver air bag area", estimated: true },
  { id: "airbag:Control module", label: "Control module", estimated: false }, // 일반 구성 목록에는 없는 이름
];
const rooms = vi.hoisted(() => ({ made: [] as unknown[] }));
vi.mock("../showroom/Showroom", () => ({
  Showroom: class {
    setLook = vi.fn(); focus = vi.fn(); setPeel = vi.fn(); show = vi.fn(); dispose = vi.fn(); bindMarker = vi.fn();
    markersOf = vi.fn((cat: string | null) => (cat === "airbag" ? MARKERS : []));
    load = vi.fn(async () => new Set(["airbag"]));
    constructor() { rooms.made.push(this); }
  },
}));

const card = [...(fixture as SearchResponse).customer_precedents, ...(fixture as SearchResponse).precedents].find((c) => c.components[0].startsWith("AIR BAGS"))!;

beforeEach(() => { rooms.made.length = 0; });
afterEach(cleanup);

const markerEls = () => [...document.querySelectorAll(".cb-3d-marker")];
const button = (name: string) => screen.getByRole("button", { name });

async function openReady() {
  const user = userEvent.setup();
  render(<ModelOverlay card={card} opener={null} onClose={() => {}} />);
  await screen.findByRole("group", { name: "Part category to show" });
  await waitFor(() => expect((rooms.made[0] as { setLook: ReturnType<typeof vi.fn> }).setLook).toHaveBeenCalled());
  return user;
}

it("3D 마커는 안내의 마지막(4) 단계에서만 그려지고, 1~3단계에서는 쇼룸이 마커를 돌려줘도 하나도 없다", async () => {
  const user = await openReady();
  for (let step = 1; step <= 3; step++) {
    expect(screen.getByText(`Step ${step} of 4`), `step ${step}`).toBeTruthy();
    expect(markerEls(), `step ${step}`).toHaveLength(0);
    expect(screen.queryByText("Parts of this category"), `step ${step}`).toBeNull();
    await user.click(button("Next"));
  }
  expect(screen.getByText("Step 4 of 4")).toBeTruthy();
  expect(markerEls().map((el) => el.textContent)).toEqual(["1", "2"]); // 번호는 이름 목록의 순서와 같다
  expect(markerEls().map((el) => el.getAttribute("title"))).toEqual(["Driver air bag area (estimated shape)", "Control module"]);
  const bound = (rooms.made[0] as { bindMarker: ReturnType<typeof vi.fn> }).bindMarker.mock.calls.filter(([, el]) => el).map(([id]) => id);
  expect([...new Set(bound)]).toEqual(MARKERS.map((m) => m.id)); // 쇼룸에 요소를 등록하는 것도 마지막 단계에서만, 마커마다 하나씩

  await user.click(button("Back")); // 3단계로 돌아가면 다시 사라진다
  expect(markerEls()).toHaveLength(0);
});

it("직접 조작으로 넘어가면 마커가 없고, 마지막 단계의 일반 구성 목록에는 이미 마커로 보이는 이름이 빠진다", async () => {
  const user = await openReady();
  for (let i = 0; i < 3; i++) await user.click(button("Next"));
  expect(markerEls()).toHaveLength(2);
  // 일반 구성 목록(Typical components)은 마커로 그려진 이름을 뺀 나머지만 보여 준다
  const typical = TYPICAL_COMPONENTS.airbag.filter((n) => !MARKERS.some((m) => m.label === n));
  const section = screen.getByRole("region", { name: "Guided view" });
  const listed = [...section.querySelectorAll(".cb-3d-parts ul li")].map((li) => li.textContent);
  expect(typical).toEqual(["Curtain air bag area"]); // 마커로 보이는 "Driver air bag area"만 빠진다
  expect(listed).toEqual(typical);

  await user.click(button("Peel next layer")); // 직접 조작으로 넘어간다
  expect(screen.queryByRole("region", { name: "Guided view" })).toBeNull();
  expect(markerEls()).toHaveLength(0);
});
