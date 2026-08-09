-- Supabase SQL 편집기에서 한 번만 실행하세요.
create table if not exists news_summaries (
    id bigint generated always as identity primary key,
    keyword text not null,
    summary text not null,
    article_count integer not null,
    articles jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

-- 기존 테이블에 이미 news_summaries가 있다면 아래 한 줄만 추가로 실행하세요.
alter table news_summaries add column if not exists articles jsonb not null default '[]'::jsonb;

create index if not exists news_summaries_keyword_created_at_idx
    on news_summaries (keyword, created_at desc);

-- 정책 탭: 금융당국/유관기관 동향 (하루 1회 Gemini 검색 결과 캐시)
create table if not exists policy_updates (
    id bigint generated always as identity primary key,
    category text not null check (category in ('authority', 'affiliate', 'assembly', 'research')),
    org_code text not null,
    org_name text not null,
    title text not null,
    summary text not null,
    tags jsonb not null default '[]'::jsonb,
    source_label text not null,
    source_url text,
    published_label text,
    fetched_date date not null,
    created_at timestamptz not null default now(),
    unique (org_code, fetched_date)
);

create index if not exists policy_updates_fetched_date_idx
    on policy_updates (fetched_date desc);

-- 뉴스 탭: 카테고리별 피드 (하루 1회 네이버 뉴스 검색 결과 캐시)
create table if not exists news_feed_items (
    id bigint generated always as identity primary key,
    category text not null check (category in ('ksfc', 'finance', 'investment', 'it')),
    keyword text not null,
    title text not null,
    description text not null default '',
    link text not null,
    published_label text,
    fetched_date date not null,
    created_at timestamptz not null default now(),
    unique (link, fetched_date)
);

create index if not exists news_feed_items_fetched_date_idx
    on news_feed_items (fetched_date desc);

-- 뉴스 탭: 오늘의 포인트 뉴스 AI 브리핑 (하루 1회 캐시)
create table if not exists news_briefing (
    id bigint generated always as identity primary key,
    fetched_date date not null unique,
    summary text not null default '',
    created_at timestamptz not null default now()
);

-- DART 공시 탭: 담보대출 수요 / 우리사주 금융 수요 관련 공시 (하루 1회 캐시)
create table if not exists dart_filings (
    id bigint generated always as identity primary key,
    category text not null check (category in ('collateral', 'employee_stock')),
    corp_name text not null,
    stock_code text,
    report_nm text not null,
    flr_nm text,
    rcept_no text not null,
    rcept_dt date,
    source_url text,
    fetched_date date not null,
    created_at timestamptz not null default now(),
    unique (rcept_no, fetched_date)
);

-- 기존 테이블에 ai_note 컬럼이 남아있다면 아래 한 줄만 추가로 실행하세요 (AI 해설 기능 제거).
alter table dart_filings drop column if exists ai_note;

create index if not exists dart_filings_fetched_date_idx
    on dart_filings (fetched_date desc);

-- 캘린더 탭: 공모주 캘린더 / 주요 권리일정 (DART 공시 제출일 기준, 월 단위 캐시)
create table if not exists dart_calendar_items (
    id bigint generated always as identity primary key,
    year_month text not null,
    category text not null check (category in ('ipo', 'rights')),
    corp_name text not null,
    report_nm text not null,
    rcept_no text not null unique,
    rcept_dt date,
    source_url text,
    right_type text,
    right_label text,
    created_at timestamptz not null default now()
);

create index if not exists dart_calendar_items_year_month_idx
    on dart_calendar_items (year_month);
