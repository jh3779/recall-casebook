// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, draft, search } from "../api";
import type { DraftItem, DraftResponse } from "../eightd/draft";
import health from "../search/__fixtures__/health.json";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type Card, type HealthResponse, type SearchResponse, type TextCause } from "../search/types";
import CasebookView from "./CasebookView";
import { EXAMPLES } from "./examples";
import { QUESTION_POOL } from "./questions";

// 네트워크는 부르지 않는다 — 검색(search)·묶기(draft)만 가짜로 바꾸고 ApiError 등 나머지는 실제 것을 쓴다
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), search: vi.fn(), draft: vi.fn() }));

const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const withText = cards.filter((c) => hasCauseText(c.cause));
const [A, B, C] = withText;
const serverHealth = health as HealthResponse;

beforeEach(() => { localStorage.clear(); vi.mocked(search).mockResolvedValue(response); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.mocked(search).mockReset(); vi.mocked(draft).mockReset(); });

const question = () => screen.getByRole("textbox", { name: "Defect description in English" }) as HTMLInputElement;
const caseInput = () => screen.getByRole("textbox", { name: "Case name" }) as HTMLInputElement;
const find = () => screen.getByRole("button", { name: "Find precedents" });
const row = (card: Card) => document.querySelector<HTMLElement>(`[data-campno="${card.campno}"]`)!;
const memo = () => screen.getAllByPlaceholderText("Your note on this precedent") as HTMLTextAreaElement[];
const d4Root = () => screen.getByPlaceholderText("The service does not fill or suggest this") as HTMLTextAreaElement;
const statuses = () => screen.getAllByRole("status").map((el) => el.textContent ?? "");
const unloadPrevented = () => { const e = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; };

function setup(props: Partial<React.ComponentProps<typeof CasebookView>> = {}) {
  const user = userEvent.setup();
  const view = render(<CasebookView health={serverHealth} {...props} />);
  return { user, ...view };
}
async function searchAndCheck(user: ReturnType<typeof userEvent.setup>, ...picked: Card[]) {
  await user.type(question(), "airbag inflator rupture");
  await user.click(find());
  await screen.findByRole("complementary", { name: "Search results" });
  for (const card of picked) await user.click(row(card));
}
const draftItem = (card: Card): DraftItem => {
  const cause = card.cause as TextCause;
  return { campno: card.campno, field: "cause", quote: cause.text, start: 0, end: cause.text.length, speaker: cause.speaker, cause_status: cause.status, cause_source: cause.source };
};
const draftResponse = (over: Partial<DraftResponse> = {}): DraftResponse => ({
  build_id: response.build_id, bundle_sha256: response.bundle_sha256, snapshot_date: response.snapshot_date, question: response.question, step: "d4",
  titles_generated: true, model: "test-model", degraded: null, groups: [], ungrouped: [], questions: [], rejected: {}, ...over,
});

