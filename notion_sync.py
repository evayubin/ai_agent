from __future__ import annotations

# ================================================================
# notion_sync.py — EVA 에이전트 팀 노션 연동
# notion-client 대신 requests 직접 사용 (버전 호환성 문제 해결)
# ================================================================

import os, requests
from dotenv import load_dotenv
load_dotenv()
from dotenv import load_dotenv
load_dotenv()
from datetime import date, datetime
from typing import Optional

NOTION_VERSION = "2022-06-28"
BASE_URL       = "https://api.notion.com/v1"

def _headers() -> dict:
    key = os.environ.get("NOTION_API_KEY", "")
    return {
        "Authorization":  f"Bearer {key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type":   "application/json",
    }

def _db(name: str) -> str:
    return os.environ.get(name, "")

# ================================================================
# 공통 유틸
# ================================================================
def _query_db(db_id: str, sorts: list = None) -> list:
    if not db_id:
        return []
    try:
        body = {}
        if sorts: body["sorts"] = sorts
        resp = requests.post(
            f"{BASE_URL}/databases/{db_id}/query",
            headers=_headers(),
            json=body,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("results", [])
        print(f"[노션 쿼리 오류] {resp.status_code}: {resp.text[:200]}")
        return []
    except Exception as e:
        print(f"[노션 쿼리 예외] {e}")
        return []

def _retrieve_db(db_id: str) -> dict:
    if not db_id:
        return {}
    try:
        resp = requests.get(
            f"{BASE_URL}/databases/{db_id}",
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return {}
    except:
        return {}

def _get_prop(page: dict, key: str):
    try:
        prop = page["properties"].get(key, {})
        t    = prop.get("type", "")
        if t == "title":
            return "".join(r["plain_text"] for r in prop.get("title", []))
        if t == "rich_text":
            return "".join(r["plain_text"] for r in prop.get("rich_text", []))
        if t == "number":
            return prop.get("number")
        if t == "select":
            s = prop.get("select")
            return s["name"] if s else ""
        if t == "multi_select":
            return ", ".join(o["name"] for o in prop.get("multi_select", []))
        if t == "date":
            d = prop.get("date")
            return d["start"] if d else ""
        if t == "checkbox":
            return prop.get("checkbox", False)
        if t == "url":
            return prop.get("url", "")
        if t == "formula":
            f = prop.get("formula", {})
            return f.get("number") or f.get("string") or ""
        if t == "rollup":
            r = prop.get("rollup", {})
            return r.get("number") or ""
        if t == "files":
            files = prop.get("files", [])
            if files:
                f = files[0]
                return (f.get("external") or {}).get("url","") or (f.get("file") or {}).get("url","")
        return ""
    except:
        return ""

# ================================================================
# 설리 (Sully) — 공기업 공고 리스트
# 컬럼: 기업명(title), 채용 상태, 공고 마감일,
#       서류합격발표일, 분석 결과, 필수 자격증, 목표 토익점수
# ================================================================
def sully_get_jobs(limit: int = 20) -> list[dict]:
    rows = _query_db(
        _db("NOTION_JOB_DB_ID"),
        sorts=[{"timestamp": "created_time", "direction": "descending"}]
    )
    jobs = []
    for r in rows[:limit]:
        jobs.append({
            "id":       r["id"],
            "title":    _get_prop(r, "기업명") or "기업명 없음",
            "status":   _get_prop(r, "채용 상태") or "",
            "deadline": _get_prop(r, "공고 마감일") or "",
            "analysis": _get_prop(r, "분석 결과") or "",
            "cert":     _get_prop(r, "필수 자격증") or "",
            "toeic":    _get_prop(r, "목표 토익점수") or "",
        })
    return jobs

def sully_summary() -> str:
    jobs  = sully_get_jobs(50)
    today = date.today()

    if not jobs:
        return "📋 공고 DB가 비어있어. 노션에서 공고 추가해줘."

    active   = [j for j in jobs if j.get("status") not in ["마감","지원완료","불합격"]]
    applying = [j for j in jobs if j.get("status") == "지원 전"]
    in_prog  = [j for j in jobs if j.get("status") not in ["마감","지원완료","불합격","지원 전",""]]

    soon = []
    for j in active:
        dl = j.get("deadline","")
        if dl:
            try:
                d = datetime.strptime(dl[:10], "%Y-%m-%d").date()
                if 0 <= (d - today).days <= 7:
                    soon.append(j)
            except:
                pass

    lines = [f"📋 공고 현황 ({today.strftime('%m/%d')})"]
    lines.append(f"• 전체 {len(jobs)}개 | 진행 중 {len(active)}개")

    if soon:
        lines.append(f"\n⚠️ 7일 내 마감:")
        for j in soon:
            lines.append(f"  → {j['title']} ~{j['deadline'][:10]}")

    if in_prog:
        lines.append(f"\n🔄 전형 진행 중:")
        for j in in_prog[:3]:
            lines.append(f"  → {j['title']} ({j['status']})")

    if applying:
        lines.append(f"\n📌 지원 예정 {len(applying)}개:")
        for j in applying[:3]:
            lines.append(f"  → {j['title']}")

    return "\n".join(lines)

# ================================================================
# 마이크 (Mike)
# - 주별투두 DB: 320b87ee-1038-8018-a0cc-e4f7eb5d59d7
# - KPT 회고 DB: 2a0b87ee-1038-81ec-835c-c57d683e0ab6
# - 칸반보드 페이지: 2a0b87ee-1038-80b8-977e-e3db6d43551a
# ================================================================

WEEKLY_TODO_DB = "320b87ee-1038-8018-a0cc-e4f7eb5d59d7"
KPT_DB         = "2a0b87ee-1038-81ec-835c-c57d683e0ab6"
KANBAN_PAGE    = "2a0b87ee-1038-80b8-977e-e3db6d43551a"


def _get_blocks(page_id: str) -> list:
    try:
        resp = requests.get(
            f"{BASE_URL}/blocks/{page_id}/children",
            headers=_headers(), timeout=15
        )
        if resp.status_code == 200:
            return resp.json().get("results", [])
    except:
        pass
    return []


def _block_text(block: dict) -> str:
    t  = block.get("type", "")
    rt = block.get(t, {}).get("rich_text", [])
    return "".join(r.get("plain_text", "") for r in rt)


def _h3(text):
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def _todo(text):
    return {"object": "block", "type": "to_do",
            "to_do": {"rich_text": [{"type": "text", "text": {"content": text}}], "checked": False}}


def _bullet(text):
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def _divider():
    return {"object": "block", "type": "divider", "divider": {}}


# 요일 매핑 (노션 heading 텍스트 → weekday 인덱스)
DAY_MAP = {
    "mon":  0, "monday":    0,
    "tues": 1, "tuesday":   1, "tue": 1,
    "wed":  2, "wednesday": 2,
    "thur": 3, "thursday":  3, "thu": 3,
    "fri":  4, "friday":    4,
    "sat":  5, "saturday":  5,
    "sun":  6, "sunday":    6,
}

def mike_get_current_week() -> dict:
    rows = _query_db(WEEKLY_TODO_DB, sorts=[{"timestamp": "last_edited_time", "direction": "descending"}])
    if not rows:
        return {}
    row     = rows[0]
    title   = _get_prop(row, "이름") or _get_prop(row, "Name") or ""
    page_id = row["id"]

    blocks  = _get_blocks(page_id)
    focus   = ""
    section = ""
    # day_schedule: { weekday_int: [{"text":..,"done":..}] }
    day_schedule = {i: [] for i in range(7)}
    routines = []
    current_day = None

    for b in blocks:
        t    = b.get("type", "")
        text = _block_text(b)

        if t in ["heading_1", "heading_2", "heading_3"]:
            section = text
            # 요일 감지
            key = text.strip().lower().rstrip(".")
            if key in DAY_MAP:
                current_day = DAY_MAP[key]
            elif "루틴" in text:
                current_day = None
            elif "초점" in text:
                current_day = None

        elif t == "to_do":
            checked = b.get("to_do", {}).get("checked", False)
            item    = {"text": text, "done": checked}
            if "루틴" in section:
                routines.append(item)
            elif current_day is not None:
                day_schedule[current_day].append(item)

        elif t == "bulleted_list_item" and "초점" in section and text:
            focus = text

        elif t == "column_list":
            # column_list 안의 column들 재귀 처리
            col_blocks = _get_blocks(b["id"])
            for col in col_blocks:
                if col.get("type") != "column":
                    continue
                col_items  = _get_blocks(col["id"])
                col_day    = None
                for cb in col_items:
                    ct   = cb.get("type", "")
                    ctxt = _block_text(cb)
                    if ct in ["heading_1","heading_2","heading_3"]:
                        key = ctxt.strip().lower().rstrip(".")
                        if key in DAY_MAP:
                            col_day = DAY_MAP[key]
                    elif ct == "to_do" and col_day is not None:
                        checked = cb.get("to_do", {}).get("checked", False)
                        day_schedule[col_day].append({"text": ctxt, "done": checked})

    return {"page_id": page_id, "title": title,
            "day_schedule": day_schedule, "routines": routines, "focus": focus}


def mike_get_kanban_goals() -> str:
    """칸반 페이지에서 장기/중기/단기 목표 전체 파싱"""
    try:
        result = []

        # 1) 첫 번째 column_list 안의 왼쪽 column 읽기
        col_list_id = "2a0b87ee-1038-8144-82f3-d88a30bc9b62"
        r = requests.get(f"{BASE_URL}/blocks/{col_list_id}/children",
                         headers=_headers(), timeout=10)
        cols = r.json().get("results", [])
        if not cols:
            return "목표 데이터 없음"

        left_col_id = cols[0]["id"]
        r2 = requests.get(f"{BASE_URL}/blocks/{left_col_id}/children",
                          headers=_headers(), timeout=10)
        blocks = r2.json().get("results", [])

        section = ""
        for b in blocks:
            t    = b.get("type", "")
            text = _block_text(b)

            # 섹션 헤더
            if t == "heading_1":
                section = text
                result.append(f"\n## {text}")

            # 장기 목표 — paragraph
            elif t == "paragraph" and "장기" in section and text.strip():
                result.append(f"• {text.strip()}")

            # 중기 목표 — callout (toggle 자식 포함)
            elif t == "callout" and "중기" in section:
                callout_text = "".join(
                    x["plain_text"]
                    for x in b.get("callout", {}).get("rich_text", [])
                )
                result.append(f"📅 {callout_text}")
                # toggle 자식들
                r3 = requests.get(f"{BASE_URL}/blocks/{b['id']}/children",
                                  headers=_headers(), timeout=10)
                children = r3.json().get("results", [])
                for child in children:
                    ct   = child.get("type", "")
                    ctxt = _block_text(child)
                    if ctxt.strip():
                        result.append(f"  {ctxt.strip()}")

            # 단기 목표 — callout children (to_do 포함)
            elif t == "callout" and "단기" in section:
                callout_text = "".join(
                    x["plain_text"]
                    for x in b.get("callout", {}).get("rich_text", [])
                )
                result.append(f"\n🎯 {callout_text}")
                r3 = requests.get(f"{BASE_URL}/blocks/{b['id']}/children",
                                  headers=_headers(), timeout=10)
                children = r3.json().get("results", [])
                for child in children:
                    ct      = child.get("type", "")
                    ctxt    = _block_text(child)
                    checked = child.get(ct, {}).get("checked", False)
                    if ct == "to_do" and ctxt.strip():
                        icon = "✅" if checked else "⬜"
                        result.append(f"  {icon} {ctxt.strip()}")
                    elif ct == "paragraph" and ctxt.strip():
                        result.append(f"  📌 {ctxt.strip()}")

        return "\n".join(result) if result else "목표 데이터 없음"

    except Exception as e:
        print(f"[마이크] 칸반 목표 읽기 실패: {e}")
        return "목표 읽기 실패"

DAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
DAY_EN = ["Mon", "Tues", "Wed", "Thur", "Fri", "Sat", "Sun"]

def mike_daily_brief() -> str:
    today   = date.today()
    weekday = today.weekday()  # 0=월 ~ 6=일

    if weekday == 5:
        return mike_kpt_create()
    if weekday == 6:
        return mike_weekly_plan_draft()

    week         = mike_get_current_week()
    day_schedule = week.get("day_schedule", {})
    focus        = week.get("focus", "")
    title        = week.get("title", "이번 주")

    today_todos  = day_schedule.get(weekday, [])
    done_today   = [t for t in today_todos if t["done"]]
    undone_today = [t for t in today_todos if not t["done"]]

    lines = ["📅 " + today.strftime("%m/%d") + "(" + DAY_KO[weekday] + ") 마이크 브리핑 — " + title]

    if focus:
        lines.append("\n🎯 이번 주 핵심 초점: " + focus)

    # 오늘 요일 할 일
    lines.append("\n📌 오늘(" + DAY_EN[weekday] + ") 할 일: " + str(len(done_today)) + "/" + str(len(today_todos)) + "개 완료")
    if today_todos:
        for t in today_todos:
            if t["text"].strip():  # 빈 항목 제외
                icon = "✅" if t["done"] else "⬜"
                lines.append("  " + icon + " " + t["text"])    
    else:
        lines.append("  오늘 배치된 할 일 없음")

    # 이번 주 전체 누적 현  황 (월~오늘)
    lines.append("\n📊 이번 주 누적 체크 현황:")
    week_done = week_total = 0
    for d in range(weekday + 1):
        day_todos = day_schedule.get(d, [])
        if not day_todos:
            continue
        d_done  = sum(1 for t in day_todos if t["done"])
        d_total = len(day_todos)
        week_done  += d_done
        week_total += d_total
        bar = "█" * d_done + "░" * (d_total - d_done)
        lines.append("  " + DAY_KO[d] + "요일 " + bar + " " + str(d_done) + "/" + str(d_total))

    if week_total > 0:
        pct = round(week_done / week_total * 100)
        lines.append("  → 누적 달성률: " + str(pct) + "% (" + str(week_done) + "/" + str(week_total) + "개)")

    # 단기 목표 — 노션 칸반에서 실시간 읽기
    try:
        goals = mike_get_kanban_goals()
        short_term_lines = []
        in_short = False
        for line in goals.split("\n"):
            if "단기" in line:
                in_short = True
                short_term_lines.append("\n📋 단기 목표 체크리스트:")
            elif in_short and line.startswith("##"):
                break
            elif in_short and line.strip():
                short_term_lines.append(line)
        if short_term_lines:
            lines.extend(short_term_lines)
    except Exception as e:
        print("[마이크] 단기 목표 읽기 실패: " + str(e))

    return "\n".join(lines)

def _kpt_template_blocks() -> list:
    return [
        _h3("이번 주 요약"),
        _todo("이번 주에 가장 기억에 남는 사건 1~3가지"),
        _todo("이번 주에 잘한 일(성과) 1~3가지"),
        _todo("이번 주에 아쉬웠던 일(실패/막힘) 1~3가지"),
        _divider(),
        _h3("주간 KPT 회고"),
        _h3("K (Keep)"),
        _todo(""), _todo(""), _todo(""),
        _h3("P (Problem)"),
        _todo(""), _todo(""), _todo(""),
        _h3("T (Try)"),
        _todo(""), _todo(""), _todo(""),
        _divider(),
        _h3("다음 주 핵심 초점 (1~2개)"),
        _bullet(""),
        _divider(),
        _h3("채우기 질문"),
        _bullet("이번 주에 시간/에너지를 가장 많이 쓴 일은?"),
        _bullet("가장 뿌듯했던 순간은?"),
        _bullet("막혔던 지점이 있다면, 원인은?"),
        _bullet("다음 주에 꼭 유지하고 싶은 루틴은?"),
        _bullet("다음 주에 반드시 바꾸고 싶은 한 가지는?"),
    ]


def mike_weekly_plan_draft() -> str:
    today    = date.today()
    week_num = today.isocalendar()[1] + 1
    title    = f"{today.year}년 {today.month}월 {week_num}주차"

    # KPT Try 항목 읽어서 Top3에 반영
    try_items = mike_get_latest_kpt_try()

    props = {"이름": {"title": [{"text": {"content": title}}]}}
    try:
        resp = requests.post(
            f"{BASE_URL}/pages",
            headers=_headers(),
            json={
                "parent": {"database_id": WEEKLY_TODO_DB},
                "properties": props,
                "children": _weekly_template_blocks(try_items),
            },
            timeout=15,
        )
        if resp.status_code in [200, 201]:
            print(f"[마이크] 새 주차 페이지 생성 ✅ {title}")
            kpt_msg = f"\n지난 주 KPT Try 항목 {len(try_items)}개를 Top3에 반영했어!" if try_items else ""
            return "\n".join([
                f"📋 {title} 주간 계획 생성 완료!{kpt_msg}",
                "",
                "노션에 새 주차 페이지 만들었어.",
                "요일별 투두 추가하거나 수정할 내용 말해줘!",
            ])
        else:
            print(f"[마이크] 주차 생성 실패: {resp.text[:200]}")
            return f"⚠️ 주차 페이지 생성 실패: {resp.text[:100]}"
    except Exception as e:
        print(f"[마이크] 주차 오류: {e}")
        return f"⚠️ 오류: {e}"


def mike_kpt_create() -> str:
    """토요일 — KPT 회고 템플릿 페이지 자동 생성"""
    today    = date.today()
    week_num = today.isocalendar()[1]
    title    = f"{today.year}년 {today.month}월 {week_num}주차 KPT"

    props = {
        "주차": {"title": [{"text": {"content": title}}]},
        "날짜": {"date": {"start": today.isoformat()}},
    }
    try:
        resp = requests.post(
            f"{BASE_URL}/pages",
            headers=_headers(),
            json={
                "parent": {"database_id": KPT_DB},
                "properties": props,
                "children": _kpt_template_blocks(),
            },
            timeout=15,
        )
        if resp.status_code in [200, 201]:
            print(f"[마이크] KPT 페이지 생성 ✅ {title}")
            return "\n".join([
                f"📝 {title} KPT 회고 템플릿 생성 완료!",
                "",
                "노션에 KPT 페이지 만들었어.",
                "Keep / Problem / Try 채워줘!",
            ])
        else:
            return f"⚠️ KPT 생성 실패: {resp.text[:100]}"
    except Exception as e:
        return f"⚠️ 오류: {e}"


def _weekly_template_blocks(try_items: list = None) -> list:
    """주간 투두 템플릿 블록 — KPT의 Try 항목을 Top3에 반영"""
    top3 = try_items or ["", "", ""]
    # Top3 목표 3개 맞추기
    while len(top3) < 3:
        top3.append("")

    def _callout(emoji: str, text: str, children: list) -> dict:
        return {
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
                "icon": {"type": "emoji", "emoji": emoji},
                "children": children,
            }
        }

    return [
        # Top 3 목표 callout
        _callout("🏆", "이번 주 Top 3 목표 (3개만)", [
            _todo(top3[0]),
            _todo(top3[1]),
            _todo(top3[2]),
        ]),
        _divider(),
        # 요일별 투두
        _h3("Mon"), _todo("운동(걷기 또는 수영)"), _todo(""),
        _h3("Tues"), _todo("운동(걷기 또는 수영)"), _todo(""),
        _h3("Wed"), _todo("운동(걷기 또는 수영)"), _todo("NCS 일반 1회독"), _todo(""),
        _h3("Thur"), _todo("운동(걷기 또는 수영)"), _todo("NCS 1회독"), _todo(""),
        _h3("Fri"), _todo("운동(걷기 또는 수영)"), _todo(""),
        _h3("Sat"), _todo("주간 KPT 회고 초안 작성"), _todo(""),
        _h3("Sun"), _todo("다음 주 계획 초안 작성"), _todo(""),
        _divider(),
        _h3("Next week"), _todo("공기업 공고/지원 일정 캘린더에 반영"), _todo(""),
        _divider(),
        # 루틴 callout
        _callout("🏃", "루틴 목표 (주간 빈도)", [
            _todo("아침 수영 주 3회"),
            _todo("걷기 매일 1만보"),
            _todo("식단 기록/관리 주 5일 이상"),
            _todo("TOEIC 학습 주 5일, 30~60분"),
        ]),
        _divider(),
        # 체크포인트 callout
        _callout("🧭", "이번 주 체크 포인트 (짧게)", [
            _todo("이번 주 정해진 일정(면접/수업/멘토링) 요일 칸에 배치"),
            _todo("TOEIC 오답노트 + 암기 핵심, 문제 풀이만 하고 넘어가지 않기"),
        ]),
    ]


def _kpt_template_blocks() -> list:
    """KPT 회고 템플릿 블록"""
    def _callout(emoji: str, text: str, children: list) -> dict:
        return {
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
                "icon": {"type": "emoji", "emoji": emoji},
                "children": children,
            }
        }

    return [
        # 이번 주 있었던 일
        _callout("🧩", "이번 주에 있었던 일(사건/성과)\n이번 주 가장 기억에 남는 순간, 힘들었던 순간, 시간을 가장 많이 쓴 일", [
            _bullet("이번 주 가장 기억에 남는 순간: "),
            _bullet("힘들었던 순간: "),
            _bullet("시간을 가장 많이 쓴 일: "),
        ]),
        _divider(),
        _h3("K (Keep) — 유지하고 싶은 것"),
        _bullet(""), _bullet(""), _bullet(""), _bullet(""),
        _divider(),
        _h3("P (Problem) — 아쉬웠던 점/막혔던 점"),
        _bullet(""), _bullet(""), _bullet(""), _bullet(""),
        _divider(),
        _h3("T (Try) — 다음 주에 시도할 것"),
        _bullet(""), _bullet(""), _bullet(""), _bullet(""),
        _divider(),
        _h3("다음 주 가장 중요한 초점 (1문장)"),
        _bullet(""),
    ]


