# 증금 인텔리전스 플랫폼 (PoC)

한국증권금융 임직원용 사내 정보 포털 PoC. 시장·정책·뉴스·여신 리드를 한 화면에서 보고,
QR로 접속해 모바일에서도 확인할 수 있도록 만든 데모입니다. **모든 데이터는 공개 출처**를 사용합니다.

## 화면 구성

좌측 사이드바(모바일에선 상단 2줄 바) 7개 메뉴 + 소개.

| 메뉴 | 내용 |
|---|---|
| 🏠 홈 | 오늘의 브리핑 — 오늘의 핵심(AI가 고른 최대 3건), 시장 한눈에(국내·해외 지수·환율·미국채), 오늘의 시장 브리핑(AI, 주식·채권·환율·장전), 오늘의 주요뉴스 5건. 접속 시 온보딩 투어 |
| 👤 나의 대시보드 | "+ 위젯 추가"/"AI가 추천하기"(mock)로 위젯을 담아 하나씩 보기. 기본 2개(한눈에 보는 기업분석, 업종별 시가총액·밸류체인). **선택은 탭 메모리에만 유지**(새로고침 시 초기화, 로그인·저장 없음) |
| 📈 자본시장 | 증시자금·유동성(예탁금·신용공여·CMA, 거래대금), CMA·단기수신(유형별 비중·증권사 금리), 발행시장(IPO·유상증자 캘린더 + AI 브리핑) |
| 💵 단기자금 | 원화(콜·KOFR·CD·CP·통안 금리, 기준금리, 스프레드, 3개월 추이, 자금중개사 시황 AI 요약, 관련 뉴스) / 외화(주요 통화 환율, 원/달러 추이, 한·미 정책금리, 관련 뉴스) — ECOS·뉴욕 연준 실데이터 |
| 🏦 여신 | 증권담보대출·우리사주대출 수요 리드 레이더(DART 공시 + 상속·증여/우리사주 뉴스 AI 판단 + AI 브리핑) |
| 📜 정책 | 금융당국·유관기관 보도자료 + AI 브리핑 |
| 📰 뉴스 | 네이버 뉴스에서 업무 관련 기사 AI 선별·태깅 + 브리핑 |

사이드바에는 없지만 해시로 열리는 화면: `#lending`(증권대차 — 주식·채권 대차 뉴스·리서치),
`#gallery`(옛 전사 위젯 갤러리, 옛 링크 호환), `#ib`·`#custody`(준비 중), 독립 페이지 `/sector`.

## 코드 구조

기능별 Flask 블루프린트 패키지 + 얇은 조립 계층(`main/`). 각 패키지는 자기 템플릿·정적 파일을
직접 소유합니다(`static_url_path="/static/<pkg>"`).

