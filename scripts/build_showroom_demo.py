"""보관된 NHTSA flat·카드에서 현대·기아 쇼룸의 차종/연식 범위를 재현한다.

실행: uv run python -m scripts.build_showroom_demo           # 다시 만들어 씀
      uv run python -m scripts.build_showroom_demo --check   # 다시 만들어 커밋된 파일과 바이트 대조
입력 판본은 `data/processed/defect/build.json`으로 확인한다 — 원본 manifest·flat ZIP·카드 파일의
sha256 사슬이 하나라도 다르면 만들지 않는다(서비스 원칙 4). 스냅샷 날짜도 build.json에서 읽는다.
검색 색인·평가셋은 수정하지 않는다.
"""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from scripts.defect_precedent.nhtsa import RCL_COLS, read_flat

ROOT = Path(__file__).resolve().parents[1]
SCOPES = {
    "sonata": ("HYUNDAI", "SONATA", 2011, 2014),
    "sorento": ("KIA", "SORENTO", 2021, 2023),
}


def categories(components: list[str]) -> list[str]:
    out = set()
    for component in components:
        if component.startswith("SERVICE BRAKES") or component.startswith("PARKING BRAKE"):
            out.add("brakes")
        elif component.startswith("ELECTRICAL SYSTEM"):
            out.add("electrical")
        elif component.startswith("ENGINE"):
            out.add("engine")
        elif component.startswith("FUEL SYSTEM"):
            out.add("fuel")
        elif component.startswith("POWER TRAIN:AUTOMATIC TRANSMISSION"):
            out.add("transmission")
        elif component.startswith("STEERING"):
            out.add("steering")
        elif component.startswith("SUSPENSION"):
            out.add("suspension")
        elif component.startswith("AIR BAGS"):
            out.add("airbag")
        elif component.startswith(("SEATS", "SEAT BELTS")):
            out.add("seat")
        elif component.startswith("EXTERIOR LIGHTING:BRAKE LIGHTS:SWITCH"):
            out.add("lighting")
        elif component.startswith("LATCHES/LOCKS/LINKAGES:DOORS"):
            out.add("latches")
        else:
            out.add("other")
    return sorted(out or {"other"})


FLAT = "FLAT_RCL_POST_2010.zip"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_inputs(raw_dir: Path, card_file: Path, build_file: Path) -> dict:
    """build.json이 가리키는 판본과 실제 입력 파일이 같은지 확인하고 판본 정보를 돌려준다."""
    build = json.loads(build_file.read_text())
    manifest_file = raw_dir / "manifest.json"
    checks = [
        ("원본 manifest", sha256(manifest_file), build["raw_manifest_sha256"]),
        ("카드 파일", sha256(card_file), build["recalls_sha256"]),
    ]
    flat_sha = sha256(raw_dir / FLAT)
    checks.append(
        ("flat ZIP", flat_sha, json.loads(manifest_file.read_text())["files"][FLAT]["sha256"])
    )
    for name, actual, expected in checks:
        if actual != expected:
            raise SystemExit(f"{name} sha256이 build.json 판본과 다르다: {actual} != {expected}")
    return {
        "snapshot_date": build["snapshot_date"],
        "raw_manifest_sha256": build["raw_manifest_sha256"],
        "flat_sha256": flat_sha,
        "cards_sha256": build["recalls_sha256"],
    }


def dumps(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def build(raw_dir: Path, card_file: Path, build_file: Path) -> dict[str, bytes]:
    version = verify_inputs(raw_dir, card_file, build_file)
    rows = read_flat(raw_dir / FLAT, RCL_COLS)
    cards = {
        c["campno"]: c for c in map(json.loads, card_file.read_text().rstrip("\n").split("\n"))
    }
    output, evidence = {}, {}
    for key, (make, model, first, last) in SCOPES.items():
        groups = defaultdict(list)
        for row in rows:
            if (
                row["MAKETXT"] == make
                and row["MODELTXT"] == model
                and first <= int(row["YEARTXT"] or 0) <= last
                and row["RCLTYPECD"] == "V"
            ):
                groups[row["CAMPNO"]].append(row)
        result = []
        for campno, matching in groups.items():
            card = cards[campno]
            components = sorted({r["COMPNAME"] for r in matching})
            populations = {int(r["POTAFF"] or 0) for r in matching}
            if len(populations) != 1:
                raise ValueError(f"{campno}: 대상 대수 판본 확인 필요")
            result.append(
                {
                    "campno": campno,
                    "maker": card["raw_maker"],
                    "received": card["received_date"],
                    "potaff": populations.pop(),
                    "defect": card["defect"],
                    "consequence": card["consequence"],
                    "remedy": card["remedy"],
                    "years": sorted({int(r["YEARTXT"]) for r in matching}),
                    "components": components,
                    "categories": categories(components),
                    "mfr_part": " · ".join(
                        sorted({r["MFR_COMP_NAME"] for r in matching if r["MFR_COMP_NAME"]})
                    ),
                    "source": f"https://www.nhtsa.gov/recalls?nhtsaId={campno}",
                }
            )
        output[key] = sorted(result, key=lambda r: (r["received"], r["campno"]), reverse=True)
        evidence[key] = {
            "make": make,
            "model": model,
            "years": [first, last],
            "record_ids": {c: sorted({r["RECORD_ID"] for r in rs}) for c, rs in groups.items()},
        }
    recalls = dumps(output)
    manifest = dumps(
        {
            **version,
            "recalls_json_sha256": hashlib.sha256(recalls).hexdigest(),
            "scopes": evidence,
        }
    )
    print(" · ".join(f"{k} {len(v)}건" for k, v in output.items()))
    return {"hyundai-kia-recalls.json": recalls, "hyundai-kia-manifest.json": manifest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="쓰지 않고 커밋된 파일과 바이트 대조")
    args = parser.parse_args(argv)
    files = build(
        ROOT / "data/raw/nhtsa",
        ROOT / "data/processed/defect/recalls.jsonl",
        ROOT / "data/processed/defect/build.json",
    )
    target = ROOT / "frontend/public/data"
    if args.check:
        differ = [name for name, body in files.items() if (target / name).read_bytes() != body]
        for name in differ:
            print(f"다름: frontend/public/data/{name}", file=sys.stderr)
        print("일치" if not differ else f"{len(differ)}개 파일이 다르다")
        return 1 if differ else 0
    for name, body in files.items():
        (target / name).write_bytes(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
