from __future__ import annotations

# ================================================================
# server_v3.py — 퀸에바의 에이전트 서버
# 기존 분석 기능 + Dock UI / 채팅 / TTS / 그룹채팅 API 추가
# ================================================================

import os, json, threading, datetime, uuid, requests
from typing import Optional
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, Response
from dotenv import load_dotenv

load_dotenv()

# 크롤러 모듈
try:
    from crawler import start_crawl_scheduler, get_crawl_result
    CRAWLER_AVAILABLE = True
except ImportError:
    CRAWLER_AVAILABLE = False
    def get_crawl_result(): return {"total": 0, "top": [], "crawled_at": None}
    def start_crawl_scheduler(): pass

# 노션 연동 모듈
try:
    from notion_sync import (
    get_agent_brief, check_notion_connection,
    sully_summary, sully_get_jobs,
    mike_daily_brief, mike_weekly_plan_draft,
    roz_daily_brief, roz_feedback_draft, roz_get_students,
    roz_get_recent_lesson, roz_get_lesson_summary, roz_generate_material_draft,
)   
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    def get_agent_brief(agent_id): return ""
    def check_notion_connection(): return {"connected": False, "error": "notion_sync.py 없음"}

# 기존 모듈 (agent.py 있을 때만 임포트)
try:
    from agent import PublicJobAgent, YubinProfile, BONUS_RULES, PENALTY_RULES
    from history import append_record, get_all, get_score_series
    AGENT_AVAILABLE = True
except Exception as e:
    print(f"[agent 임포트 오류] {e}")
    AGENT_AVAILABLE = False

app = Flask(__name__, static_folder="dashboard")

# ================================================================
# [1] 에이전트 페르소나 설정 (agents.json 로 영속화)
# ================================================================
AGENTS_FILE = Path(__file__).parent / "agents.json"

DEFAULT_AGENTS = [
    {
        "id":          "sully",
        "name":        "설리",
        "emoji":       "🟦",
        "role":        "공기업 채용 전략가",
        "model":       "gpt-4o",
        "provider":    "openai",
        "color":       "#1565C0",
        "accent":      "#42A5F5",
        "voice":       "echo",
        "dock_order":  0,
        "online":      True,
        "notify_interval": 3600,
        "system_prompt": (
            "너는 설리(Sully)야. 몬스터 주식회사의 설리반처럼 듬직하고 믿음직한 공기업 채용 전략가야. "
            "유빈(바에)의 스펙(토익 780, OPIc IH, 충북 지역인재, 국제개발협력 경력 2년, 온라인 서비스 기획 3년)을 기반으로 "
            "https://www.alio.go.kr/ 등 공기업, 공공기관 공고를 분석하고 합격 가능성을 스코어링해줘. "
            "항상 한국어로, 핵심만 짧고 명확하게 말해. 수치와 근거를 제시해."
        ),
        "notify_messages": [
            "유빈, 오늘 새 공고 {count}개 올라왔어. 확인해볼까?",
            "마감 임박 공고 {count}개 있어. 지금 봐야 해.",
            "이번 주 지원 가능한 공고 분석 완료했어.",
        ],
    },
    {
        "id":          "mike",
        "name":        "마이크",
        "emoji":       "🟢",
        "role":        "시스템 통합 & 스크럼 매니저",
        "model":       "gpt-4o",
        "provider":    "openai",
        "color":       "#2E7D32",
        "accent":      "#66BB6A",
        "voice":       "alloy",
        "dock_order":  1,
        "online":      True,
        "notify_interval": 28800,
        "system_prompt": (
            "너는 마이크(Mike)야. 몬스터 주식회사의 마이크처럼 꼼꼼하고 철저한 시스템 매니저야. "
            "유빈의 데일리 스크럼, 주간/월간 목표, 투두리스트를 관리해. "
            "오늘 할 일, 마감 일정, 우선순위를 명확하게 정리해줘. "
            "항상 한국어로, 리스트 형식으로 간결하게 말해."
            "설리가 찾아온 공고와 로즈가 만든 자료가 노션 DB의 제 위치에 정확히 기록되었는지 검증해."
            "주간/월간 단위로 유빈 님의 활동 데이터를 수집해. '이번 주는 실행률이 60%밖에 안 되는군. 다음 주는 분발하게나.'라며 팩트 폭격 리포트 생성해."
        ),
        "notify_messages": [
            "유빈, 오늘 할 일 {count}개 남았어. 시작할까?",
            "데일리 스크럼 시간이야. 어제 뭐 했어?",
            "주간 목표 점검할 시간이야.",
        ],
    },
    {
        "id":          "roz",
        "name":        "로즈",
        "emoji":       "🟣",
        "role":        "교육 운영 & 수강생 관리",
        "model":       "gpt-4o",
        "provider":    "openai",
        "color":       "#6A1B9A",
        "accent":      "#CE93D8",
        "voice":       "shimmer",
        "dock_order":  2,
        "online":      True,
        "notify_interval": 14400,
        "system_prompt": (
            "너는 로즈(Roz)야. 몬스터 주식회사의 로즈처럼 철저하고 기록을 중시하는 교육 운영 매니저야. "
            "유빈의 한국어 말하기 수강생 관리, 교육 자료 제작, 매일 수업의 피드백을 분석해서 콘텐츠 제작 초안 작성을 담당해. "
            "항상 한국어로, 교육자 입장에서 실용적으로 말해."
            "노션 수강생 DB, 수업피드백자료 DB 에서 '수강생별 니즈'를 파악해서 단시간내에 수업 자료 및 과제 텍스트 초안 생성해."
        ),
        "notify_messages": [
            "유빈, 오늘 수업 {count}명 예정이야. 자료 준비됐어?",
            "수강생 피드백 작성할 시간이야.",
            "이번 주 교육 자료 업데이트 필요해.",
        ],
    },
]

