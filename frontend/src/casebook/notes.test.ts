import { expect, it } from "vitest";
import { adoptNotes, clearNotes, loadNotes, normalizeCaseName, notesText, noteKey, saveNote, type StorageLike } from "./notes";

function memory(): StorageLike & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data, get length() { return data.size; },
    getItem: (k) => data.get(k) ?? null, setItem: (k, v) => { data.set(k, v); }, removeItem: (k) => { data.delete(k); },
    key: (i) => [...data.keys()][i] ?? null,
  };
}
it("같은 리콜의 메모도 사건 이름이 다르면 섞이지 않는다", () => {
  const s = memory();
  saveNote(s, "Case A", "20V001", "우리 부품과 같은 공급사");
  saveNote(s, "Case B", "20V001", "공급사 다름");
  expect(loadNotes(s, "Case A")).toEqual({ "20V001": "우리 부품과 같은 공급사" });
  expect(loadNotes(s, "Case B")).toEqual({ "20V001": "공급사 다름" });
});
it("사건 이름이 없으면 저장하지 않는다", () => {
  const s = memory();
  expect(saveNote(s, "   ", "20V001", "메모")).toBe(false);
  expect(s.data.size).toBe(0);
  expect(loadNotes(s, "")).toEqual({});
});
it("사건 이름은 공백을 정리하고 한 사건의 메모만 지운다", () => {
  const s = memory();
  expect(normalizeCaseName("  Case   A ")).toBe("Case A");
  saveNote(s, "Case A", "1", "a"); saveNote(s, "Case B", "1", "b");
  clearNotes(s, "Case  A");
  expect(loadNotes(s, "Case A")).toEqual({});
  expect(loadNotes(s, "Case B")).toEqual({ "1": "b" });
});
it("글이 비면 지우고, 저장소가 막혔으면 false를 돌려준다", () => {
  const s = memory();
  saveNote(s, "A", "1", "x");
  saveNote(s, "A", "1", "");
  expect(s.data.has(noteKey("A", "1"))).toBe(false);
  const blocked: StorageLike = { length: 0, key: () => null, getItem: () => null, removeItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  expect(saveNote(blocked, "A", "1", "x")).toBe(false);
  expect(loadNotes(blocked, "A")).toEqual({});
  expect(saveNote(null, "A", "1", "x")).toBe(false);
});
it("전체 복사 글은 체크한 순서대로 메모가 있는 선례만 싣는다", () => {
  const cards = [{ campno: "B", maker: "Ford" }, { campno: "A", maker: "GM" }, { campno: "C", maker: "Kia" }];
  expect(notesText(cards, { A: " 두 번째 ", B: "첫째" })).toBe("[B · Ford]\n첫째\n\n[A · GM]\n두 번째");
});
it("사건 이름을 정하면 저장된 메모를 불러오고 화면에만 있던 메모를 옮긴다", () => {
  const s = memory();
  saveNote(s, "Case A", "1", "저장된 글");
  const merged = adoptNotes(s, "Case A", { "1": "화면 글", "2": "새 메모" });
  expect(merged).toEqual({ "1": "저장된 글", "2": "새 메모" });
  expect(loadNotes(s, "Case A")).toEqual({ "1": "저장된 글", "2": "새 메모" });
  expect(adoptNotes(null, "Case A", { "3": "x" })).toEqual({ "3": "x" });
});
