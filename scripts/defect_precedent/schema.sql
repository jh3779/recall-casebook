-- 결함 선례 데이터 테이블 (Supabase / Postgres). DEC-034.
-- 적용: uv run --env-file .env python -m scripts.defect_precedent.load_db schema
-- 여러 번 실행해도 된다 (create ... if not exists). 아직 어떤 DB에도 올리기 전의 첫 버전이다 —
-- 올린 뒤에 칸을 바꿀 때는 이 파일의 기존 칸을 고치지 않고 새 migration을 만든다.
--
-- build 단위로 보관한다. build_id는 입력 파일 4개(원본 명세·카드·시험지·원인 파일)의 sha256으로 정해지는 불변 식별자라서
-- 내용이 하나라도 다르면 다른 build다 — 같은 날짜(snapshot_date)라도 덮어쓰지 않고 둘 다 남는다
-- (예: 같은 날짜의 표본 build와 전체 build). 줄마다 build_id를 두고 (build_id, 번호)를 기본키로 쓴다.
-- 새 build를 올려도 지난 build는 그대로이고(과거 답변이 쓴 데이터를 되살릴 수 있다), 평소 조회는 *_latest 뷰로 한다.
-- build를 지우는 명령은 두지 않는다 — 지운 데이터를 되살릴 보관소(아카이브)가 생길 때 추가한다 (DEC-034 미결).
--
-- 날짜 칸은 date 타입이다. 원본은 YYYYMMDD(snapshot_date는 YYYY-MM-DD) 문자열이고, 적재 스크립트가 칸마다 정해진
-- 형식만 받아 틀리면 중단한다 (추측해 고치지 않는다).
-- 벡터 칸(recall_embeddings)은 임베딩 모델이 정해진 뒤 만든다. 지금은 만들지 않는다.

-- build 1개 = 1줄. 어느 원본·어느 파일에서 만들었는지, 이전 날짜와 무엇이 달라졌는지를 남긴다
create table if not exists data_builds (
    build_id             text primary key,         -- sha256(원본 명세|카드|시험지|원인 파일)의 앞 16자리
    snapshot_date        date not null,
    raw_manifest_sha256  text not null,
    recalls_sha256       text not null,
    eval_sha256          text not null,
    causes_kind          text not null check (causes_kind in ('sample', 'full')),
    causes_file          text not null,
    causes_sha256        text not null,
    causes_rows          integer not null,
    causes_expected_rows integer not null,         -- 독립된 명세에서 온 기대 줄 수 (표본: 기준 파일의 캠페인 목록, 전체: causes.manifest.json)
    causes_spec          jsonb not null,           -- 대조한 명세 (표본: 기준 파일 이름·줄 수·캠페인 목록 sha256, 전체: manifest 내용)
    change_summary       jsonb not null default '{}',  -- 직전 날짜의 build 대비 새로 생김·바뀜(칸별)·사라짐·그대로 건수
    loaded_at            timestamptz not null default now()
);
create index if not exists data_builds_snapshot_idx on data_builds (snapshot_date);

-- 리콜 카드 1건 = 1줄 (recalls.jsonl)
create table if not exists recalls (
    build_id      text not null references data_builds (build_id),
    snapshot_date date not null,
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
    row_sha256    text not null,                                      -- 데이터 칸 전체의 해시. build 사이에 바뀐 줄을 찾는 데 쓴다
    primary key (build_id, campno)
);
create index if not exists recalls_campaign6_idx on recalls (build_id, campaign6);
create index if not exists recalls_received_date_idx on recalls (build_id, received_date);
create index if not exists recalls_dup_group_idx on recalls (build_id, dup_group);

-- 시험 질문 1개 = 1줄 (eval.jsonl). 정답 리콜은 같은 build의 recalls.campno 목록 (배열이라 외래 키는 못 건다 — 적재 스크립트가 대조한다)
create table if not exists eval_questions (
    build_id      text not null references data_builds (build_id),
    snapshot_date date not null,
    action_no     text not null,
    question      text not null,
    open_date     date not null,
    gold_campnos  text[] not null,
    sets          text[] not null,          -- all · since2010 · rclrpt_range
    row_sha256    text not null,
    primary key (build_id, action_no)
);

-- 원본 보고서(Part 573) 1건 = 1줄 (causes.jsonl 또는 표본 causes_sample.jsonl — data_builds.causes_kind)
create table if not exists causes (
    build_id           text not null references data_builds (build_id),
    snapshot_date      date not null,
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
    primary key (build_id, campaign)
);
create index if not exists causes_submission_date_idx on causes (build_id, submission_date);

-- 평소 조회용: build 하나만 고른다 — 전체본(full)이 하나라도 있으면 가장 최근 날짜의 전체본, 없을 때만 가장 최근 표본(sample).
-- 날짜보다 종류가 먼저다: 나중 날짜의 표본(300건)이 이전 날짜의 전체본(약 1.2만 건)을 평소 조회에서 가리지 않게 한다.
-- 같은 종류 안에서는 가장 최근 날짜, 같은 날짜면 나중에 올린 것. 표본·옛 build는 지워지지 않고 남는다.
-- 표본만 보고 싶으면 아래 *_latest_sample 뷰를 쓴다.
-- security_invoker = true — 뷰가 호출한 사람의 권한으로 테이블을 읽게 해서 아래 RLS를 우회하지 않는다 (뷰는 기본이 만든 사람 권한).
create or replace view latest_build with (security_invoker = true) as
    select build_id, snapshot_date from data_builds
    order by (causes_kind = 'full') desc, snapshot_date desc, loaded_at desc
    limit 1;
create or replace view recalls_latest with (security_invoker = true) as
    select r.* from recalls r join latest_build l using (build_id);
create or replace view eval_questions_latest with (security_invoker = true) as
    select q.* from eval_questions q join latest_build l using (build_id);
create or replace view causes_latest with (security_invoker = true) as
    select c.* from causes c join latest_build l using (build_id);

-- 표본 전용 조회: 가장 최근 날짜의 표본 build (전체본이 있어도 표본을 따로 볼 때)
create or replace view latest_sample_build with (security_invoker = true) as
    select build_id, snapshot_date from data_builds
    where causes_kind = 'sample'
    order by snapshot_date desc, loaded_at desc
    limit 1;
create or replace view recalls_latest_sample with (security_invoker = true) as
    select r.* from recalls r join latest_sample_build l using (build_id);
create or replace view eval_questions_latest_sample with (security_invoker = true) as
    select q.* from eval_questions q join latest_sample_build l using (build_id);
create or replace view causes_latest_sample with (security_invoker = true) as
    select c.* from causes c join latest_sample_build l using (build_id);

-- Supabase는 public 테이블을 REST API로 열어 준다. 정책 없이 RLS를 켜서 anon·authenticated 키로는 아무것도 못 읽게 막는다.
-- 서버·스크립트는 postgres 계정으로 접속하므로 영향이 없다 (RLS를 우회한다).
alter table data_builds    enable row level security;
alter table recalls        enable row level security;
alter table eval_questions enable row level security;
alter table causes         enable row level security;
