// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { search } from "../api";
import { D4_EVIDENCE_TITLE } from "../eightd/document";
import health from "../search/__fixtures__/health.json";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type Card, type HealthResponse, type SearchResponse } from "../search/types";
import CasebookView from "./CasebookView";
import { D4Panel } from "./D4Panel";
import ModelOverlay from "./ModelOverlay";
import { Results } from "./Results";

// 이슈 #159·#163·#165·#167 후속 — 네트워크는 부르지 않고(search만 가짜), WebGL(three.js)은 호출만 기록하는 가짜 쇼룸으로 바꾼다
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), search: vi.fn() }));
const room = vi.hoisted(() => ({ markers: [] as { id: string; label: string; estimated: boolean }[] }));
vi.mock("../showroom/Showroom", () => ({
  Showroom: class {
    setLook = vi.fn(); focus = vi.fn(); setPeel = vi.fn(); show = vi.fn(); dispose = vi.fn(); bindMarker = vi.fn();
    markersOf = vi.fn(() => room.markers);
    load = vi.fn(async () => new Set(["airbag"]));
  },
}));

const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const A = cards.find((c) => hasCauseText(c.cause))!;
const airbagCard = cards.find((c) => c.components[0].startsWith("AIR BAGS"))!;
const serverHealth = health as HealthResponse;

beforeEach(() => { localStorage.clear(); room.markers = []; vi.mocked(search).mockResolvedValue(response); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.mocked(search).mockReset(); });

// ---- 복사·삭제 실패 안내가 구역마다 엇갈리지 않는다 (#159: storeMessage·copyMessage) ----
const DELETE_FAILED = "Could not delete the saved note — it may remain in this browser.";
const deleteWarnings = () => screen.queryAllByText(DELETE_FAILED);
const question = () => screen.getByRole("textbox", { name: "Defect description in English" });
const caseInput = () => screen.getByRole("textbox", { name: "Case name" });
const find = () => screen.getByRole("button", { name: "Find precedents" });
const memo = () => screen.getAllByPlaceholderText("Your note on this precedent") as HTMLTextAreaElement[];
async function withDeleteFailure() {
  const user = userEvent.setup();
  render(<CasebookView health={serverHealth} />);
  await user.type(question(), "airbag inflator rupture");
  await user.click(find());
  await screen.findByRole("complementary", { name: "Search results" });
  await user.click(document.querySelector<HTMLElement>(`[data-campno="${A.campno}"]`)!);
  await user.type(caseInput(), "Case A{Enter}");
  await user.type(memo()[0], "x");
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); }); // 저장된 글을 지우지 못한다
  await user.clear(memo()[0]);
  expect(deleteWarnings()).toHaveLength(2); // 메모 구역과 D4 구역 둘 다
  return user;
}

it("복사하면 메모 구역은 복사 결과를 보이고 D4 구역에 남아 있던 지난 삭제 실패 안내도 걷힌다", async () => {
  const user = await withDeleteFailure();
  await user.click(screen.getByRole("button", { name: "Copy all notes" }));
  expect(await screen.findByText("Copied.")).toBeTruthy();
  expect(deleteWarnings()).toHaveLength(0);
});

it("사건 이름을 바꾸면 이전 사건의 삭제 실패 안내가 두 구역 모두에서 사라진다", async () => {
  const user = await withDeleteFailure();
  await user.clear(caseInput());
  await user.type(caseInput(), "Case B{Enter}");
  expect(deleteWarnings()).toHaveLength(0);
});

it("새 검색 결과가 오면 이전 결과의 삭제 실패 안내가 두 구역 모두에서 사라진다", async () => {
  const user = await withDeleteFailure();
  await user.click(find());
  await screen.findByRole("complementary", { name: "Search results" });
  expect(deleteWarnings()).toHaveLength(0);
});

// ---- 결과 화면 조립 (#165: on3d·onRemove 전달) ----
const resultsProps = { response, checked: [A] as Card[], checkedKey: A.campno, notes: {}, onNoteChange: () => {}, caseName: "", persistent: false, storageBlocked: false, onCopy: () => {}, onClear: () => {}, copyMessage: "", storeMessage: "", onGroupPicked: () => {}, picked: [] as string[] };

