import type { Card } from "../search/types";

/**
 * D4 확인 질문 — 도구가 만든 고정 문장이다. 서버 `server/rag/draft.py`의 `QUESTIONS["d4"]`·`QUESTION_UNKNOWN`과 글자까지 같아야 하고
 * (`questions.test.ts`가 서버 파일을 읽어 대조한다), 공개 서버에는 `/draft`가 없어도 질문이 나오도록 화면에도 둔다(DEC-069).
 * 문장은 선례의 원인이 우리 건의 원인이라고 말하지 않으며, 같다·다르다를 판정하지 않는다. LLM이 쓰거나 고르지 않는다 — 아래 규칙(코드)이 붙인다.
 */
export const D4_QUESTIONS: readonly string[] = [
  "위 원인 문장은 제조사가 쓴 공개 서술이며 우리 건의 원인이 아닙니다. 발생 원인과 유출 원인을 직접 분석했습니까?",
  "선례의 공급사·생산 기간(확인 항목)과 우리 건의 공급사·생산 기간이 겹칩니까?"
];
export const QUESTION_UNKNOWN = "원인 칸에 '미보고·조사 중' 표현(N/A·NR 등)이 있는 선례는, 그 표현 뒤에 별도의 원인 서술이 이어지는지 원문 전체를 확인했습니까?";

/** 서버 `questions_for`와 같은 규칙: 기본 문장에, 체크한 선례 중 원인 칸이 "미보고·조사 중" 표현으로 시작하는 글이 있으면 그 확인 문장을 더한다 */
export const d4Questions = (cards: readonly Pick<Card, "cause">[]): string[] =>
  [...D4_QUESTIONS, ...(cards.some((c) => c.cause.status === "stated_unknown") ? [QUESTION_UNKNOWN] : [])];
