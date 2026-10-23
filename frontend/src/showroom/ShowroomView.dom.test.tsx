// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MODELS } from "../config";
import ShowroomView from "./ShowroomView";

// WebGL(three.js)은 jsdom에서 쓸 수 없다 — 무대는 가짜로 바꾸고, 첫 화면을 준비하다 실패했을 때 화면이 어떤 안내를 고르는지(이슈 #110)만 본다
const scene = vi.hoisted(() => ({ load: undefined as undefined | (() => Promise<unknown>) }));
vi.mock("./Showroom", () => ({
  Showroom: class {
    load = vi.fn(() => scene.load!());
    dispose = vi.fn();
  },
}));

beforeEach(() => { scene.load = () => new Promise(() => {}); }); // 기본은 끝나지 않는 로딩
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("데모 JSON을 받지 못하면(404) 모델 파일이 아니라 데이터를 받지 못했다고 알린다", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })));
  render(<ShowroomView onSearch={() => {}} />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("쇼룸 데모 데이터를 받지 못했습니다 (data/hyundai-kia-*.json)");
  expect(alert.textContent).not.toContain(MODELS.sonata.glb);
});

it("데모 JSON 요청이 네트워크 오류로 실패해도 데이터 안내다", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
  render(<ShowroomView onSearch={() => {}} />);
  expect((await screen.findByRole("alert")).textContent).toContain("쇼룸 데모 데이터를 받지 못했습니다");
});

it("데이터는 받았는데 3D 모델 파일을 못 받으면 기존대로 모델 파일 경로를 안내한다", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) })));
  scene.load = async () => { throw new Error("glb 404"); };
  render(<ShowroomView onSearch={() => {}} />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain(`3D 모델을 불러오지 못했습니다 (public/${MODELS.sonata.glb})`);
  expect(alert.textContent).not.toContain("데모 데이터");
});

it("데이터와 3D 모델이 함께 실패하면 어느 쪽이 먼저 끝나든 데이터 안내를 보인다", async () => {
  // 네트워크가 끊긴 상황 — 모델 요청은 곧바로, JSON 요청은 한 박자 뒤에 실패한다
  scene.load = async () => { throw new Error("glb network"); };
  vi.stubGlobal("fetch", vi.fn(async () => { await new Promise((r) => setTimeout(r, 20)); throw new TypeError("Failed to fetch"); }));
  render(<ShowroomView onSearch={() => {}} />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("쇼룸 데모 데이터를 받지 못했습니다");
  expect(alert.textContent).not.toContain(MODELS.sonata.glb);
});
