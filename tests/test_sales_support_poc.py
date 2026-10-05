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
