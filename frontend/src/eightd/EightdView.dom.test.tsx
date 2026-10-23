// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { draft } from "../api";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type Card, type SearchResponse, type TextCause } from "../search/types";
import type { DraftResponse } from "./draft";
import EightdView from "./EightdView";

// 묶음 초안(/draft)만 가짜로 바꾼다 — 네트워크는 부르지 않는다
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), draft: vi.fn() }));

const response = fixture as SearchResponse;
const [A, B] = [...response.customer_precedents, ...response.precedents].filter((c) => hasCauseText(c.cause));

afterEach(() => { cleanup(); vi.mocked(draft).mockReset(); vi.restoreAllMocks(); });

const bodyBox = () => screen.getByPlaceholderText(/D4 선례 참고에서 넣은 타사 원인 원문이 여기 들어갑니다/) as HTMLTextAreaElement;
const appendixBox = () => screen.getByPlaceholderText(/D4 선례 참고에서 넣은 타사 원인 원문이 부록에도 한 번 더 들어갑니다/) as HTMLTextAreaElement;
const d2Box = () => screen.getByPlaceholderText(/6하 원칙/) as HTMLTextAreaElement;
const insertButton = (card: Card) => within(screen.getByRole("article", { name: `선례 ${card.campno}` })).getByRole("button");
const quote = (card: Card) => `[타사 선례 ${card.campno} `;
const total = () => screen.getByText(/^D4에 넣은 선례 항목 \d+건$/).textContent;
const message = () => document.querySelector(".ed-bar p.note")!.textContent;
const draftOf = (cards: readonly Card[], res: SearchResponse | null = response, extra: { fresh?: number; freshQuestion?: string } = {}) =>
  <EightdView cards={cards} response={res} onBack={() => {}} {...extra} />;

// ---- D4 선례 삽입 (#167: toggleBoth 연결 · EightdView가 D4Reference를 조립하는 부분) ----
it("선례 버튼 하나가 D4 칸 본문과 부록에 함께 넣고, 다시 누르면 둘 다에서 뺀다 — 넣은 건수·넣음 표시·눌림 상태가 함께 바뀐다", async () => {
  const user = userEvent.setup();
  render(draftOf([A, B]));
  expect(bodyBox().value).toBe("");
  expect(appendixBox().value).toBe("");
  expect(total()).toBe("D4에 넣은 선례 항목 0건");
  expect(insertButton(A).getAttribute("aria-pressed")).toBe("false"); // 눌러야만 들어간다

  await user.click(insertButton(A));
  expect(bodyBox().value).toContain(quote(A));
  expect(appendixBox().value).toContain(quote(A));
  expect(bodyBox().value).not.toContain(quote(B));
  expect(total()).toBe("D4에 넣은 선례 항목 1건");
  expect(screen.getByText("넣음 1건")).toBeTruthy();
  expect(insertButton(A).getAttribute("aria-pressed")).toBe("true");
  expect(insertButton(A).textContent).toBe("D4 본문·부록에 넣음 ✓ (다시 누르면 뺌)");
  expect(message()).toContain("“[타사 선례 번호 · 회사 · 접수일]”"); // 넣었으면 출처 표시 안내가 뜬다

  await user.click(insertButton(B));
  expect(bodyBox().value.indexOf(quote(A))).toBeLessThan(bodyBox().value.indexOf(quote(B)));
  expect(appendixBox().value).toContain(quote(B));
  expect(total()).toBe("D4에 넣은 선례 항목 2건");

  await user.click(insertButton(A)); // 다시 누르면 뺀다
  for (const box of [bodyBox(), appendixBox()]) { expect(box.value).not.toContain(quote(A)); expect(box.value).toContain(quote(B)); }
  expect(total()).toBe("D4에 넣은 선례 항목 1건");
  expect(insertButton(A).getAttribute("aria-pressed")).toBe("false");

  await user.click(screen.getByRole("button", { name: "텍스트" })); // 넣은 선례가 있으면 파일 글 끝에 근거 데이터 한 줄이 붙고, 모두 빼면 붙지 않는다
  const text = () => document.querySelector("pre.ev-text.paper")!.textContent!;
  expect(text()).toContain(`※ 선례 근거 데이터: build ${response.build_id}`);
  await user.click(insertButton(B));
  expect(text()).not.toContain("※ 선례 근거 데이터");
});

