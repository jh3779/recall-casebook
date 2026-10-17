import JSZip from "jszip";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { patchDocx } from "../eightd/docxPatch";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type SearchResponse } from "../search/types";
import { D4_KEYS, d4Export, d4Values, exportMessage } from "./d4Doc";
import { D4Panel } from "./D4Panel";
import { D4_QUESTIONS, QUESTION_UNKNOWN } from "./questions";
import { isUnsaved, loadNotes, losesNotesOnSwitch, notesText, saveNote, type StorageLike } from "./notes";

const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const withText = cards.filter((c) => hasCauseText(c.cause));
const without = cards.filter((c) => !hasCauseText(c.cause));
const VERIFY = "VERIFY-ONLY-SECRET-PLAN";
const values = { escape: "검사 공정에서 탐지하지 못했다", root: "우리 건의 근본 원인 초안", verify: VERIFY };
const prov = { build_id: response.build_id, snapshot_date: response.snapshot_date };

it("D4 글에는 엔지니어가 쓴 Escape·Root Cause만 들어가고 검증 방법은 빠진다", () => {
  const out = d4Export({ values, cards: [], includeAppendix: false, prov });
  expect(out.steps[4].map((p) => (p.prefix ?? "") + p.text)).toEqual(["Escape Cause: 검사 공정에서 탐지하지 못했다", "Root Cause: 우리 건의 근본 원인 초안"]);
  expect(out.text).toContain("DISCIPLINE 4");
  expect(out.text).not.toContain(VERIFY);
  expect(JSON.stringify(out)).not.toContain(VERIFY);
});
it("부록은 고르지 않으면 비어 있고(체크해도 자동으로 들어가지 않는다), 골라도 원인 글이 있는 선례만 들어간다", () => {
  const off = d4Export({ values, cards, includeAppendix: false, prov });
  expect(off.appendix).toEqual([]);
  expect(off.footer).toBeNull();
  expect(off.appendixCount).toBe(0);
  const on = d4Export({ values, cards, includeAppendix: true, prov });
  expect(on.appendixCount).toBe(withText.length);
  expect(on.skipped).toEqual(without.map((c) => c.campno));
  expect(on.footer).toContain(response.build_id);
});
it("부록 인용은 DEC-064 ③ 형식 — 머리줄·원문 그대로·말한 주체·출처 파일·sha256 앞 12자를 유지한다", () => {
  const on = d4Export({ values, cards: withText, includeAppendix: true, prov });
  const text = on.appendix.map((p) => p.text).join("\n");
  for (const c of withText) {
    if (!hasCauseText(c.cause)) continue;
    expect(text).toContain(`[타사 선례 ${c.campno} · ${c.maker}`);
    expect(text).toContain(`"${c.cause.text}"`);
    expect(text).toContain(`말한 주체: ${c.cause.speaker}`);
    expect(text).toContain(c.cause.source.file);
    expect(text).toContain(c.cause.source.pdf_sha256.slice(0, 12));
  }
});
it("쓴 글도 부록도 없으면 내보낼 것이 없다", () => {
  expect(d4Export({ values: { escape: "", root: "  ", verify: VERIFY }, cards, includeAppendix: false, prov }).hasContent).toBe(false);
  expect(d4Export({ values: { escape: "", root: "", verify: "" }, cards: without, includeAppendix: true, prov }).hasContent).toBe(false); // 부록을 골라도 원인 글이 하나도 없으면 빈 부록을 만들지 않는다
  expect(d4Export({ values, cards: [], includeAppendix: false, prov }).hasContent).toBe(true);
});

