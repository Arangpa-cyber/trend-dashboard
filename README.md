# 추세 대시보드 — GitHub 자동 갱신 설정

이 폴더를 GitHub 저장소에 올리면, 매일 미국장 마감 뒤 GitHub가 데이터를 받아 `data.json`을 만들고,
대시보드는 GitHub Pages 주소에서 **열자마자** 뜹니다. 맥·아이폰·아이패드 어디서나 같은 주소로 봅니다.

## 들어 있는 파일

| 파일 | 역할 |
|---|---|
| `index.html` | 대시보드 (서버에 `data.json`이 있으면 그걸 쓰고, 없으면 API 키로 직접 받음) |
| `scripts/build_data.py` | 시세(Twelve Data)·실적 일정(Nasdaq)을 받아 `data.json` 생성 |
| `.github/workflows/update-data.yml` | 평일 21:10 UTC(한국 화-토 06:10)에 위 스크립트 실행 |

## 처음 한 번 설정 (10분)

1. **저장소 만들기**: github.com → New repository → 이름 예: `trend-dashboard`
   - GitHub Pages를 무료로 쓰려면 **Public** 이어야 합니다. (Private + Pages는 유료 요금제)
   - Public이면 대시보드 주소를 아는 사람은 누구나 볼 수 있습니다. 개인 보유 종목 같은 정보는 들어 있지 않습니다.
2. **파일 올리기**: 이 폴더의 파일을 모두 올립니다. `.github` 폴더(숨김 폴더)도 꼭 포함하세요.
3. **API 키 등록**: 저장소 Settings → Secrets and variables → Actions → New repository secret
   - Name: `TWELVE_DATA_KEY` / Secret: 본인 Twelve Data 키
4. **Pages 켜기**: Settings → Pages → Source: Deploy from a branch → Branch: `main`, 폴더 `/ (root)` → Save
5. **첫 실행**: Actions 탭 → "데이터 갱신" → Run workflow. 약 15-20분 뒤 `data.json`이 생깁니다.
6. **열기**: `https://<내 아이디>.github.io/trend-dashboard/` 를 즐겨찾기에 추가.

## 알아 둘 점

- 무료 키 하루 한도 800회 중 매일 약 105회를 씁니다.
- GitHub 예약 실행은 몇십 분 늦게 시작할 수 있습니다. 화면 위 "다음 서버 갱신 … 무렵"은 대략적인 시각입니다.
- 실적 일정은 Nasdaq의 비공식 경로를 씁니다. 막히면 실적 표시만 빠지고 나머지는 정상입니다.
- 나스닥100 종목이 바뀌면 `index.html`의 `UNIVERSE`만 고치면 됩니다. 서버 스크립트도 같은 목록을 읽습니다.
- 저장소에 60일 동안 활동이 없으면 GitHub가 예약 실행을 멈출 수 있습니다. 매일 데이터가 커밋되므로 보통은 문제없지만,
  멈췄다면 Actions 탭에서 다시 켜면 됩니다.