it("선례 상세의 Show in 3D·Remove는 결과 화면이 받은 on3d·onToggle로 그 선례를 넘긴다", async () => {
  const user = userEvent.setup();
  const on3d = vi.fn();
  const onToggle = vi.fn();
  render(<Results {...resultsProps} on3d={on3d} onToggle={onToggle} />);
  const show = screen.getByRole("button", { name: `Show part category of ${A.campno} in 3D` });
  await user.click(show);
  expect(on3d).toHaveBeenCalledWith(A, show); // 연 버튼을 함께 넘겨 닫을 때 초점이 돌아간다
  await user.click(screen.getByRole("button", { name: `Remove ${A.campno}` }));
  expect(onToggle).toHaveBeenCalledWith(A);
});

// ---- D4 안내 문구의 제목은 상수와 같다 (#167: D4_EVIDENCE_TITLE) ----
it("D4 구역의 선례 옵션 안내가 가리키는 제목 줄은 서류에 실제로 들어가는 D4_EVIDENCE_TITLE과 같다", async () => {
  const user = userEvent.setup();
  render(<D4Panel cards={[A]} response={response} notes={{}} onChange={() => {}} caseName="" persistent={false} storageBlocked={false} storeMessage="" picked={[]} />);
  await user.click(screen.getByRole("checkbox"));
  const guide = screen.getByText((_, el) => el?.tagName === "P" && !!el.textContent?.includes("In the D4 cell they follow your Escape and Root Cause text"));
  expect(guide.textContent).toContain(`“${D4_EVIDENCE_TITLE}”`);
});

// ---- 3D 창 (#163: 재생 종료 초점 · 3D 마커 연결부) ----
async function openGuided() {
  render(<ModelOverlay card={airbagCard} opener={null} onClose={() => {}} />);
  await screen.findByRole("group", { name: "Part category to show" });
  await waitFor(() => expect(screen.getByRole("region", { name: "Guided view" })).toBeTruthy());
}
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;
const tickPlay = () => act(() => { vi.advanceTimersByTime(3000); }); // GUIDE_PLAY_MS

it("자동 재생이 끝날 때 초점이 비활성이 되는 Play에 있었으면 Back으로 옮긴다", async () => {
  await openGuided();
  vi.useFakeTimers();
  button("Play").focus();
  fireEvent.click(button("Play"));
  tickPlay(); tickPlay(); tickPlay(); // 1단계 → 4단계(마지막)
  expect(screen.getByText("Step 4 of 4")).toBeTruthy();
  expect(button("Play").disabled).toBe(true);
  expect(document.activeElement).toBe(button("Back"));
});

it.each(["Close", "air bag"])("재생 중 사용자가 초점을 %s 단추로 옮겼으면 끝나도 뺏지 않는다", async (name) => {
  await openGuided();
  vi.useFakeTimers();
  fireEvent.click(button("Play"));
  tickPlay(); tickPlay();
  button(name).focus(); // 재생 중에 다른 곳으로 옮겼다
  tickPlay();
  expect(screen.getByText("Step 4 of 4")).toBeTruthy();
  expect(document.activeElement).toBe(button(name));
});

it("3D 위의 부품 이름 마커는 마지막(Parts) 단계에서만 보이고, 직접 조작으로 넘어가면 사라진다 (view?.markers 연결)", async () => {
  room.markers = [{ id: "airbag:Airbag module", label: "Airbag module", estimated: true }];
  const user = userEvent.setup();
  await openGuided();
  const markers = () => [...document.querySelectorAll<HTMLElement>(".cb-3d-marker")];
  for (let step = 1; step <= 3; step++) { // 1~3단계에는 마커가 없다
    expect(screen.getByText(`Step ${step} of 4`), `step ${step}`).toBeTruthy();
    expect(markers(), `step ${step}`).toHaveLength(0);
    await user.click(button("Next"));
  }
  expect(screen.getByText("Step 4 of 4")).toBeTruthy();
  expect(markers().map((m) => [m.textContent, m.title])).toEqual([["1", "Airbag module (estimated shape)"]]);

  await user.click(button("Put back one layer")); // 직접 조작
  expect(screen.queryByRole("region", { name: "Guided view" })).toBeNull();
  expect(markers()).toHaveLength(0);
});
