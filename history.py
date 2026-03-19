from __future__ import annotations

# ================================================================
# history.py — 로컬 기록 누적 모듈
# 매일 결과를 history.json 에 쌓아서 대시보드 히스토리에 사용합니다.
# ================================================================

import json
from datetime import date
from pathlib import Path

HISTORY_FILE = Path(__file__).parent / "history.json"


def _load() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(records: list):
    HISTORY_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def append_record(
    target_company: str,
    score:          int,
    grade:          str,
    verdict:        str,
    bonuses:        list,
    penalties:      list,
    todos:          list,
    spec_progress:  list,
    gang_pro_log:   list,
):
    """오늘 결과를 history.json 에 추가 (날짜 중복 시 덮어쓰기)"""
    records = _load()
    today   = date.today().isoformat()

    done_count  = sum(1 for t in todos if t.get("done"))
    total_count = len(todos) or 1

    new_record = {
        "date":          today,
        "company":       target_company,
        "score":         score,
        "grade":         grade,
        "verdict":       verdict,
        "bonuses":       bonuses,
        "penalties":     penalties,
        "todos":         todos,
        "todo_rate":     round(done_count / total_count * 100),
        "spec_progress": spec_progress,
        "gang_pro_log":  gang_pro_log[-10:],   # 최근 10줄만 저장
    }

    # 오늘 날짜 기록이 이미 있으면 덮어쓰기
    records = [r for r in records if r.get("date") != today]
    records.append(new_record)

    # 최근 90일치만 유지
    records = sorted(records, key=lambda r: r["date"], reverse=True)[:90]
    _save(records)
    print(f"📝 로컬 기록 저장 완료 ({len(records)}일치 누적)")


def get_all() -> list:
    """전체 히스토리 반환 (최신 순)"""
    return sorted(_load(), key=lambda r: r["date"], reverse=True)


def get_score_series() -> list:
    """날짜-점수 시계열 반환 (차트용, 오래된 순)"""
    records = sorted(_load(), key=lambda r: r["date"])
    return [{"date": r["date"], "score": r["score"], "grade": r["grade"]}
            for r in records]