import JSZip from "jszip";
import { expect, it } from "vitest";
import { DOCX_MIME, DocxError, inspectDocx, patchDocumentXml, patchDocx, stepOfLabel } from "./docxPatch";

const W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
const p = (text = "", ppr = "", rpr = "") => text ? `<w:p>${ppr}<w:r>${rpr}<w:t>${text}</w:t></w:r></w:p>` : `<w:p>${ppr}</w:p>`;
const tc = (...ps: string[]) => `<w:tc><w:tcPr><w:tcW w:w="100" w:type="dxa"/></w:tcPr>${ps.join("")}</w:tc>`;
const tr = (...cells: string[]) => `<w:tr><w:trPr><w:cantSplit/></w:trPr>${cells.join("")}</w:tr>`;
const tbl = (...rows: string[]) => `<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>${rows.join("")}</w:tbl>`;
const doc = (...body: string[]) => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ${W}><w:body>${body.join("")}</w:body></w:document>`;
const PPR = '<w:pPr><w:pStyle w:val="CellText"/><w:spacing w:after="60"/></w:pPr>';
const split = (a: string, b: string) => `<w:p><w:r><w:t>${a}</w:t></w:r><w:r><w:t>${b}</w:t></w:r></w:p>`; // 글자가 run 사이에서 끊긴 라벨
const form = (...contents: string[]) => doc(
  p("CORRECTIVE ACTION REPORT"),
  tbl(tr(tc(p("TO")), tc(p()), tc(p("DATE")), tc(p())), tr(tc(p("SUBJECT")), tc(p()))),
  tbl(tr(tc(p("8-DISCIPLINE REPORT"))),
    tr(tc(split("DISC", "IPLINE 2"), p("PROBLEM DESCRIPTION")), tc(p("내 글", PPR, "<w:rPr><w:rFonts w:ascii=\"Arial\"/><w:b/><w:sz w:val=\"19\"/></w:rPr>"))),
    tr(tc(p("DISCIPLINE 3"), p("CONTAINMENT ACTION")), tc(p("", PPR))),
    tr(tc(p("DISCIPLINE 4"), p("DEFINE THE PROBLEM CAUSE")), tc(p("A", PPR))),
    ...contents.map((c) => tr(tc(p(c)), tc(p())))));
const content = (steps: Parameters<typeof patchDocumentXml>[1]["steps"], extra: Partial<Parameters<typeof patchDocumentXml>[1]> = {}) => ({ subject: "", footer: null, steps, ...extra });

it("라벨로 8D 단계를 가른다 — DEFINE THE PROBLEM CAUSE는 원인(4), PROBLEM DESCRIPTION은 문제(2)", () => {
  expect(stepOfLabel("DISCIPLINE 4 DEFINE THE PROBLEM CAUSE")).toBe(4);
  expect(stepOfLabel("DISCIPLINE 2 PROBLEM DESCRIPTION")).toBe(2);
  expect(stepOfLabel("D3 임시 조치(봉쇄)")).toBe(3);
  expect(stepOfLabel("PREVENTIVE RECURRENCE")).toBe(7);
  expect(stepOfLabel("TO")).toBeNull();
  expect(stepOfLabel("")).toBeNull();
  expect(stepOfLabel("PROBLEM ".repeat(30))).toBeNull(); // 안내 문단처럼 긴 글은 라벨이 아니다
});
it("글이 run 사이에서 끊긴 라벨도 읽고, 인식한 칸 위치를 표·행·열로 알려 준다", async () => {
  const zip = new JSZip(); zip.file("word/document.xml", form());
  const view = await inspectDocx(await zip.generateAsync({ type: "blob" }));
  expect(view.matches).toEqual({ 2: [{ table: 2, row: 2, col: 2 }], 3: [{ table: 2, row: 3, col: 2 }], 4: [{ table: 2, row: 4, col: 2 }] });
  expect(view.cells).toContainEqual({ table: 1, row: 2, col: 2, label: "SUBJECT", guess: null }); // 단계 라벨이 아닌 칸도 직접 고를 수 있게 후보에 든다
  expect(view.cells).toContainEqual({ table: 2, row: 4, col: 2, label: "DISCIPLINE 4 DEFINE THE PROBLEM CAUSE", guess: 4 });
  expect(view.subject).toBe(true);
});
// 같은 단계 라벨이 두 번 나오는 양식 — 문서 번호 칸("Problem Report No.")이 진짜 문제 기술 칸보다 앞에 있다
const twoProblems = () => doc(tbl(
  tr(tc(p("Supplier Problem Report No.")), tc(p("SPR-1"))),
  tr(tc(p("Problem Description")), tc(p())),
  tr(tc(p("Root Cause")), tc(p()))));
it("라벨이 맞은 칸이 여럿이면 짐작하지 않고 넣지 않으며 ambiguous로 알린다(DEC-064 보완)", () => {
  const r = patchDocumentXml(twoProblems(), content({ 2: [{ text: "내용" }], 4: [{ text: "원인" }] }));
  expect(r.ambiguous).toEqual([2]);
  expect(r.filled).toEqual([4]);
  expect(r.xml).not.toContain("내용");
  expect(r.xml).toContain("원인");
});
it("사용자가 고른 칸이 라벨 인식보다 우선한다 — 후보가 여럿이어도, 라벨이 없는 칸이어도 넣는다", () => {
  const r = patchDocumentXml(twoProblems(), content({ 2: [{ text: "내용" }] }, { cells: { 2: { table: 1, row: 2, col: 2 } } }));
  expect(r.filled).toEqual([2]);
  expect(r.ambiguous).toEqual([]);
  expect(r.xml.indexOf("내용")).toBeGreaterThan(r.xml.indexOf("Problem Description"));
  expect(r.xml.indexOf("내용")).toBeLessThan(r.xml.indexOf("Root Cause"));
  const free = patchDocumentXml(twoProblems(), content({ 3: [{ text: "봉쇄" }] }, { cells: { 3: { table: 1, row: 1, col: 2 } } })); // "Supplier Problem Report No." 옆 칸
  expect(free.filled).toEqual([3]);
  expect(free.xml.indexOf("봉쇄")).toBeGreaterThan(free.xml.indexOf("SPR-1"));
});
it("고른 칸이 문서에 없으면 다른 칸으로 바꿔 넣지 않고 missing으로 알린다", () => {
  const r = patchDocumentXml(twoProblems(), content({ 2: [{ text: "내용" }] }, { cells: { 2: { table: 9, row: 1, col: 2 } } }));
  expect(r.missing).toEqual([2]);
  expect(r.xml).not.toContain("내용");
});
it("칸 끝에 문단을 덧붙이고, 덧붙인 글 밖은 원본과 바이트가 같다", () => {
  const xml = form();
  const r = patchDocumentXml(xml, content({ 2: [{ text: "한 줄" }, { text: "두 줄" }] }));
  // 칸의 마지막 문단과 같은 문단 서식·글자 서식을 쓰되 굵기는 가져오지 않는다
  const added = `<w:p>${PPR}<w:r><w:rPr><w:rFonts w:ascii="Arial"/><w:sz w:val="19"/></w:rPr><w:t xml:space="preserve">한 줄</w:t></w:r></w:p><w:p>${PPR}<w:r><w:rPr><w:rFonts w:ascii="Arial"/><w:sz w:val="19"/></w:rPr><w:t xml:space="preserve">두 줄</w:t></w:r></w:p>`;
  const cellEnd = xml.indexOf("</w:tc>", xml.indexOf("내 글"));
  expect(r.xml).toBe(xml.slice(0, cellEnd) + added + xml.slice(cellEnd));
  expect(r.filled).toEqual([2]);
});
it("글자를 XML로 안전하게 넣는다(& < > 와 선행 공백)", () => {
  const r = patchDocumentXml(form(), content({ 4: [{ text: '  A & B <script>"x"</script>' }] }));
  expect(r.xml).toContain('<w:t xml:space="preserve">  A &amp; B &lt;script&gt;"x"&lt;/script&gt;</w:t>');
  expect(r.xml).not.toContain("<script>");
});
it("칸이 여럿인 단계는 칸 이름을 굵게 앞에 붙인다(rPr 순서 유지)", () => {
  const r = patchDocumentXml(form(), content({ 4: [{ prefix: "Root Cause: ", text: "원인 글" }] }));
  expect(r.xml).toContain('<w:r><w:rPr><w:b/><w:bCs/></w:rPr><w:t xml:space="preserve">Root Cause: </w:t></w:r><w:r><w:t xml:space="preserve">원인 글</w:t></w:r>');
});
it("칸이 비어 있으면 빈 문단 자리에 넣어 위쪽에 빈 줄이 생기지 않는다", () => {
  const xml = form();
  const r = patchDocumentXml(xml, content({ 3: [{ text: "잠정 조치" }] }));
  expect(r.xml).not.toContain(`<w:tc><w:tcPr><w:tcW w:w="100" w:type="dxa"/></w:tcPr>${p("", PPR)}</w:tc>`);
  expect(r.xml).toContain(`${PPR}<w:r><w:t xml:space="preserve">잠정 조치</w:t></w:r></w:p></w:tc>`);
  expect(r.xml.split("<w:p>").length).toBe(xml.split("<w:p>").length); // 문단 수는 그대로(빈 문단을 바꿈)
});
it("빈 칸이 self-closing 문단(<w:p/>)뿐이어도 넣는다", () => {
  const xml = doc(tbl(tr(tc(p("CONTAINMENT ACTION")), tc("<w:p/>"))));
  const r = patchDocumentXml(xml, content({ 3: [{ text: "X" }] }));
  expect(r.xml).toContain('<w:t xml:space="preserve">X</w:t></w:r></w:p></w:tc>');
  expect(r.xml).not.toContain("<w:p/>");
});
it("글이 없는 단계는 건드리지 않고, 글이 있는데 칸을 못 찾은 단계는 알린다", () => {
  const xml = form();
  const r = patchDocumentXml(xml, content({ 2: [], 7: [{ text: "수평 전개" }], 8: [{ text: "종료" }] }));
  expect(r.xml).toBe(xml);
  expect(r.filled).toEqual([]);
  expect(r.missing).toEqual([7, 8]);
});
it("중첩 표 안의 라벨도 찾고, 바깥 칸의 문단을 헷갈리지 않는다", () => {
  const inner = tbl(tr(tc(p("PERMANENT ACTION")), tc(p("기존"))));
  const xml = doc(tbl(tr(tc(p("DISCIPLINE 6 VERIFICATION")), tc(p("v", PPR), inner, p("끝", PPR)))));
  const r = patchDocumentXml(xml, content({ 5: [{ text: "안쪽" }], 6: [{ text: "바깥" }] }));
  expect(r.filled).toEqual([5, 6]);
  const innerEnd = r.xml.indexOf("안쪽");
  expect(r.xml.indexOf("</w:tbl>", innerEnd)).toBeGreaterThan(innerEnd); // 안쪽 글은 안쪽 표 안
  expect(r.xml.indexOf("바깥")).toBeGreaterThan(r.xml.indexOf("</w:tbl>")); // 바깥 글은 안쪽 표가 끝난 뒤
});
it("SUBJECT는 비어 있을 때만 채운다", () => {
  expect(patchDocumentXml(form(), content({}, { subject: "airbag" })).xml).toContain(">airbag</w:t>");
  const filled = doc(tbl(tr(tc(p("SUBJECT")), tc(p("원래 제목")))));
  expect(patchDocumentXml(filled, content({}, { subject: "airbag" })).xml).toBe(filled);
});
it("선례를 넣었을 때의 근거 데이터 줄은 8D 표 바로 뒤에 붙는다", () => {
  const r = patchDocumentXml(form(), content({ 2: [{ text: "a" }] }, { footer: "※ 근거 & 출처" }));
  const second = r.xml.indexOf("</w:tbl>", r.xml.indexOf("DISC"));
  expect(r.xml.slice(second, second + 200)).toContain("</w:tbl><w:p><w:r><w:rPr><w:sz w:val=\"16\"/></w:rPr><w:t xml:space=\"preserve\">※ 근거 &amp; 출처</w:t>");
  expect(patchDocumentXml(form(), content({ 2: [{ text: "a" }] })).xml).not.toContain("w:val=\"16\"");
});
it("구조가 깨진 document.xml은 DocxError", () => {
  expect(() => patchDocumentXml("<w:document><w:tbl><w:tr></w:tbl>", content({}))).toThrow(DocxError);
});

const build = async (parts: Record<string, string | Uint8Array>) => {
  const zip = new JSZip();
  for (const [name, data] of Object.entries(parts)) zip.file(name, data);
  return await zip.generateAsync({ type: "blob" });
};
it("새 .docx는 document.xml만 바뀌고 다른 파트(스타일·그림 등)는 내용이 같다", async () => {
  const picture = new Uint8Array([137, 80, 78, 71, 0, 1, 2, 255, 254]);
  const file = await build({ "[Content_Types].xml": "<Types/>", "_rels/.rels": "<Relationships/>", "word/styles.xml": "<styles>한글</styles>", "word/media/image1.png": picture, "word/document.xml": form() });
  const r = await patchDocx(file, content({ 2: [{ text: "새 글" }] }));
  expect(r.blob.type).toBe(DOCX_MIME);
  const out = await JSZip.loadAsync(await r.blob.arrayBuffer());
  expect(Object.keys(out.files).sort()).toEqual(Object.keys((await JSZip.loadAsync(await file.arrayBuffer())).files).sort()); // 항목 목록이 그대로(폴더 항목을 새로 만들지 않음)
  expect(await out.file("word/styles.xml")!.async("string")).toBe("<styles>한글</styles>");
  expect([...(await out.file("word/media/image1.png")!.async("uint8array"))]).toEqual([...picture]);
  expect(await out.file("word/document.xml")!.async("string")).toContain("새 글");
});
it("폴더 항목이 없는 원본(Word가 만든 모양)에서도 항목 목록이 그대로다", async () => {
  const zip = new JSZip();
  zip.file("[Content_Types].xml", "<Types/>", { createFolders: false });
  zip.file("word/document.xml", form(), { createFolders: false });
  const file = await zip.generateAsync({ type: "blob" });
  const r = await patchDocx(file, content({ 2: [{ text: "x" }] }));
  expect(Object.keys((await JSZip.loadAsync(await r.blob.arrayBuffer())).files).sort()).toEqual(["[Content_Types].xml", "word/document.xml"]);
});
it("Word 파일이 아니면 DocxError로 알린다", async () => {
  await expect(patchDocx(new Blob(["그냥 글"]), content({}))).rejects.toThrow("읽지 못했습니다");
  await expect(patchDocx(await build({ "a.txt": "x" }), content({}))).rejects.toThrow("word/document.xml");
  await expect(inspectDocx(new Blob(["x"]))).rejects.toBeInstanceOf(DocxError);
});
