import type { Card } from "./types";
export function PickToggle({ card, picked, onToggle }: { card: Card; picked: boolean; onToggle: () => void }) {
  return <button type="button" className={`pick${picked ? " on" : ""}`} aria-pressed={picked} aria-label={`${card.campno} 8D 근거로 ${picked ? "빼기" : "담기"}`} onClick={onToggle}>{picked ? "담음 ✓" : "8D 근거로 담기"}</button>;
}