it("묶음 초안의 묶음·확인 질문도 같은 방식으로 D4 본문과 부록에 함께 들어가고 다시 누르면 빠진다 (D4Reference → DraftPanel 연결)", async () => {
  const user = userEvent.setup();
  const cause = A.cause as TextCause;
  const result: DraftResponse = {
    build_id: response.build_id, bundle_sha256: response.bundle_sha256, snapshot_date: response.snapshot_date, question: response.question, step: "d4",
    titles_generated: true, model: "test-model", degraded: null, ungrouped: [], rejected: {}, questions: ["QUESTION-ONE?"],
    groups: [{ title: "hidden title", items: [{ campno: A.campno, field: "cause", quote: cause.text, start: 0, end: cause.text.length, speaker: cause.speaker, cause_status: cause.status, cause_source: cause.source }] }],
  };
  vi.mocked(draft).mockResolvedValue(result);
  render(draftOf([A]));
  await user.click(screen.getByRole("button", { name: "묶음 초안 만들기" }));
  const group = await screen.findByRole("article", { name: "묶음 1" });
  expect(vi.mocked(draft).mock.calls[0].slice(0, 3)).toEqual([response.question, [A.campno], "d4"]);
  expect(screen.queryByText("hidden title")).toBeNull();
  expect(total()).toBe("D4에 넣은 선례 항목 0건");

  await user.click(within(group).getByRole("button"));
  for (const box of [bodyBox(), appendixBox()]) { expect(box.value).toContain(quote(A)); expect(box.value).toContain(cause.text); expect(box.value).not.toContain("hidden title"); }
  expect(within(group).getByRole("button").textContent).toBe("D4 본문·부록에 넣음 ✓ (다시 누르면 뺌)");
  expect(total()).toBe("D4에 넣은 선례 항목 1건");

  const questions = screen.getByRole("article", { name: "확인 질문" });
  await user.click(within(questions).getByRole("button"));
  for (const box of [bodyBox(), appendixBox()]) expect(box.value).toContain("QUESTION-ONE?");
  expect(total()).toBe("D4에 넣은 선례 항목 2건");

  await user.click(within(group).getByRole("button")); // 묶음만 뺀다
  for (const box of [bodyBox(), appendixBox()]) { expect(box.value).not.toContain(cause.text); expect(box.value).toContain("QUESTION-ONE?"); }
  expect(total()).toBe("D4에 넣은 선례 항목 1건");
});

it("넣은 인용을 직접 고쳤으면 자동으로 빼지 않고 칸에서 직접 지우라고 알린다", async () => {
  const user = userEvent.setup();
  render(draftOf([A]));
  await user.click(insertButton(A));
  await user.clear(bodyBox());
  await user.type(bodyBox(), "my own words");
  await user.click(insertButton(A));
  expect(message()).toBe("직접 고친 글이라 자동으로 뺄 수 없는 곳이 있습니다. 그 칸에서 직접 지워 주세요.");
  expect(bodyBox().value).toBe("my own words"); // 고친 글은 지우지 않는다
  expect(appendixBox().value).toBe(""); // 그대로인 부록 쪽은 뺀다
});

it("담은 선례가 줄어든 채 돌아오면 더는 담지 않은 선례의 인용만 본문과 부록에서 걷어 내고 그 사실을 알린다", async () => {
  const user = userEvent.setup();
  const view = render(draftOf([A, B]));
  await user.click(insertButton(A));
  await user.click(insertButton(B));
  view.rerender(draftOf([A]));
  for (const box of [bodyBox(), appendixBox()]) { expect(box.value).toContain(quote(A)); expect(box.value).not.toContain(quote(B)); }
  expect(message()).toMatch(/^담지 않은 선례의 인용 \d+건을 본문에서 뺐습니다\./);
  expect(screen.getByText("8D 근거로 담은 선례 1건")).toBeTruthy();
  expect(total()).toBe("D4에 넣은 선례 항목 1건");
});

