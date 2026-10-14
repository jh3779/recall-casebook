// 쏘나타 GLB의 참조되지 않는 텍스처 좌표(TEXCOORD_n)만 지운다 — Vercel CLI 업로드 100MB 한도 때문(작업 F, DEC-058).
// 지운 뒤 남은 정점 속성·인덱스의 바이트와 프리미티브별 재질 배정(재질 이름)이 원본과 같을 때만 쓴다.
// 이 모델 전용이다 — 재질 확장(KHR_texture_transform·clearcoat 등)은 이 스크립트가 등록하지 않아 읽고 쓰는 동안 사라질 수 있으므로 확장이 있는 파일은 거부한다.
// 사용: node scripts/strip-unused-texcoords.mjs <원본 sonata GLB> public/models/sonata.glb
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { NodeIO } from "@gltf-transform/core";

// 원본 Sketchfab 파일(DR1KING100K, CC BY 4.0) — README "3D 모델 파일" 절
const SOURCE = { bytes: 116543736, sha256: "e3a9bf1e821ba553e23c51da3d7ac668a9a0e5678a9ba304fd329b4ae0355470" };
const SLOTS = ["BaseColor", "Emissive", "Normal", "Occlusion", "MetallicRoughness"];

const [src, dst] = process.argv.slice(2);
if (!src || !dst) throw new Error("사용: node scripts/strip-unused-texcoords.mjs <원본 GLB> <출력 GLB>");
const input = readFileSync(src);
const sha = createHash("sha256").update(input).digest("hex");
if (input.length !== SOURCE.bytes || sha !== SOURCE.sha256) throw new Error(`원본 쏘나타 GLB가 아니다: ${input.length}바이트 ${sha}`);

const io = new NodeIO();
const before = await io.readBinary(new Uint8Array(input));
const doc = await io.readBinary(new Uint8Array(input));
const extensions = JSON.parse(input.subarray(20, 20 + input.readUInt32LE(12)).toString()).extensionsUsed ?? [];
if (extensions.length) throw new Error(`확장이 있는 GLB는 다루지 않는다: ${extensions.join(", ")}`);
const usedSets = (material) =>
  new Set(SLOTS.filter((slot) => material?.[`get${slot}Texture`]()).map((slot) => material[`get${slot}TextureInfo`]().getTexCoord()));
let removed = 0;
for (const mesh of doc.getRoot().listMeshes())
  for (const prim of mesh.listPrimitives()) {
    const keep = usedSets(prim.getMaterial());
    for (const semantic of prim.listSemantics()) {
      const set = /^TEXCOORD_(\d+)$/.exec(semantic);
      if (set && !keep.has(Number(set[1]))) {
        const accessor = prim.getAttribute(semantic);
        prim.setAttribute(semantic, null);
        if (accessor.listParents().every((parent) => parent === doc.getRoot())) accessor.dispose();
        removed++;
      }
    }
  }

const bytes = (array) => Buffer.from(array.buffer, array.byteOffset, array.byteLength);
const primsOf = (d) => d.getRoot().listMeshes().flatMap((mesh) => mesh.listPrimitives());
const [a, b] = [primsOf(before), primsOf(doc)];
let differences = a.length === b.length ? 0 : 1;
a.forEach((p, i) => {
  const q = b[i];
  for (const semantic of p.listSemantics()) {
    const kept = q.getAttribute(semantic);
    if (kept && !bytes(p.getAttribute(semantic).getArray()).equals(bytes(kept.getArray()))) differences++;
    if (!kept && !semantic.startsWith("TEXCOORD_")) differences++;
  }
  if (!bytes(p.getIndices().getArray()).equals(bytes(q.getIndices().getArray()))) differences++;
  if (p.getMaterial() !== null && p.getMaterial()?.getName() !== q.getMaterial()?.getName()) differences++;
});
if (differences) throw new Error(`원본과 다른 곳 ${differences}개 — 쓰지 않는다`);

const output = await io.writeBinary(doc);
writeFileSync(dst, output);
const outSha = createHash("sha256").update(output).digest("hex");
console.log(JSON.stringify({ removedAttributes: removed, primitives: a.length, source: SOURCE, output: { bytes: output.length, sha256: outSha } }));
