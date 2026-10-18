import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { MODELS } from "./config";

// 화면 CLI 배포(DEC-058)가 비밀값·빌드 산출물·보관 모델을 올리지 않는지 — API 쪽 tests/test_vercel_entry.py와 같은 취지
const lines = readFileSync(new URL("../.vercelignore", import.meta.url), "utf8")
  .split("\n")
  .map((line) => line.trim())
  .filter((line) => line && !line.startsWith("#"));
const allowed = lines.filter((line) => line.startsWith("!")).map((line) => line.slice(1));

describe("화면 .vercelignore", () => {
  it("먼저 전부 막고 허용 목록만 연다", () => {
    expect(lines[0]).toBe("/*");
    expect(allowed).toEqual([
      "index.html",
      "package.json",
      "package-lock.json",
      ".nvmrc",
      "tsconfig*.json",
      "vite.config.ts",
      "vercel.json",
      "src",
      "public",
      "public/models/sonata.glb",
      "public/models/sorento.glb",
    ]);
  });
  it("비밀값·빌드 산출물·의존성 폴더는 열지 않는다", () => {
    expect(allowed.some((path) => /^(\.env|dist|node_modules)/.test(path))).toBe(false);
  });
  it("랜딩 배경 영상·포스터는 배포에 올리지 않는다(DEC-074)", () => {
    expect(lines.indexOf("public/landing/*")).toBeGreaterThan(lines.indexOf("!public"));
    expect(allowed.some((path) => path.startsWith("public/landing"))).toBe(false);
  });
  it("3D 모델은 화면이 부르는 파일만 연다(#108)", () => {
    expect(lines.indexOf("public/models/*")).toBeGreaterThan(lines.indexOf("!public"));
    const models = allowed.filter((path) => path.startsWith("public/models/")).map((path) => path.replace("public/", ""));
    expect(models.sort()).toEqual(Object.values(MODELS).map((model) => model.glb).sort());
  });
});
