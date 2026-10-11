"""scripts/defect_precedent/parts_boost.py(기각한 v3 실험)의 규칙 테스트 — 보고서 3-3절 수치를 낸 규칙이 바뀌지 않게 고정한다."""

from scripts.defect_precedent.parts_boost import matched_categories, norm, phrases


def test_phrases_split_category_names_and_drop_generic_words():
    assert phrases("SERVICE BRAKES, HYDRAULIC") == [["brake"], ["hydraulic"]]
    assert phrases("LATCHES/LOCKS/LINKAGES") == [["latch"], ["lock"], ["linkage"]]
    assert phrases("ENGINE AND ENGINE COOLING") == [["engine"], ["engine", "cooling"]]
    assert phrases("EQUIPMENT") == [] and phrases("UNKNOWN OR OTHER") == []


def test_norm_strips_plural_endings():
    assert [norm(w) for w in ("brakes", "latches", "bus", "airbags")] == [
        "brake",
        "latch",
        "bus",
        "airbag",
    ]


def test_category_matches_all_phrase_words_or_joined_form():
    cats = {c: phrases(c) for c in ("AIR BAGS", "SEAT BELTS", "SEATS", "POWER TRAIN", "STEERING")}
    assert matched_categories("Driver airbag inflator ruptured", cats) == {"AIR BAGS"}
    assert matched_categories("seat belt buckle released", cats) == {"SEAT BELTS", "SEATS"}
    assert matched_categories("loss of power steering", cats) == {
        "STEERING"
    }  # power 하나로는 POWER TRAIN이 아니다
