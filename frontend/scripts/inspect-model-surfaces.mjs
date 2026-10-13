// Node 24, frontend/에서: node scripts/inspect-model-surfaces.mjs
// 원본 GLB는 쓰지 않고 런타임과 같은 정리를 메모리에서 검증한다.
import { readFileSync } from "node:fs";
import { Box3 } from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { refineGeometry } from "../src/showroom/geometry.ts";

for (const model of ["silverado", "ram"]) {
  const bytes = readFileSync(`public/models/${model}.glb`);
  const parts = JSON.parse(readFileSync(`public/data/${model}_parts.json`, "utf8"));
  const { scene } = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), "");
  scene.updateMatrixWorld(true);
  const bounds = new Box3().setFromObject(scene);
  const report = { model, meshes: 0, trianglesBefore: 0, trianglesAfter: 0, verticesBefore: 0, verticesAfter: 0, invalidNormals: 0, movedVertices: 0 };
  const surfaces = new Map();
  scene.traverse((mesh) => {
    if (!mesh.isMesh) return;
    const name = /^p\d+/.test(mesh.name) ? mesh.name : mesh.parent?.name;
    const part = parts[name] ?? {};
    const group = `${part.defect ?? "body"}:${part.look ?? "body"}:${mesh.matrixWorld.elements.join(",")}`;
    if (!surfaces.has(group)) surfaces.set(group, new Set());
    const original = mesh.geometry;
    const result = refineGeometry(original, surfaces.get(group));
    report.meshes++;
    report.trianglesBefore += original.index.count / 3;
    report.trianglesAfter += result.index.count / 3;
    report.verticesBefore += original.attributes.position.count;
    report.verticesAfter += result.attributes.position.count;
    const positions = (attr) => Array.from({ length: attr.count }, (_, i) => `${attr.getX(i)},${attr.getY(i)},${attr.getZ(i)}`);
    const sourcePositions = new Set(positions(original.attributes.position));
    report.movedVertices += positions(result.attributes.position).filter((p) => !sourcePositions.has(p)).length;
    if (result.index.count) {
      const n = result.attributes.normal;
      for (let i = 0; i < n.count; i++) {
        const length = Math.hypot(n.getX(i), n.getY(i), n.getZ(i));
        if (!Number.isFinite(length) || Math.abs(length - 1) > .01) report.invalidNormals++;
      }
    }
    mesh.geometry = result;
  });
  const boundsUnchanged = bounds.equals(new Box3().setFromObject(scene));
  console.log(JSON.stringify({ ...report, boundsUnchanged }));
  if (report.invalidNormals || report.movedVertices || !boundsUnchanged) process.exitCode = 1;
}
