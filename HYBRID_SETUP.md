# 자동화 설정 가이드

매일 08:00 GitHub Actions가 수집·분석 → 노션에 "후보" 업로드.
출근 후 노션 DB에서 "상태" 컬럼을 직접 후보 → 선정/제외로 바꿔가며 검토.

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

노션 DB를 열고 "상태=후보"로 필터링한 뒤, 검토한 기사의 "상태" 값을
직접 "선정" 또는 "제외"로 바꾼다.

## 6. 선정 사례 학습(선택)

상태를 "선정완료"로 바꾼 기사가 쌓이면, 그 사례를 AI 분석 프롬프트에 few-shot으로
넣어 비슷한 결의 기사를 더 잘 골라내도록 만들 수 있다.

- `.github/workflows/update_examples.yml`이 매주 일요일 07:00(KST)에 자동 실행되어
  노션에서 "상태=선정완료" 기사를 모아 `prompts/selected_examples.txt`를 갱신하고 커밋한다.
- 즉시 반영하려면 Actions 탭 → "Update Selected Examples" → "Run workflow".
- 로컬에서 직접 돌리려면: `.env`에 NOTION_API_KEY/NOTION_DATABASE_ID 설정 후 `python -m core.notion_learn`.
- 노션 DB의 "상태" 옵션에 `선정완료`가 없다면 추가하거나, `config.py`의
  `NOTION_LEARNED_STATUS` 값을 실제 사용 중인 상태명으로 바꾼다.

## 동작 요약

| 시점 | 주체 | 동작 |
|------|------|------|
| 08:00 | GitHub Actions | 수집·분석 → 노션 "후보" 10개 |
| 09:00 | 나 (노션) | 후보 검토 → "선정완료"/"제외"로 상태 변경 |
| 매주 일요일 07:00 | GitHub Actions | "선정완료" 기사 학습 → AI 프롬프트 예시 갱신 |
| 이후 | 노션 | "선정완료"만 모아 활용 |
