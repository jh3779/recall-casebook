/**
 * 모달 창 안에서 Tab·Shift+Tab을 순환시킨다(`aria-modal`인 3D 창이 열린 동안 키보드가 뒤 화면으로 새지 않게).
 * `current`는 지금 초점이 있는 요소의 순번(-1이면 창 밖이거나 목록에 없음)이고, 다음에 초점을 줄 순번을 돌려준다. 요소가 없으면 -1.
 */
export function nextFocusIndex(count: number, current: number, backwards: boolean): number {
  if (count <= 0) return -1;
  if (current < 0 || current >= count) return backwards ? count - 1 : 0;
  return backwards ? (current - 1 + count) % count : (current + 1) % count;
}
export const FOCUSABLE = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
