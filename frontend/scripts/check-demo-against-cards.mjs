import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

if (!process.argv[2]) {
  console.error("사용법: node scripts/check-demo-against-cards.mjs <recalls.jsonl 경로> [데모 JSON 경로]");
  process.exit(1);
}
const demo = JSON.parse(readFileSync(process.argv[3] ?? fileURLToPath(new URL("../public/data/hyundai-kia-recalls.json", import.meta.url)), "utf8"));
const cards = new Map(readFileSync(process.argv[2], "utf8").trim().split("\n").map((line) => {
  const card = JSON.parse(line);
  return [card.campno, card];
}));
const differences = [];
let matched = 0;
const recalls = Object.values(demo).flat();
for (const recall of recalls) {
  const card = cards.get(recall.campno);
  if (!card) {
    differences.push(`${recall.campno}: 카드 없음`);
    continue;
  }
  const fields = ["defect", "consequence", "remedy", "maker"].filter((field) =>
    !Buffer.from(recall[field]).equals(Buffer.from(card[field === "maker" ? "raw_maker" : field])),
  );
  if (fields.length) differences.push(`${recall.campno}: ${fields.join(", ")}`);
  else matched++;
}
console.log(`총 ${recalls.length}건 · 일치 ${matched}건`);
differences.forEach((message) => console.error(message));
process.exitCode = differences.length ? 1 : 0;
