# 증금 인텔리전스 플랫폼 (PoC)

한국증권금융 임직원용 사내 정보 포털 PoC. 시장·정책·발행시장·종목 지표를 한 화면에서 보고,
QR로 접속해 모바일에서도 확인할 수 있도록 만든 데모입니다. **모든 데이터는 공개 출처**를 사용합니다.

## 화면 구성

상단 4개 카테고리 + 업무별 8개 화면 구조입니다.

| 카테고리 | 내용 |
|---|---|
| 🏠 홈 대시보드 | 정책·리서치 통합 브리핑(AI) + 이상징후/발행시장/금융당국 알림(최대 3건) |
| 👤 내 위젯 | 전사 위젯에서 고른 위젯 모음(브라우저 로컬 저장, 로그인 없음). 기업분석은 위젯 안에서 직접 종목 검색 가능 |
| 🗂️ 부서 위젯 | 아래 8개 업무별 화면 |
| 🏢 전사 위젯 | 등재된 위젯을 살펴보고 "내 위젯"에 추가하는 갤러리 |

업무별 화면(부서 위젯) 8개:

| 화면 | 내용 |
|---|---|
| 📈 자본시장 | 증시자금·유동성(투자자예탁금·신용공여·CMA), CMA·단기수신(유형별 비중·증권사 금리), 발행시장(IPO·유상증자 캘린더 + AI 브리핑) |
| 📜 정책·규제 | 금융당국 4곳·유관기관 4곳 보도자료 + AI 브리핑 |
| 📰 리서치·뉴스 | 네이버 뉴스에서 업무 관련 기사 AI 선별·태깅 + 브리핑 |
| 🏦 여신·심사 | 종목 기업분석(기초정보·가격범위·재무요약·실적분석) / 공시(DART) / 증권사 리포트(목표주가 컨센서스) |
| 💼 투자금융 / 🔐 수탁 / 💱 자금·외화 / 🔄 증권대차 | 준비 중 |

## 코드 구조

기능별 Flask 블루프린트 패키지 + 얇은 조립 계층(`main/`)으로 구성됩니다.

```
main/               상단 nav 조립, 홈 대시보드, 공통 설정/DB/AI 클라이언트
  app.py              Flask 앱, 블루프린트 등록, /internal/warmup
  home.py             홈 대시보드 알림·통합 브리핑 집계
  config.py           환경변수 로딩(Settings)
  snapshot_store.py   일일 스냅샷 공용 저장소(Supabase → 메모리 폴백)
  supabase_client.py  Supabase 클라이언트
  gemini.py           Gemini 호출 공용 래퍼(키 폴백)
  templates/          index.html(nav 셸) + home/gallery/personal.html
  static/             home.js(홈·전사위젯·내위젯 공용 로직), style.css(전역 스타일)

capital/            자본시장 탭 (증시자금유동성 / CMA·단기수신 / 발행시장)
  liquidity.py, cma.py, cma_rates.py, turnover.py   각 지표 API 호출 + 캐시 + 샘플 폴백
  issuance/            발행시장 세부탭(자체 블루프린트: calendar.py, sources.py, widget.py)
  sample_data.py       공공데이터 실패 시 대체 데이터
  templates/, static/  capital.html, capital.js, charts.js(공용 인라인 SVG 차트)

credit/             여신·심사 탭 (기업분석 / 공시 / 리포트)
  equity.py, financials.py, filings.py, reports.py, corp_map.py, store.py
  sample_data.py       외부 API 실패 시 대체 데이터
  templates/, static/  credit.html, credit.js

policy/             정책·규제 탭
  sources.py, briefing.py, widget.py
  templates/, static/  policy.html, policy.js

research/           리서치·뉴스 탭
  sources.py, curate.py, widget.py
  templates/, static/  research.html, research.js
```

각 패키지는 자기 블루프린트의 템플릿·정적 파일을 직접 소유합니다(`static_url_path="/static/<pkg>"`).
`main/static/style.css` 하나가 전역 스타일시트이며, `main/static/home.js`가 홈/전사위젯/내위젯의
공용 로직(위젯 카탈로그, localStorage 저장, 미리보기 렌더링)을 담당합니다.

## 데이터 소스

- **공공데이터포털(data.go.kr)** — 금융투자협회 종합통계, 지수시세정보, 주식시세정보
- **금융감독원 DART** — 유상증자 공시, 기업개황·재무제표·공시목록·주요계정
- **38커뮤니케이션** — IPO 수요예측·청약 일정
- **네이버 검색 API / 네이버 금융** — 업무 관련 뉴스, 기업분석 업종·PER·PBR(참고용)
- **한경컨센서스** — 증권사 리포트·목표주가 컨센서스(스크랩)
- **Google AI Studio(Gemini)** — 각 탭 AI 브리핑/선별/CMA 금리 조사 (하루 1회, DB 캐시)
- **Supabase** — 일일 스냅샷 저장(정책·리서치·발행시장·CMA금리·종목별 기업분석)

## 로컬 실행

```bash
python -m venv .venv && .venv/Scripts/activate     # Windows
pip install -r requirements.txt
cp .env.example .env    # 값 채우기
flask --app main.app run --port 5000
```

## 배포 (Render)

`render.yaml` Blueprint 사용 또는 Web Service 수동 생성:

- Build: `pip install -r requirements.txt`
- Start: `gunicorn main.app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --worker-class gthread --timeout 120`
  (free 플랜 메모리 제약 + 인프로세스 캐시 공유를 위해 워커 1 + 스레드 4)
- 환경변수: `.env.example` 참고 (DATA_GO_KR_API_KEY, GEMINI_API_KEY(_2~_5), NAVER_CLIENT_ID/SECRET,
  DART_API_KEY, SUPABASE_URL/KEY, WARMUP_KEY)
- Supabase에서 `schema.sql` 실행

### 매일 아침 스냅샷 예열 (`/internal/warmup`)

정책·규제/리서치·뉴스/발행시장/CMA금리 스냅샷은 KST 자정에 "오늘 것"으로 바뀌는데, 첫 방문자가
콜드 스크랩(외부 API+AI 호출)에 걸려 응답이 늦어지는 것을 막기 위해 배치로 미리 데워둡니다.

- `.github/workflows/warmup.yml`이 매일 **00:01 KST**에 `GET /internal/warmup?key=<WARMUP_KEY>`를 호출
- 이 엔드포인트는 즉시 202를 응답하고, 실제 스크랩은 백그라운드 스레드에서 진행(gunicorn 120초
  타임아웃 회피)
- GitHub 저장소 Secrets에 `WARMUP_KEY`를 Render 환경변수와 동일한 값으로 등록해야 동작합니다

## 스택

Flask · 순수 HTML/CSS/JS(인라인 SVG 차트) · Supabase · Render · GitHub Actions(일일 예열)
