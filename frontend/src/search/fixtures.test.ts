import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

it("목업 응답 픽스처를 글자 그대로 보관한다", () => {
  const html = readFileSync(new URL("../../../docs/design-system/mockup.html", import.meta.url), "utf8");
  for (const [id, file] of [["data-search", "search_airbag.json"], ["data-health", "health.json"]]) {
    const body = html.match(new RegExp('<script[^>]*id="' + id + '"[^>]*>([\\s\\S]*?)</script>'))![1];
    expect(readFileSync(new URL(`./__fixtures__/${file}`, import.meta.url), "utf8")).toBe(body);
  }
});