def _load_agents() -> list:
    if AGENTS_FILE.exists():
        return json.loads(AGENTS_FILE.read_text(encoding="utf-8"))
    _save_agents(DEFAULT_AGENTS)
    return DEFAULT_AGENTS

def _save_agents(agents: list):
    AGENTS_FILE.write_text(json.dumps(agents, ensure_ascii=False, indent=2))

# ================================================================
# [2] 채팅 히스토리 (chat_history.json)
# ================================================================
CHAT_FILE = Path(__file__).parent / "chat_history.json"

def _load_chats() -> dict:
    if CHAT_FILE.exists():
        return json.loads(CHAT_FILE.read_text(encoding="utf-8"))
    return {}

def _save_chats(chats: dict):
    for k in chats:
        chats[k] = chats[k][-200:]
    CHAT_FILE.write_text(json.dumps(chats, ensure_ascii=False, indent=2))

# ================================================================
# [3] AI 응답 생성 — OpenAI Only (텍스트 폴백용)
# ================================================================
def _call_llm(agent: dict, messages: list) -> str:
    from openai import OpenAI
    client    = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    model     = agent.get("model", "gpt-4o")
    sys_p     = agent.get("system_prompt", "")
    full_msgs = [{"role": "system", "content": sys_p}] + messages
    resp = client.chat.completions.create(model=model, messages=full_msgs, max_tokens=1024)
    return resp.choices[0].message.content

# ================================================================
# [5] 분석 에이전트 상태 (기존 코드 연결)
# ================================================================
STATE_FILE = Path(__file__).parent / "daily_result.json"
_state = {
    "status": "idle", "last_run": None, "score": None, "grade": None,
    "verdict": None, "bonuses": [], "penalties": [], "todos": [],
    "spec_progress": [], "message": "", "log": [],
}

import random
NANO_MSG = {
    "S": ["🍌 이건 무조건 넣어야 해!"], "A": ["🍌 이번 주 안에 지원하자!"],
    "B": ["🍌 스펙 보완 병행하자~"],     "C": ["🍌 리스크 먼저 확인해!"],
    "D": ["🍌 스펙 먼저 올리자!"],       "idle": ["🍌 분석 버튼 눌러봐~"],
    "running": ["🍌 분석 중이야~"],      "error": ["🍌 오류났어. 로그 확인!"],
}
def _pick(g): return random.choice(NANO_MSG.get(g, NANO_MSG["idle"]))
def _save_state(): STATE_FILE.write_text(json.dumps(_state, ensure_ascii=False, indent=2))
def _load_state():
    if STATE_FILE.exists(): _state.update(json.loads(STATE_FILE.read_text()))