```
main/                조립 계층 + 공용 모듈
  app.py               Flask 앱, 블루프린트 등록, /api/home/summary, /internal/warmup(_WARMUP_JOBS)
  home.py              홈 오늘의 브리핑 요약 집계(각 탭 스냅샷 재사용, 새 AI 호출 없음)
  config.py            환경변수 → Settings
  utils.py             KST 날짜 헬퍼(now_kst/today_iso/stamp/ymd_to_iso)
  cache.py             ttl_cache(실패·샘플 값은 짧게만 캐시)
  daily_snapshot.py    일일 스냅샷 공용 흐름(table_lock, try_ai, parse_json_obj)
  snapshot_store.py    스냅샷 저장소(Supabase → 메모리 폴백, 복사본 반환)
  supabase_client.py   Supabase 클라이언트
  gemini.py            Gemini 호출 공용 래퍼(앱 전체 일일 호출 상한)
  naver_news.py        네이버 뉴스 검색 공용 클라이언트
  templates/           index.html(사이드바 셸) + home / personal / gallery.html
  static/
    common.js          window.KSFC 공용 헬퍼(esc, safeUrl, get, CIRCLED, bindBriefMore)
    style.css          전역 스타일(토큰·레이아웃·사이드바·블록·KPI·차트·표·AI 브리핑 카드 등)
    home.css           홈·나의 대시보드·모달·온보딩 스타일
    home.js            window.HomeDashboard 연결(진입점)
    home/              catalog → mini → stock-glance → sector-card → personal → briefing → onboarding
                       (빌드 없이 순서대로 로드, window.KSFC.home 공유)

capital/             자본시장 탭
  liquidity.py, turnover.py, cma.py, cma_rates.py   지표 API + 캐시 + 샘플 폴백
  _datago.py           data.go.kr 공통 호출
  market_snapshot.py   홈 "시장 한눈에"(국내·해외 지수·환율·금리 + 1년 추이)
  briefing.py          홈 "오늘의 시장 브리핑"(AI)
  issuance/            발행시장 세부탭(자체 블루프린트 issuance: calendar.py, sources.py, static/issuance.css·js)
  templates/, static/  capital.html, capital.js, charts.js(공용 인라인 SVG 차트), capital.css

credit/              여신 탭 + 기업분석 API(나의 대시보드 위젯이 사용)
  leads.py, lead_briefing.py, today_summary.py      리드 레이더(DART) · AI 브리핑 · 오늘 신규 건수
  inherit_news.py, esop_news.py, news_filter.py     상속·증여/우리사주 뉴스 동향(AI 관련도 판단)
  equity.py, financials.py, filings.py, reports.py, corp_map.py, store.py   기업분석·시장 리포트
  templates/, static/  credit.html, credit.js, credit.css

risk/                심사·리스크 탭(signals.py: DART 거래소공시 시그널·급락 종목, watch.py: 워치 유니버스·업종지수,
                     news.py: 부정 키워드 기사 AI 선별) — risk.html, risk.js, risk.css
funding/             단기자금 탭(ecos.py: ECOS 클라이언트, money_market.py: 원화·외화 요약) — funding.html, funding.js, funding.css
lending/             증권대차 화면(news.py) — lending.html, lending.js, lending.css
policy/              정책 탭(sources.py, briefing.py) — policy.html, policy.js, policy.css
research/            뉴스 탭(sources.py, curate.py) — research.html, research.js, research.css
it_news/             IT·정보보호 뉴스(curate.py, sources.py) — 나의 대시보드 위젯용 API만(화면 없음)
sector/              업종별 시가총액·밸류체인(market_map.py, value_chain.py, classify.py, constituents.py)
                     — /sector 페이지 + window.SectorWidget(sector.js), sector.css
```

CSS는 `index.html`에서 style.css → capital → lending → policy → issuance → research → credit → funding → risk →
home → sector 순으로 링크합니다(분리 전 style.css 안의 순서 그대로).

## 코드 컨벤션

- **날짜**: 서버 시계가 UTC라 "오늘"은 항상 `main.utils`(`today_iso()`, `now_kst()`)로 구한다. `date.today()` 금지.
- **일일 스냅샷**: `main.daily_snapshot.table_lock(table)` 안에서 조회→수집→저장, AI 가공은 `try_ai()`(스냅샷당 시도 상한)로.
  저장은 `main.snapshot_store`(Supabase 테이블은 `schema.sql`).
- **네이버 뉴스**: 직접 호출하지 말고 `main.naver_news` 사용(장애 시 `NewsFetchError`로 "기사 없음"과 구분).
- **Gemini**: `main.gemini.generate_text()`만 사용(앱 전체 일일 상한 적용).
- **JS**: 공용 헬퍼는 `window.KSFC`(common.js). 외부 텍스트를 `innerHTML`에 넣을 땐 반드시 `KSFC.esc()`,
  외부 링크 `href`는 `KSFC.esc(KSFC.safeUrl(url))`.

## 데이터 소스

- **공공데이터포털(data.go.kr)** — 금융투자협회 종합통계, 지수시세정보, 주식시세정보
- **금융감독원 DART** — 유상증자·지분 공시, 기업개황·재무제표·공시목록
- **38커뮤니케이션** — IPO 수요예측·청약 일정
- **네이버 검색 API / 네이버 금융** — 업무 관련 뉴스, 기업분석 참고 지표
- **한경컨센서스** — 증권사 리포트(스크랩)
- **Yahoo Finance(비공식)** — 해외 지수·환율·미국채 10년(참고용)
- **Google AI Studio(Gemini)** — 브리핑·뉴스 선별·리드 판단·업종 분류 (CMA 금리는 증권사 공식 홈페이지를 직접 읽음, capital/cma_firms.py)
- **Supabase** — 일일 스냅샷 저장

## 로컬 실행

```bash
python -m venv .venv && .venv/Scripts/activate     # Windows
pip install -r requirements.txt
cp .env.example .env    # 값 채우기(비워도 샘플 데이터·메모리 저장으로 동작)
flask --app main.app run --port 5000
```

