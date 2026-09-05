# 증금 인텔리전스 플랫폼 (PoC)

한국증권금융 임직원용 사내 정보 포털 PoC. 시장·정책·발행시장 지표를 한 화면에서 보고,
QR로 접속해 모바일에서도 확인할 수 있도록 만든 데모입니다. **모든 데이터는 공개 출처**를 사용합니다.

## 탭

| 탭 | 내용 |
|---|---|
| 자본시장 | 증시자금·유동성(투자자예탁금·신용공여·CMA), CMA·단기수신, 발행시장(IPO 캘린더 + AI 브리핑) |
| 정책·규제 | 금융당국 4곳·유관기관 4곳 보도자료 + AI 브리핑 |
| 리서치·뉴스 | 네이버 뉴스에서 업무 관련 기사 AI 선별·태깅 + 브리핑 |
| 그 외 5개 탭 | 준비 중 |

## 데이터 소스

- **공공데이터포털(data.go.kr)** — 금융투자협회 종합통계, 지수시세정보
- **금융감독원 DART** — 유상증자 공시
- **38커뮤니케이션** — IPO 수요예측·청약 일정
- **네이버 검색 API** — 뉴스
- **Google AI Studio(Gemini)** — 각 탭 AI 브리핑 (하루 1회, DB 캐시)
- **Supabase** — 일일 스냅샷 저장

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
- Start: `gunicorn main.app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- 환경변수: `.env.example` 참고 (DATA_GO_KR_API_KEY, GEMINI_API_KEY(_2), NAVER_CLIENT_ID/SECRET, DART_API_KEY, SUPABASE_URL/KEY)
- Supabase에서 `schema.sql` 실행

## 스택

Flask · 순수 HTML/CSS/JS(인라인 SVG 차트) · Supabase · Render
