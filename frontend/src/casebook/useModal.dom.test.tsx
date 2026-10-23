// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { lazy, Suspense, useRef } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { OverlayBoundary, OverlayLoading } from "./OverlayBoundary";
import { useModal } from "./useModal";

afterEach(() => { cleanup(); document.body.innerHTML = ""; vi.restoreAllMocks(); });

/** 모달 훅만 시험하려고 세운 작은 창 — 초점을 받는 요소가 셋이다 */
function Dialog({ onClose, opener }: { onClose: () => void; opener: HTMLElement | null }) {
  const dialog = useRef<HTMLDivElement>(null);
  const close = useModal(dialog, onClose, opener);
  return <div ref={dialog} role="dialog" aria-label="test dialog">
    <button type="button">first</button>
    <button type="button">second</button>
    <button type="button" onClick={close}>Close</button>
  </div>;
}
/** 창을 연 버튼 — 마우스 클릭이 초점을 주지 않는 브라우저처럼 한 번도 초점을 받지 않은 채로 둔다 */
function makeOpener() {
  const opener = document.createElement("button");
  opener.textContent = "Show in 3D";
  document.body.append(opener);
  return opener;
}

it("Esc를 누르면 창이 닫히고 초점이 연 버튼으로 돌아간다 (연 버튼이 초점을 받은 적이 없어도)", async () => {
  const user = userEvent.setup();
  const opener = makeOpener();
  const onClose = vi.fn();
  render(<Dialog onClose={onClose} opener={opener} />);
  screen.getByRole("button", { name: "second" }).focus();
  expect(document.activeElement).not.toBe(opener);
  await user.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(document.activeElement).toBe(opener);
});

it("Tab·Shift+Tab은 창 안에서 돌고, 초점이 창 밖에 있으면 안으로 끌어온다", async () => {
  const user = userEvent.setup();
  const opener = makeOpener();
  render(<Dialog onClose={() => {}} opener={opener} />);
  const [first, second, last] = ["first", "second", "Close"].map((name) => screen.getByRole("button", { name }));
  last.focus();
  await user.keyboard("{Tab}");
  expect(document.activeElement).toBe(first); // 마지막에서 Tab → 처음
  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(document.activeElement).toBe(last); // 처음에서 Shift+Tab → 마지막
  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(document.activeElement).toBe(second);
  opener.focus(); // 창 밖(뒤 화면)
  await user.keyboard("{Tab}");
  expect(document.activeElement).toBe(first);
});

it("Close 단추는 창이 사라지기 전에 초점을 먼저 돌려주고, 연 버튼이 화면에서 사라졌어도 오류 없이 닫는다", async () => {
  const user = userEvent.setup();
  const opener = makeOpener();
  let focusedWhenClosed: Element | null = null;
  const onClose = vi.fn(() => { focusedWhenClosed = document.activeElement; });
  const view = render(<Dialog onClose={onClose} opener={opener} />);
  await user.click(screen.getByRole("button", { name: "Close" }));
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(focusedWhenClosed).toBe(opener); // onClose가 불리는 시점에 이미 연 버튼에 초점이 있다

  const gone = makeOpener();
  gone.remove();
  const second = vi.fn();
  view.rerender(<Dialog onClose={second} opener={gone} />);
  await user.keyboard("{Escape}");
  expect(second).toHaveBeenCalledTimes(1); // 연 버튼이 없어도 닫힌다
});

it("3D 코드를 받는 동안 뜨는 창도 모달이다 — Tab이 뒤 화면으로 새지 않고 Esc로 닫으며 연 버튼으로 돌아간다", async () => {
  const user = userEvent.setup();
  const opener = makeOpener();
  const onClose = vi.fn();
  render(<OverlayLoading onClose={onClose} opener={opener} />);
  const close = screen.getByRole("button", { name: "Close" });
  expect(document.activeElement).toBe(close); // autoFocus
  await user.keyboard("{Tab}");
  expect(document.activeElement).toBe(close);
  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(document.activeElement).toBe(close);
  await user.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(document.activeElement).toBe(opener);
});

it("lazy로 받는 3D 코드가 거부되면 경계가 잡아 안내창을 띄우고, 그 창의 Close도 연 버튼으로 초점을 돌려준다", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {}); // React가 잡힌 오류도 콘솔에 남긴다
  const user = userEvent.setup();
  const opener = makeOpener();
  const onClose = vi.fn();
  const Broken = lazy(() => Promise.reject(new Error("chunk failed")));
  render(<OverlayBoundary onClose={onClose} opener={opener}>
    <Suspense fallback={<OverlayLoading onClose={onClose} opener={opener} />}><Broken /></Suspense>
  </OverlayBoundary>);
  const alert = await screen.findByRole("alertdialog", { name: "3D view unavailable" });
  expect(alert.textContent).toContain("could not be loaded");
  expect(screen.queryByRole("dialog", { name: "Loading the 3D view" })).toBeNull(); // 로딩 창은 안내창으로 바뀌었다
  await user.click(screen.getByRole("button", { name: "Close" }));
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(document.activeElement).toBe(opener);
});
