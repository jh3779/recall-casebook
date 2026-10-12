-- 서빙 묶음 기록 (DEC-048 ⑤, DEC-049). 배포 서버는 Supabase Storage에서 받은 묶음의 sha256을 이 기록과 대조한다.
-- 적용: uv run --env-file .env python -m server.rag.bundle schema   (schema.sql·embeddings.sql을 먼저 적용)
-- 여러 번 실행해도 된다 (create ... if not exists). 한 번 쓴 기록은 지우거나 덮어쓰지 않는다 (DEC-034와 같은 규칙).

create table if not exists serving_bundles (
    build_id      text not null references data_builds (build_id),
    model         text not null,            -- BAAI/bge-small-en-v1.5
    bundle_sha256 text not null,            -- 묶음 파일(tar) 전체의 sha256
    storage_path  text not null,            -- Storage 버킷 안의 경로 (serving-bundles/<path>)
    format        integer not null,         -- 묶음 형식 판본 (server/rag/bundle.py FORMAT)
    created_at    timestamptz not null default now(),
    primary key (build_id, model),
    foreign key (build_id, model) references embedding_sets (build_id, model)
);

-- 다른 테이블과 같이 정책 없이 RLS를 켠다. 서버용 조회 전용 계정(rag_reader)의 조회 정책은 배포 때 만든다(server/README.md 3단계, #63)
alter table serving_bundles enable row level security;
