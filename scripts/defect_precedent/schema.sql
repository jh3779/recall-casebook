-- 결함 선례 데이터 테이블 (Supabase / Postgres). DEC-034.
-- 적용: uv run --env-file .env python -m scripts.defect_precedent.load_db schema
-- 여러 번 실행해도 된다 (create ... if not exists). 칸을 바꿀 때는 새 migration을 만든다 — 이 파일의 기존 칸을 고치지 않는다.
--
-- 날짜 칸은 date 타입이다. 원본은 YYYYMMDD 문자열이고, 적재 스크립트가 엄격하게 읽어 형식이 틀리면 중단한다 (추측해 고치지 않는다).
-- 벡터 칸(recall_embeddings)은 임베딩 모델이 정해진 뒤 만든다. 지금은 만들지 않는다.

-- 어떤 원본에서 만든 데이터인가 — 답변 → 근거 → 데이터 버전 추적용 (AGENTS.md 2절 4항)
create table if not exists data_builds (
    snapshot_date       date primary key,
    raw_manifest_sha256 text not null,
    recalls_sha256      text not null,
    eval_sha256         text not null,
    loaded_at           timestamptz not null default now()
);

-- 리콜 카드 1건 = 1줄 (recalls.jsonl)
create table if not exists recalls (
    campno        text primary key,                                   -- 24V412000 (9자리, 원본 그대로)
    campaign6     text generated always as (left(campno, 6)) stored,  -- 24V412 — causes.campaign과 잇는 칸. DB가 계산한다
    maker         text not null,
    raw_maker     text not null,
    components    text[] not null default '{}',
    defect        text not null,
    consequence   text not null,
    remedy        text not null,
    received_date date not null,
    recall_type   text not null,
    influenced_by text not null,
    dup_group     text not null,
    snapshot_date date not null references data_builds (snapshot_date)
);
create index if not exists recalls_campaign6_idx on recalls (campaign6);
create index if not exists recalls_received_date_idx on recalls (received_date);
create index if not exists recalls_dup_group_idx on recalls (dup_group);

-- 시험 질문 1개 = 1줄 (eval.jsonl). 정답 리콜은 recalls.campno 목록 (배열이라 외래 키는 못 건다 — 적재 스크립트가 대조한다)
create table if not exists eval_questions (
    action_no    text primary key,
    question     text not null,
    open_date    date not null,
    gold_campnos text[] not null,
    sets         text[] not null            -- all · since2010 · rclrpt_range
);

-- 원본 보고서(Part 573) 1건 = 1줄 (causes.jsonl). 지금은 표본 300건
create table if not exists causes (
    campaign           text primary key,    -- 24V412 (6자리). recalls.campaign6과 잇는다 — 한 캠페인이 recalls 여러 건에 붙을 수 있다
    versions           integer not null,
    source_file        text not null,
    submission_date    date,                -- 날짜를 모르는 판본은 비워 둔다 (resolution = unresolved)
    cause_text         text,
    cause_status       text not null check (cause_status in ('filled', 'empty', 'no_field')),
    supplier_names     text[] not null default '{}',
    supplier_countries text[] not null default '{}',
    new_form           boolean not null,
    pdfs               jsonb not null default '{}',   -- 판본 주소 → sha256
    resolution         text not null check (resolution in ('auto', 'manual', 'unresolved')),
    unresolved_reasons text[] not null default '{}'
);
create index if not exists causes_submission_date_idx on causes (submission_date);

-- Supabase는 public 테이블을 REST API로 열어 준다. 정책 없이 RLS를 켜서 anon·authenticated 키로는 아무것도 못 읽게 막는다.
-- 서버·스크립트는 postgres 계정으로 접속하므로 영향이 없다 (RLS를 우회한다).
alter table data_builds    enable row level security;
alter table recalls        enable row level security;
alter table eval_questions enable row level security;
alter table causes         enable row level security;
