-- 카드 임베딩 (Supabase / Postgres + pgvector). DEC-039 — 검색은 API 서버 메모리에서 하고, 벡터는 여기 보관한다.
-- 적용: uv run --env-file .env python -m server.rag.embeddings schema   (scripts/defect_precedent/schema.sql을 먼저 적용)
-- 여러 번 실행해도 된다 (create ... if not exists). 벡터는 build 단위로 보관하고 지우거나 덮어쓰지 않는다 (DEC-034와 같은 규칙).

create extension if not exists vector;

-- (build, 모델) 1개 = 1줄. 어떤 카드 글·어떤 판본의 모델로 만든 벡터인지 남긴다 — 서버가 시작할 때 대조한다
create table if not exists embedding_sets (
    build_id          text not null references data_builds (build_id),
    model             text not null,            -- BAAI/bge-small-en-v1.5
    fastembed_version text not null,            -- 0.9.0 (보고서 수치를 잰 판본)
    texts_sha256      text not null,            -- 임베딩한 카드 글(결함·결과·시정을 이은 것)을 줄바꿈으로 이은 문자열의 sha256
    model_fingerprint text not null,            -- 카드 16장 재임베딩 값의 지문 (retrieval_compare.embed_cards와 같은 방식, 기록용)
    rows              integer not null,
    loaded_at         timestamptz not null default now(),
    primary key (build_id, model)
);

-- 카드 1장 = 1줄. 같은 build의 recalls 줄에만 붙는다
create table if not exists recall_embeddings (
    build_id  text not null,
    model     text not null,
    campno    text not null,
    embedding vector(384) not null,             -- 정규화 전 값 (서버가 읽은 뒤 정규화한다)
    primary key (build_id, model, campno),
    foreign key (build_id, model) references embedding_sets (build_id, model),
    foreign key (build_id, campno) references recalls (build_id, campno)
);

-- schema.sql과 같이 정책 없이 RLS를 켜서 anon·authenticated 키로는 읽지 못하게 막는다 (적재는 관리자 연결, 서버는 조회 전용 rag_reader 계정에 따로 준 조회 정책으로 읽는다 — server/README.md, DEC-042 ⑤)
alter table embedding_sets    enable row level security;
alter table recall_embeddings enable row level security;
