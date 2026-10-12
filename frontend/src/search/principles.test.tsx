import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { PrecedentDetail } from "./PrecedentDetail";
import { Welcome } from "./Welcome";
import type { SearchResponse } from "./types";
import fixture from "./__fixtures__/search_airbag.json";

const forbidden = /applies|verdict|is_?applicable|recall[_\s-]?required|리콜\s*대상(입니다|이다)|원인은\s.{0,30}입니다|해당(합니다|됩니다|되지\s*않습니다)|적용(됩니다|되지\s*않습니다)/;
const response = fixture as SearchResponse;
it("렌더 결과에 판정 필드·문구가 없다", () => {
  const html = renderToStaticMarkup(<><Welcome health="loading" onExample={() => {}} onShowroom={() => {}} />{[...response.customer_precedents, ...response.precedents].map((card) => <PrecedentDetail key={card.campno} card={card} response={response} />)}</>);
  expect(html.match(forbidden)).toBeNull();
});
it("테스트와 설명 주석을 제외한 화면 소스에 판정 필드·문구가 없다", () => {
  const root = fileURLToPath(new URL("../", import.meta.url));
  const printer = ts.createPrinter({ removeComments: true });
  function check(dir: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) check(path);
      else if (/\.(ts|tsx)$/.test(path) && !/\.test\./.test(path)) {
        const parsed = ts.createSourceFile(path, readFileSync(path, "utf8"), ts.ScriptTarget.Latest, true);
        expect(printer.printFile(parsed).match(forbidden), path).toBeNull();
      }
    }
  }
  check(root);
});
