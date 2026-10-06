"""scripts/sales_support_poc.py 테스트 — 청킹·FAQ 추출·RRF·지표. 모델·네트워크 호출 없음."""

import json

import pytest

from scripts import sales_support_poc as poc

DOC = """---
title: 예시
---

소개 문단 {{< member-by-name "Kim" >}}

## 주문 처리

{{% alert title="주의" %}}
알림 안의 글
{{% /alert %}}

### 견적

```
# 코드 안 샵은 헤딩이 아니다
```

## FAQ

1. **Will I still get emails?**

   - Yes.

### Where do I look?

Here.
"""


def test_preprocess_removes_frontmatter_and_shortcodes():
    out = poc.preprocess(DOC)
    assert "title:" not in out
    assert "Kim" in out and "member-by-name" not in out
    assert "{{%" not in out and "알림 안의 글" in out


def test_chunks_follow_heading_path_and_ignore_code_hash():
    chunks = poc.chunk_file("a/b.md", DOC)
    paths = [c.heading_path for c in chunks]
    assert paths[0] == ""  # 첫 헤딩 앞 소개 문단
    assert "주문 처리>견적" in paths
    assert not any("코드 안 샵" in p for p in paths)
    assert all(c.commit_sha == poc.COMMIT_SHA for c in chunks)
    assert [c.chunk_id for c in chunks] == list(range(len(chunks)))


def test_long_section_splits_on_paragraphs_with_same_heading():
    body = "\n\n".join(["x" * 900] * 5)
    chunks = poc.chunk_file("a.md", f"## 긴 섹션\n\n{body}\n")
    assert len(chunks) > 1
    assert {c.heading_path for c in chunks} == {"긴 섹션"}
    assert all(len(c.chunk_text) <= poc.MAX_CHUNK_CHARS for c in chunks)


def test_chunk_hash_ignores_whitespace_differences():
    a = poc.chunk_file("a.md", "## H\n\nfoo   bar\n")[0]
    b = poc.chunk_file("a.md", "## H\n\nfoo bar\n")[0]
    assert a.chunk_hash == b.chunk_hash


def test_extract_faq_finds_bold_and_heading_questions_with_gold_section():
    faq = poc.extract_faq("a/b.md", DOC)
    assert [(q.question, q.gold_section_keys) for q in faq] == [
        ("Will I still get emails?", ["a/b.md#FAQ"]),
        ("Where do I look?", ["a/b.md#FAQ>Where do I look?"]),
    ]
    assert all(q.question_id.startswith("faq-") for q in faq)


def test_extract_faq_strips_q_prefix_and_stops_at_next_section():
    raw = "## FAQ\n\nQ: **Is it free?**\n\n## 다음\n\n**Outside?**\n"
    faq = poc.extract_faq("a.md", raw)
    assert [q.question for q in faq] == ["Is it free?"]


def test_rrf_prefers_documents_ranked_well_in_both_lists():
    assert poc.rrf([[1, 2, 3], [3, 1, 2]])[0] == 1


def test_evaluate_counts_hits_by_file_and_section():
    chunks = poc.chunk_file("a.md", "## A\n\nx\n\n## B\n\ny\n") + poc.chunk_file(
        "b.md", "## A\n\nz\n"
    )
    q = poc.EvalQuestion("faq-1", "q", ["a.md#B"])
    result = poc.evaluate([[2, 1, 0]], chunks, [q])  # b.md#A, a.md#B, a.md#A 순
    assert result["file"]["Hit@1"] == 0.0 and result["file"]["Hit@3"] == 1.0
    assert result["section"]["Hit@1"] == 0.0 and result["section"]["Hit@3"] == 1.0
    assert result["section"]["MRR"] == 0.5