def _weekly_template_blocks(try_items: list = None) -> list:
    """주간 투두 템플릿 블록 — KPT의 Try 항목을 Top3에 반영"""
    top3 = try_items or ["", "", ""]
    # Top3 목표 3개 맞추기
    while len(top3) < 3:
        top3.append("")

    def _callout(emoji: str, text: str, children: list) -> dict:
        return {
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
                "icon": {"type": "emoji", "emoji": emoji},
                "children": children,
            }
        }

    return [
        # Top 3 목표 callout
        _callout("🏆", "이번 주 Top 3 목표 (3개만)", [
            _todo(top3[0]),
            _todo(top3[1]),
            _todo(top3[2]),
        ]),
        _divider(),
        # 요일별 투두
        _h3("Mon"), _todo("운동(걷기 또는 수영)"), _todo(""),
        _h3("Tues"), _todo("운동(걷기 또는 수영)"), _todo(""),
        _h3("Wed"), _todo("운동(걷기 또는 수영)"), _todo("NCS 일반 1회독"), _todo(""),
        _h3("Thur"), _todo("운동(걷기 또는 수영)"), _todo("NCS 1회독"), _todo(""),
        _h3("Fri"), _todo("운동(걷기 또는 수영)"), _todo(""),
        _h3("Sat"), _todo("주간 KPT 회고 초안 작성"), _todo(""),
        _h3("Sun"), _todo("다음 주 계획 초안 작성"), _todo(""),
        _divider(),
        _h3("Next week"), _todo("공기업 공고/지원 일정 캘린더에 반영"), _todo(""),
        _divider(),
        # 루틴 callout
        _callout("🏃", "루틴 목표 (주간 빈도)", [
            _todo("아침 수영 주 3회"),
            _todo("걷기 매일 1만보"),
            _todo("식단 기록/관리 주 5일 이상"),
            _todo("TOEIC 학습 주 5일, 30~60분"),
        ]),
        _divider(),
        # 체크포인트 callout
        _callout("🧭", "이번 주 체크 포인트 (짧게)", [
            _todo("이번 주 정해진 일정(면접/수업/멘토링) 요일 칸에 배치"),
            _todo("TOEIC 오답노트 + 암기 핵심, 문제 풀이만 하고 넘어가지 않기"),
        ]),
    ]


