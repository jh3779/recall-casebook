import type { Card, SearchResponse } from "../search/types";

/**
 * 8D 작성 화면에 들어온 검색 결과가 이전 작업의 것과 다른 질문·서버 판본(build_id와 묶음 지문 bundle_sha256)에서 나온 것인가.
 * 다르면 이전 질문의 선례 인용·검색 결과 표는 자동으로 걷어 내고(`pruneInserted`), 사용자가 쓴 글·올린 파일은 **지우지 않고** 비울지 묻는다
 * (리뷰 지적: 쓴 글을 말없이 지워도, 이전 질문의 글이 새 서류에 말없이 남아도 안 된다). 한쪽이 검색 결과 없이 쓰던 작업이면 같은 작업으로 본다.
 */
export const workChanged = (prev: SearchResponse | null, next: SearchResponse | null): boolean =>
  !!prev && !!next && (prev.question !== next.question || prev.build_id !== next.build_id || (prev.bundle_sha256 ?? null) !== (next.bundle_sha256 ?? null));

export interface EightdInput { cards: readonly Card[]; response: SearchResponse | null; fresh: number }
/**
 * 검색 화면에서 "8D 작성"을 누를 때의 새 입력 — 검색이 진행 중·실패라 응답이 비어 있으면 마지막 응답을 유지한다(넣어 둔 글의 출처 꼬리줄·SUBJECT·검색 결과 표 토글이 사라지지 않게, 리뷰 지적).
 * "선례 없이 8D 작성하기"(fresh)는 새로 시작하겠다는 뜻이므로 fresh 번호를 올려 화면이 이전 글·파일을 어떻게 할지 묻게 한다(입력창만 바꾼 질문은 8D 쪽이 알 수 없다 — 리뷰 지적).
 */
export const nextEightdInput = (prev: EightdInput, cards: readonly Card[], response: SearchResponse | null, fresh = false): EightdInput => ({ cards, response: response ?? prev.response, fresh: prev.fresh + (fresh ? 1 : 0) });