// ---- 묶기(GroupPanel)와 체크 변경 배선 (#154 묶기 성공 경로 · #159 GroupResult 라벨·CasebookView togglePicked) ----
it("묶기가 성공하면 묶음·말한 주체·출처가 보이고 탈락 라벨·고른 확인 질문이 나온다. 체크를 바꾸면 모두 걷히고, 같은 조합으로 돌아와도 되살아나지 않는다", async () => {
  const { user } = setup();
  await searchAndCheck(user, A, B);
  vi.mocked(draft).mockResolvedValue(draftResponse({
    groups: [{ title: "hidden title", items: [draftItem(A), draftItem(B)] }],
    picked_questions: [{ id: "P3", text: "model text is ignored" }, { id: "P99", text: "not in the pool" }],
    rejected: { not_in_source: 1, unknown_question: 2, bad_title: 4 },
  }));
  await user.click(screen.getByRole("button", { name: "Group the checked causes" }));

  const group = await screen.findByRole("article", { name: "Group 1" });
  expect(vi.mocked(draft).mock.calls[0].slice(0, 3)).toEqual([response.question, [A.campno, B.campno], "d4"]);
  expect([...group.querySelectorAll("q")].map((q) => q.textContent)).toEqual([(A.cause as TextCause).text, (B.cause as TextCause).text]); // 인용은 원문 그대로
  expect(group.textContent).toContain(`Said by ${(A.cause as TextCause).speaker}`);
  expect(group.textContent).toContain(`sha256 ${(A.cause as TextCause).source.pdf_sha256}`);
  expect(screen.queryByText("hidden title")).toBeNull(); // 묶음 제목은 보이지 않는다
  expect(screen.getByText("Excluded by the server's checks: not in the source 1 · question id not in the fixed list 2.")).toBeTruthy(); // bad_title은 라벨에서 뺀다
  expect(screen.getByText(`model test-model · build ${response.build_id}`)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Group again" })).toBeTruthy();
  // 모델이 고른 번호는 D4 구역에 풀의 문장으로 가고, 풀에 없는 번호는 버린다
  expect(screen.getByRole("heading", { name: /Picked by the model/ })).toBeTruthy();
  expect(screen.getByText(new RegExp(QUESTION_POOL.P3.slice(0, 20)))).toBeTruthy();
  expect(screen.queryByText(/model text is ignored|P99/)).toBeNull();

  await user.click(row(C)); // 체크한 선례가 바뀌면 묶음이 걷히고 모델이 고른 질문도 걷힌다
  expect(screen.queryByRole("article", { name: "Group 1" })).toBeNull();
  expect(screen.queryByRole("heading", { name: /Picked by the model/ })).toBeNull();
  expect(screen.getByRole("button", { name: "Group the checked causes" })).toBeTruthy();
  await user.click(row(C)); // 처음과 같은 조합(A, B)으로 돌아와도
  expect(screen.queryByRole("heading", { name: /Picked by the model/ })).toBeNull();
  expect(screen.queryByRole("article", { name: "Group 1" })).toBeNull();
});

it("묶기가 실패하면 종류별 영어 안내를 보이고 모델이 고른 질문을 남기지 않는다 (판본 불일치·호출 상한·404)", async () => {
  const { user } = setup();
  await searchAndCheck(user, A);
  const button = () => screen.getByRole("button", { name: "Group the checked causes" });
  vi.mocked(draft).mockResolvedValueOnce(draftResponse({ build_id: "another-build", groups: [{ title: "t", items: [draftItem(A)] }], picked_questions: [{ id: "P1", text: "" }] }));
  await user.click(button());
  expect((await screen.findByRole("alert")).textContent).toBe("The server data version changed since the search. Search again.");
  expect(screen.queryByRole("article", { name: "Group 1" })).toBeNull();
  expect(screen.queryByRole("heading", { name: /Picked by the model/ })).toBeNull();

  vi.mocked(draft).mockRejectedValueOnce(new ApiError("rate_limit", "x", 429, undefined, 30));
  await user.click(button());
  expect((await screen.findByText("Too many requests. Try again in 30 seconds.")).getAttribute("role")).toBe("alert");

  vi.mocked(draft).mockRejectedValueOnce(new ApiError("server", "x", 404));
  await user.click(button());
  expect((await screen.findByText("Grouping is not available on this server.")).getAttribute("role")).toBe("alert");
});

// ---- 검색 흐름 (#165 예시 질문·요청 취소·3초 안내·호출 상한) ----
it("예시 질문 단추는 입력창을 채우고 그 질문으로 바로 검색한다", async () => {
  const { user } = setup();
  await user.click(screen.getByRole("button", { name: EXAMPLES[1] }));
  expect(question().value).toBe(EXAMPLES[1]);
  expect(vi.mocked(search).mock.calls[0][0]).toBe(EXAMPLES[1]);
  expect(await screen.findByRole("complementary", { name: "Search results" })).toBeTruthy();
  expect(screen.queryByText("Example questions")).toBeNull();
});

it("진행 중인 검색은 새 질문(쇼룸에서 온 draft)이 오면 취소되고, 늦게 도착한 이전 응답은 새 질문 밑에 들어가지 않는다 (useLayoutEffect abort 배선)", async () => {
  let release!: (value: SearchResponse) => void;
  vi.mocked(search).mockReturnValue(new Promise((resolve) => { release = resolve; }));
  const { user, rerender } = setup();
  await user.type(question(), "old question");
  await user.click(find());
  expect(screen.getByRole("button", { name: "Searching…" }).hasAttribute("disabled")).toBe(true);
  const signal = vi.mocked(search).mock.calls[0][1]!;
  expect(signal.aborted).toBe(false);

  rerender(<CasebookView health={serverHealth} draft={{ question: "new question from the showroom", key: 1 }} />);
  expect(signal.aborted).toBe(true); // 새 질문이 오는 커밋에서 이전 요청을 취소했다
  expect(question().value).toBe("new question from the showroom");
  expect(document.activeElement).toBe(question()); // 입력창에 초점이 간다
  expect(find().hasAttribute("disabled")).toBe(false); // 로딩 상태도 비웠다
  expect(screen.getByText("Example questions")).toBeTruthy();

  await act(async () => { release(response); }); // 취소를 무시하고 늦게 끝난 이전 응답
  expect(screen.queryByRole("complementary", { name: "Search results" })).toBeNull();
  expect(screen.getByText("Example questions")).toBeTruthy();
});

it("3초가 지나도 응답이 없으면 서버가 깨어나는 중이라고 알리고, 호출 상한(429)이면 남은 초 동안 검색·Retry를 막다가 끝나면 푼다", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(1_000_000);
  let reject!: (reason: unknown) => void;
  vi.mocked(search).mockReturnValue(new Promise((_, no) => { reject = no; }));
  setup();
  fireEvent.change(question(), { target: { value: "brake fluid leak" } });
  fireEvent.click(find());
  expect(document.querySelector("p.cb-empty[role=status]")!.textContent).toBe("Searching…");
  act(() => { vi.advanceTimersByTime(2999); });
  expect(screen.queryByText(/The server may be waking up/)).toBeNull();
  act(() => { vi.advanceTimersByTime(1); });
  expect(screen.getByText(/The server may be waking up/)).toBeTruthy();

  await act(async () => { reject(new ApiError("rate_limit", "x", 429, undefined, 3)); });
  act(() => { vi.advanceTimersByTime(0); }); // 남은 초를 읽는 첫 틱
  expect(screen.getByRole("alert").textContent).toBe("Too many requests.");
  expect(screen.getByText("3s left")).toBeTruthy();
  const retry = () => screen.getByRole("button", { name: /^Retry/ });
  expect(retry().hasAttribute("disabled")).toBe(true);
  expect(find().hasAttribute("disabled")).toBe(true);
  act(() => { vi.advanceTimersByTime(1000); });
  expect(screen.getByText("2s left")).toBeTruthy();
  act(() => { vi.advanceTimersByTime(2000); });
  expect(retry().hasAttribute("disabled")).toBe(false);
  expect(find().hasAttribute("disabled")).toBe(false);
  expect(screen.getByText("You can search again.")).toBeTruthy();
});