const W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
const p = (t = "") => (t ? `<w:p><w:r><w:t>${t}</w:t></w:r></w:p>` : "<w:p/>");
const tc = (...x: string[]) => `<w:tc><w:tcPr><w:tcW w:w="100" w:type="dxa"/></w:tcPr>${x.join("")}</w:tc>`;
const form = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ${W}><w:body><w:tbl><w:tr>${tc(p("SUBJECT"))}${tc(p())}</w:tr><w:tr>${tc(p("DISCIPLINE 4"), p("DEFINE THE PROBLEM CAUSE"))}${tc(p())}</w:tr></w:tbl><w:p><w:r><w:t>END</w:t></w:r></w:p></w:body></w:document>`;
async function docxBlob() { const zip = new JSZip(); zip.file("word/document.xml", form); return zip.generateAsync({ type: "blob" }); }
const read = async (blob: Blob) => (await (await JSZip.loadAsync(await blob.arrayBuffer())).file("word/document.xml")!.async("string"));

it(".docx로 내보내면 D4 칸에 엔지니어 글이, 8D 표 뒤에 부록이 들어가고 검증 방법은 파일 어디에도 없다", async () => {
  const out = d4Export({ values, cards: withText.slice(0, 2), includeAppendix: true, prov });
  const r = await patchDocx(await docxBlob(), { subject: "", steps: out.steps, footer: out.footer, appendix: out.appendix });
  expect(r.filled).toEqual([4]);
  expect(r.appendixPlaced).toBe(true);
  const xml = await read(r.blob);
  expect(xml).toContain("검사 공정에서 탐지하지 못했다");
  expect(xml).toContain("우리 건의 근본 원인 초안");
  expect(xml).not.toContain(VERIFY);
  const table = xml.indexOf("</w:tbl>");
  expect(xml.indexOf("우리 건의 근본 원인 초안")).toBeLessThan(table); // D4 칸 안
  expect(xml.indexOf("타사 선례")).toBeGreaterThan(table); // 부록은 표 밖(뒤)
  expect(xml).toContain(response.build_id);
});
it("부록을 고르지 않으면 파일에 타사 원문이 한 글자도 들어가지 않는다", async () => {
  const out = d4Export({ values, cards: withText, includeAppendix: false, prov });
  const r = await patchDocx(await docxBlob(), { subject: "", steps: out.steps, footer: out.footer, appendix: out.appendix });
  const xml = await read(r.blob);
  expect(xml).not.toContain("타사 선례");
  for (const c of withText) if (hasCauseText(c.cause)) expect(xml).not.toContain(c.cause.text.slice(0, 40));
});

it("D4 글은 메모와 같은 저장 키 장치로 사건 이름 아래 저장·복원되고, 메모 복사에는 섞이지 않는다", () => {
  const data = new Map<string, string>();
  const s: StorageLike = { get length() { return data.size; }, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => { data.set(k, v); }, removeItem: (k) => { data.delete(k); }, key: (i) => [...data.keys()][i] ?? null };
  saveNote(s, "Case A", D4_KEYS.root, "내 근본 원인");
  saveNote(s, "Case B", D4_KEYS.root, "다른 사건");
  const loaded = loadNotes(s, "Case A");
  expect(d4Values(loaded).root).toBe("내 근본 원인");
  expect(loadNotes(s, "Case B")[D4_KEYS.root]).toBe("다른 사건");
  expect(notesText(cards, loaded)).toBe(""); // 선례 메모 복사에 D4 글이 끼지 않는다
});

const panel = (checked = cards.slice(0, 2), notes: Record<string, string> = {}) => renderToStaticMarkup(<D4Panel cards={checked} response={response} notes={notes} onChange={() => {}} />);
it("D4 칸은 고정 확인 질문 전부와 세 입력 칸을 보이고, 서비스가 채우지 않는다고 밝힌다", () => {
  const m = panel();
  for (const q of D4_QUESTIONS) expect(m).toContain(renderToStaticMarkup(<span>{q}</span>).slice(6, -7));
  expect(m).toContain("never fills or suggests");
  expect(m).toContain("Escape Cause");
  expect(m).toContain("Root Cause");
  expect(m).toContain("stays here — the 8D form has no cell for it");
  expect(m).toContain("not exported");
  expect(m).not.toMatch(/type="checkbox"[^>]*checked/); // 부록은 기본 꺼짐
  expect(m).toMatch(/<button[^>]*disabled[^>]*>Download \.docx/);
  expect(m).toMatch(/<button[^>]*disabled[^>]*>Copy the D4 text/);
});
it("미보고·조사 중 원인 글이 있는 선례를 체크하면 확인 문장이 하나 더 보인다", () => {
  const unknown = cards.find((c) => c.cause.status === "stated_unknown")!;
  expect(panel([unknown])).toContain(renderToStaticMarkup(<span>{QUESTION_UNKNOWN}</span>).slice(6, -7));
  const plain = cards.find((c) => c.cause.status === "filled")!;
  expect(panel([plain])).not.toContain(renderToStaticMarkup(<span>{QUESTION_UNKNOWN}</span>).slice(6, -7));
});
it("쓴 글이 있으면 복사·내려받기 준비가 되고, 저장된 글이 입력 칸에 그대로 보인다", () => {
  const m = panel(cards.slice(0, 1), { [D4_KEYS.root]: "내 근본 원인", [D4_KEYS.verify]: VERIFY });
  expect(m).toContain("내 근본 원인");
  expect(m).toContain(VERIFY); // 입력 칸에는 보이지만
  expect(m).toMatch(/<button(?![^>]*disabled)[^>]*>Copy the D4 text/);
  expect(m.split("Preview of what goes into the file")[1]).not.toContain(VERIFY); // 파일 미리보기에는 없다
});

it("검색 문장은 SUBJECT 칸에도 복사문에도 들어가지 않는다 — 양식의 빈 SUBJECT 칸은 그대로다", async () => {
  const SEARCH = "brake noise possible leak";
  const out = d4Export({ values, cards: withText.slice(0, 1), includeAppendix: true, prov });
  expect(out.text).not.toContain("SUBJECT");
  expect(out.text).not.toContain(SEARCH);
  expect(out.text.startsWith("DISCIPLINE 4")).toBe(true);
  const xml = await read((await patchDocx(await docxBlob(), { subject: "", steps: out.steps, footer: out.footer, appendix: out.appendix })).blob);
  expect(xml).not.toContain(SEARCH);
  expect(xml).toContain("<w:tc><w:tcPr><w:tcW w:w=\"100\" w:type=\"dxa\"/></w:tcPr><w:p/></w:tc></w:tr><w:tr>"); // SUBJECT 줄의 값 칸이 빈 채로 남는다
});

it("8D 표가 없는 파일에는 부록이 들어가지 않고 안내도 넣었다고 말하지 않는다", async () => {
  const zip = new JSZip();
  zip.file("word/document.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ${W}><w:body><w:p><w:r><w:t>no table here</w:t></w:r></w:p></w:body></w:document>`);
  const out = d4Export({ values, cards: withText.slice(0, 2), includeAppendix: true, prov });
  const r = await patchDocx(await zip.generateAsync({ type: "blob" }), { subject: "", steps: out.steps, footer: out.footer, appendix: out.appendix });
  expect(r.appendixPlaced).toBe(false);
  expect(await read(r.blob)).not.toContain(withText[0].campno);
  const msg = exportMessage(r, "f_D4.docx", out.appendixCount);
  expect(msg).toContain("could not be placed");
  expect(msg).not.toContain("placed after the 8D table");
  expect(msg).toContain("D4 text not inserted");
});

