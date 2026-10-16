import { expect, it } from "vitest";
import { adoptNotes, clearNotes, loadNotes, nextUnsaved, normalizeCaseName, notesText, noteKey, saveNote, UNNAMED_MARK, type StorageLike } from "./notes";

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
  const { notes, saved } = adoptNotes(s, "Case A", { "2": "새 메모" });
  expect(notes).toEqual({ "1": "저장된 글", "2": "새 메모" });
  expect(saved).toBe(true);
  expect(loadNotes(s, "Case A")).toEqual({ "1": "저장된 글", "2": "새 메모" });
  expect(adoptNotes(null, "Case A", { "3": "x" })).toEqual({ notes: { "3": "x" }, saved: false });
});
it("같은 리콜에 서로 다른 글이 있으면 어느 쪽도 버리지 않고 이어 붙인다", () => {
  const s = memory();
  saveNote(s, "Case A", "1", "예전 글");
  const { notes } = adoptNotes(s, "Case A", { "1": "방금 쓴 글" });
  expect(notes["1"]).toBe(`예전 글\n\n${UNNAMED_MARK}\n방금 쓴 글`);
  expect(loadNotes(s, "Case A")["1"]).toBe(notes["1"]);
  expect(adoptNotes(s, "Case A", { "1": notes["1"] }).notes["1"]).toBe(notes["1"]); // 같은 글이면 다시 붙이지 않는다
  expect(adoptNotes(s, "Case A", { "1": "예전 글" }).notes["1"]).toBe(notes["1"]);
});
it("저장소가 쓰기에 실패하면 saved가 false이고 화면 메모는 그대로 돌려준다", () => {
  const full: StorageLike = { length: 0, key: () => null, getItem: () => null, removeItem: () => {}, setItem: () => { throw new Error("QuotaExceededError"); } };
  expect(adoptNotes(full, "Case A", { "1": "글" })).toEqual({ notes: { "1": "글" }, saved: false });
});
it("사건 이름에 |가 있어도 다른 사건의 메모가 섞이거나 함께 지워지지 않는다", () => {
  const s = memory();
  saveNote(s, "Case A", "1", "a");
  saveNote(s, "Case A|B", "1", "ab");
  saveNote(s, "A", "x|y", "리콜 번호 쪽 |는 이름과 겹치지 않는다");
  expect(loadNotes(s, "Case A")).toEqual({ "1": "a" });
  expect(loadNotes(s, "Case A|B")).toEqual({ "1": "ab" });
  expect(clearNotes(s, "Case A")).toBe(true);
  expect(loadNotes(s, "Case A")).toEqual({});
  expect(loadNotes(s, "Case A|B")).toEqual({ "1": "ab" });
  expect(loadNotes(s, "A")).toEqual({ "x|y": "리콜 번호 쪽 |는 이름과 겹치지 않는다" });
});
it("clearNotes는 저장소가 막혔으면 false", () => {
  const blocked: StorageLike = { length: 1, key: () => "casebook.note.v1|A|1", getItem: () => null, setItem: () => {}, removeItem: () => { throw new Error("blocked"); } };
  expect(clearNotes(blocked, "A")).toBe(false);
  expect(clearNotes(null, "A")).toBe(false);
});
it("저장된 글의 일부 단어와 겹쳐도 다른 메모면 버리지 않는다", () => {
  const s = memory();
  saveNote(s, "Case A", "1", "not confirmed");
  const { notes } = adoptNotes(s, "Case A", { "1": "confirmed" });
  expect(notes["1"]).toBe(`not confirmed\n\n${UNNAMED_MARK}\nconfirmed`);
});
it("저장 실패한 메모 집합은 다른 메모를 저장해도 비지 않는다", () => {
  let failed = nextUnsaved(new Set(), "A", false);
  failed = nextUnsaved(failed, "B", true);
  expect([...failed]).toEqual(["A"]);
  failed = nextUnsaved(failed, "B", false);
  expect([...failed].sort()).toEqual(["A", "B"]);
  failed = nextUnsaved(nextUnsaved(failed, "A", true), "B", true);
  expect(failed.size).toBe(0);
});
it("80자에서 이모지가 잘려도 사건 이름 처리가 예외를 던지지 않는다", () => {
  const name = `${"x".repeat(79)}😀😀`;
  const normalized = normalizeCaseName(name);
  expect(Array.from(normalized)).toHaveLength(80);
  const s = memory();
  expect(() => loadNotes(s, name)).not.toThrow();
  expect(saveNote(s, name, "1", "글")).toBe(true);
  expect(loadNotes(s, name)).toEqual({ "1": "글" });
});
