import type { Card } from "./types";

/** 8D 근거로 담은 선례 목록 — 담은 순서를 지키고, 같은 선례는 리콜 번호로 가른다 */
export const isPicked = (picked: readonly Card[], card: Card) => picked.some((p) => p.campno === card.campno);

export function togglePick(picked: readonly Card[], card: Card): Card[] {
  return isPicked(picked, card) ? picked.filter((p) => p.campno !== card.campno) : [...picked, card];
}
