// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JSZip from "jszip";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { APPENDIX_TITLE, D4_EVIDENCE_TITLE } from "../eightd/document";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type SearchResponse } from "../search/types";
import { D4_KEYS } from "./d4Doc";
import { D4Panel } from "./D4Panel";

const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const withText = cards.filter((c) => hasCauseText(c.cause));
const without = cards.find((c) => !hasCauseText(c.cause))!;

afterEach(() => { cleanup(); vi.restoreAllMocks(); Reflect.deleteProperty(URL, "createObjectURL"); Reflect.deleteProperty(URL, "revokeObjectURL"); });

/** 글이 상태로 쌓이는 부모 — 칸에 쓴 글이 키를 따라 D4Panel로 되돌아온다 */
function Harness({ checked, onChange = () => {} }: { checked: typeof cards; onChange?: (key: string, text: string) => void }) {
  const [notes, setNotes] = useState<Record<string, string>>({});
  return <D4Panel cards={checked} response={response} notes={notes} onChange={(key, text) => { onChange(key, text); setNotes((n) => ({ ...n, [key]: text })); }}
    caseName="Case A" persistent storageBlocked={false} storeMessage="" picked={[]} />;
}
const field = (placeholder: string) => screen.getByPlaceholderText(placeholder) as HTMLTextAreaElement;
const escape = () => field("Why the defect was not caught in your process");
const root = () => field("The service does not fill or suggest this");
const verify = () => field("How you will verify the cause (kept here only)");
const preview = () => document.querySelector("pre")!.textContent ?? "";
const copy = () => screen.getByRole("button", { name: "Copy the D4 text" }) as HTMLButtonElement;
const download = () => screen.getByRole("button", { name: /Download \.docx|Making the file/ }) as HTMLButtonElement;
const tick = () => screen.getByRole("checkbox") as HTMLInputElement;

// ---- 선례 삽입 체크박스 (#167) ----
it("체크박스 하나가 D4 칸 본문과 부록 둘 다를 정한다 — 켜면 둘 다 들어가고 끄면 둘 다 빠지며, 원인 글이 없는 선례는 건너뛴다고 알린다", async () => {
  const user = userEvent.setup();
  render(<Harness checked={[withText[0], without]} />);
  expect(tick().checked).toBe(false);
  expect(copy().disabled).toBe(true); // 쓴 글도 선례 선택도 없으면 내보낼 것이 없다
  expect(preview()).not.toContain("타사 선례");
  expect(preview()).not.toContain(D4_EVIDENCE_TITLE);

  await user.click(tick());
  expect(tick().checked).toBe(true);
  expect(copy().disabled).toBe(false);
  expect(preview()).toContain(D4_EVIDENCE_TITLE); // D4 칸 본문
  expect(preview()).toContain(APPENDIX_TITLE); // 표 뒤 부록
  expect(preview().match(new RegExp(`\\[타사 선례 ${withText[0].campno} `, "g"))).toHaveLength(2); // 같은 인용이 두 곳에 한 번씩
  expect(preview()).not.toContain(without.campno);
  expect(screen.getByText(new RegExp(`No cause text for ${without.campno} — left out, nothing is filled in\\.`))).toBeTruthy();

  await user.click(tick());
  expect(preview()).not.toContain("타사 선례");
  expect(preview()).not.toContain(APPENDIX_TITLE);
  expect(copy().disabled).toBe(true);
  expect(screen.queryByText(/left out, nothing is filled in/)).toBeNull();
});

// ---- 작성 칸 키·복사·내려받기 인자 연결 (#159) ----
it("세 작성 칸은 각자의 @d4 키로 글을 올리고, 파일 미리보기에는 Escape·Root Cause만 들어간다 (검증 방법은 빠진다)", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<Harness checked={[withText[0]]} onChange={onChange} />);
  await user.type(escape(), "ESC-TEXT");
  await user.type(root(), "ROOT-TEXT");
  await user.type(verify(), "VERIFY-TEXT");
  expect(onChange).toHaveBeenCalledWith(D4_KEYS.escape, "ESC-TEXT");
  expect(onChange).toHaveBeenCalledWith(D4_KEYS.root, "ROOT-TEXT");
  expect(onChange).toHaveBeenCalledWith(D4_KEYS.verify, "VERIFY-TEXT");
  expect(preview()).toMatch(/Escape Cause[^\n]*\nESC-TEXT\n/);
  expect(preview()).toMatch(/Root Cause[^\n]*\nROOT-TEXT\n/);
  expect(preview()).not.toContain("VERIFY-TEXT");
  expect(preview()).not.toContain("타사 선례"); // 선례 선택을 켜기 전에는 타사 원문이 들어가지 않는다
  expect(escape().value).toBe("ESC-TEXT"); // 입력 칸에는 세 글 모두 그대로 보인다
  expect(verify().value).toBe("VERIFY-TEXT");
});