def _kpt_template_blocks() -> list:
    """KPT 회고 템플릿 블록"""
    def _callout(emoji: str, text: str, children: list) -> dict:
        return {
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
                "icon": {"type": "emoji", "emoji": emoji},
                "children": children,
            }
        }

    return [
        # 이번 주 있었던 일
        _callout("🧩", "이번 주에 있었던 일(사건/성과)\n이번 주 가장 기억에 남는 순간, 힘들었던 순간, 시간을 가장 많이 쓴 일", [
            _bullet("이번 주 가장 기억에 남는 순간: "),
            _bullet("힘들었던 순간: "),
            _bullet("시간을 가장 많이 쓴 일: "),
        ]),
        _divider(),
        _h3("K (Keep) — 유지하고 싶은 것"),
        _bullet(""), _bullet(""), _bullet(""), _bullet(""),
        _divider(),
        _h3("P (Problem) — 아쉬웠던 점/막혔던 점"),
        _bullet(""), _bullet(""), _bullet(""), _bullet(""),
        _divider(),
        _h3("T (Try) — 다음 주에 시도할 것"),
        _bullet(""), _bullet(""), _bullet(""), _bullet(""),
        _divider(),
        _h3("다음 주 가장 중요한 초점 (1문장)"),
        _bullet(""),
    ]