## 환경변수 (`.env.example` 참고)

| 변수 | 용도 |
|---|---|
| `DATA_GO_KR_API_KEY` | data.go.kr 공용 인증키(없으면 샘플 데이터) |
| `GEMINI_API_KEY` | Gemini 키(하나만 사용, 없으면 AI 가공 생략) |
| `GEMINI_MODEL` | 모델명(기본 `gemini-3.6-flash`) |
| `GEMINI_MAX_CALLS_PER_DAY` | 앱 전체 하루 Gemini 실호출 상한(기본 40, 0이면 무제한) |
| `POLICY_MAX_GEMINI_CALLS_PER_DAY` | 이름과 달리 **스냅샷 1건당 AI 재시도 상한**(모든 탭 공통, 기본 3) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 검색 API |
| `DART_API_KEY` | DART OpenAPI |
| `ECOS_API_KEY` | 한국은행 ECOS Open API — 단기자금 탭(없으면 탭에 오류 문구만 표시) |
| `SUPABASE_URL` / `SUPABASE_KEY` | 스냅샷 저장(없으면 프로세스 메모리) |
| `WARMUP_KEY` | `/internal/warmup` 인증(없으면 403) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 배치 결과 텔레그램 알림(main/batch_report.py, 없으면 발송 안 함) |

## 배포 (Render)

`render.yaml` Blueprint 사용 또는 Web Service 수동 생성:

- Build: `pip install -r requirements.txt`
- Start: `gunicorn main.app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --worker-class gthread --timeout 120`
  (free 플랜 메모리 제약 + 인프로세스 캐시·락 공유를 위해 워커 1 + 스레드 4)
- Supabase에서 `schema.sql` 실행

### 매일 스냅샷 예열 (`/internal/warmup`, 05:00 + 07:00)

`.github/workflows/warmup.yml`이 매일 **05:00 KST**에 `GET /internal/warmup?key=<WARMUP_KEY>`를 호출합니다.
엔드포인트는 즉시 202를 응답하고(호출 측 curl `--max-time`·프록시 타임아웃 회피) 백그라운드 스레드에서
`main/app.py`의 `_WARMUP_JOBS`를 순서대로 실행합니다:

정책·규제 → 뉴스 → 발행시장 → CMA 금리 → 오늘의 시장 브리핑 → 시장 리포트 동향 → IT·정보보호 뉴스 →
증권대차 뉴스 → 여신 리드(`force=True`) → 상속·증여 뉴스 → 우리사주 뉴스 → 여신 리드 AI 브리핑(`force=True`)

같은 워크플로가 **07:00 KST**에 한 번 더 `...&mode=morning`으로 호출해 `_MORNING_JOBS`만 다시 만듭니다
(05:00엔 미국 장이 막 끝났거나 아직 열려 있고, 당일 기사도 거의 없기 때문):

오늘의 시장 브리핑(`force=True`) → 뉴스 → IT·정보보호 뉴스 → 증권대차 뉴스 → 상속·증여 뉴스 → 우리사주 뉴스
(모두 `rebuild=True`) → 여신 리드 AI 브리핑. 재생성이 실패하면 새벽 스냅샷이 그대로 유지됩니다.
Actions 탭에서 수동 실행(workflow_dispatch) 시 `mode`를 `daily`/`morning`으로 고를 수 있습니다.

GitHub 저장소 Secrets에 `WARMUP_KEY`를 Render 환경변수와 같은 값으로 등록해야 동작합니다.

### 업종 분류 수동 실행

업종별 시가총액 맵의 전종목 업종 분류(Gemini 대량 호출)는 API 사용량 때문에 예열에 넣지 않았습니다.
화면은 저장된 분류만 읽으므로, 필요할 때(약 30일 주기) 직접 실행합니다:

```bash
.venv/Scripts/python.exe -c "from sector.classify import refresh_sector_classification as r; r()"
```

기본은 마지막 분류 후 30일이 지났을 때만 재분류하며, 바로 다시 돌리려면 `r(force=True)`. 이 호출은 일일 Gemini 상한에서 제외됩니다.

## 스택

Flask · 순수 HTML/CSS/JS(인라인 SVG 차트, 빌드 없음) · Supabase · Render · GitHub Actions(일일 예열)
