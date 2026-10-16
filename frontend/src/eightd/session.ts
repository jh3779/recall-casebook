import type { SearchResponse } from "../search/types";

/**
 * 8D 작성 화면에 들어온 검색 결과가 이전 작업의 것과 다른 질문·서버 판본에서 나온 것인가.
 * 다르면 이전 질문의 선례 인용·검색 결과 표는 자동으로 걷어 내고(`pruneInserted`), 사용자가 쓴 글·올린 파일은 **지우지 않고** 비울지 묻는다
 * (리뷰 지적: 쓴 글을 말없이 지워도, 이전 질문의 글이 새 서류에 말없이 남아도 안 된다). 한쪽이 검색 결과 없이 쓰던 작업이면 같은 작업으로 본다.
 */
export const workChanged = (prev: SearchResponse | null, next: SearchResponse | null): boolean =>
  !!prev && !!next && (prev.question !== next.question || prev.build_id !== next.build_id);
