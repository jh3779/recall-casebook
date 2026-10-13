// GLB 안의 메시·재질·본 이름으로 확인한 표시 대응표를 재현한다. 렌더링은 하지 않는다.
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

globalThis.self = globalThis;
// Node에서는 텍스처 픽셀을 해독하지 않는다. 대응표에는 이미지 정보가 필요 없다.
globalThis.createImageBitmap = async () => ({ width: 1, height: 1, close() {} });
const sources = {};
for (const key of ["sonata", "sorento"]) {
  const bytes = readFileSync(new URL(`../public/models/${key}.glb`, import.meta.url));
  const asset = JSON.parse(bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString()).asset;
  const gltf = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length), "");
  const parts = {};
  gltf.scene.traverse(m => {
    if (!m.isMesh) return;
    const material = m.material.name;
    let bone = "", look = null, defect = null;
    if (m.isSkinnedMesh) {
      const indices = m.geometry.getAttribute("skinIndex"), weights = m.geometry.getAttribute("skinWeight");
      const sums = new Map();
      for (let i = 0; i < indices.count; i++) for (let j = 0; j < 4; j++) {
        const id = indices.getComponent(i, j);
        sums.set(id, (sums.get(id) ?? 0) + weights.getComponent(i, j));
      }
      bone = m.skeleton.bones[[...sums].sort((a, b) => b[1] - a[1])[0][0]].name;
    }
    if (key === "sonata") {
      if (material === "carpaint") look = "paint";
      if (material === "Tire") look = "tire";
      if (material === "Rims") look = "rim";
      // 같은 816정점·3840인덱스 유리 표면의 내외층. 불투명한 흰 수출 재질을 모두 유리로 맞춘다.
      if (material === "glass" || ["Object321603_Ktm_0", "Object321561_Nekl_0"].includes(m.name)) look = "glass";
      if (material === "redglass") look = "tailLight";
      if (material === "brakedisk") defect = "brakes";
      if (material.startsWith("int-mratb")) defect = "seat";
    } else {
      // 원본에서 빠진 색·텍스처를 파일에 명시된 재질·부품 이름에 맞춰 보완한다.
      look = "under";
      if (material.includes("PRIMARY")) look = "paint";
      else if (/glass/.test(material)) look = "glass";
      else if (material.includes("tyrewall")) look = "tire";
      else if (material === "xromat") look = "chrome";
      if (m.name.startsWith("wheel_lfchild_2021")) look = "rim";
      if (/^(taillight|brakelight|indicator_[lr]r|fara_)/.test(bone) && material.startsWith("2021")) look = "tailLight";
      if (/^(headlight|reversinglight)/.test(bone) && material.startsWith("2021")) look = "light";
      if (bone.startsWith("steeringwheel")) defect = "steering";
      if (bone.startsWith("suspension")) defect = "suspension";
      if (bone.startsWith("seats")) defect = "seat";
      if (bone === "boot_080") defect = "tailgate";
      if (m.name === "Object_142" && bone === "motor_010") defect = "engine";
    }
    parts[m.name] = { title: [bone, material].filter(Boolean).join(" / "), defect, look };
  });
  writeFileSync(new URL(`../public/data/${key}_parts.json`, import.meta.url), JSON.stringify(parts, null, 2) + "\n");
  sources[key] = { bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex"), ...asset.extras };
  console.log(`${key}: ${Object.keys(parts).length} meshes`);
}
writeFileSync(new URL("../public/data/vehicle-sources.json", import.meta.url), JSON.stringify(sources, null, 2) + "\n");
