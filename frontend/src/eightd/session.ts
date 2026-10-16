import type { Card, SearchResponse } from "../search/types";

/** 8D 작성 한 번의 입력 — nonce가 바뀌면 화면의 작업 상태(쓴 글·넣은 인용·올린 파일·고른 칸)를 모두 새로 시작한다 */
export interface EightdSession { cards: readonly Card[]; response: SearchResponse | null; nonce: number }
export const emptySession: EightdSession = { cards: [], response: null, nonce: 0 };

/** 검색 화면에서 "8D 작성"을 누를 때마다 새 작업이다. "← 선례 찾기로"로 갔다 돌아오는 것은 이 함수를 거치지 않으므로 같은 작업이 이어진다
 * (리뷰 지적: 이전 질문의 쓴 글·인용·파일이 다음 작업의 서류에 섞이던 문제) */
export const startEightd = (prev: EightdSession, cards: readonly Card[], response: SearchResponse | null): EightdSession => ({ cards, response, nonce: prev.nonce + 1 });