it("복사 단추는 미리보기와 같은 글을 클립보드에 넣고, 클립보드를 쓸 수 없으면 직접 선택하라고 알린다", async () => {
  const user = userEvent.setup();
  render(<Harness checked={[withText[0]]} />);
  await user.type(root(), "ROOT-TEXT");
  await user.click(tick());
  await user.click(copy());
  expect(await navigator.clipboard.readText()).toBe(preview());
  expect(screen.getByText("Copied the D4 text.")).toBeTruthy();

  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
  await user.click(copy());
  expect(await screen.findByText("Could not copy — select the preview text instead.")).toBeTruthy();
});

const W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
const p = (t = "") => (t ? `<w:p><w:r><w:t>${t}</w:t></w:r></w:p>` : "<w:p/>");
const tc = (...x: string[]) => `<w:tc><w:tcPr><w:tcW w:w="100" w:type="dxa"/></w:tcPr>${x.join("")}</w:tc>`;
const form = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ${W}><w:body><w:tbl><w:tr>${tc(p("SUBJECT"))}${tc(p())}</w:tr><w:tr>${tc(p("DISCIPLINE 4"), p("DEFINE THE PROBLEM CAUSE"))}${tc(p())}</w:tr></w:tbl><w:p><w:r><w:t>END</w:t></w:r></w:p></w:body></w:document>`;
async function docxFile(name: string) {
  const zip = new JSZip();
  zip.file("word/document.xml", form);
  return new File([await zip.generateAsync({ type: "arraybuffer" })], name);
}

it("8D 양식(.docx)을 올리면 D4 칸을 찾아 보이고, 내려받으면 쓴 글·선례 인용이 들어간 새 파일을 만들며 원본 이름 뒤에 _D4를 붙인다", async () => {
  const user = userEvent.setup();
  const made: Blob[] = [];
  const downloaded: string[] = [];
  Object.assign(URL, { createObjectURL: (blob: Blob) => { made.push(blob); return "blob:fake"; }, revokeObjectURL: () => {} }); // jsdom에는 없다
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { downloaded.push(this.download); });
  render(<Harness checked={withText.slice(0, 2)} />);
  expect(download().disabled).toBe(true); // 파일을 올리기 전에는 꺼져 있다

  await user.type(root(), "ROOT-TEXT");
  await user.click(tick());
  await user.upload(screen.getByLabelText("8D form file"), await docxFile("my8d.docx"));
  const select = (await screen.findByRole("combobox", { name: "D4 cell" })) as HTMLSelectElement;
  expect(select.options[0].textContent).toMatch(/^Detected: table 1, row 2 — “DISCIPLINE 4/);
  await waitFor(() => expect(download().disabled).toBe(false));

  await user.click(download());
  await waitFor(() => expect(downloaded).toEqual(["my8d_D4.docx"]));
  const out = await JSZip.loadAsync(await made[0].arrayBuffer());
  const xml = await out.file("word/document.xml")!.async("string");
  expect(xml).toContain("ROOT-TEXT"); // D4 칸에 엔지니어 글
  expect(xml).toContain(D4_EVIDENCE_TITLE); // 본문 선택이 파일에 이어졌다
  expect(xml).toContain(APPENDIX_TITLE); // 부록 선택도 이어졌다
  for (const c of withText.slice(0, 2)) expect(xml).toContain(c.campno);
  expect(xml.indexOf(APPENDIX_TITLE)).toBeGreaterThan(xml.indexOf("</w:tbl>")); // 부록은 표 뒤
  expect(xml.indexOf(D4_EVIDENCE_TITLE)).toBeLessThan(xml.indexOf("</w:tbl>")); // 본문 인용은 D4 칸 안
  expect(await screen.findByText(/^Downloaded my8d_D4\.docx\. D4 text inserted \(including 2 precedent quote\(s\) after your text\); appendix 2 precedent\(s\) placed after the 8D table\./)).toBeTruthy();
});
