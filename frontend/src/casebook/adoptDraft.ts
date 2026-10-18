/**
 * 3D 쇼룸이 넘긴 질문(draft)을 입력창에 채울지 정한다. 케이스북은 숨겨진 채 계속 떠 있으므로 새 draft가 올 때만(key가 달라질 때만) 채운다.
 * 새 질문이 오면 reset이 참이다 — 이전 질문의 검색 결과·체크·진행 중 요청이 새 질문 밑에 남아 8D로 넘어가지 않게 비운다(PR #164 Codex 리뷰).
 * 그 밖에는 사용자가 쓰던 질문을 그대로 둔다.
 */
export function adoptDraft(seenKey: number, draft: { question: string; key: number } | null, question: string): { key: number; question: string; reset: boolean } {
  return draft && draft.key !== seenKey ? { key: draft.key, question: draft.question, reset: true } : { key: seenKey, question, reset: false };
}
