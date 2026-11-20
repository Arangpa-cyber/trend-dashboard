# 추세 대시보드 (나스닥100)

오닐·미너비니식 주도주 추세 추종을 위한 개인용 대시보드입니다.
GitHub가 매일 미국장(시간외 거래까지) 마감 뒤 데이터를 받아 `data.json`을 만들고,
GitHub Pages 주소에서 열자마자 뜹니다. 맥·아이폰·아이패드 어디서나 같은 주소로 봅니다.

- 사이트: https://arangpa-cyber.github.io/trend-dashboard/
- 보는 법: 화면 오른쪽 위 **? 도움말**, 각 층 제목 옆 **?**
- 작업 안내(구조·규칙·기준값의 근거): [`CLAUDE.md`](CLAUDE.md)

## 화면

| 층 | 질문 |
|---|---|
| 0층 고정 바 | 지금 상황 한 줄(시장 판정 · 매수 후보 수 · 보유의 팔기·정리 수) |
| 1층 시장 | 지금 사도 되나(공격 · 대기 · 방어: QQQ 200일선 · 200일선 기울기 · 52주 고점 대비 −12%) |
| 2층 산업 | 주도 산업은 어디인가(산업 안 주도주 비율로 22개 산업 중 5-7곳) |
| 3층 종목 | 무엇을 살까(매수 후보 = 주도 산업의 주도주 · 주도주 · 전체) |
| 4층 내 종목 | ★★ 보유는 언제 파나(팔기 · 정리 검토 · 보유 유지), ★ 관심은 언제 사나(3층 매수 조건으로 네 묶음) |
| 5층 큰손 | 큰 자본은 무엇을 샀나(13F 상위 종목) |

휴대폰(640px 이하)에서는 종목 표가 한 종목 한 카드로 바뀝니다.

## 파일

| 파일 | 역할 |
|---|---|
| `index.html` | 대시보드 전부(HTML·CSS·JS 한 파일). 종목 목록 `UNIVERSE`도 여기 있고 서버가 같은 목록을 읽음 |
| `vendor/` | 차트 라이브러리 사본(TradingView Lightweight Charts 4.2.0, Apache 2.0) |
| `data.json` | 서버가 매일 커밋하는 결과(직접 고치지 않음) |
| `profiles.json` | 종목별 기업 프로필(확대 차트 위 패널) |
| `press-notices.json` | 나스닥100 변경 발표 알림(매주 화요일 Claude 예약 작업이 적음) |
| `whales/` | 5층 큰손 13F 파일(`scripts/build_whale.py`로 분기마다 만듦) |
| `scripts/build_data.py` | 서버 데이터 수집 → `data.json` |
| `scripts/build_whale.py` | 큰손 13F 파일 만들기(손으로 실행, SEC 접속) |
| `scripts/check_profiles.py` | `profiles.json`이 종목 목록과 맞는지 확인 |
| `scripts/backfill_history.py` | 백테스트용 긴 일봉 받기 |
| `backtest/` | 백테스트(node). `index.html`의 계산 함수를 그대로 씀 |
| `.github/workflows/update-data.yml` | 매일 데이터 갱신(예약) |
| `.github/workflows/backfill-history.yml` | 백테스트용 긴 일봉 받기(수동) |

## 데이터

- **시세**: Twelve Data 무료 키(분당 8회, 하루 800회). 나스닥100 · 큰손 종목 · QQQ, 하루 약 125회.
- **실적 일정·재무**: Alpha Vantage 무료 키(하루 25회). 실적 달력 1회, QQQ 보유 종목 1회, 재무(분기 매출·주식 수) 하루 11종목.
- **갱신 시각**: 예약은 한국시간 화-토 09:30. GitHub 대기열 때문에 실제 반영은 보통 오전 11시 무렵입니다.
  서버는 미국 동부 20:15(시간외 거래 마감 뒤)까지 기다렸다 받고, 그 전에 받은 "오늘" 일봉은 버립니다.

## 처음 설정 (새 저장소에 다시 만들 때)

1. 저장소를 **Public**으로 만듭니다(GitHub Pages 무료 조건). 보유 종목 같은 개인 정보는 저장소에 들어가지 않고 각자 브라우저에만 저장됩니다.
2. 파일을 모두 올립니다(`.github` 숨김 폴더 포함).
3. Settings → Secrets and variables → Actions에 키 두 개를 넣습니다: `TWELVE_DATA_KEY`, `ALPHAVANTAGE_KEY`.
4. Settings → Pages → Deploy from a branch → `main`, `/ (root)`.
5. Actions → "데이터 갱신" → Run workflow. 약 20분 뒤 `data.json`이 생깁니다.

## 알아 둘 점

- 나스닥100 종목이 바뀌면(매년 12월 정기 변경 등) `index.html`의 `UNIVERSE`와 `profiles.json`을 함께 고치고 `python3 scripts/check_profiles.py`로 확인합니다.
- 저장소에 60일 동안 활동이 없으면 GitHub가 예약 실행을 멈출 수 있습니다. 매일 데이터가 커밋되므로 보통은 문제없습니다.
- 서버 데이터가 없을 때는 ⚙ 설정에 Twelve Data 키를 넣어 브라우저에서 직접 받을 수도 있습니다(재무·실적 일정은 빠짐).
