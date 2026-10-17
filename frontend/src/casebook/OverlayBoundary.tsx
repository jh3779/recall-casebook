import { Component, type ReactNode } from "react";

/** 3D 창 코드를 받지 못했을 때(오래 열어 둔 탭·끊긴 네트워크) 안내 — 케이스북과 저장 전 메모는 그대로 둔다 */
export function OverlayFailed({ onClose }: { onClose: () => void }) {
  return <div className="cb-3d cb-3d-failed" role="alertdialog" aria-modal="true" aria-label="3D view unavailable">
    <div className="cb-3d-msg" role="alert">
      <p>The 3D view could not be loaded (the page code did not download). The casebook and your notes are unchanged. Close this and try again; if it keeps failing, reload the page after saving your notes under a case name.</p>
      <button type="button" className="cb-btn" onClick={onClose} autoFocus>Close</button>
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
