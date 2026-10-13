"""보관된 NHTSA flat·카드에서 현대·기아 쇼룸의 차종/연식 범위를 재현한다.

실행: uv run python -m scripts.build_showroom_demo
검색 색인·평가셋은 수정하지 않는다.
"""

import hashlib
import json
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


def main() -> None:
    raw = ROOT / "data/raw/nhtsa/FLAT_RCL_POST_2010.zip"
    card_file = ROOT / "data/processed/defect/recalls.jsonl"
    rows = read_flat(raw, RCL_COLS)
    cards = {c["campno"]: c for c in map(json.loads, card_file.read_text().splitlines())}
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
    target = ROOT / "frontend/public/data"
    (target / "hyundai-kia-recalls.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
    (target / "hyundai-kia-manifest.json").write_text(
        json.dumps(
            {
                "snapshot_date": "2026-10-06",
                "flat_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                "cards_sha256": hashlib.sha256(card_file.read_bytes()).hexdigest(),
                "scopes": evidence,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(" · ".join(f"{k} {len(v)}건" for k, v in output.items()))


if __name__ == "__main__":
    main()