def mike_get_latest_kpt_try() -> list:
    """최근 KPT DB에서 Try 항목 읽기"""
    try:
        rows = _query_db(KPT_DB, sorts=[{"timestamp": "created_time", "direction": "descending"}])
        if not rows:
            return []
        page_id = rows[0]["id"]
        blocks  = _get_blocks(page_id)
        try_items = []
        in_try = False
        for b in blocks:
            t    = b.get("type", "")
            text = _block_text(b)
            if t in ["heading_1","heading_2","heading_3"]:
                in_try = "Try" in text or "시도" in text
            elif in_try and t == "bulleted_list_item" and text.strip():
                try_items.append(text.strip())
        return try_items[:3]
    except Exception as e:
        print("[마이크] KPT Try 읽기 실패:", e)
        return []


# ================================================================
# 로즈 (Roz) — 수업 수강자 현황
# 컬럼: 이름(title), 남은 횟수, 총 등록수업횟수, 수업 자료
# ================================================================
def roz_get_students() -> list[dict]:
    rows = _query_db(
        _db("NOTION_STUDENT_DB_ID"),
        sorts=[{"timestamp": "last_edited_time", "direction": "descending"}]
    )
    students = []
    for r in rows:
        students.append({
            "id":         r["id"],
            "name":       _get_prop(r,"이름") or "이름없음",
            "remaining":  _get_prop(r,"남은 횟수") or 0,
            "total":      _get_prop(r,"총 등록수업횟수") or 0,
            "lesson_url": _get_prop(r,"수업 자료") or "",
        })
    return students

