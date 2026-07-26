-- Supabase SQL 편집기에서 한 번만 실행하세요.
create table if not exists news_summaries (
    id bigint generated always as identity primary key,
    keyword text not null,
    summary text not null,
    article_count integer not null,
    created_at timestamptz not null default now()
);