it("이름 없이 적은 메모가 있으면 다시 검색할 때 확인하고, 거절하면 검색하지 않고 메모를 남기며, 승인하면 새 결과가 온 뒤 비운다", async () => {
  const confirm = vi.fn(() => false);
  vi.stubGlobal("confirm", confirm);
  const { user } = setup();
  await searchAndCheck(user, A);
  await user.type(memo()[0], "my note");
  await user.click(find());
  expect(confirm).toHaveBeenCalledWith("Notes and D4 text without a case name will be discarded when you search again. Continue?");
  expect(search).toHaveBeenCalledTimes(1);
  expect(memo()[0].value).toBe("my note");

  confirm.mockReturnValue(true);
  await user.click(find());
  expect(search).toHaveBeenCalledTimes(2);
  await screen.findByRole("complementary", { name: "Search results" });
  expect(screen.getByText("Check precedents on the left. Each one stacks here with its original wording, who said it, and the report it came from.")).toBeTruthy(); // 체크도 비었다
  await user.click(row(A));
  expect(memo()[0].value).toBe(""); // 메모도 비었다
});

// ---- 메모·D4 글 저장 (#159 D4 키 합치기·안내 상태, #154 사건 이름·저장 실패·삭제 실패) ----
it("사건 이름을 정하기 전 쓴 메모와 D4 글은 탭에만 있다는 안내와 이탈 경고를 보이고, 이름을 정하면 같은 사건 이름 아래 함께 저장한다", async () => {
  const { user } = setup();
  await searchAndCheck(user, A);
  await user.type(memo()[0], "memo one");
  await user.type(d4Root(), "root one");
  expect(statuses().filter((s) => s.startsWith("No case name"))).toHaveLength(2); // 메모 구역과 D4 구역 둘 다
  expect(unloadPrevented()).toBe(true);
  expect(localStorage.length).toBe(0);

  await user.type(caseInput(), "Case A{Enter}");
  expect(localStorage.getItem(`casebook.note.v1|Case%20A|${A.campno}`)).toBe("memo one");
  expect(localStorage.getItem("casebook.note.v1|Case%20A|@d4:root")).toBe("root one"); // 메모와 D4 글이 한 사건 아래 합쳐진다
  expect(statuses().filter((s) => s.startsWith("Saved in this browser under “Case A”"))).toHaveLength(2);
  expect(unloadPrevented()).toBe(false);
});

