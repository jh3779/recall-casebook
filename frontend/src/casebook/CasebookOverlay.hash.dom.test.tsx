// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { search } from "../api";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { SearchResponse } from "../search/types";
import CasebookView from "./CasebookView";

// 네트워크도 three.js도 쓰지 않는다 — 검색은 픽스처로, 3D 창 코드(lazy)는 바로 도착하는 가짜로 바꾼다
// (코드가 늦게 도착하는 경우는 CasebookOverlay.dom.test.tsx가 따로 시험한다)
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), search: vi.fn() }));
vi.mock("./ModelOverlay", () => ({
  default: ({ card, onClose }: { card: { campno: string }; onClose: () => void }) => <div role="dialog" aria-label={`fake 3D ${card.campno}`}><button type="button" onClick={onClose}>fake close</button></div>,
}));

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

it("3D 창을 연 채 다른 화면의 주소로 이동하면 닫히고, 케이스북 주소로의 이동은 닫지 않는다", async () => {
  const { user, opener } = await openFirstCard();
  await user.click(opener);
  expect(await screen.findByRole("dialog", { name: `fake 3D ${card.campno}` })).toBeTruthy();

  act(() => { history.replaceState(null, "", "/#casebook"); window.dispatchEvent(new HashChangeEvent("hashchange")); });
  expect(screen.getByRole("dialog", { name: `fake 3D ${card.campno}` })).toBeTruthy();
  act(() => { history.replaceState(null, "", "/#8d"); window.dispatchEvent(new HashChangeEvent("hashchange")); });
  expect(screen.queryByRole("dialog")).toBeNull();
});
