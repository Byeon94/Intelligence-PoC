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