def _run_agent_thread(company: str, pdf_path: Optional[str] = None):
    if not AGENT_AVAILABLE:
        _state["status"] = "error"
        _state["log"]    = ["[ERROR] agent.py 를 찾을 수 없습니다."]
        return
    _state.update({"status": "running", "log": [], "message": _pick("running")})
    def log(m): _state["log"].append(m); print(m)
    try:
        ts = lambda: datetime.datetime.now().strftime("%H:%M:%S")
        profile = YubinProfile(name="임유빈", birth_year=1995, toeic=780, opic="IH",
                               preferred_region="충북", home_region="충북")
        agent = PublicJobAgent(target_company=company, profile=profile,
                               pdf_path=pdf_path, max_iterations=3)
        agent.run_scoring()
        sr = agent.score_result
        _state.update({
            "score":     sr.total_score,
            "grade":     sr.grade,
            "verdict":   sr.verdict,
            "bonuses":   [{"label": l, "score": s} for l, s in sr.matched_bonuses],
            "penalties": [{"label": l, "score": s, "msg": m} for l, s, m in sr.matched_penalties],
            "message":   _pick(sr.grade),
        })
        agent.add_task("응시 자격 요건 및 결격 사유 1차 검토")
        agent.run()
        _state["todos"] = [{"text": t, "done": False} for t in agent.completed_tasks]
        penalty_count = len([p for p in _state["penalties"] if p["score"] < 0])
        _state["spec_progress"] = [
            {"label": "가점 항목 충족", "pct": min(100, len(_state["bonuses"]) * 25)},
            {"label": "감점 항목 해소", "pct": max(0, 100 - penalty_count * 25)},
            {"label": "전체 준비도",    "pct": max(0, min(100, sr.total_score))},
        ]
        _state["last_run"] = datetime.date.today().isoformat()
        _state["status"]   = "done"
        log(f"[{ts()}] ✅ 완료")
        append_record(
            target_company=company, score=_state["score"], grade=_state["grade"],
            verdict=_state["verdict"], bonuses=_state["bonuses"], penalties=_state["penalties"],
            todos=_state["todos"], spec_progress=_state["spec_progress"], gang_pro_log=_state["log"]
        )
        log(f"[{ts()}] 📝 로컬 기록 저장 완료")
    except Exception as e:
        _state["status"]  = "error"
        _state["message"] = _pick("error")
        log(f"[ERROR] {e}")
    _save_state()

# ================================================================
# API — 에이전트 관리
# ================================================================
@app.route("/api/agents", methods=["GET"])
def api_agents_get():
    return jsonify(sorted(_load_agents(), key=lambda a: a.get("dock_order", 99)))

@app.route("/api/agents", methods=["POST"])
def api_agents_save():
    agents = request.get_json()
    _save_agents(agents)
    return jsonify({"ok": True})

@app.route("/api/agents/<agent_id>", methods=["PATCH"])
def api_agent_patch(agent_id):
    agents = _load_agents()
    patch  = request.get_json() or {}
    for a in agents:
        if a["id"] == agent_id:
            a.update(patch)
            break
    _save_agents(agents)
    return jsonify({"ok": True})

# ================================================================
# API — 채팅
# ================================================================
@app.route("/api/chat/group/history", methods=["GET"])
def api_group_history():
    chats = _load_chats()
    return jsonify(chats.get("group", []))

@app.route("/api/chat/<agent_id>", methods=["GET"])
def api_chat_get(agent_id):
    chats = _load_chats()
    return jsonify(chats.get(agent_id, []))

@app.route("/api/chat/<agent_id>", methods=["POST"])
def api_chat_post(agent_id):
    agents_map = {a["id"]: a for a in _load_agents()}
    agent      = agents_map.get(agent_id)
    if not agent:
        return jsonify({"error": "에이전트를 찾을 수 없습니다"}), 404

    body     = request.get_json() or {}
    user_msg = body.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "메시지가 비어있습니다"}), 400

    chats   = _load_chats()
    history = chats.get(agent_id, [])

    # 노션 컨텍스트 주입 — 에이전트별 최신 데이터를 시스템 프롬프트에 추가
    notion_context = ""
    if NOTION_AVAILABLE:
        try:
            notion_context = get_agent_brief(agent_id)
            # 로즈: 수강생 이름 감지 시 수업 내용 추가 주입
            if agent_id == "roz":
                from notion_sync import roz_get_lesson_summary, roz_generate_material_draft
                for name in ["도미닉", "eve", "이브", "소담", "레나"]:
                    if name.lower() in user_msg.lower():
                        if "교재" in user_msg or "자료" in user_msg:
                            notion_context += "\n\n" + roz_generate_material_draft(name)
                        else:
                            notion_context += "\n\n" + roz_get_lesson_summary(name)
                        break
        except:
            pass

    # 시스템 프롬프트 + 노션 컨텍스트 합성
    sys_prompt = agent.get("system_prompt", "")
    if notion_context:
        sys_prompt += f"\n\n[현재 노션 데이터 요약]\n{notion_context}"

    llm_msgs = [{"role": m["role"], "content": m["content"]} for m in history[-20:]]
    llm_msgs.append({"role": "user", "content": user_msg})

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY",""))
        resp   = client.chat.completions.create(
            model    = agent.get("model","gpt-4o"),
            messages = [{"role":"system","content":sys_prompt}] + llm_msgs,
            max_tokens = 1024,
        )
        reply = resp.choices[0].message.content
    except Exception as e:
        reply = f"[오류] {e}"

    ts = datetime.datetime.now().isoformat()
    history.append({"id": str(uuid.uuid4()), "role": "user",
                    "content": user_msg, "ts": ts})
    history.append({"id": str(uuid.uuid4()), "role": "assistant",
                    "content": reply, "agent_id": agent_id, "ts": ts})
    chats[agent_id] = history
    _save_chats(chats)
    return jsonify({"reply": reply, "agent": agent["name"]})