// ---- 렌더 중 상태 보정 (#145 9: 두 번 걷어 내기·쓴 글 보존 확인) ----
it("질문이 바뀐 검색 결과로 돌아오면 쓴 글은 남기고 알린다 — 이어서 쓰기는 안내만 닫고, 새로 시작은 글을 비운다", async () => {
  const user = userEvent.setup();
  const view = render(draftOf([], response));
  await user.type(d2Box(), "D2-NOTE");
  expect(screen.queryByRole("alert")).toBeNull();

  view.rerender(draftOf([], { ...response, question: "a different question" }));
  expect(screen.getByRole("alert").textContent).toMatch(/^질문이 바뀌었습니다\. 이전 질문의 선례 인용은 뺐지만, 이전에 쓴 글은 남아 있습니다/);
  expect(d2Box().value).toBe("D2-NOTE"); // 쓴 글을 말없이 지우지 않는다
  await user.click(screen.getByRole("button", { name: "이어서 쓰기" }));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(d2Box().value).toBe("D2-NOTE");

  view.rerender(draftOf([], { ...response, question: "yet another question" }));
  await user.click(screen.getByRole("button", { name: "이전 작업 비우고 새로 시작" }));
  expect(d2Box().value).toBe("");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(message()).toBe("이전 작업을 비우고 새로 시작했습니다.");
});

it("같은 질문의 검색 결과가 다시 와도 알림을 띄우지 않고, '선례 없이 새로 시작'을 누르면 쓴 글이 있을 때만 묻고 SUBJECT를 새 질문으로 바꾼다", async () => {
  const user = userEvent.setup();
  const view = render(draftOf([], response));
  await user.type(d2Box(), "D2-NOTE");
  view.rerender(draftOf([], { ...response })); // 같은 질문·같은 판본
  expect(screen.queryByRole("alert")).toBeNull();

  view.rerender(draftOf([], response, { fresh: 1, freshQuestion: "brand new question" }));
  expect(screen.getByRole("alert").textContent).toMatch(/^새로 시작했지만 이전에 쓴 글은 남아 있습니다/);
  expect((screen.getByRole("textbox", { name: "SUBJECT" }) as HTMLInputElement).value).toBe("brand new question");
  expect(d2Box().value).toBe("D2-NOTE");
  await user.click(screen.getByRole("button", { name: "이전 작업 비우고 새로 시작" }));
  expect(d2Box().value).toBe("");

  const clean = render(draftOf([], null)); // 쓴 글이 없으면 묻지 않는다
  clean.rerender(draftOf([], null, { fresh: 1, freshQuestion: "another" }));
  expect(within(clean.container).queryByRole("alert")).toBeNull();
});

// ---- 적용할 단계·미리보기·복사 (#145 화면 연결) ----
it("단계를 빼도 쓴 글은 남고 미리보기·복사에서만 빠지며, 다시 적용하면 돌아온다. 복사 글은 미리보기와 같다", async () => {
  const user = userEvent.setup();
  render(draftOf([]));
  await user.type(d2Box(), "D2-NOTE");
  await user.click(screen.getByRole("button", { name: "텍스트" }));
  const text = () => document.querySelector("pre.ev-text.paper")!.textContent!;
  expect(text()).toContain("D2-NOTE");

  await user.click(screen.getByRole("button", { name: "D2" }));
  expect(screen.getByRole("button", { name: "D2" }).getAttribute("aria-pressed")).toBe("false");
  expect(screen.queryByPlaceholderText(/6하 원칙/)).toBeNull();
  expect(text()).not.toContain("D2-NOTE");
  expect(text()).not.toContain("DISCIPLINE 2");

  await user.click(screen.getByRole("button", { name: "적용하기" }));
  expect(d2Box().value).toBe("D2-NOTE"); // 써 둔 글은 그대로였다
  expect(text()).toContain("D2-NOTE");

  await user.click(screen.getByRole("button", { name: "D4만" }));
  const pressed = [1, 2, 3, 4, 5, 6, 7, 8].filter((n) => screen.getByRole("button", { name: `D${n}` }).getAttribute("aria-pressed") === "true");
  expect(pressed).toEqual([4]);
  expect(text()).not.toContain("D2-NOTE");
  await user.click(screen.getByRole("button", { name: "전체" }));
  expect(text()).toContain("D2-NOTE");

  await user.click(screen.getByRole("button", { name: "파일 글 복사" }));
  expect(await navigator.clipboard.readText()).toBe(text());
  expect(message()).toBe("파일에 들어갈 글을 클립보드에 복사했습니다.");
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
  await user.click(screen.getByRole("button", { name: "파일 글 복사" }));
  expect(await screen.findByText("복사하지 못했습니다. 아래 미리보기에서 직접 선택해 복사해 주세요.")).toBeTruthy();
});
