import type { Card, SearchResponse } from "../search/types";

/** 8D 작성 한 번의 입력 — nonce가 바뀌면 화면의 작업 상태(쓴 글·넣은 인용·올린 파일·고른 칸)를 모두 새로 시작한다 */
export interface EightdSession { cards: readonly Card[]; response: SearchResponse | null; nonce: number }
export const emptySession: EightdSession = { cards: [], response: null, nonce: 0 };

/**
 * 검색 화면에서 "8D 작성"을 누를 때의 새 입력. **질문이나 서버 판본이 바뀐 새 검색이면 새 작업**(nonce 증가 — 이전 질문의 인용·파일이 다음 서류에 섞이지 않게),
 * **같은 질문에서 선례만 더 담았거나 선례 없이 쓰던 작업에 선례를 더하는 것이면 같은 작업이 이어진다**(사용자가 쓴 글·올린 파일을 지우지 않는다).
 * 이어질 때 새 선례 목록에 없는 선례의 인용은 화면이 본문에서 걷어 낸다(`pruneInserted`).
 */
export function startEightd(prev: EightdSession, cards: readonly Card[], response: SearchResponse | null): EightdSession {
  const sameWork = !prev.response || !response || (prev.response.question === response.question && prev.response.build_id === response.build_id);
  return { cards, response: response ?? prev.response, nonce: sameWork ? prev.nonce : prev.nonce + 1 };
}