def test_evaluate_multiple_gold_sections_counts_recall_and_hit():
    chunks = poc.chunk_file("a.md", "## A\n\nx\n\n## B\n\ny\n") + poc.chunk_file(
        "b.md", "## A\n\nz\n"
    )
    q = poc.EvalQuestion("faq-1", "q", ["a.md#A", "b.md#A"])  # 정답이 두 섹션
    result = poc.evaluate([[2, 1, 0]], chunks, [q])  # b.md#A(정답), a.md#B, a.md#A(정답)
    sec = result["section"]
    assert sec["Hit@1"] == 1.0  # 두 정답 중 하나라도 있으면 적중
    assert sec["Recall@1"] == 0.5 and sec["Recall@3"] == 1.0  # 정답 중 찾은 비율
    assert sec["MRR"] == 1.0  # 첫 정답 순위 1


def test_build_faq_merges_gold_of_same_question_instead_of_dropping(tmp_path):
    hb = tmp_path / "hb"
    for name in ("a", "b"):
        d = hb / "sales"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text("## FAQ\n\n1. **How do I get access?**\n", encoding="utf-8")
    faq = poc.build_faq(hb)
    assert len(faq) == 1
    assert faq[0].gold_section_keys == ["sales/a.md#FAQ", "sales/b.md#FAQ"]


def _fake_handbook(tmp_path):
    hb = tmp_path / "hb"
    files = {
        "customer-experience/customer-onboarding/index.md": "## FAQ\n\n**Is this for customers?**\n",
        "customer-experience/playbooks/a.md": "## 절차\n\n내용\n",
        "sales/b.md": "## 절차\n\n내용\n",
    }
    for rel, text in files.items():
        f = hb / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return hb


def test_customer_onboarding_folder_is_excluded_from_files_chunks_and_faq(tmp_path):
    hb = _fake_handbook(tmp_path)
    rels = [f.relative_to(hb).as_posix() for f in poc.list_files(hb)]
    assert "customer-experience/customer-onboarding/index.md" not in rels
    assert "customer-experience/playbooks/a.md" in rels
    assert not any("customer-onboarding" in c.source_path for c in poc.build_chunks(hb))
    assert poc.build_faq(hb) == []


def _meta_for(chunks, shape):
    return poc.build_meta(chunks, shape, fastembed_version="9.9.9")


def test_check_index_passes_when_everything_matches():
    chunks = poc.chunk_file("a.md", "## A\n\nx\n")
    meta = _meta_for(chunks, (len(chunks), 384))
    assert poc.check_index(meta, chunks, chunks, (len(chunks), 384), "9.9.9") == []


def test_check_index_reports_model_version_chunking_and_data_changes():
    chunks = poc.chunk_file("a.md", "## A\n\nx\n")
    meta = _meta_for(chunks, (len(chunks), 384))
    meta["embedding_model"] = "other/model"
    meta["data_commit_sha"] = "0" * 40
    meta["chunking"] = {"max_chunk_chars": 1}
    problems = poc.check_index(meta, chunks, chunks, (len(chunks), 384), "1.0.0")
    joined = " ".join(problems)
    for word in ("embedding_model", "data_commit_sha", "chunking", "fastembed"):
        assert word in joined


def test_check_index_reports_changed_chunks_and_vector_shape():
    old = poc.chunk_file("a.md", "## A\n\nx\n")
    new = poc.chunk_file("a.md", "## A\n\ny\n")  # 본문이 바뀜 → 청크 목록 해시가 달라짐
    meta = _meta_for(old, (1, 384))
    problems = poc.check_index(meta, new, old, (2, 384), "9.9.9")
    joined = " ".join(problems)
    assert "chunks_digest" in joined and "vectors" in joined


FM_DOC = "---\ntitle: \"Quote Approvals\"\ndescription: 'How quotes get approved'\n---\n\n## Steps\n\nDo it.\n"


def test_frontmatter_title_and_description_are_kept_as_chunk_metadata():
    meta = poc.parse_frontmatter(FM_DOC)
    assert meta == {"title": "Quote Approvals", "description": "How quotes get approved"}
    chunk = poc.chunk_file("sales/a.md", FM_DOC)[0]
    assert (chunk.doc_title, chunk.doc_description) == (
        "Quote Approvals",
        "How quotes get approved",
    )
    assert "title:" not in chunk.chunk_text  # 본문에는 넣지 않는다(메타데이터로만 보존)


