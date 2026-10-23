// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { draft } from "../api";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type Card, type SearchResponse } from "../search/types";
import type { DraftResponse } from "./draft";
import EightdView from "./EightdView";

// 묶음 초안(/draft)만 가짜로 바꾼다 — 네트워크는 부르지 않는다
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), draft: vi.fn() }));

// 이슈 #145(7)·#167(선례 한 건을 빼도 "2건") 후속
const response = fixture as SearchResponse;
const [A] = [...response.customer_precedents, ...response.precedents].filter((c) => hasCauseText(c.cause));

afterEach(() => { cleanup(); vi.mocked(draft).mockReset(); });

const view = (cards: readonly Card[], res: SearchResponse | null = response) => <EightdView cards={cards} response={res} onBack={() => {}} />;
const subjectInput = () => screen.getByRole("textbox", { name: "SUBJECT" }) as HTMLInputElement;
const message = () => document.querySelector(".ed-bar p.note")!.textContent;

it("SUBJECT만 직접 고쳤어도 질문이 바뀐 검색 결과로 돌아오면 알린다 — 고친 SUBJECT가 새 질문을 가리고 있다 (#145 7)", async () => {
  const user = userEvent.setup();
  const rendered = render(view([]));
  await user.clear(subjectInput());
  await user.type(subjectInput(), "my own subject");
  expect(screen.queryByRole("alert")).toBeNull();

  rendered.rerender(view([], { ...response, question: "a different question" }));
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toMatch(/^질문이 바뀌었습니다\. 이전 질문의 선례 인용은 뺐지만, 직접 고친 SUBJECT가 그대로 남아 있습니다/);
  expect(alert.textContent).not.toContain("이전에 쓴 글"); // 쓴 글은 없다 — SUBJECT만 남은 경우에 맞는 문구
  expect(subjectInput().value).toBe("my own subject"); // 말없이 지우지 않는다

  await user.click(screen.getByRole("button", { name: "이전 작업 비우고 새로 시작" }));
  expect(subjectInput().value).toBe("a different question"); // 비우면 새 질문이 SUBJECT가 된다
  expect(screen.queryByRole("alert")).toBeNull();
});

it("아무것도 고치지 않았으면 질문이 바뀌어도 알리지 않고 SUBJECT가 새 질문을 따른다", () => {
  const rendered = render(view([]));
  rendered.rerender(view([], { ...response, question: "a different question" }));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(subjectInput().value).toBe("a different question");
});

it("선례 한 건을 D4 본문과 부록에 넣었다가 담은 목록에서 빠지면 '2건'이 아니라 선례 1건으로 알린다 (#167)", async () => {
  const user = userEvent.setup();
  const rendered = render(view([A]));
  await user.click(within(screen.getByRole("article", { name: `선례 ${A.campno}` })).getByRole("button"));
  expect(screen.getByText(/^D4에 넣은 선례 항목 1건$/)).toBeTruthy();

  rendered.rerender(view([]));
  expect(message()).toMatch(/^담지 않은 선례의 인용 1건을 본문에서 뺐습니다\./);
});

it("넣은 인용을 직접 고친 뒤 담은 목록에서 빠지면 못 뺀 것도 선례 1건으로 센다", async () => {
  const user = userEvent.setup();
  const rendered = render(view([A]));
  await user.click(within(screen.getByRole("article", { name: `선례 ${A.campno}` })).getByRole("button"));
  for (const box of screen.getAllByPlaceholderText(/D4 선례 참고에서 넣은 타사 원인 원문이/)) { await user.clear(box); await user.type(box, "my words"); }

  rendered.rerender(view([]));
  expect(message()).toMatch(/직접 고친 글이라 자동으로 못 뺀 1건은 칸에서 직접 지워 주세요/);
});

it("'선례 없이 새로 시작'으로 질문만 바꿔 열 때 걷히는 확인 질문도 본문·부록 한 쌍을 1건으로 알린다", async () => {
  const user = userEvent.setup();
  const result: DraftResponse = {
    build_id: response.build_id, bundle_sha256: response.bundle_sha256, snapshot_date: response.snapshot_date, question: response.question, step: "d4",
    titles_generated: true, model: "test-model", degraded: null, groups: [], ungrouped: [], rejected: {}, questions: ["QUESTION-ONE?"],
  };
  vi.mocked(draft).mockResolvedValue(result);
  const rendered = render(<EightdView cards={[A]} response={response} onBack={() => {}} />);
  await user.click(screen.getByRole("button", { name: "묶음 초안 만들기" }));
  await user.click(within(await screen.findByRole("article", { name: "확인 질문" })).getByRole("button"));
  expect(screen.getByText(/^D4에 넣은 선례 항목 1건$/)).toBeTruthy();

  rendered.rerender(<EightdView cards={[A]} response={response} fresh={1} freshQuestion="a brand new question" onBack={() => {}} />);
  expect(message()).toMatch(/^이전 질문의 인용·확인 질문 1건을 뺐습니다\./);
});

it("확인 질문을 직접 고친 뒤 질문만 바꿔 열면 못 뺀 것도 1건으로 알린다", async () => {
  const user = userEvent.setup();
  vi.mocked(draft).mockResolvedValue({
    build_id: response.build_id, bundle_sha256: response.bundle_sha256, snapshot_date: response.snapshot_date, question: response.question, step: "d4",
    titles_generated: true, model: "test-model", degraded: null, groups: [], ungrouped: [], rejected: {}, questions: ["QUESTION-ONE?"],
  });
  const rendered = render(<EightdView cards={[A]} response={response} onBack={() => {}} />);
  await user.click(screen.getByRole("button", { name: "묶음 초안 만들기" }));
  await user.click(within(await screen.findByRole("article", { name: "확인 질문" })).getByRole("button"));
  for (const box of screen.getAllByPlaceholderText(/D4 선례 참고에서 넣은 타사 원인 원문이/)) { await user.clear(box); await user.type(box, "my words"); }

  rendered.rerender(<EightdView cards={[A]} response={response} fresh={1} freshQuestion="a brand new question" onBack={() => {}} />);
  expect(message()).toMatch(/직접 고친 글이라 자동으로 못 뺀 1건은 칸에서 직접 지워 주세요\.$/);
});