# ================================================================
# API — 노션 연동
# ================================================================
@app.route("/api/notion/status", methods=["GET"])
def api_notion_status():
    return jsonify(check_notion_connection())

@app.route("/api/notion/brief/<agent_id>", methods=["GET"])
def api_notion_brief(agent_id):
    """에이전트 클릭 시 노션 기반 브리핑 즉시 반환"""
    if not NOTION_AVAILABLE:
        return jsonify({"brief": "", "error": "notion_sync.py 없음"})
    try:
        brief = get_agent_brief(agent_id)
        return jsonify({"brief": brief, "agent_id": agent_id})
    except Exception as e:
        return jsonify({"brief": "", "error": str(e)}), 500

@app.route("/api/notion/jobs", methods=["GET"])
def api_notion_jobs():
    if not NOTION_AVAILABLE:
        return jsonify([])
    try:
        return jsonify(sully_get_jobs(30))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notion/students", methods=["GET"])
def api_notion_students():
    if not NOTION_AVAILABLE:
        return jsonify([])
    try:
        return jsonify(roz_get_students())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ================================================================
# API — 그룹 채팅
# ================================================================
@app.route("/api/chat/group", methods=["POST"])
def api_group_chat():
    body      = request.get_json() or {}
    user_msg  = body.get("message", "").strip()
    agent_ids = body.get("agents", [])

    if not user_msg:
        return jsonify({"error": "메시지가 비어있습니다"}), 400

    agents_map  = {a["id"]: a for a in _load_agents()}
    chats       = _load_chats()
    group_hist  = chats.get("group", [])
    ts          = datetime.datetime.now().isoformat()

    group_hist.append({"id": str(uuid.uuid4()), "role": "user",
                       "content": user_msg, "ts": ts})

    responses    = []
    prev_replies = ""

    for aid in agent_ids:
        agent = agents_map.get(aid)
        if not agent:
            continue

        context_msg = user_msg
        if prev_replies:
            context_msg = (
                f"[그룹 토론 중] 유저 질문: {user_msg}\n"
                f"앞선 팀원 답변:\n{prev_replies}\n"
                f"이제 {agent['name']}로서 추가 의견이나 다른 관점을 짧게 말해."
            )

        try:
            reply = _call_llm(agent, [{"role": "user", "content": context_msg}])
        except Exception as e:
            reply = f"[{agent['name']} 오류] {e}"

        prev_replies += f"\n{agent['name']}: {reply}"
        responses.append({"agent_id": aid, "agent_name": agent["name"],
                          "emoji": agent["emoji"], "reply": reply})
        group_hist.append({"id": str(uuid.uuid4()), "role": "assistant",
                           "content": reply, "agent_id": aid,
                           "agent_name": agent["name"], "ts": ts})

    chats["group"] = group_hist
    _save_chats(chats)
    return jsonify({"responses": responses})

