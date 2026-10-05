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
    assert [(q.question, q.heading_path) for q in faq] == [
        ("Will I still get emails?", "FAQ"),
        ("Where do I look?", "FAQ>Where do I look?"),
    ]


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
    faq = [poc.FaqQuestion("q", "a.md", "B")]
    result = poc.evaluate([[2, 1, 0]], chunks, faq)  # b.md#A, a.md#B, a.md#A 순
    assert result["file"]["Hit@1"] == 0.0 and result["file"]["Hit@3"] == 1.0
    assert result["section"]["Hit@1"] == 0.0 and result["section"]["Hit@3"] == 1.0
    assert result["section"]["MRR"] == 0.5
