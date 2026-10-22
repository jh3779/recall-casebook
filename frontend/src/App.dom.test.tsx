// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "./App";
import { health, search } from "./api";
import healthFixture from "./search/__fixtures__/health.json";
import fixture from "./search/__fixtures__/search_airbag.json";
import type { HealthResponse, SearchResponse } from "./search/types";

// 네트워크도 three.js도 쓰지 않는다 — 서버 호출은 가짜로, 3D 쇼룸 화면은 질문을 넘기는 단추 하나뿐인 가짜로 바꾼다
vi.mock("./api", async (importOriginal) => ({ ...(await importOriginal<typeof import("./api")>()), health: vi.fn(), search: vi.fn() }));
const showroom = vi.hoisted(() => ({ fail: false }));
vi.mock("./showroom/ShowroomView", () => ({
  default: ({ onSearch }: { onSearch: (question: string) => void }) => {
    if (showroom.fail) throw new Error("3D chunk failed");
    return <button type="button" onClick={() => onSearch("steering rack noise")}>fake showroom search</button>;
  },
}));

const response = fixture as SearchResponse;
const card = response.customer_precedents[0] ?? response.precedents[0];

beforeEach(() => {
  history.replaceState(null, "", "/");
  showroom.fail = false;
  vi.mocked(health).mockResolvedValue(healthFixture as HealthResponse);
  vi.mocked(search).mockResolvedValue(response);
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined); // jsdom에는 영상 재생이 없다
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.mocked(health).mockReset(); vi.mocked(search).mockReset(); history.replaceState(null, "", "/"); });

/** 주소창의 해시를 바꾸고 브라우저처럼 hashchange를 알린다 */
const goTo = (url: string) => act(() => { history.replaceState(null, "", url); window.dispatchEvent(new HashChangeEvent("hashchange")); });
const panes = () => [...document.querySelectorAll<HTMLElement>(".view-pane")]; // [케이스북, 8D]
const question = () => screen.getByRole("textbox", { name: "Defect description in English" }) as HTMLInputElement;
const openCasebookButton = () => screen.queryByRole("button", { name: "Open casebook" });

it("랜딩에서 시작해 Open casebook을 누르면 케이스북이 열리고 주소 해시가 바뀌며 서버 판본이 앱 바에 나온다", async () => {
  const user = userEvent.setup();
  render(<App />);
  expect(openCasebookButton()).toBeTruthy();
  expect(document.activeElement).not.toBe(openCasebookButton()); // 첫 로드에서는 초점 테두리를 찍지 않는다
  expect(screen.queryByRole("navigation", { name: "화면 전환" })).toBeNull();
  expect(panes().map((pane) => pane.hidden)).toEqual([true, true]);

  await user.click(openCasebookButton()!);
  expect(location.hash).toBe("#casebook");
  expect(openCasebookButton()).toBeNull();
  expect(screen.getByRole("navigation", { name: "화면 전환" })).toBeTruthy();
  expect(panes().map((pane) => pane.hidden)).toEqual([false, true]);
  expect(await screen.findByText("카드 30,350장 · 스냅샷 2026-10-06")).toBeTruthy();
});

it.each([
  ["#8d", "8d"], ["", "landing"], ["#search", "casebook"],
])("주소 해시가 %s로 바뀌면(hashchange) %s 화면을 보인다", async (hash, expected) => {
  render(<App />);
  goTo(`/${hash}`);
  expect(!!openCasebookButton()).toBe(expected === "landing");
  expect(panes().map((pane) => !pane.hidden)).toEqual([expected === "casebook", expected === "8d"]);
});

it("케이스북의 뒤로 가기 단추로 랜딩에 돌아오면 Open casebook에 초점이 가고 해시가 비워진다", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(openCasebookButton()!);
  await user.click(screen.getByRole("button", { name: "시작 화면으로" }));
  expect(location.hash).toBe("");
  expect(document.activeElement).toBe(openCasebookButton());
});

it("체크한 선례로 8D를 열면 선례가 넘어가고, 케이스북으로 돌아와도 검색 결과가 남으며, 선례 없이 열면 입력창의 질문이 SUBJECT가 된다", async () => {
  const user = userEvent.setup();
  history.replaceState(null, "", "/#casebook");
  render(<App />);
  await user.type(question(), "airbag inflator rupture");
  await user.click(screen.getByRole("button", { name: "Find precedents" }));
  await user.click(await screen.findByRole("button", { name: new RegExp(card.campno) }));
  await user.click(screen.getByRole("button", { name: /^Write 8D from checked \(1\)/ }));

  expect(location.hash).toBe("#8d");
  expect(panes().map((pane) => pane.hidden)).toEqual([true, false]);
  expect(screen.getByText("8D 근거로 담은 선례 1건")).toBeTruthy();
  expect(screen.getByText(card.campno, { selector: ".ed-chip" })).toBeTruthy();

  await user.click(screen.getByRole("button", { name: "← 케이스북으로" }));
  expect(location.hash).toBe("#casebook");
  expect(panes().map((pane) => pane.hidden)).toEqual([false, true]);
  expect(question().value).toBe("airbag inflator rupture"); // 입력도
  expect(screen.getByRole("complementary", { name: "Search results" })).toBeTruthy(); // 검색 결과도 남는다

  await user.clear(question());
  await user.type(question(), "a different defect line");
  await user.click(screen.getByRole("button", { name: /^Write 8D without precedents/ }));
  expect(screen.getByText("담은 선례 없음 — 선례 없이 작성합니다")).toBeTruthy();
  expect((screen.getByRole("textbox", { name: "SUBJECT" }) as HTMLInputElement).value).toBe("a different defect line");
});

it("3D 쇼룸에서 넘긴 질문은 케이스북 입력창을 채우고 초점을 주지만 자동으로 검색하지는 않는다", async () => {
  const user = userEvent.setup();
  history.replaceState(null, "", "/#showroom");
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "fake showroom search" }));
  expect(location.hash).toBe("#casebook");
  expect(question().value).toBe("steering rack noise");
  expect(document.activeElement).toBe(question());
  expect(search).not.toHaveBeenCalled();
});

it("3D 쇼룸 코드를 받지 못하면 안내를 띄우고, 케이스북으로 단추는 해시를 케이스북으로 바꾼다", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {}); // React가 잡힌 오류도 콘솔에 남긴다
  showroom.fail = true;
  const user = userEvent.setup();
  history.replaceState(null, "", "/#showroom");
  render(<App />);
  expect((await screen.findByRole("alert")).textContent).toContain("3D 쇼룸을 불러오지 못했습니다.");
  await user.click(screen.getByRole("button", { name: "케이스북으로" }));
  expect(location.hash).toBe("#casebook");
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull()); // 브라우저가 알린 hashchange로 케이스북이 열린다
  expect(panes()[0].hidden).toBe(false);
});

it("서버 판본을 받지 못하면 앱 바가 그렇게 알리고, 화면이 사라지면 판본 요청을 취소한다", async () => {
  history.replaceState(null, "", "/#casebook");
  vi.mocked(health).mockRejectedValueOnce(new Error("down"));
  const failed = render(<App />);
  expect(await screen.findAllByText("서버 판본을 받지 못했습니다")).not.toHaveLength(0);
  failed.unmount();

  vi.mocked(health).mockReturnValue(new Promise(() => {}));
  const pending = render(<App />);
  const signal = vi.mocked(health).mock.calls.at(-1)![0]!;
  expect(signal.aborted).toBe(false);
  pending.unmount();
  expect(signal.aborted).toBe(true);
});
