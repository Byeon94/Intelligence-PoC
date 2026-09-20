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

-- 전사 위젯 > 증권사 리포트 전체 동향: 종목 무관, 조회 기준일의 시장 전체 리포트
-- 건수 + 상위 20건 + AI 브리핑을 하루 1건 스냅샷.
create table if not exists market_report_snapshots (
    snapshot_date date primary key,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

-- 전사 위젯 > 오늘의 IT·정보보호 뉴스(IT부 제작): 당일 후보 기사 풀 + AI 선별·브리핑을
-- 하루 1건 스냅샷.
create table if not exists it_news_snapshots (
    snapshot_date date primary key,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

-- 증권대차 탭: 공매도·주식대차/채권대차 관련 뉴스 3건씩(실데이터)을 하루 1건 스냅샷.
-- (대차잔고·상위종목 KPI는 lending/sample.py 예시값이라 별도 테이블 불필요)
create table if not exists lending_news_snapshots (
    snapshot_date date primary key,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

-- 여신·심사 메인 화면: 코스피 전 종목 담보대출·우리사주 금융 수요 리드(DART 실데이터, 하루 1회 수집)
create table if not exists credit_lead_snapshots (
    snapshot_date date primary key,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

-- 여신·심사 > 기업분석 탭: 종목별 '오늘자' 조회 결과 캐시(기초정보·재무정보).
-- 같은 종목을 하루 안에 다시 열면 외부 API(data.go.kr·DART·네이버)를 재호출하지 않는다.
-- code='_corpmap' 행은 DART 종목코드→corp_code 매핑(하루치).
create table if not exists equity_snapshots (
    snapshot_date date not null,
    code text not null,
    payload jsonb not null,
    created_at timestamptz not null default now(),
    primary key (snapshot_date, code)
);

-- 서버가 publishable(anon) 키로 접속한다면 아래 RLS 정책을 추가해야 읽기/쓰기가 됩니다.
-- (service_role / sb_secret_ 키를 쓰면 RLS를 우회하므로 불필요합니다.)
-- alter table policy_snapshots  enable row level security;
-- alter table research_snapshots enable row level security;
-- create policy "anon rw policy_snapshots"  on policy_snapshots  for all using (true) with check (true);
-- create policy "anon rw research_snapshots" on research_snapshots for all using (true) with check (true);
-- create policy "anon rw equity_snapshots"  on equity_snapshots  for all using (true) with check (true);
