// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { search } from "../api";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { SearchResponse } from "../search/types";
import CasebookView from "./CasebookView";

// 네트워크도 three.js도 쓰지 않는다 — 검색은 픽스처로, 3D 창 코드(lazy)는 열쇠를 풀기 전까지 도착하지 않는 가짜로 바꾼다
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), search: vi.fn() }));
const gate = vi.hoisted(() => { let open!: () => void; const arrived = new Promise<void>((resolve) => { open = resolve; }); return { arrived, open }; });
vi.mock("./ModelOverlay", async () => {
  await gate.arrived;
  return { default: ({ card, onClose }: { card: { campno: string }; onClose: () => void }) => <div role="dialog" aria-label={`fake 3D ${card.campno}`}><button type="button" onClick={onClose}>fake close</button></div> };
});

const response = fixture as SearchResponse;
const card = response.customer_precedents[0] ?? response.precedents[0];

beforeEach(() => { vi.mocked(search).mockResolvedValue(response); history.replaceState(null, "", "/#casebook"); });
afterEach(() => { cleanup(); history.replaceState(null, "", "/"); });

async function openFirstCard() {
  const user = userEvent.setup();
  render(<CasebookView health="loading" />);
  await user.type(screen.getByRole("textbox", { name: "Defect description in English" }), "airbag inflator rupture");
  await user.click(screen.getByRole("button", { name: "Find precedents" }));
  await user.click(await screen.findByRole("button", { name: new RegExp(card.campno) }));
  const opener = screen.getByRole("button", { name: `Show part category of ${card.campno} in 3D` });
  return { user, opener };
}

// 이 시험은 3D 코드가 아직 도착하지 않은 상태가 필요하고, 한 번 도착하면 모듈에 남는다(React.lazy 캐시) — 그래서 이 파일에는 이 시험 하나만 둔다.
// 코드가 도착한 상태를 쓰는 시험은 CasebookOverlay.hash.dom.test.tsx로 나눠, 실행 순서를 섞어도(--sequence.shuffle) 서로 영향을 주지 않게 한다
it("3D 코드를 받는 중에 Esc로 닫으면 연 버튼으로 초점이 돌아가고, 코드가 늦게 도착해도 닫힌 창이 되살아나지 않는다", async () => {
  const { user, opener } = await openFirstCard();
  await user.click(opener);
  const loading = await screen.findByRole("dialog", { name: "Loading the 3D view" });
  expect(document.activeElement).toBe(within(loading).getByRole("button", { name: "Close" }));
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(opener);

  await act(async () => { gate.open(); await gate.arrived; });
  expect(screen.queryByRole("dialog")).toBeNull();
});