def roz_get_lessons() -> list[dict]:
    rows = _query_db(
        _db("NOTION_LESSON_DB_ID"),
        sorts=[{"timestamp": "created_time", "direction": "descending"}]
    )
    lessons = []
    for r in rows:
        lessons.append({
            "id":     r["id"],
            "title":  _get_prop(r,"이름") or _get_prop(r,"Name") or "",
            "date":   _get_prop(r,"날짜") or _get_prop(r,"Date") or "",
            "status": _get_prop(r,"상태") or _get_prop(r,"Status") or "",
        })
    return lessons

def roz_daily_brief() -> str:
    students = roz_get_students()
    today    = date.today()

    if not students:
        return "📚 수강생 DB가 비어있어. 노션 연결 확인해줘."

    lines = [f"📚 {today.strftime('%m/%d')} 로즈 브리핑"]
    lines.append(f"• 수강생 {len(students)}명\n")
    lines.append("📋 수강생 현황:")

    for s in students:
        remaining = s.get("remaining") or 0
        total     = s.get("total") or 0
        warn      = " ⚠️" if int(remaining) <= 3 else ""
        lines.append(f"  • {s['name']} — 잔여 {remaining}회 / 총 {total}회{warn}")

    low = [s for s in students if (s.get("remaining") or 0) and int(s.get("remaining") or 0) <= 3]
    if low:
        lines.append(f"\n⚠️ 잔여 3회 이하 — 연장 안내 필요:")
        for s in low:
            lines.append(f"  → {s['name']} ({s['remaining']}회 남음)")

    lines.append("\n피드백 초안이나 수업자료 필요하면 말해줘!")
    return "\n".join(lines)

