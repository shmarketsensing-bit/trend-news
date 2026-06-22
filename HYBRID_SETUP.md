# 하이브리드 자동화 설정 가이드

매일 08:00 GitHub Actions가 수집·분석 → 노션에 "후보" 업로드.
출근 후 Streamlit 화면에서 노션 후보를 검토 → 선정/제외.

## 1. 노션 DB에 "상태" 컬럼 추가 (필수)

DB 표 오른쪽 `+` → 이름 **상태**, 유형 **선택(Select)**.
옵션 3개 추가: `후보`, `선정`, `제외`

## 2. GitHub Secrets 등록 (이미 완료)

저장소 → Settings → Secrets and variables → Actions 에 5개:
- NAVER_CLIENT_ID
- NAVER_CLIENT_SECRET
- GEMINI_API_KEY
- NOTION_API_KEY
- NOTION_DATABASE_ID

## 3. 코드 푸시

```
git add .
git commit -m "하이브리드 자동화"
git push
```

`.github/workflows/daily_collect.yml`이 올라가면 Actions 탭에 워크플로가 나타남.

## 4. 즉시 테스트 (8시까지 안 기다리고)

저장소 → Actions 탭 → "Daily Trend News Collect" → "Run workflow" 버튼.
1~2분 뒤 노션 DB에 "상태=후보" 기사 10개가 올라오면 성공.

> 스케줄은 매일 KST 08:00(UTC 23:00) 자동 실행.
> GitHub Actions 스케줄은 부하에 따라 수 분~십수 분 늦을 수 있음(정상).

## 5. 출근 후 큐레이션

로컬에서:
```
.venv\Scripts\python.exe -m streamlit run app.py
```
→ "보기: 후보" 에서 검토 → 선정/제외 클릭 → 노션 상태가 바로 바뀜.

## 동작 요약

| 시점 | 주체 | 동작 |
|------|------|------|
| 08:00 | GitHub Actions | 수집·분석 → 노션 "후보" 10개 |
| 09:00 | 나 (Streamlit) | 후보 검토 → "선정"/"제외" |
| 이후 | 노션 | "선정"만 모아 활용 |
