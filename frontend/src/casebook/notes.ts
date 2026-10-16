/**
 * 선례별 메모(DEC-067). 서버·LLM에는 보내지 않고 이 브라우저 안에만 둔다.
 * 저장 키는 "사건 이름 + 리콜 번호"다 — 사건 이름이 없으면 저장하지 않고 화면 메모리에만 둔다(다른 사건의 메모가 같은 선례에 나타나지 않게).
 */
export interface StorageLike { getItem(key: string): string | null; setItem(key: string, value: string): void; removeItem(key: string): void; key(index: number): string | null; readonly length: number }

const PREFIX = "casebook.note.v1|";
export const normalizeCaseName = (name: string) => name.trim().replace(/\s+/g, " ").slice(0, 80);
export const noteKey = (caseName: string, campno: string) => `${PREFIX}${caseName}|${campno}`;

/** 저장소를 못 쓰는 환경(사생활 보호 창·차단)에서는 null — 호출하는 쪽이 메모리에만 두고 경고한다 */
export function browserStorage(): StorageLike | null {
  try {
    const probe = "casebook.probe";
    globalThis.localStorage.setItem(probe, "1");
    globalThis.localStorage.removeItem(probe);
    return globalThis.localStorage;
  } catch { return null; }
}

export function loadNotes(storage: StorageLike | null, caseName: string): Record<string, string> {
  const name = normalizeCaseName(caseName);
  if (!storage || !name) return {};
  const head = `${PREFIX}${name}|`;
  const out: Record<string, string> = {};
  try {
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (key?.startsWith(head)) { const value = storage.getItem(key); if (value) out[key.slice(head.length)] = value; }
    }
  } catch { return out; }
  return out;
}

/** 저장했으면 true. 글이 비면 지운다. 저장소가 막혔으면 false(화면 메모리 값은 그대로 둔다) */
export function saveNote(storage: StorageLike | null, caseName: string, campno: string, text: string): boolean {
  const name = normalizeCaseName(caseName);
  if (!storage || !name) return false;
  try {
    if (text) storage.setItem(noteKey(name, campno), text); else storage.removeItem(noteKey(name, campno));
    return true;
  } catch { return false; }
}

export function clearNotes(storage: StorageLike | null, caseName: string): void {
  const name = normalizeCaseName(caseName);
  if (!storage || !name) return;
  try {
    const head = `${PREFIX}${name}|`;
    const keys: string[] = [];
    for (let i = 0; i < storage.length; i++) { const key = storage.key(i); if (key?.startsWith(head)) keys.push(key); }
    keys.forEach((key) => storage.removeItem(key));
  } catch { /* 저장소가 막혔으면 지울 것도 없다 */ }
}

/** 전체 복사용 글 — 체크한 선례 순서대로, 메모가 있는 것만 */
export function notesText(cards: readonly { campno: string; maker: string }[], notes: Readonly<Record<string, string>>): string {
  return cards.filter((c) => notes[c.campno]?.trim()).map((c) => `[${c.campno} · ${c.maker}]\n${notes[c.campno].trim()}`).join("\n\n");
}

/**
 * 사건 이름을 정했을 때: 저장돼 있던 그 사건의 메모를 불러오고, 이름 없이 화면에만 적어 둔 메모는 저장소에 옮긴다(저장된 글이 있으면 저장된 글이 이긴다).
 * 돌려주는 값이 화면에 둘 메모다. 저장소가 막혔으면 화면 메모를 그대로 돌려준다.
 */
export function adoptNotes(storage: StorageLike | null, caseName: string, memory: Readonly<Record<string, string>>): Record<string, string> {
  const stored = loadNotes(storage, caseName);
  const merged = { ...memory, ...stored };
  for (const [campno, text] of Object.entries(merged)) if (stored[campno] !== text) saveNote(storage, caseName, campno, text);
  return merged;
}