def test_frontmatter_missing_or_block_values_become_empty():
    assert poc.parse_frontmatter("## no frontmatter\n") == {"title": "", "description": ""}
    folded = "---\ntitle: T\ndescription: >\n  long text\n---\nbody\n"
    assert poc.parse_frontmatter(folded) == {"title": "T", "description": ""}


def test_chunks_digest_detects_title_or_description_changes():
    a = poc.chunk_file("sales/a.md", FM_DOC)
    b = poc.chunk_file("sales/a.md", FM_DOC.replace("Quote Approvals", "Quote Approval Steps"))
    c = poc.chunk_file("sales/a.md", FM_DOC.replace("How quotes get approved", "Other"))
    assert poc.chunks_digest(a) != poc.chunks_digest(b)
    assert poc.chunks_digest(a) != poc.chunks_digest(c)


def _write_questions(tmp_path, rows):
    path = tmp_path / "q.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def test_load_questions_reads_common_format_for_all_question_types(tmp_path):
    rows = [
        {
            "question_id": "syn-1",
            "question": "q1",
            "question_type": "synthetic",
            "gold_section_keys": ["a.md#A", "b.md#B"],
        },
        {
            "question_id": "real-1",
            "question": "q2",
            "question_type": "real",
            "gold_section_keys": ["a.md#A"],
        },
    ]
    qs = poc.load_questions(_write_questions(tmp_path, rows))
    assert [(q.question_id, q.question_type, q.gold_section_keys) for q in qs] == [
        ("syn-1", "synthetic", ["a.md#A", "b.md#B"]),
        ("real-1", "real", ["a.md#A"]),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {
            "question_id": "x",
            "question": "q",
            "question_type": "made-up",
            "gold_section_keys": ["a#b"],
        },
        {"question_id": "x", "question": "q", "question_type": "real", "gold_section_keys": []},
        {"question_id": "", "question": "q", "question_type": "real", "gold_section_keys": ["a#b"]},
    ],
)
def test_load_questions_rejects_bad_rows(tmp_path, bad):
    with pytest.raises(ValueError):
        poc.load_questions(_write_questions(tmp_path, [bad]))


def test_load_questions_rejects_duplicate_ids(tmp_path):
    row = {
        "question_id": "x",
        "question": "q",
        "question_type": "real",
        "gold_section_keys": ["a#b"],
    }
    with pytest.raises(ValueError, match="중복"):
        poc.load_questions(_write_questions(tmp_path, [row, row]))


def test_question_set_digest_ignores_order_and_changes_with_content():
    a = poc.EvalQuestion("1", "q1", ["x#a"])
    b = poc.EvalQuestion("2", "q2", ["y#b", "z#c"])
    assert poc.question_set_digest([a, b]) == poc.question_set_digest([b, a])
    changed = poc.EvalQuestion("2", "q2", ["y#b"])
    assert poc.question_set_digest([a, b]) != poc.question_set_digest([a, changed])
    renamed = poc.EvalQuestion("2", "q2 changed", ["y#b", "z#c"])
    assert poc.question_set_digest([a, b]) != poc.question_set_digest([a, renamed])


def test_eval_report_records_question_set_and_retrieval_settings():
    qs = [poc.EvalQuestion("1", "q1", ["x#a"]), poc.EvalQuestion("2", "q2", ["y#b"], "synthetic")]
    report = poc.build_report(qs, n_chunks=10, results={})
    assert report["question_set"]["n"] == 2
    assert report["question_set"]["types"] == {"doc_derived": 1, "synthetic": 1}
    assert report["question_set"]["digest"] == poc.question_set_digest(qs)
    settings = report["retrieval_settings"]
    for key in ("top_k", "candidates", "rrf_k", "rank_bm25_version", "fastembed_version"):
        assert key in settings


def test_compare_refuses_results_from_different_question_sets():
    a = {"question_set": {"digest": "aaa"}, "results": {}}
    b = {"question_set": {"digest": "bbb"}, "results": {}}
    with pytest.raises(ValueError, match="질문 세트"):
        poc.compare_reports(a, b)


