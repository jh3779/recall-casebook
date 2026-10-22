// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { SearchResponse } from "../search/types";
import { CATEGORY_LAYER } from "../showroom/peel";
import ModelOverlay from "./ModelOverlay";

// WebGL(three.js)은 jsdom에서 쓸 수 없다 — 쇼룸은 호출만 기록하는 가짜로 바꾸고, 화면이 쇼룸에 무엇을 넘기는지(상태 연결)를 본다
type FakeRoom = { setLook: ReturnType<typeof vi.fn>; focus: ReturnType<typeof vi.fn>; setPeel: ReturnType<typeof vi.fn> };
const rooms = vi.hoisted(() => ({ made: [] as unknown[] }));
vi.mock("../showroom/Showroom", () => ({
  Showroom: class {
    setLook = vi.fn(); focus = vi.fn(); setPeel = vi.fn(); show = vi.fn(); dispose = vi.fn(); bindMarker = vi.fn();
    markersOf = vi.fn(() => []);
    load = vi.fn(async () => new Set(["airbag"]));
    constructor() { rooms.made.push(this); }
  },
}));

const card = [...(fixture as SearchResponse).customer_precedents, ...(fixture as SearchResponse).precedents].find((c) => c.components[0].startsWith("AIR BAGS"))!;
const AIRBAG_LAYER = CATEGORY_LAYER.airbag;

beforeEach(() => { rooms.made.length = 0; });
afterEach(cleanup);

const room = () => rooms.made[0] as FakeRoom;
/** 쇼룸이 마지막으로 받은 시각 상태 */
const look = () => { const [mode, category, , highlight] = room().setLook.mock.lastCall!; return { mode, category, highlight, zoomed: room().focus.mock.lastCall![0] === "airbag" }; };
const peeled = () => room().setPeel.mock.lastCall![0];
async function openReady() {
  const user = userEvent.setup();
  render(<ModelOverlay card={card} opener={null} onClose={() => {}} />);
  await screen.findByRole("group", { name: "Part category to show" });
  return user;
}
const button = (name: string) => screen.getByRole("button", { name });

it("안내 보기에서 직접 조작으로 넘어가면 안내가 보여 주던 강조·확대·층을 이어받는다 (manual의 setHeld(holdOf(view)) 연결)", async () => {
  const user = await openReady();
  expect(look()).toEqual({ mode: "exterior", category: "airbag", highlight: false, zoomed: false }); // 1단계: 완성 모델
  expect(peeled()).toBe(0);

  await user.click(button("Next")); // 2단계: 층을 걷어내 분류가 드러나고 주황 강조
  expect(look().highlight).toBe(true);
  expect(peeled()).toBe(AIRBAG_LAYER);

  await user.click(button("Put back one layer")); // 직접 조작으로 넘어간다
  expect(screen.queryByRole("region", { name: "Guided view" })).toBeNull();
  expect(button("Start guided view")).toBeTruthy();
  expect(peeled()).toBe(AIRBAG_LAYER - 1); // 층은 이어받은 값에서 한 층 내려간다
  expect(look().highlight).toBe(true); // 강조는 이어받아 남는다

  await user.click(button("Start guided view")); // 다시 안내를 시작하면 처음 단계로 돌아간다
  expect(look().highlight).toBe(false);
  expect(peeled()).toBe(0);
});

it("확대한 안내 단계에서 직접 조작으로 넘어가도 확대가 남고, See-through 단추는 이어받은 강조를 비우며 Exterior로 돌아오면 확대도 풀린다", async () => {
  const user = await openReady();
  await user.click(button("Next"));
  await user.click(button("Next")); // 3단계: 분류로 확대
  expect(look()).toMatchObject({ highlight: true, zoomed: true });

  await user.click(button("Peel next layer"));
  expect(look()).toMatchObject({ mode: "exterior", highlight: true, zoomed: true }); // 안내가 보여 주던 확대·강조를 이어받는다

  await user.click(button("See-through"));
  expect(look()).toMatchObject({ mode: "xray", highlight: false, zoomed: true }); // 강조는 비우고, 결함 투시는 늘 부품 가까이 본다
  expect(button("See-through").getAttribute("aria-pressed")).toBe("true");

  await user.click(button("Exterior"));
  expect(look()).toMatchObject({ mode: "exterior", highlight: false, zoomed: false }); // 결함 투시가 아니고 이어받은 확대도 없으니 풀린다
  expect(button("Exterior").getAttribute("aria-pressed")).toBe("true");
});