# 수강생별 수업기록 DB ID
STUDENT_LESSON_DBS = {
    "eve":     "191b87ee-1038-80df-8eb0-e5679e82f724",
    "이브":    "191b87ee-1038-80df-8eb0-e5679e82f724",
    "도미닉":  "2a8b87ee-1038-815a-81f0-d9d58de60864",
    "dominic": "2a8b87ee-1038-815a-81f0-d9d58de60864",
}

def roz_get_recent_lesson(student_name: str, limit: int = 1) -> list:
    key   = student_name.lower().replace("님","").strip()
    db_id = STUDENT_LESSON_DBS.get(key) or STUDENT_LESSON_DBS.get(student_name.replace("님",""))
    if not db_id:
        return []
    rows = _query_db(db_id, sorts=[{"timestamp": "created_time", "direction": "descending"}])
    results = []
    for row in rows[:limit]:
        title       = _get_prop(row, "이름") or ""
        lesson_date = _get_prop(row, "수업 날짜") or ""
        page_id     = row["id"]
        blocks      = _get_blocks(page_id)
        feedback    = []
        words       = []
        section     = ""
        for b in blocks:
            t    = b.get("type","")
            text = _block_text(b)
            if t in ["heading_1","heading_2","heading_3"]:
                section = text
            elif t in ["bulleted_list_item","numbered_list_item"] and text.strip():
                if "피드백" in section or "말하기" in section:
                    feedback.append(text.strip())
                elif "단어" in section:
                    words.append(text.strip())
            elif t == "paragraph" and text.strip() and "피드백" in section:
                feedback.append(text.strip())
        results.append({"title": title, "date": lesson_date,
                        "page_id": page_id, "feedback": feedback, "words": words})
    return results


