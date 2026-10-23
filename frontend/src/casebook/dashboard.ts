import type { Card, SearchResponse } from "../search/types";
import { causeBadge } from "./sources";

/**
 * 검색 결과 집계 — `/search` 응답 한 건을 세어 분포·건수로 바꾸는 순수 함수 모음이다.
 *
 * 출처: 병합 없이 닫은 PR #140(작성자 powercodingman, "검색 결과 분석 대시보드 추가")의 `deriveDashboard.ts` 집계 로직과
 * '근거 매트릭스' 아이디어를 가져왔다. 화면 연결은 하지 않는다 — 붙일 곳이던 `SearchView`는 DEC-075로 지워졌고 케이스북 화면
 * 배치는 디자인 결정이 필요해 후속으로 남긴다(이슈 #179 3절).
 *
 * 지키는 것:
 * - 이번 응답에 실린 선례만 센다. 응답 밖 리콜을 보태지 않고, 숫자는 전체 NHTSA 통계가 아니다.
 * - 모든 집계 항목은 근거가 되는 리콜 번호(CAMPNO) 목록(`campnos`)을 함께 돌려 준다(추적 가능성).
 * - 판정·순위·위험도를 만들지 않는다. 원인 칸은 글이 있는지만 가른다(`stated_unknown`을 원인 불명으로 단정하지 않는다).
 * - 공급사는 집계하지 않는다(데이터·스키마 동결 DEC-059 ⑤: 공급사 항목에는 573 판본 출처가 없다).
 * - 응답에 없는 필드는 만들지 않고, 빈 입력·누락 필드에는 빈 집계를 돌려 준다.
 *
 * PR #140과 달라진 점: 공급사 집계 제외, 상위 7개 자르기 제외(어디까지 보일지는 화면 결정), "날짜 미상" 같은 가짜 라벨 대신
 * `missing` 목록, 카드 수를 CAMPNO 중복 없이 세기, 모든 행에 `campnos` 부착, 원인 상태 원본 분포 추가.
 */

/** 건수와 그 근거 리콜 번호 — `count`는 언제나 `campnos.length`다 */
export interface Bucket {
  count: number;
  campnos: string[];
}

/** 분포의 한 칸 — `label`은 응답의 글자 그대로다 */
export interface Row extends Bucket {
  label: string;
}

/** `missing`은 값이 비어 어느 칸에도 넣지 못한 선례의 리콜 번호다(없는 값을 지어내 채우지 않는다) */
export interface Distribution {
  rows: Row[];
  missing: string[];
}

/** 근거 매트릭스의 한 줄 — 원문이 있는지만 알리고 내용은 싣지 않는다 */
export interface MatrixRow {
  campno: string;
  maker: string;
  received_date: string;
  /** 원인 칸: 글 있음(`text`) · 미보고·조사 중 표현으로 시작(`stated`) · 원문 없음(`none`) */
  cause: "text" | "stated" | "none";
  hasInvestigation: boolean;
  hasProductionPeriod: boolean;
}

export interface Dashboard {
  /** 이번 응답에 실린 선례(리콜 번호 중복 없이). 고객사 구역과 그 밖 구역 */
  precedents: { all: Bucket; customer: Bucket; other: Bucket };
  /** 회사(`maker`) 분포 — 회사명 대응표가 반영된 응답의 표시명(신고서 원문 표기는 서버 응답에 없는 `raw_maker`에 보존된다) */
  makers: Distribution;
  /** 부품 분류(`components`) 분포 — NHTSA 분류 문자열 그대로, 한 선례가 여러 분류를 가질 수 있다 */
  components: Distribution;
  /** 접수 연도(`received_date` 앞 4자리) 분포, 오래된 해부터 */
  years: Distribution;
  /** 원인 칸 상태를 셋으로 묶은 건수 */
  causeLevels: { text: Bucket; stated: Bucket; none: Bucket };
  /** 원인 칸 상태 원본(`filled`·`stated_unknown`·`no_573_report` 등) 분포 */
  causeStatuses: Distribution;
  /** 출처 종류별로 근거가 있는 선례 — 573 보고서(원인 글 또는 생산 기간), 결함 조사 */
  sources: { part573: Bucket; investigation: Bucket; productionPeriod: Bucket };
  /** 연결된 결함 조사 번호(`ACTION`) 분포 */
  investigationActions: Distribution;
  /** 같은 본문 묶음(`dup_group`) 분포 */
  dupGroups: Distribution;
  /** 선례마다 원문이 있는지 한눈에 보는 표 */
  matrix: MatrixRow[];
}