def test_compare_reports_marks_differences_at_or_above_threshold():
    mk = lambda v: {  # noqa: E731
        "question_set": {"digest": "same"},
        "results": {"BM25": {"section": {"Hit@1": v, "MRR": 0.5}}},
    }
    rows = poc.compare_reports(mk(0.50), mk(0.55))
    by_metric = {(r["config"], r["unit"], r["metric"]): r for r in rows}
    hit = by_metric[("BM25", "section", "Hit@1")]
    assert hit["diff"] == pytest.approx(0.05) and hit["different"] is True
    assert by_metric[("BM25", "section", "MRR")]["different"] is False


# ---- 임시 chunk_key (팀 합의 전 제안 A: 네 값을 구분 문자로 이어 해시) ----


def test_chunk_key_recipe_matches_the_documented_formula():
    import hashlib

    parts = ["sales/a.md", "0ab0299ce073b847558867ae5abbc42c570bc8d5", "A>B", "abc123"]
    expected = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    assert poc.make_chunk_key(*parts) == expected
    assert len(poc.make_chunk_key(*parts)) == poc.CHUNK_KEY_LEN == 32


def test_each_chunk_has_doc_id_chunk_key_and_domains():
    chunks = poc.chunk_file("sales/a.md", "## A\n\nx\n\n## B\n\ny\n")
    assert all(c.chunk_key and c.doc_id and c.domains == [poc.DOMAIN] for c in chunks)
    assert len({c.chunk_key for c in chunks}) == len(chunks)
    assert len({c.doc_id for c in chunks}) == 1  # 같은 문서는 같은 doc_id
    other = poc.chunk_file("sales/b.md", "## A\n\nx\n")
    assert other[0].doc_id != chunks[0].doc_id and other[0].chunk_key != chunks[0].chunk_key


def test_chunk_key_changes_when_any_of_the_four_fields_changes():
    base = ("p.md", "sha", "H", "h1")
    keys = {poc.make_chunk_key(*base)}
    for i, other in enumerate(("q.md", "sha2", "H2", "h2")):
        changed = list(base)
        changed[i] = other
        keys.add(poc.make_chunk_key(*changed))
    assert len(keys) == 5


def test_duplicate_chunk_keys_are_rejected():
    chunk = poc.chunk_file("sales/a.md", "## A\n\nx\n")[0]
    with pytest.raises(ValueError, match="chunk_key 중복"):
        poc.assert_unique_keys([chunk, chunk])


def test_vectors_are_aligned_by_chunk_key_even_if_chunk_order_changes():
    import numpy as np

    chunks = poc.chunk_file("sales/a.md", "## A\n\nx\n\n## B\n\ny\n\n## C\n\nz\n")
    keys = [c.chunk_key for c in chunks]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])  # 청크 순서(A, B, C)대로 만든 벡터
    shuffled = [chunks[2], chunks[0], chunks[1]]  # 청크 파일 순서가 바뀐 경우
    aligned = poc.align_vectors(shuffled, keys, vectors)
    assert aligned.tolist() == [[1.0, 1.0], [1.0, 0.0], [0.0, 1.0]]


def test_align_vectors_reports_missing_keys():
    import numpy as np

    chunks = poc.chunk_file("sales/a.md", "## A\n\nx\n")
    with pytest.raises(ValueError, match="벡터가 없는 청크"):
        poc.align_vectors(chunks, ["other-key"], np.zeros((1, 2)))


def test_load_checked_index_exits_with_a_clear_message_when_index_files_are_missing(tmp_path):
    (tmp_path / "index_meta.json").write_text("{}", encoding="utf-8")
    (tmp_path / "chunks.jsonl").write_text("", encoding="utf-8")  # 임베딩 파일만 없는 상태
    with pytest.raises(SystemExit) as e:
        poc.load_checked_index(tmp_path, tmp_path)
    assert "색인 파일" in str(e.value) and "embeddings.npz" in str(e.value)


