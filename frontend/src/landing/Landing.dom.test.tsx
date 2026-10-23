// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Landing from "./Landing";

// jsdom에는 영상 재생과 화면 설정(matchMedia)이 없다 — 재생은 호출만 기록하는 가짜로, 움직임 줄이기 설정은 시험마다 세운다
let play: ReturnType<typeof vi.spyOn>;
beforeEach(() => { play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const reduceMotion = () => vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("prefers-reduced-motion"), media: query }));
const video = () => document.querySelector("video");

it("Open casebook을 누르면 onEnter를 부르고, 앱에서 돌아온 경우에만 그 버튼에 초점을 준다", async () => {
  const user = userEvent.setup();
  const onEnter = vi.fn();
  const first = render(<Landing onEnter={onEnter} />);
  const button = screen.getByRole("button", { name: "Open casebook" });
  expect(document.activeElement).not.toBe(button); // 첫 로드에서는 초점 테두리가 화면에 찍히지 않게
  await user.click(button);
  expect(onEnter).toHaveBeenCalledTimes(1);
  first.unmount();

  render(<Landing onEnter={onEnter} focusEnter />);
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open casebook" }));
});

it("배경 영상을 불러오지 못하면(onError) 영상 요소를 걷어 내고 검은 바탕으로 둔다", () => {
  render(<Landing onEnter={() => {}} />);
  expect(video()).toBeTruthy();
  expect(video()!.getAttribute("preload")).toBe("auto");
  expect(play).toHaveBeenCalledTimes(1);
  fireEvent.error(video()!);
  expect(video()).toBeNull();
  expect(screen.getByRole("button", { name: "Open casebook" })).toBeTruthy(); // 영상이 없어도 들어가는 길은 그대로
});

it("움직임 줄이기 설정이면 영상을 재생하지 않고 미리 받지도 않는다", () => {
  reduceMotion();
  render(<Landing onEnter={() => {}} />);
  expect(play).not.toHaveBeenCalled();
  expect(video()!.getAttribute("preload")).toBe("none");
});
