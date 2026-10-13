// artifact의 .gltf.json(버퍼를 base64 data URI로 품은 glTF)을 .glb로 묶는다. 내용은 그대로이고 포장만 바뀐다.
// artifact app.js의 jsonToGlb와 같은 방식. frontend/README.md "3D 모델 파일" 참고.
// usage: node scripts/gltf-json-to-glb.mjs <in.gltf.json> <out.glb>
import { readFileSync, writeFileSync } from "node:fs";

const [src, dst] = process.argv.slice(2);
const json = JSON.parse(readFileSync(src, "utf8"));
if (json.buffers.length !== 1) throw new Error(`buffers ${json.buffers.length}개 — 1개만 처리`);
const uri = json.buffers[0].uri;
const bin = Buffer.from(uri.slice(uri.indexOf(",") + 1), "base64");
if (bin.length !== json.buffers[0].byteLength) throw new Error("byteLength 불일치");
delete json.buffers[0].uri;

const head = Buffer.from(JSON.stringify(json), "utf8");
const jpad = (4 - (head.length % 4)) % 4;
const bpad = (4 - (bin.length % 4)) % 4;
const total = 12 + 8 + head.length + jpad + 8 + bin.length + bpad;
const out = Buffer.alloc(total);
out.writeUInt32LE(0x46546c67, 0); out.writeUInt32LE(2, 4); out.writeUInt32LE(total, 8);
out.writeUInt32LE(head.length + jpad, 12); out.writeUInt32LE(0x4e4f534a, 16);
head.copy(out, 20); out.fill(0x20, 20 + head.length, 20 + head.length + jpad);
const b = 20 + head.length + jpad;
out.writeUInt32LE(bin.length + bpad, b); out.writeUInt32LE(0x004e4942, b + 4);
bin.copy(out, b + 8);
writeFileSync(dst, out);
console.log(`${dst}: ${total} bytes (json ${head.length}, bin ${bin.length})`);
