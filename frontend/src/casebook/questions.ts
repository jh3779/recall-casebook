import type { Card } from "../search/types";

/**
 * D4 확인 질문 — 도구가 만든 고정 문장이다. 서버 `server/rag/draft.py`의 `QUESTIONS["d4"]`·`QUESTION_UNKNOWN`과 글자까지 같아야 하고
 * (`questions.test.ts`가 서버 파일을 읽어 대조한다), 공개 서버에는 `/draft`가 없어도 질문이 나오도록 화면에도 둔다(DEC-069).
 * 문장은 선례의 원인이 우리 건의 원인이라고 말하지 않으며, 같다·다르다를 판정하지 않는다. 기본 문장은 LLM이 쓰거나 고르지 않는다 — 아래 규칙(코드)이 붙인다.
 * 추가 질문은 아래 풀(`QUESTION_POOL`)에서 LLM이 **번호만** 고른다(DEC-071, 서버 `QUESTION_POOL`과 글자까지 같음). 문장은 응답이 아니라 이 풀에서 가져온다.
 */
export const D4_QUESTIONS: readonly string[] = [
  "위 원인 문장은 제조사가 쓴 공개 서술이며 우리 건의 원인이 아닙니다. 발생 원인과 유출 원인을 직접 분석했습니까?",
  "선례의 공급사·생산 기간(확인 항목)과 우리 건의 공급사·생산 기간이 겹칩니까?"
];
export const QUESTION_UNKNOWN = "원인 칸에 '미보고·조사 중' 표현(N/A·NR 등)이 있는 선례는, 그 표현 뒤에 별도의 원인 서술이 이어지는지 원문 전체를 확인했습니까?";

/** 서버 `questions_for`와 같은 규칙: 기본 문장에, 체크한 선례 중 원인 칸이 "미보고·조사 중" 표현으로 시작하는 글이 있으면 그 확인 문장을 더한다 */
export const d4Questions = (cards: readonly Pick<Card, "cause">[]): string[] =>
  [...D4_QUESTIONS, ...(cards.some((c) => c.cause.status === "stated_unknown") ? [QUESTION_UNKNOWN] : [])];

/** 확인 질문 풀(DEC-071) — 서버 `server/rag/draft.py`의 `QUESTION_POOL`과 같다. LLM은 번호만 고르고, 화면은 응답이 들고 온 글자가 아니라 이 풀의 문장을 보인다 */
export const QUESTION_POOL: Readonly<Record<string, string>> = {
  P1: "선례 원문이 소재·재질·열처리 등 재료 이유를 말한다면, 우리 건의 같은 부품 재료·공정 변경 이력을 확인했습니까?",
  P2: "선례 원문이 제조·가공 공정상의 이유를 말한다면, 우리 건의 해당 공정 조건과 변경점(설비·작업 조건·작업자)을 확인했습니까?",
  P3: "선례 원문이 조립·체결 이유를 말한다면, 우리 건의 조립·체결 조건(토크·순서·치구) 기록을 확인했습니까?",
  P4: "선례 원문이 설계·사양 이유를 말한다면, 우리 부품의 도면·공차·사양 이력을 확인했습니까?",
  P5: "선례 원문이 이물·오염을 말한다면, 우리 공정의 이물 관리·청정도 기록을 확인했습니까?",
  P6: "선례 원문이 소프트웨어·제어 로직을 말한다면, 우리 건의 소프트웨어 버전·교정값 이력을 확인했습니까?",
  P7: "선례 원문이 공급사·하위 공급사를 말한다면, 우리 건의 공급사·하위 공급사 기록을 확인했습니까?",
  P8: "선례 원문이 검사·시험에서 걸러내지 못한 이유를 말한다면, 우리 검사 항목이 같은 결함을 찾도록 되어 있는지 확인했습니까?",
  P9: "선례 원문이 특정 생산 기간·로트를 말한다면, 우리 건의 생산 시기·로트 기록을 확인했습니까?",
  P10: "선례 원문이 사용 환경(온도·습도·부식)이나 시간 경과를 말한다면, 우리 건의 사용 조건 자료를 확인했습니까?",
};
export const MAX_PICK = 3; // 서버 `MAX_PICK`

/** 고른 번호를 질문으로 — 풀 안의 번호만, 중복 없이 준 순서대로 최대 `MAX_PICK`개. 문장은 풀의 것이다 */
export function pickedQuestions(ids: readonly string[] | undefined): { id: string; text: string }[] {
  const kept: string[] = [];
  for (const id of ids ?? []) if (Object.hasOwn(QUESTION_POOL, id) && !kept.includes(id) && kept.length < MAX_PICK) kept.push(id);
  return kept.map((id) => ({ id, text: QUESTION_POOL[id] }));
}
/** 묶기 응답에서 LLM이 고른 번호 — 응답이 문장을 들고 와도 번호만 쓴다 */
export const pickedIdsOf = (result: { picked_questions?: readonly { id: string }[] }): string[] => pickedQuestions(result.picked_questions?.map((q) => q.id)).map((q) => q.id);
