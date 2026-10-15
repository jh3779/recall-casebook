import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import fixture from "../__fixtures__/search_airbag.json";
import type { SearchResponse } from "../types";
import { deriveDashboard } from "./deriveDashboard";
import { RetrievalDashboard } from "./RetrievalDashboard";

const response = fixture as SearchResponse;

describe("retrieval dashboard", () => {
  it("표시된 검색 결과만 집계한다", () => {
    const data = deriveDashboard(response);
    expect(data.total).toBe(response.customer_precedents.length + response.precedents.length);
    expect(data.customerCount).toBe(response.customer_precedents.length);
    expect(data.otherCount).toBe(response.precedents.length);
    expect(data.cause.filled + data.cause.stated + data.cause.missing).toBe(data.total);
    expect(data.investigationActions).toBe(new Set(data.cards.flatMap((card) => card.investigations.map((item) => item.action))).size);
  });

  it("원문 공급사 이름을 고유 CAMPNO로만 센다", () => {
    const card = structuredClone(response.precedents[0]);
    card.checklist.push({ item: "supplier", label: "공급사", evidence: [{ field: "573.supplier_names", text: "Example Supplier" }] });
    const data = deriveDashboard({ ...response, customer_precedents: [card], precedents: [card] });
    expect(data.suppliers.find((item) => item.name === "Example Supplier")?.campnos).toEqual([card.campno]);
  });

  it("질문·판본·출처 흐름·주의 문구를 렌더한다", () => {
    const html = renderToStaticMarkup(<RetrievalDashboard response={response} question={response.question} />);
    expect(html).toContain(response.question);
    expect(html).toContain(response.build_id);
    expect(html).toContain("질문에서 원본까지");
    expect(html).toContain("현재 표시 결과 한정");
    expect(html).toContain("전체 NHTSA 통계가 아니라");
    expect(html).not.toContain("관련도");
    expect(html).not.toContain("확률");
  });

  it("응답 fixture의 질문이 달라도 방금 실행한 검색어를 표시한다", () => {
    const question = "engine connecting rod bearing failure";
    const html = renderToStaticMarkup(<RetrievalDashboard response={response} question={question} />);
    expect(html).toContain(question);
    expect(html).not.toContain(`>${response.question}</strong>`);
  });
});
