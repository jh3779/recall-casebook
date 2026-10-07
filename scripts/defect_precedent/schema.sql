-- 결함 선례 데이터 테이블 (Supabase / Postgres). DEC-034.
-- 적용: uv run --env-file .env python -m scripts.defect_precedent.load_db schema
-- 여러 번 실행해도 된다 (create ... if not exists). 아직 어떤 DB에도 올리기 전의 첫 버전이다 —
-- 올린 뒤에 칸을 바꿀 때는 이 파일의 기존 칸을 고치지 않고 새 migration을 만든다.
--
-- 스냅샷별로 보관한다: 데이터 줄마다 snapshot_date를 두고 (snapshot_date, 번호)를 기본키로 쓴다.
-- 새 스냅샷을 올려도 지난 스냅샷은 그대로 남고(과거 답변이 쓴 데이터를 되살릴 수 있다), 평소 조회는 *_latest 뷰로 한다.
-- 오래된 스냅샷은 load_db prune으로 데이터 줄만 지우고 data_builds 줄은 pruned_at 표시와 함께 남긴다.
--
-- 날짜 칸은 date 타입이다. 원본은 YYYYMMDD(snapshot_date는 YYYY-MM-DD) 문자열이고, 적재 스크립트가 칸마다 정해진
-- 형식만 받아 틀리면 중단한다 (추측해 고치지 않는다).
-- 벡터 칸(recall_embeddings)은 임베딩 모델이 정해진 뒤 만든다. 지금은 만들지 않는다.

-- 스냅샷(= 적재 1회) 1개 = 1줄. 어느 원본·어느 파일에서 만들었는지, 이전 스냅샷과 무엇이 달라졌는지를 남긴다
create table if not exists data_builds (
    snapshot_date        date primary key,
    raw_manifest_sha256  text not null,
    recalls_sha256       text not null,
    eval_sha256          text not null,
    causes_kind          text not null check (causes_kind in ('sample', 'full')),
    causes_file          text not null,
    causes_sha256        text not null,
    causes_rows          integer not null,
    causes_expected_rows integer,             -- full일 때 사람이 알려 준 기대 건수 (파일이 중간까지만 만들어진 경우를 막는다)
    change_summary       jsonb not null default '{}',  -- 직전 스냅샷 대비 새로 생김·바뀜(칸별)·사라짐·그대로 건수
    loaded_at            timestamptz not null default now(),
    pruned_at            timestamptz              -- 데이터 줄을 지운 시각 (prune). 비어 있으면 데이터가 남아 있다
);

-- 리콜 카드 1건 = 1줄 (recalls.jsonl)
create table if not exists recalls (
    snapshot_date date not null references data_builds (snapshot_date),
    campno        text not null,                                      -- 24V412000 (9자리, 원본 그대로)
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
    row_sha256    text not null,                                      -- 데이터 칸 전체의 해시. 스냅샷 사이에 바뀐 줄을 찾는 데 쓴다
    primary key (snapshot_date, campno)
);
create index if not exists recalls_campaign6_idx on recalls (snapshot_date, campaign6);
create index if not exists recalls_received_date_idx on recalls (snapshot_date, received_date);
create index if not exists recalls_dup_group_idx on recalls (snapshot_date, dup_group);

-- 시험 질문 1개 = 1줄 (eval.jsonl). 정답 리콜은 같은 스냅샷 recalls.campno 목록 (배열이라 외래 키는 못 건다 — 적재 스크립트가 대조한다)
create table if not exists eval_questions (
    snapshot_date date not null references data_builds (snapshot_date),
    action_no     text not null,
    question      text not null,
    open_date     date not null,
    gold_campnos  text[] not null,
    sets          text[] not null,          -- all · since2010 · rclrpt_range
    row_sha256    text not null,
    primary key (snapshot_date, action_no)
);

-- 원본 보고서(Part 573) 1건 = 1줄 (causes.jsonl 또는 표본 causes_sample.jsonl — data_builds.causes_kind)
create table if not exists causes (
    snapshot_date      date not null references data_builds (snapshot_date),
    campaign           text not null,       -- 24V412 (6자리). recalls.campaign6과 잇는다 — 한 캠페인이 recalls 여러 건에 붙을 수 있다
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
    unresolved_reasons text[] not null default '{}',
    row_sha256         text not null,
    primary key (snapshot_date, campaign)
);
create index if not exists causes_submission_date_idx on causes (snapshot_date, submission_date);

-- 평소 조회용: 데이터가 남아 있는 스냅샷 중 가장 최근 것만 보여 준다.
-- security_invoker = true — 뷰가 호출한 사람의 권한으로 테이블을 읽게 해서 아래 RLS를 우회하지 않는다 (뷰는 기본이 만든 사람 권한).
create or replace view latest_snapshot with (security_invoker = true) as
    select max(snapshot_date) as snapshot_date from data_builds where pruned_at is null;
create or replace view recalls_latest with (security_invoker = true) as
    select r.* from recalls r join latest_snapshot l using (snapshot_date);
create or replace view eval_questions_latest with (security_invoker = true) as
    select q.* from eval_questions q join latest_snapshot l using (snapshot_date);
create or replace view causes_latest with (security_invoker = true) as
    select c.* from causes c join latest_snapshot l using (snapshot_date);

-- Supabase는 public 테이블을 REST API로 열어 준다. 정책 없이 RLS를 켜서 anon·authenticated 키로는 아무것도 못 읽게 막는다.
-- 서버·스크립트는 postgres 계정으로 접속하므로 영향이 없다 (RLS를 우회한다).
alter table data_builds    enable row level security;
alter table recalls        enable row level security;
alter table eval_questions enable row level security;
alter table causes         enable row level security;