def roz_get_lesson_summary(student_name: str) -> str:
    lessons = roz_get_recent_lesson(student_name, limit=1)
    if not lessons:
        return student_name + "님 수업 기록을 찾을 수 없어."
    l = lessons[0]
    lines = ["📖 " + student_name + " 최근 수업: " + l["title"]]
    if l["date"]:
        lines.append("📅 수업일: " + l["date"])
    if l["feedback"]:
        lines.append("\n💬 말하기 피드백 (" + str(len(l["feedback"])) + "문장):")
        for f in l["feedback"][:5]:
            lines.append("  • " + f[:60])
    if l["words"]:
        lines.append("\n📝 학습 단어/표현 (" + str(len(l["words"])) + "개):")
        for w in l["words"][:5]:
            lines.append("  • " + w[:60])
    return "\n".join(lines)


def roz_generate_material_draft(student_name: str) -> str:
    lessons = roz_get_recent_lesson(student_name, limit=3)
    if not lessons:
        return student_name + "님 수업 기록 없음"
    lines = ["📚 " + student_name + " 교재 제작용 수업 데이터\n"]
    for l in lessons:
        lines.append("=== " + l["title"] + " (" + l["date"] + ") ===")
        if l["feedback"]:
            lines.append("[말하기 피드백]")
            for f in l["feedback"]:
                lines.append("  " + f)
        if l["words"]:
            lines.append("[단어/표현]")
            for w in l["words"]:
                lines.append("  " + w)
        lines.append("")
    return "\n".join(lines)


def roz_feedback_draft(student_name: str) -> str:
    students = roz_get_students()
    s = next((x for x in students if student_name in x.get("name","")), None)
    lesson_summary = roz_get_lesson_summary(student_name)
    lines = ["📝 " + student_name + " 피드백 초안\n"]
    if s:
        lines.append("• 총 등록: " + str(s.get("total",0)) + "회 | 잔여: " + str(s.get("remaining",0)) + "회")
    lines.append("\n" + lesson_summary)
    lines.append("\n교재 초안 필요하면 '교재 만들어줘' 라고 말해줘!")
    return "\n".join(lines)

# ================================================================
# 통합 함수
# ================================================================
def get_agent_brief(agent_id: str) -> str:
    try:
        if agent_id == "sully":  return sully_summary()
        elif agent_id == "mike": return mike_daily_brief()
        elif agent_id == "roz":  return roz_daily_brief()
    except Exception as e:
        return f"[노션 오류] {e}"
    return ""