const bucket = (campnos: string[]): Bucket => ({ count: campnos.length, campnos });

/** 카드 목록을 값별로 묶는다. 한 카드가 같은 값을 여러 번 내도 한 번만 센다 */
function distribute(cards: readonly Card[], valuesOf: (card: Card) => readonly (string | null | undefined)[]): Distribution {
  const groups = new Map<string, string[]>();
  const missing: string[] = [];
  for (const card of cards) {
    const values = new Set(valuesOf(card).filter((v): v is string => typeof v === "string" && v !== ""));
    if (!values.size) missing.push(card.campno);
    for (const value of values) groups.set(value, [...(groups.get(value) ?? []), card.campno]);
  }
  const rows = [...groups].map(([label, campnos]) => ({ label, ...bucket(campnos) }));
  return { rows: rows.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)), missing };
}

const causeLevel = (card: Card): MatrixRow["cause"] => (card.cause ? causeBadge(card).level : "none");
const hasProductionPeriod = (card: Card) => (card.checklist ?? []).some((item) => item.item === "production_period");

export function deriveDashboard(response: Partial<Pick<SearchResponse, "customer_precedents" | "precedents">> | null | undefined): Dashboard {
  const seen = new Set<string>();
  const take = (list: readonly Card[] | undefined) => (list ?? []).filter((card) => {
    if (!card || typeof card.campno !== "string" || card.campno === "" || seen.has(card.campno)) return false;
    seen.add(card.campno);
    return true;
  });
  const customer = take(response?.customer_precedents);
  const other = take(response?.precedents);
  const cards = [...customer, ...other];
  const numbers = (pick: (card: Card) => boolean) => bucket(cards.filter(pick).map((card) => card.campno));
  const level = (want: "text" | "stated" | "none") => numbers((card) => causeLevel(card) === want);
  const actions = (card: Card) => (card.investigations ?? []).map((item) => item.action);
  const year = (card: Card) => (typeof card.received_date === "string" ? /^\d{4}/.exec(card.received_date)?.[0] : undefined);
  const years = distribute(cards, (card) => [year(card)]);
  return {
    precedents: { all: bucket(cards.map((c) => c.campno)), customer: bucket(customer.map((c) => c.campno)), other: bucket(other.map((c) => c.campno)) },
    makers: distribute(cards, (card) => [card.maker]),
    components: distribute(cards, (card) => card.components ?? []),
    years: { ...years, rows: [...years.rows].sort((a, b) => a.label.localeCompare(b.label)) },
    causeLevels: { text: level("text"), stated: level("stated"), none: level("none") },
    causeStatuses: distribute(cards, (card) => [card.cause?.status]),
    sources: {
      part573: numbers((card) => causeLevel(card) !== "none" || hasProductionPeriod(card)),
      investigation: numbers((card) => actions(card).length > 0),
      productionPeriod: numbers(hasProductionPeriod),
    },
    investigationActions: distribute(cards, actions),
    dupGroups: distribute(cards, (card) => [card.dup_group]),
    matrix: cards.map((card) => ({
      campno: card.campno,
      maker: card.maker ?? "",
      received_date: card.received_date ?? "",
      cause: causeLevel(card),
      hasInvestigation: actions(card).length > 0,
      hasProductionPeriod: hasProductionPeriod(card),
    })),
  };
}