# ================================================================
# API — OpenAI Realtime ephemeral token 발급
# ================================================================
@app.route("/api/realtime/token", methods=["POST"])
def api_realtime_token():
    body     = request.get_json() or {}
    agent_id = body.get("agent_id", "Mike")
    agents   = {a["id"]: a for a in _load_agents()}
    agent    = agents.get(agent_id, {})

    resp = requests.post(
        "https://api.openai.com/v1/realtime/sessions",
        headers={
            "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}",
            "Content-Type":  "application/json",
        },
        json={
            "model":        "gpt-4o-realtime-preview-2024-12-17",
            "voice":        agent.get("voice", "alloy"),
            "instructions": agent.get("system_prompt", "친근하게 짧게 대답해."),
            "modalities":   ["audio", "text"],
            "turn_detection": {
                "type":                "server_vad",
                "threshold":           0.5,
                "silence_duration_ms": 600,
            },
            "input_audio_transcription": {"model": "whisper-1"},
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return jsonify({"error": resp.text}), resp.status_code
    return jsonify(resp.json())

# ================================================================
# API — 이미지 생성 (DALL-E 3)
# ================================================================
@app.route("/api/image/generate", methods=["POST"])
def api_image_generate():
    """
    body: { "prompt": "...", "size": "1024x1024", "quality": "standard" }
    returns: { "url": "https://..." }
    """
    body    = request.get_json() or {}
    prompt  = body.get("prompt", "")
    size    = body.get("size", "1024x1024")     # 1024x1024 / 1792x1024 / 1024x1792
    quality = body.get("quality", "standard")   # standard / hd

    if not prompt:
        return jsonify({"error": "prompt 필요"}), 400

    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    try:
        resp = client.images.generate(
            model   = "dall-e-3",
            prompt  = prompt,
            size    = size,
            quality = quality,
            n       = 1,
        )
        return jsonify({
            "url":            resp.data[0].url,
            "revised_prompt": resp.data[0].revised_prompt,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ================================================================
# API — 분석 에이전트 (기존 기능)
# ================================================================
@app.route("/api/state")
def api_state(): return jsonify(_state)

@app.route("/api/run", methods=["POST"])
def api_run():
    body = request.get_json(silent=True) or {}
    if _state["status"] == "running":
        return jsonify({"ok": False}), 409
    threading.Thread(
        target=_run_agent_thread,
        args=(body.get("company") or body.get("org", "KOICA"), body.get("pdf_path")),
        daemon=True
    ).start()
    return jsonify({"ok": True})

@app.route("/api/todos/toggle/<int:idx>", methods=["POST"])
def api_toggle_todo(idx):
    if 0 <= idx < len(_state["todos"]):
        _state["todos"][idx]["done"] = not _state["todos"][idx]["done"]
        _save_state()
    return jsonify(_state["todos"])

@app.route("/api/history")
def api_history():
    return jsonify(get_all() if AGENT_AVAILABLE else [])

@app.route("/api/history/chart")
def api_history_chart():
    return jsonify(get_score_series() if AGENT_AVAILABLE else [])

# ================================================================
# API — 크롤링 결과
# ================================================================
@app.route("/api/crawl/result", methods=["GET"])
def api_crawl_result():
    return jsonify(get_crawl_result())

@app.route("/api/crawl/run", methods=["POST"])
def api_crawl_run():
    """수동 크롤링 즉시 실행"""
    if not CRAWLER_AVAILABLE:
        return jsonify({"error": "crawler.py 없음"}), 500
    def _run():
        from crawler import AlioCrawler
        AlioCrawler().run()
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": "크롤링 시작됨"})

# ================================================================
# API — 에이전트 알림 (notify)
# ================================================================
_notify_queue: list = []   # 브라우저가 폴링해서 가져가는 알림 큐

def push_notify(agent_id: str, message: str):
    _notify_queue.append({
        "id":         str(uuid.uuid4()),
        "agent_id":   agent_id,
        "message":    message,
        "ts":         datetime.datetime.now().isoformat(),
        "read":       False,
    })
    # 최대 20개 유지
    if len(_notify_queue) > 20:
        _notify_queue.pop(0)

@app.route("/api/notify", methods=["GET"])
def api_notify_get():
    """브라우저가 5초마다 폴링"""
    unread = [n for n in _notify_queue if not n["read"]]
    return jsonify(unread)

@app.route("/api/notify/read/<nid>", methods=["POST"])
def api_notify_read(nid: str):
    for n in _notify_queue:
        if n["id"] == nid:
            n["read"] = True
    return jsonify({"ok": True})

@app.route("/api/notify/read_all", methods=["POST"])
def api_notify_read_all():
    for n in _notify_queue:
        n["read"] = True
    return jsonify({"ok": True})

def _notify_scheduler():
    """에이전트가 주기적으로 알림 생성"""
    import time
    agents_map = {}
    time.sleep(10)  # 서버 완전 기동 후 시작

    while True:
        try:
            agents   = _load_agents()
            crawl    = get_crawl_result()
            now      = datetime.datetime.now()
            todos    = _state.get("todos", [])
            undone   = len([t for t in todos if not t.get("done", False)])

            for agent in agents:
                msgs    = agent.get("notify_messages", [])
                interval = agent.get("notify_interval", 3600)
                aid      = agent["id"]
                last_key = f"{aid}_last_notify"

                last_ts  = agents_map.get(last_key, 0)
                if time.time() - last_ts < interval:
                    continue

                # 에이전트별 알림 생성
                if aid == "sully" and msgs:
                    count = crawl.get("total", 0)
                    if count > 0:
                        msg = msgs[0].format(count=count)
                        push_notify(aid, msg)
                        agents_map[last_key] = time.time()

                elif aid == "mike" and msgs:
                    msg = msgs[0].format(count=undone)
                    push_notify(aid, msg)
                    agents_map[last_key] = time.time()

                elif aid == "roz" and msgs:
                    msg = msgs[0].format(count=1)
                    push_notify(aid, msg)
                    agents_map[last_key] = time.time()

        except Exception as e:
            print(f"[notify 스케줄러 오류] {e}")

        time.sleep(60)

# ================================================================
# 정적 파일
# ================================================================
@app.route("/")
def index(): return send_from_directory("dashboard", "index.html")

@app.route("/voice")
def voice_page(): return send_from_directory("dashboard", "voice.html")

@app.route("/static/<path:path>")
def static_assets(path): return send_from_directory("dashboard/static", path)

@app.route("/<path:path>")
def static_files(path): return send_from_directory("dashboard", path)

# ================================================================
# API — 스크럼 & 목표 관리
# ================================================================
GOALS_FILE = Path(__file__).parent / "goals.json"
SCRUM_FILE = Path(__file__).parent / "scrum_log.json"

def _load_goals() -> dict:
    if GOALS_FILE.exists():
        return json.loads(GOALS_FILE.read_text(encoding="utf-8"))
    return {"monthly": [], "weekly": [], "daily_template": []}

def _save_goals(data: dict):
    GOALS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def _load_scrum_log() -> list:
    if SCRUM_FILE.exists():
        return json.loads(SCRUM_FILE.read_text(encoding="utf-8"))
    return []

def _save_scrum_log(log: list):
    SCRUM_FILE.write_text(json.dumps(log[-90:], ensure_ascii=False, indent=2))

@app.route("/api/goals", methods=["GET"])
def api_goals_get():
    return jsonify(_load_goals())

@app.route("/api/goals", methods=["POST"])
def api_goals_save():
    data = request.get_json() or {}
    _save_goals(data)
    return jsonify({"ok": True})

@app.route("/api/scrum/log", methods=["GET"])
def api_scrum_log_get():
    return jsonify(_load_scrum_log())

@app.route("/api/scrum/complete", methods=["POST"])
def api_scrum_complete():
    body   = request.get_json() or {}
    today  = datetime.date.today().isoformat()
    log    = _load_scrum_log()
    record = {
        "date":         today,
        "yesterday":    body.get("yesterday", []),
        "today":        body.get("today", []),
        "score":        _state.get("score"),
        "grade":        _state.get("grade"),
        "spec_avg":     body.get("spec_avg", 0),
        "mood":         body.get("mood", "😊"),
        "completed_at": datetime.datetime.now().isoformat(),
    }
    log = [r for r in log if r.get("date") != today]
    log.append(record)
    _save_scrum_log(log)
    return jsonify({"ok": True})

@app.route("/api/scrum/today", methods=["GET"])
def api_scrum_today():
    today = datetime.date.today().isoformat()
    log   = _load_scrum_log()
    done  = next((r for r in log if r.get("date") == today), None)
    return jsonify({"done": done is not None, "record": done})

@app.route("/scrum")
def scrum_page():
    return send_from_directory("dashboard", "scrum.html")

# ================================================================
# 시작
# ================================================================
def _auto_run_if_needed():
    today = datetime.date.today().isoformat()
    if AGENT_AVAILABLE and _state.get("last_run") != today:
        threading.Thread(
            target=_run_agent_thread, args=("KOICA(한국국제협력단)",), daemon=True
        ).start()

if __name__ == "__main__":
    _load_state()
    Path("dashboard").mkdir(exist_ok=True)
    _auto_run_if_needed()
    # 크롤러 스케줄러 시작
    start_crawl_scheduler()
    # 알림 스케줄러 시작
    threading.Thread(target=_notify_scheduler, daemon=True).start()
    print("🍌 나노바나나 v3 시작! → http://localhost:5050")
    app.run(host="127.0.0.1", port=5050, debug=False)