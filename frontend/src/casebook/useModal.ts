import { useCallback, useEffect, useRef, type RefObject } from "react";
import { FOCUSABLE, nextFocusIndex } from "./focusTrap";

/**
 * `aria-modal` 창의 키보드 규칙 — Esc로 닫고, Tab·Shift+Tab은 창 안에서 순환하며, 닫으면 창을 연 요소로 초점을 돌려준다.
 * - 연 요소(`opener`)는 **클릭하는 순간 부모가 저장해** 넘긴다 — 창이 뜨기 전(코드를 받는 동안)에 사용자가 움직여도, 마우스 클릭이 버튼에 초점을 주지 않는 브라우저에서도 같다.
 *   창 안에서 `document.activeElement`로 짐작하면 `autoFocus`가 먼저 실행돼 Close가 저장되고(첫 구현의 결함) 로딩 중 이동한 요소가 저장될 수 있다.
 * - 초점 복귀는 effect 정리 함수가 아니라 **닫는 동작**(Close·Esc)에서 한다 — 개발 모드(StrictMode)는 effect와 ref를 모의로 한 번 떼었다 붙여서 정리 함수의 "창이 사라졌는가" 판정이 틀린다.
 * - `onClose`는 ref로 읽어 부모가 다시 렌더돼도 효과가 다시 등록되지 않는다.
 * 돌려주는 `close`를 Close 버튼에 달아야 한다. 주소창 해시 이동처럼 밖에서 창을 닫으면 화면을 떠난 것이므로 초점을 돌려주지 않는다.
 */
export function useModal(dialog: RefObject<HTMLElement | null>, onClose: () => void, opener: HTMLElement | null): () => void {
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });
  const close = useCallback(() => {
    if (opener?.isConnected) opener.focus(); // 창이 사라지기 전에 초점을 먼저 돌려주면 창이 닫힌 뒤에도 그대로 남는다
    closeRef.current();
  }, [opener]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { close(); return; }
      if (e.key !== "Tab" || !dialog.current) return;
      const items = [...dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
      const next = nextFocusIndex(items.length, items.indexOf(document.activeElement as HTMLElement), e.shiftKey);
      if (next < 0) return;
      e.preventDefault(); // 초점이 창 밖(뒤 화면)으로 나가지 않게 창 안에서 돈다
      items[next].focus();
    };
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  }, [dialog, close]);
  return close;
}
