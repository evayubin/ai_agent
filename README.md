# ai_agent_(가칭. 🎯 EVA 에이전트 팀)

Building AI agent for managing the day and crawling job opening data for getting a job in public company sector.
> 공기업 취준생 + 한국어 강사의 이중 생활을 돕는 AI 에이전트 데스크탑 앱

macOS 바탕화면에 상주하는 플로팅 Dock UI로, 3명의 AI 에이전트가 취업 준비 · 일정 관리 · 수업 운영을 실시간으로 지원합니다.

---

## 👥 에이전트 소개

| 캐릭터 | 이름 | 역할 |
|--------|------|------|
| 🔵 설리 | Sully | 공기업 채용 전략가 — 공고 수집·분석·점수화 |
| 🟢 마이크 | Mike | 스크럼 & 시스템 매니저 — 주간 브리핑·KPT·투두 관리 |
| 🟣 로즈 | Roz | 교육 운영 매니저 — 수강생 현황·수업 기록·교재 제작 |

---

## 🖥️ 화면 구성

```
┌─────────────────────────────────────┐
│  [마이크] [설리] [로즈] │ 🏠 📅 📋  │  ← 플로팅 Dock (항상 표시)
└─────────────────────────────────────┘
         ↑ 클릭 시 채팅창 열림

📅 주간 버튼 → 마이크 브리핑 패널
📋 공고 버튼 → 오늘의 공기업 공고 목록
```

---

## 🛠️ 기술 스택

| 구분 | 기술 |
|------|------|
| 프론트엔드 | Electron + HTML/CSS/JS |
| 백엔드 | Python Flask (포트 5050) |
| AI | OpenAI GPT-4o |
| 연동 | Notion API, ALIO 공기업 공고 API |
| 패키징 | macOS Automator .app 번들 |

---

## 📁 프로젝트 구조

```
ai_agent/
├── main.js                 # Electron 메인 프로세스
├── preload.js              # Electron preload
├── server_v3.py            # Flask 백엔드 서버 (포트 5050)
├── notion_sync.py          # Notion API 연동 (설리/마이크/로즈)
├── crawler.py              # ALIO 공기업 공고 크롤러
├── agent.py                # 공기업 분석 엔진
├── history.py              # 분석 기록 관리
├── agents.json             # 에이전트 설정
├── .env                    # API 키 (gitignore)
└── dashboard/
    ├── voice.html          # 플로팅 Dock UI
    ├── index.html          # 대시보드 메인
    └── static/
        ├── sully/          # 설리 캐릭터 영상
        ├── mike/           # 마이크 캐릭터 영상
        └── roz/            # 로즈 캐릭터 영상
```

---

## ⚙️ 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/evayubin/ai_agent.git
cd ai_agent
```

### 2. Python 가상환경 설정
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Node.js 패키지 설치
```bash
npm install
```

### 4. 환경변수 설정
`.env` 파일 생성 후 아래 값 입력:
```
OPENAI_API_KEY=sk-proj-...
NOTION_API_KEY=ntn_...
NOTION_JOB_DB_ID=...
NOTION_WEEKLY_DB=...
NOTION_KPT_DB=...
NOTION_KANBAN_PAGE=...
NOTION_STUDENT_DB_ID=...
NOTION_LESSON_DB_ID=...
ALIO_API_KEY=...
```

### 5. 실행
```bash
npm start
```

---

## 🚀 바탕화면 앱으로 실행

Automator로 `.app` 번들 생성:

1. **Spotlight** → `Automator` 실행
2. `새 도큐멘트` → **응용 프로그램** 선택
3. `셸 스크립트 실행` 추가 후 아래 입력:
```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
pkill -f "electron.*ai_agent" 2>/dev/null
pkill -f "server_v3.py" 2>/dev/null
sleep 0.5
cd /Users/imeva/AI_agent_build/ai_agent
npm start > /tmp/eva.log 2>&1 &
```
4. `Cmd+S` → 바탕화면에 **EVA 에이전트팀** 으로 저장

---

## 📋 주요 기능

### 설리 — 공기업 채용 전략
- ALIO API로 매일 09:00 공고 자동 수집
- 자격증·토익·전공 기준 점수화 및 랭킹
- Notion 공고 DB 자동 저장

### 마이크 — 스크럼 매니저
- 매일 아침 오늘 요일 할 일 브리핑
- 주간 누적 달성률 바 차트
- 단기 목표 노션 칸반에서 실시간 읽기
- **토요일** → KPT 회고 템플릿 자동 생성
- **일요일** → 다음 주 주간 계획 자동 생성 (KPT Try 항목 반영)

### 로즈 — 교육 운영
- 수강생 잔여 수업 현황 실시간 확인
- 수업 기록 (피드백/단어) 파싱
- 교재 제작 컨텍스트 자동 생성

---

## 🔧 오류 대응 가이드

### 앱이 실행 안 될 때
```bash
cat /Users/imeva/AI_agent_build/ai_agent/server.log | tail -30
```

### 마이크 브리핑 안 나올 때
```bash
cd /Users/imeva/AI_agent_build/ai_agent
source venv/bin/activate
python3 -c "from notion_sync import mike_daily_brief; print(mike_daily_brief())"
```

### 서버 재시작
```bash
pkill -f server_v3.py
cd /Users/imeva/AI_agent_build/ai_agent
source venv/bin/activate
python3 server_v3.py
```

### 문법 오류 확인
```bash
python3 -c "import notion_sync"
python3 -c "import server_v3"
```

---

## 🔑 Notion 연동 필수 설정

아래 DB/페이지에 integration 연결 필요:

| DB | 용도 |
|----|------|
| 주별투두 DB | 마이크 주간 브리핑 |
| KPT 회고 DB | 토요일 회고 템플릿 |
| 칸반 페이지 | 장기/중기/단기 목표 |
| 공고 리스트 DB | 설리 공고 관리 |
| 수강생 현황 DB | 로즈 수업 관리 |

연결 방법: 노션 페이지 → `•••` → **연결** → integration 추가

---

## 📝 개발 기록

| 버전 | 내용 |
|------|------|
| v1.0 | 기본 Dock UI + 3 에이전트 채팅 |
| v1.1 | 크림색 UI 리디자인 + 캐릭터 원형 클립 |
| v1.2 | 마이크 브리핑 파서 개선 + 단기목표 노션 연동 |
| v1.3 | KPT/주간계획 자동 생성 + DB ID 안정화 |

---

## ⚠️ 주의사항

- `.env` 파일은 절대 GitHub에 올리지 않습니다
- API 키 노출 시 즉시 재발급 필요
- Notion integration 연결이 끊기면 브리핑 데이터 미표시

---

*Built with ❤️ by 임유빈 (Eva) — 공기업 취준생 겸 한국어 강사*    
