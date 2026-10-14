// 쏘나타 GLB의 참조되지 않는 텍스처 좌표(TEXCOORD_n)만 지운다 — Vercel CLI 업로드 100MB 한도 때문(작업 F, DEC-058).
// 출력을 다시 읽어 남은 정점 속성·인덱스 바이트, 재질 값·텍스처(이미지 지문·texCoord·샘플러), 재질·노드·메시 목록이 원본과 같고,
// 출력이 기록된 배포본(크기·SHA-256·지운 속성 수)과 같을 때만 쓴다.
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
const inputSha = createHash("sha256").update(input).digest("hex");
if (input.length !== SOURCE.bytes || inputSha !== SOURCE.sha256) throw new Error(`원본 쏘나타 GLB가 아니다: ${input.length}바이트 ${inputSha}`);

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
const sha = (buf) => createHash("sha256").update(buf).digest("hex");
const primsOf = (d) => d.getRoot().listMeshes().flatMap((mesh) => mesh.listPrimitives());
// 재질은 이름뿐 아니라 값과 텍스처(이미지 지문·texCoord·샘플러)까지 비교한다
const materialSig = (m) => JSON.stringify(m && {
  name: m.getName(), alphaMode: m.getAlphaMode(), alphaCutoff: m.getAlphaCutoff(), doubleSided: m.getDoubleSided(),
  baseColor: m.getBaseColorFactor(), emissive: m.getEmissiveFactor(), metallic: m.getMetallicFactor(), roughness: m.getRoughnessFactor(),
  textures: SLOTS.map((slot) => {
    const tex = m[`get${slot}Texture`](), info = m[`get${slot}TextureInfo`]();
    return tex && { slot, image: sha(tex.getImage()), mime: tex.getMimeType(), texCoord: info.getTexCoord(),
      sampler: [info.getMagFilter(), info.getMinFilter(), info.getWrapS(), info.getWrapT()] };
  }),
});
// 원본과 "다시 읽은 출력"을 비교한다 — 쓰기 과정에서 바뀐 것도 잡는다
const compare = (orig, out) => {
  const [a, b] = [primsOf(orig), primsOf(out)];
  let differences = a.length === b.length ? 0 : 1;
  a.forEach((p, i) => {
    const q = b[i];
    if (!q) return;
    for (const semantic of p.listSemantics()) {
      const kept = q.getAttribute(semantic);
      if (kept && !bytes(p.getAttribute(semantic).getArray()).equals(bytes(kept.getArray()))) differences++;
      if (!kept && !semantic.startsWith("TEXCOORD_")) differences++;
    }
    for (const semantic of q.listSemantics()) if (!p.getAttribute(semantic)) differences++;
    if (!bytes(p.getIndices().getArray()).equals(bytes(q.getIndices().getArray()))) differences++;
    if (materialSig(p.getMaterial()) !== materialSig(q.getMaterial())) differences++;
    if (p.getMode() !== q.getMode()) differences++;
  });
  const names = (d, list) => JSON.stringify(d.getRoot()[list]().map((x) => x.getName()));
  for (const list of ["listMaterials", "listNodes", "listMeshes", "listSkins"]) if (names(orig, list) !== names(out, list)) differences++;
  const images = (d) => JSON.stringify(d.getRoot().listTextures().map((t) => sha(t.getImage())).sort());
  if (images(orig) !== images(out)) differences++;
  return { primitives: a.length, differences };
};

const output = await io.writeBinary(doc);
const check = compare(before, await io.readBinary(output));
if (check.differences) throw new Error(`원본과 다른 곳 ${check.differences}개 — 쓰지 않는다`);
// 같은 입력에서 같은 결과여야 한다(DEC-058) — 라이브러리·코드가 바뀌어 결과가 달라지면 쓰지 않고 멈춘다
const EXPECTED = { removedAttributes: 3935, primitives: 412, bytes: 44211620, sha256: "6e00b8603a84e95fac76c1c00f58157fdd21f0044b35f007aea0aecb53499345" };
const got = { removedAttributes: removed, primitives: check.primitives, bytes: output.length, sha256: sha(output) };
if (JSON.stringify(got) !== JSON.stringify(EXPECTED)) throw new Error(`기록된 배포본과 다르다 — 쓰지 않는다: ${JSON.stringify(got)}`);
writeFileSync(dst, output);
console.log(JSON.stringify({ ...got, source: SOURCE }));
