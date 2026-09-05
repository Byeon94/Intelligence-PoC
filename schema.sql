-- Supabase SQL 편집기에서 한 번 실행하세요.

-- ── 자본시장 탭 ───────────────────────────────────────────────
-- 별도 DB가 필요 없습니다. 모든 지표는 data.go.kr(금융위원회) API를 조회해
-- 프로세스 메모리에 짧게 캐시합니다. 증권사별 CMA 금리는 capital/cma_rates.json.

-- ── 정책·규제 / 리서치·뉴스 탭 ────────────────────────────────
-- 하루 1회 수집한 원자료 + AI 산출물(브리핑·선별)을 날짜별 스냅샷 1건으로 저장.
create table if not exists policy_snapshots (
    snapshot_date date primary key,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists research_snapshots (
    snapshot_date date primary key,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

-- 자본시장 탭: 증권사별 CMA 금리를 하루 1회 AI(웹검색)로 갱신해 캐시.
create table if not exists cma_rate_snapshots (
    snapshot_date date primary key,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

-- 자본시장 > 발행시장 탭: IPO 일정·유상증자 공시 + AI 브리핑을 하루 1건 스냅샷.
create table if not exists issuance_snapshots (
    snapshot_date date primary key,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

-- 서버가 publishable(anon) 키로 접속한다면 아래 RLS 정책을 추가해야 읽기/쓰기가 됩니다.
-- (service_role / sb_secret_ 키를 쓰면 RLS를 우회하므로 불필요합니다.)
-- alter table policy_snapshots  enable row level security;
-- alter table research_snapshots enable row level security;
-- create policy "anon rw policy_snapshots"  on policy_snapshots  for all using (true) with check (true);
-- create policy "anon rw research_snapshots" on research_snapshots for all using (true) with check (true);