it("사건 이름을 바꾸면 그 사건의 메모와 D4 글로 바뀌고, 돌아오면 복원되며, 사건 지우기는 확인 뒤 저장분까지 지운다", async () => {
  localStorage.setItem(`casebook.note.v1|Case%20A|${A.campno}`, "stored memo");
  localStorage.setItem("casebook.note.v1|Case%20A|@d4:root", "stored root");
  const confirm = vi.fn(() => false);
  vi.stubGlobal("confirm", confirm);
  const { user } = setup();
  await searchAndCheck(user, A);
  await user.type(caseInput(), "Case A{Enter}");
  expect(memo()[0].value).toBe("stored memo");
  expect(d4Root().value).toBe("stored root");

  await user.clear(caseInput());
  await user.type(caseInput(), "Case B{Enter}");
  expect(memo()[0].value).toBe("");
  expect(d4Root().value).toBe("");
  await user.clear(caseInput());
  await user.type(caseInput(), "Case A{Enter}");
  expect(memo()[0].value).toBe("stored memo");
  expect(d4Root().value).toBe("stored root");

  const clear = screen.getByRole("button", { name: "Clear notes and D4 text of this case" });
  await user.click(clear); // 거절하면 그대로
  expect(confirm).toHaveBeenLastCalledWith("Delete all notes and D4 text saved under “Case A”?");
  expect(memo()[0].value).toBe("stored memo");
  confirm.mockReturnValue(true);
  await user.click(clear);
  expect(memo()[0].value).toBe("");
  expect(d4Root().value).toBe("");
  expect(localStorage.getItem(`casebook.note.v1|Case%20A|${A.campno}`)).toBeNull();
  expect(localStorage.getItem("casebook.note.v1|Case%20A|@d4:root")).toBeNull();
});

it("저장에 실패하면 저장됐다고 말하지 않고 이탈을 경고하며, 지우기에 실패하면 화면 글을 되돌리고 알린다", async () => {
  const { user } = setup();
  await searchAndCheck(user, A);
  await user.type(caseInput(), "Case A{Enter}");
  const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  await user.type(memo()[0], "x");
  expect(statuses().filter((s) => s.startsWith("This browser could not save the notes"))).toHaveLength(2);
  expect(unloadPrevented()).toBe(true);
  set.mockRestore();
  await user.type(memo()[0], "y"); // 다시 저장되면 경고가 걷힌다
  expect(localStorage.getItem(`casebook.note.v1|Case%20A|${A.campno}`)).toBe("xy");
  expect(statuses().filter((s) => s.startsWith("Saved in this browser under “Case A”"))).toHaveLength(2);
  expect(unloadPrevented()).toBe(false);

  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
  await user.clear(memo()[0]);
  expect(memo()[0].value).toBe("xy"); // 저장소에서 못 지웠으면 화면도 그대로 둔다(새로고침하면 되살아날 글)
  expect(screen.getAllByText("Could not delete the saved note — it may remain in this browser.").length).toBeGreaterThan(0);
  expect(unloadPrevented()).toBe(false); // 삭제 실패는 "잃는다"는 경고가 아니다
});

it("한글 입력기로 조합하는 중의 Enter는 사건 이름을 확정하지 않고, 조합이 끝난 Enter만 확정한다 (실제 입력기 확인은 따로 필요)", async () => {
  const { user } = setup();
  await searchAndCheck(user, A);
  fireEvent.change(caseInput(), { target: { value: "사건" } });
  fireEvent.keyDown(caseInput(), { key: "Enter", isComposing: true, keyCode: 13 }); // 조합 중임을 isComposing으로 알리는 브라우저
  fireEvent.keyDown(caseInput(), { key: "Enter", isComposing: false, keyCode: 229 }); // keyCode 229로만 알리는 브라우저
  expect(statuses().filter((s) => s.startsWith("No case name"))).toHaveLength(2); // 아직 이름이 없다
  fireEvent.keyDown(caseInput(), { key: "Enter", isComposing: false, keyCode: 13 });
  expect(statuses().filter((s) => s.startsWith("Saved in this browser under “사건”"))).toHaveLength(2);
});
