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
