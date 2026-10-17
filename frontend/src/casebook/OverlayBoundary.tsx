import { Component, useRef, type ReactNode } from "react";
import { useModal } from "./useModal";

/** 3D 창 코드를 받지 못했을 때(오래 열어 둔 탭·끊긴 네트워크) 안내 — 케이스북과 저장 전 메모는 그대로 둔다 */
export function OverlayFailed({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDivElement>(null);
  const close = useModal(dialog, onClose); // 실패 안내창도 Esc·Tab 순환·초점 복귀를 갖는다
  return <div className="cb-3d cb-3d-failed" ref={dialog} role="alertdialog" aria-modal="true" aria-label="3D view unavailable">
    <div className="cb-3d-msg" role="alert">
      <p>The 3D view could not be loaded (the page code did not download). The casebook and your notes are unchanged. Opening it again will fail the same way until the page is reloaded, so save your notes under a case name first, then reload the page.</p>
      <button type="button" className="cb-btn" onClick={close} autoFocus>Close</button>
    </div>
  </div>;
}

/** `lazy`로 받는 3D 창 코드의 로딩 실패를 가둔다 — 이 경계가 없으면 케이스북 화면 전체가 내려가 저장 전 메모를 잃는다 */
export class OverlayBoundary extends Component<{ onClose: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <OverlayFailed onClose={this.props.onClose} /> : this.props.children;
  }
}
