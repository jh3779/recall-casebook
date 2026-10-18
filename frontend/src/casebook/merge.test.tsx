import { isValidElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import health from "../search/__fixtures__/health.json";
import synthetic from "../search/__fixtures__/cause_statuses_synthetic.json";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { Card, HealthResponse, SearchResponse } from "../search/types";
import EightdView from "../eightd/EightdView";
import { adoptDraft } from "./adoptDraft";
import { ApiError } from "../api";
import { fieldLabel, itemLabel, plainItems } from "./checkItems";
import { errorText, searchErrorMessage } from "./errors";
import { SearchError } from "./SearchError";
import { countdownLeft, secondsLeft } from "./useCountdown";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import CasebookView from "./CasebookView";
import { EXAMPLES } from "./examples";
import { Intro } from "./Intro";
import { Provenance } from "./Provenance";
import { Results } from "./Results";
import { Write8dBar, Write8dPlain } from "./Write8dBar";

// 선례 검색 화면을 케이스북에 합친 부분(DEC-075)
const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const escaped = (text: string) => renderToStaticMarkup(<span>{text}</span>).slice(6, -7);

it("검색 전 안내에 예시 질문 4개·하는 일/하지 않는 일·데이터 판본이 있다", () => {
  const markup = renderToStaticMarkup(<Intro health={health as HealthResponse} onExample={() => {}} />);
  expect(EXAMPLES).toHaveLength(4);
  for (const q of EXAMPLES) expect(markup).toMatch(new RegExp(`<button[^>]*>${q}</button>`));
  expect(markup).toContain("What this tool does");
  expect(markup).toContain("What it does not do");
  for (const line of ["What it does not do", "It does not decide whether a recall is needed, or what the cause is.", "It does not translate or summarize the originals.", "It does not guess a cause or a supplier that is not in the source."]) expect(markup).toContain(line);
  expect(markup).toContain(`build ${health.build_id}`);
  expect(markup).toContain(`snapshot ${health.snapshot_date}`);
});
it("서버 판본을 아직 못 받았으면 데이터 판본 자리에 그 상태를 밝힌다", () => {
  expect(renderToStaticMarkup(<Intro health="loading" onExample={() => {}} />)).toContain("Checking server…");
  expect(renderToStaticMarkup(<Intro health="error" onExample={() => {}} />)).toContain("Server version unavailable");
});
it("케이스북 첫 화면에 안내가 나오고, 3D 쇼룸이 넘긴 질문이 입력창에 채워진다", () => {
  expect(renderToStaticMarkup(<CasebookView health="loading" />)).toContain("Example questions");
  const withDraft = renderToStaticMarkup(<CasebookView health="loading" draft={{ question: "steering rack noise", key: 1 }} />);
  expect(withDraft).toContain('value="steering rack noise"');
});
it("선례 없이 8D 작성 버튼은 8D로 넘길 수 있을 때만 있다", () => {
  expect(renderToStaticMarkup(<CasebookView health="loading" onWrite8d={() => {}} />)).toContain("Write 8D without precedents");
  expect(renderToStaticMarkup(<CasebookView health="loading" />)).not.toContain("Write 8D");
});
it("체크한 선례가 있을 때만 8D 작성 줄이 나오고, 누르면 체크한 선례와 검색 결과를 넘긴다", () => {
  const seen: unknown[] = [];
  expect(Write8dBar({ checked: [], response, onWrite8d: () => {} })).toBeNull();
  const bar = Write8dBar({ checked: cards.slice(0, 2), response, onWrite8d: (...args) => { seen.push(args); } }) as ReactElement<{ children: ReactElement<{ onClick: () => void }>[] }>;
  expect(isValidElement(bar)).toBe(true);
  bar.props.children[0].props.onClick();
  expect(seen).toEqual([[cards.slice(0, 2), response]]);
  expect(renderToStaticMarkup(bar)).toContain("Write 8D from checked (2)");
});
it("HTML과 U+0092도 텍스트 노드로 보존한다", () => {
  const text = '<script>alert("test")</script> GM\u0092s';
  const markup = renderToStaticMarkup(<CaseDetail card={{ ...response.precedents[0], defect: text }} response={response} onRemove={() => {}} />);
  expect(markup).toContain(escaped(text));
  expect(markup).not.toContain("<script>");
});
it("응답 출처에 묶음 sha256 64자 전체와 질문이 있고, 묶음이 없으면 그렇게 밝힌다", () => {
  expect(response.bundle_sha256).toHaveLength(64);
  const markup = renderToStaticMarkup(<Provenance data={response} />);
  expect(markup).toMatch(new RegExp("<details[^>]*>[\\s\\S]*Full version[\\s\\S]*" + response.bundle_sha256 + "[\\s\\S]*</details>"));
  expect(markup).toContain(`build ${response.build_id}`);
  expect(markup).toContain(escaped(response.question));
  expect(renderToStaticMarkup(<Provenance data={{ ...response, bundle_sha256: null }} />)).toContain("no bundle (server started from local files)");
});
it("8D 화면의 돌아가기 단추는 케이스북을 가리킨다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={[]} response={null} onBack={() => {}} />);
  expect(markup).toContain("← 케이스북으로");
  expect(markup).not.toContain("선례 찾기로");
});
it("이미 떠 있는 케이스북은 새 draft가 올 때만 질문을 채우고, 쓰던 질문은 그대로 둔다", () => {
  expect(adoptDraft(0, { question: "brake hose leak", key: 1 }, "typed by user")).toEqual({ key: 1, question: "brake hose leak", reset: true }); // 새 질문이 오면 이전 질문의 결과·체크·진행 중 요청을 비운다
  expect(adoptDraft(1, { question: "brake hose leak", key: 1 }, "typed after")).toEqual({ key: 1, question: "typed after", reset: false });
  expect(adoptDraft(0, null, "typed")).toEqual({ key: 0, question: "typed", reset: false });
});
it.each(synthetic)("합성 원인 상태 $status도 빈 블록으로 남지 않고 상태를 말한다", (cause) => {
  const markup = renderToStaticMarkup(<CaseDetail card={{ ...response.precedents[0], cause } as unknown as Card} response={response} onRemove={() => {}} />);
  expect(markup).toMatch(/<p class="cb-status">[^<]+<\/p>/);
});
it("고객사 결과가 없더라도 구역과 안내를 남긴다", () => {
  const markup = renderToStaticMarkup(<CaseList response={{ ...response, customer_precedents: [] }} checked={[]} onToggle={() => {}} />);
  expect(markup).toContain("Customer precedents · Hyundai / Kia");
  expect(markup).toContain("No Hyundai / Kia recall in the top 100.");
});