def check_notion_connection() -> dict:
    key = os.environ.get("NOTION_API_KEY","")
    result = {
        "connected":  False,
        "job_db":     False,
        "goal_db":    False,
        "yearly_db":  False,
        "student_db": False,
        "lesson_db":  False,
        "error":      None,
    }
    if not key:
        result["error"] = "API 키 없음"
        return result

    # 연결 테스트
    try:
        r = requests.get(f"{BASE_URL}/users/me", headers=_headers(), timeout=10)
        if r.status_code != 200:
            result["error"] = f"인증 실패: {r.status_code}"
            return result
        result["connected"] = True
    except Exception as e:
        result["error"] = str(e)
        return result

    for key_name, env in [
        ("job_db",    "NOTION_JOB_DB_ID"),
        ("goal_db",   "NOTION_GOAL_DB_ID"),
        ("yearly_db", "NOTION_YEARLY_DB_ID"),
        ("student_db","NOTION_STUDENT_DB_ID"),
        ("lesson_db", "NOTION_LESSON_DB_ID"),
    ]:
        db_id = _db(env)
        if not db_id:
            result[key_name] = "ID 미설정"
            continue
        try:
            r = requests.get(f"{BASE_URL}/databases/{db_id}", headers=_headers(), timeout=10)
            if r.status_code == 200:
                result[key_name] = True
            else:
                result[key_name] = f"오류: {r.json().get('message','')[:80]}"
        except Exception as e:
            result[key_name] = f"오류: {str(e)[:80]}"
    return result


# ================================================================
# 설리 — 공고 저장 함수 (크롤러 연동)
# ================================================================
import re as _re

def sully_add_job(title: str, deadline: str = "", certs: list = None,
                  toeic: int = 0, status: str = "지원 전", url: str = ""):
    """
    공고 DB에 새 행 추가. 중복이면 "SKIP" 반환.
    쓰기 가능 컬럼: 기업명, 공고 마감일, 필수 자격증, 목표 토익점수, 진행 상태, 공고문 URL
    """
    db_id = _db("NOTION_JOB_DB_ID")
    if not db_id:
        return None

    # 중복 체크 (기업명 기준)
    existing = sully_get_jobs(200)
    if any(j["title"].strip() == title.strip() for j in existing):
        return "SKIP"

    props = {
        "기업명":   {"title": [{"text": {"content": title[:100]}}]},
        "진행 상태": {"status": {"name": status}},
    }
    if deadline:
        try:
            datetime.strptime(deadline[:10], "%Y-%m-%d")
            props["공고 마감일"] = {"date": {"start": deadline[:10]}}
        except:
            pass
    if certs:
        props["필수 자격증"] = {"multi_select": [{"name": c} for c in certs[:5]]}
    if toeic and int(toeic) > 0:
        props["목표 토익점수(합격컷)"] = {"number": int(toeic)}
    if url and url.startswith("http"):
        props["공고문 URL"] = {"url": url}

    try:
        resp = requests.post(
            f"{BASE_URL}/pages",
            headers=_headers(),
            json={"parent": {"database_id": db_id}, "properties": props},
            timeout=15,
        )
        if resp.status_code == 200:
            page_id = resp.json().get("id","")
            print(f"[노션] ✅ {title} 추가됨")
            return page_id
        print(f"[노션] 추가 실패 {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"[노션] 추가 오류: {e}")
        return None


def sully_save_crawl_results(jobs: list) -> dict:
    """
    크롤러 결과 리스트를 노션 공고 DB에 저장
    중복(기업명 동일) 건너뜀
    """
    added = skipped = failed = 0
    for job in jobs:
        title    = job.get("title","").strip()
        deadline = job.get("end","") or job.get("deadline","")
        url      = job.get("url","") or ""
        if not title or len(title) < 2:
            continue

        # 날짜 형식 정규화 YYYYMMDD → YYYY-MM-DD / YYYY.MM.DD → YYYY-MM-DD
        deadline = _re.sub(r'(\d{4})[./](\d{2})[./](\d{2}).*', r'\1-\2-\3', deadline)
        if _re.match(r'\d{8}$', deadline):
            deadline = f"{deadline[:4]}-{deadline[4:6]}-{deadline[6:8]}"
        if not _re.match(r'\d{4}-\d{2}-\d{2}', deadline):
            deadline = ""

        result = sully_add_job(title=title, deadline=deadline, url=url)
        if result == "SKIP":
            skipped += 1
        elif result:
            added += 1
        else:
            failed += 1

    print(f"[노션 저장] 추가:{added} / 스킵:{skipped} / 실패:{failed}")
    return {"added": added, "skipped": skipped, "failed": failed}