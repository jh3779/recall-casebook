"""scripts/sales_support_poc.py 테스트 — 청킹·FAQ 추출·RRF·지표. 모델·네트워크 호출 없음."""

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