const resultsProps = { response, checked: [] as Card[], checkedKey: "", onToggle: () => {}, on3d: () => {}, notes: {}, onNoteChange: () => {}, caseName: "", persistent: false, storageBlocked: null as never, onCopy: () => {}, onClear: () => {}, copyMessage: "", storeMessage: "", onGroupPicked: () => {}, picked: [] as string[] };
it("결과 화면에는 응답 출처(묶음 sha 전체)가 항상 붙고, 8D 줄은 체크한 선례가 있고 넘길 수 있을 때만 붙는다", () => {
  const none = renderToStaticMarkup(<Results {...resultsProps} />);
  expect(none).toContain(response.bundle_sha256);
  expect(none).not.toContain("Write 8D");
  const withChecked = renderToStaticMarkup(<Results {...resultsProps} checked={cards.slice(0, 2)} onWrite8d={() => {}} />);
  expect(withChecked).toContain("Write 8D from checked (2)");
  expect(withChecked).toContain(response.bundle_sha256);
  expect(renderToStaticMarkup(<Results {...resultsProps} checked={cards.slice(0, 2)} />)).not.toContain("Write 8D");
  expect(renderToStaticMarkup(<Results {...resultsProps} onWrite8d={() => {}} />)).not.toContain("Write 8D");
});
it("선례 없이 8D 단추는 체크한 선례를 넘기지 않고 입력창의 질문을 새 질문으로 넘긴다", () => {
  const seen: unknown[] = [];
  const el = Write8dPlain({ question: "my question", response, onWrite8d: (...args) => { seen.push(args); } }) as ReactElement<{ onClick: () => void }>;
  el.props.onClick();
  expect(seen).toEqual([[[], response, { question: "my question" }]]);
});
it("싣지 못한 생산 기간 블록이 0이면 안내를 그리지 않는다", () => {
  const source = { campaign: "X", file: "odi/rcl/2026/RCLRPT-X.pdf", pdf_sha256: "c".repeat(64), submission_date: "20260710" };
  const production = { item: "production_period" as const, label: "생산 기간", evidence: [{ field: "573.production_dates", text: "Vehicle 1: 2015" }], omitted: 0, unread: 0, source };
  const card = { ...cards.find((c) => c.cause.status === "no_573_report")!, cause: { status: "cause_empty" as const, campaign: "X" }, checklist: [production] };
  const markup = renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />);
  expect(markup).toContain("Production period");
  expect(markup).not.toContain("not shown");
  expect(markup).not.toContain("without a readable date");
});
it("확인 항목 6종이 모두 근거 원문과 함께 보인다(PRD FR-7)", () => {
  const kinds = new Set<string>();
  for (const card of cards) {
    const markup = renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />);
    for (const item of card.checklist) {
      kinds.add(item.item);
      if (item.item === "production_period" || item.item === "supplier") continue; // 둘은 출처 보고서와 함께 따로 그린다(위 시험)
      expect(markup).toContain(`<h5>${itemLabel(item.item)}</h5>`);
      for (const e of item.evidence) { expect(markup).toContain(escaped(e.text)); expect(fieldLabel(e.field)).not.toBe(e.field); expect(markup).toContain(fieldLabel(e.field)); } // 칸 이름은 내부 키가 아니라 사람이 읽는 이름으로 보인다
    }
    expect(plainItems(card).every((item) => !["production_period", "supplier"].includes(item.item))).toBe(true);
  }
  expect([...kinds].sort()).toEqual(["cause_speaker", "failure_mode", "remedy", "same_part", "supplier"]); // 픽스처에는 생산 기간 항목이 없다(위 시험이 합성 카드로 지킨다)
});
it("호출 상한 뒤 남은 초는 올림으로 세고, 마감이 없거나 지났으면 0이다", () => {
  expect(secondsLeft(null, 1000)).toBe(0);
  expect(secondsLeft(500, 1000)).toBe(0);
  expect(secondsLeft(8200, 1000)).toBe(8);
  expect(secondsLeft(2000, 1000)).toBe(1);
});
it("결과 화면은 저장 안내와 복사 안내를 D4 칸과 메모 칸에 그대로 넘긴다", () => {
  const markup = renderToStaticMarkup(<Results {...resultsProps} checked={cards.slice(0, 1)} storeMessage="STORE-MSG-X" copyMessage="COPY-MSG-Y" />);
  expect(markup).toContain("STORE-MSG-X");
  expect(markup).toContain("COPY-MSG-Y");
});
it("확인 항목은 서버가 준 순서 그대로 그린다(같은 부품 → 생산 기간 → 고장 양상 → 시정 → 공급사 → 원인을 말한 주체)", () => {
  const source = { campaign: "X", file: "odi/rcl/2026/RCLRPT-X.pdf", pdf_sha256: "c".repeat(64), submission_date: "20260710" };
  const base = cards.find((c) => c.cause.status === "no_573_report")!;
  const pick = (kind: string) => cards.flatMap((c) => c.checklist).find((i) => i.item === kind)!;
  const production = { item: "production_period" as const, label: "생산 기간", evidence: [{ field: "573.production_dates", text: "Vehicle 1: 2015" }], omitted: 0, unread: 0, source };
  const checklist = [pick("same_part"), production, pick("failure_mode"), pick("remedy"), pick("supplier"), pick("cause_speaker")];
  const markup = renderToStaticMarkup(<CaseDetail card={{ ...base, cause: { status: "cause_empty" as const, campaign: "X" }, checklist } as Card} response={response} onRemove={() => {}} />);
  const at = ["Same part", "Production period", "Failure mode", "Remedy", "Supplier", "Who said the cause"].map((h) => markup.indexOf(`<div class="cb-check-item"><h5>${h}</h5>`));
  expect(at.every((n) => n >= 0)).toBe(true);
  expect([...at].sort((a, b) => a - b)).toEqual(at);
});
it("남은 초는 마감이 바뀌면 옛 시각으로 세지 않고(막힌 채 1), 같은 마감이면 시각으로 센다", () => {
  expect(countdownLeft(null, null)).toBe(0);
  expect(countdownLeft(9000, null)).toBe(1);
  expect(countdownLeft(9000, { deadline: 5000, at: 100 })).toBe(1); // 옛 마감 때 읽은 시각
  expect(countdownLeft(9000, { deadline: 9000, at: 1000 })).toBe(8);
  expect(countdownLeft(9000, { deadline: 9000, at: 9000 })).toBe(0);
});
it("429 안내는 기다리는 동안 Retry를 막고, 남은 초는 낭독기가 읽지 않는 곳에만 둔다", () => {
  const waiting = renderToStaticMarkup(<SearchError message="Too many requests. Try again in 4 seconds." limited wait={3} onRetry={() => {}} />);
  expect(waiting).toContain('<p role="alert">Too many requests. Try again in 4 seconds.</p>');
  expect(waiting).toContain('<p aria-hidden="true">3s left</p>');
  expect(waiting).toMatch(/<button[^>]*disabled=""[^>]*>Retry<span aria-hidden="true"> \(3\)<\/span><\/button>/);
  expect(waiting).toContain('<p role="status" class="sr-only"></p>'); // 끝났을 때 채울 live 영역은 기다리는 동안에도 비어 있는 채로 먼저 있다
  const done = renderToStaticMarkup(<SearchError message="Too many requests. Try again in 4 seconds." limited wait={0} onRetry={() => {}} />);
  expect(done).not.toContain("disabled");
  expect(done).toContain("You can search again.");
  const other = renderToStaticMarkup(<SearchError message="Could not reach the server." limited={false} wait={0} onRetry={() => {}} />);
  expect(other).not.toContain("You can search again.");
  expect(other).not.toContain("disabled");
});
it("생산 기간과 공급사 근거에도 원문이 나온 칸 이름을 함께 보인다(PRD FR-7)", () => {
  const source = { campaign: "X", file: "odi/rcl/2026/RCLRPT-X.pdf", pdf_sha256: "c".repeat(64), submission_date: "20260710" };
  const production = { item: "production_period" as const, label: "생산 기간", evidence: [{ field: "573.production_dates", text: "Vehicle 1: 2015 | Apr 18, 2015 - Aug 24, 2015" }], omitted: 0, unread: 0, source };
  const supplier = { item: "supplier" as const, label: "공급사", evidence: [{ field: "573.supplier_names", text: "ACME Parts, Inc." }] };
  const card = { ...cards.find((c) => c.cause.status === "no_573_report")!, cause: { status: "cause_empty" as const, campaign: "X" }, checklist: [production, supplier] } as Card;
  const markup = renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />);
  expect(markup).toContain("Part 573 production dates · </span>Vehicle 1: 2015");
  expect(markup).toContain("Part 573 supplier names · </span>ACME Parts, Inc.");
  expect(markup).toContain(source.file); // 칸 이름이 붙어도 출처 보고서는 그대로 보인다
  expect(fieldLabel("573.production_dates")).not.toBe("573.production_dates");
});
it("호출 상한 오류 문구에는 처음 받은 대기 초가 고정으로 남지 않는다(남은 초는 따로 센다)", () => {
  const limited = errorText(new ApiError("rate_limit", "x", 429, undefined, 12), "search");
  expect(limited).toContain("12 seconds"); // 대기 시간을 알 수 없는 경우(머리글 없음)의 문구는 그대로다
  expect(searchErrorMessage(limited, true)).toBe("Too many requests.");
  expect(searchErrorMessage(limited, false)).toBe(limited);
  expect(searchErrorMessage("Could not reach the server.", false)).toBe("Could not reach the server.");
});