def test_chunk_key_fixed_literal_test_vector():
    # 계산식(UTF-8, 구분 문자 U+001F, sha256, 앞 32자)이 바뀌면 이 고정값이 달라져 실패한다
    key = poc.make_chunk_key(
        "sales/a.md", "0ab0299ce073b847558867ae5abbc42c570bc8d5", "A>B", "abc123"
    )
    assert key == "5203c258dd38e5392a58755a62840ae0"


# ---- PR #20 1차 리뷰: 데이터 지문·비교 조건 검사·입력 검증 ----


def test_data_fingerprint_changes_when_any_indexed_file_changes(tmp_path):
    hb = tmp_path / "hb"
    (hb / "sales").mkdir(parents=True)
    (hb / "sales" / "a.md").write_text("## A\n\nx\n", encoding="utf-8")
    (hb / "support").mkdir()
    (hb / "support" / "b.md").write_text("## B\n\ny\n", encoding="utf-8")
    before = poc.data_fingerprint(hb)
    assert before == poc.data_fingerprint(hb)  # 같은 파일이면 같다
    (hb / "support" / "b.md").write_text("## B\n\ny changed\n", encoding="utf-8")
    assert poc.data_fingerprint(hb) != before
    (hb / "support" / "b.md").write_text("## B\n\ny\n", encoding="utf-8")
    (hb / "sales" / "new.md").write_text("## N\n\nz\n", encoding="utf-8")  # 파일이 늘어도 달라진다
    assert poc.data_fingerprint(hb) != before


def test_data_status_marks_data_that_differs_from_the_pinned_snapshot():
    assert poc.data_status(poc.SNAPSHOT_FINGERPRINT) == "matches_pinned_snapshot"
    assert poc.data_status("0" * 64) == "differs_from_pinned_snapshot"


def test_check_index_reports_a_changed_data_fingerprint():
    chunks = poc.chunk_file("a.md", "## A\n\nx\n")
    meta = poc.build_meta(chunks, (1, 384), fastembed_version="9.9.9", data_fingerprint="aaa")
    assert poc.check_index(meta, chunks, chunks, (1, 384), "9.9.9", data_fingerprint="aaa") == []
    problems = poc.check_index(meta, chunks, chunks, (1, 384), "9.9.9", data_fingerprint="bbb")
    assert any("data_fingerprint" in p for p in problems)


def _report(**over):
    base = {
        "question_set": {"digest": "same"},
        "index_meta": {
            "data_commit_sha": "sha",
            "data_fingerprint": "fp",
            "chunks_digest": "cd",
            "chunking": {"max_chunk_chars": 2000},
            "excluded_dirs": ["x"],
            "embedding_model": "m1",
        },
        "retrieval_settings": {"top_k": [1], "candidates": 100, "rrf_k": 60, "tokenizer": "t"},
        "results": {"BM25": {"section": {"Hit@1": 0.5}}},
    }
    for key, value in over.items():
        if key in base["index_meta"]:
            base["index_meta"][key] = value
        else:
            base[key] = value
    return base


def test_compare_refuses_runs_with_different_data_or_chunking_conditions():
    for key, value in (
        ("data_fingerprint", "other"),
        ("chunks_digest", "other"),
        ("chunking", {"max_chunk_chars": 500}),
        ("excluded_dirs", []),
    ):
        with pytest.raises(ValueError, match=key):
            poc.compare_reports(_report(), _report(**{key: value}))


def test_compare_allows_only_explicitly_permitted_differences():
    other_model = _report(embedding_model="m2")
    with pytest.raises(ValueError, match="embedding_model"):
        poc.compare_reports(_report(), other_model)
    rows = poc.compare_reports(_report(), other_model, allow=("embedding_model",))
    assert rows and rows[0]["config"] == "BM25"
    settings = _report(
        retrieval_settings={"top_k": [1], "candidates": 50, "rrf_k": 60, "tokenizer": "t"}
    )
    with pytest.raises(ValueError, match="retrieval_settings"):
        poc.compare_reports(_report(), settings)
    assert poc.compare_reports(_report(), settings, allow=("retrieval_settings",))


def test_load_questions_rejects_an_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="비어"):
        poc.load_questions(path)