it("내려받은 뒤 안내: 부록이 표 뒤에 놓였을 때만 놓였다고 말한다", async () => {
  const out = d4Export({ values, cards: withText.slice(0, 2), includeAppendix: true, prov });
  const r = await patchDocx(await docxBlob(), { subject: "", steps: out.steps, footer: out.footer, appendix: out.appendix });
  const msg = exportMessage(r, "f_D4.docx", out.appendixCount);
  expect(msg).toContain("D4 text inserted");
  expect(msg).toContain("2 precedent(s) placed after the 8D table");
  expect(exportMessage({ filled: [4], missing: [], ambiguous: [], appendixPlaced: null }, "f", 0)).toContain("appendix not added");
});

it("D4 글에 &·<가 있어도 .docx XML이 깨지지 않게 이스케이프한다", async () => {
  const out = d4Export({ values: { escape: "a & b < c", root: "x > y", verify: "" }, cards: [], includeAppendix: false, prov });
  const xml = await read((await patchDocx(await docxBlob(), { subject: "", steps: out.steps, footer: out.footer, appendix: out.appendix })).blob);
  expect(xml).toContain("a &amp; b &lt; c");
  expect(xml).toContain("x &gt; y");
  expect(xml).not.toContain("a & b");
});

it("사건 이름 없이 D4 글만 쓴 상태도 저장 안 된 글로 잡힌다(사건 전환·새 검색 확인창의 근거)", () => {
  const onlyD4 = { [D4_KEYS.root]: "내 근본 원인" };
  expect(isUnsaved("", onlyD4, false, true)).toBe(true);
  expect(isUnsaved("사건A", onlyD4, false, true)).toBe(false);
  expect(isUnsaved("사건A", onlyD4, true, true)).toBe(true);
  expect(losesNotesOnSwitch("사건A", onlyD4, true, true)).toBe(true);
  expect(losesNotesOnSwitch("", onlyD4, false, true)).toBe(false);
});
