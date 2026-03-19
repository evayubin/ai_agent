from __future__ import annotations
"""
crawler.py — 공기업 채용공고 크롤러
소스: job.alio.go.kr / 사람인 / 잡코리아
"""

import os, json, datetime, time, threading, re
import requests
from pathlib import Path
from typing import Optional

try:
    from bs4 import BeautifulSoup
    BS4 = True
except ImportError:
    BS4 = False

# ================================================================
# 설정
# ================================================================
CRAWL_FILE = Path(__file__).parent / "crawl_result.json"
CRAWL_LOG  = Path(__file__).parent / "crawl_log.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 유빈 스펙 키워드
YUBIN_KEYWORDS = [
    "국제협력", "ICT", "정보통신", "해외", "ODA",
    "스페인", "중남미", "외국어", "어학", "언어",
    "충북", "청주", "충청", "한국어", "교육",
    "인문", "행정", "일반직", "사무",
]
YUBIN_EXCLUDE = ["박사", "경력 10년", "전문연구요원", "의사", "간호", "기계", "전기"]

# ================================================================
# 크롤러
# ================================================================
class PublicJobCrawler:

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ── 1. 공공데이터포털 ALIO API ──────────────────────────────
    def fetch_alio(self) -> list[dict]:
        """
        공공데이터포털 채용공고 API
        필터: 충북/세종 근무지, 정규직, 신입/경력/신입+경력
        여러 NCS 직종 코드로 반복 조회 후 합산
        """
        api_key = os.environ.get("ALIO_API_KEY", "")
        if not api_key:
            print("[ALIO API] 키 없음 — .env에 ALIO_API_KEY 추가 필요")
            return []

        BASE = "https://apis.data.go.kr/1051000/recruitment/list"

        # 유빈 맞춤 필터
        WORK_REGIONS  = ["R3020", "R3026"]          # 충북, 세종
        HIRE_TYPES    = ["R1010"]                    # 정규직만
        RECRUIT_SE    = ["R2010", "R2020", "R2030"]  # 신입, 경력, 신입+경력
        # NCS 코드: 경영.회계.사무, 정보통신, 사업관리, 교육.자연.사회과학
        NCS_CODES     = ["R600002", "R600020", "R600001", "R600004"]

        jobs = []
        seen = set()

        for ncs in NCS_CODES:
            for region in WORK_REGIONS:
                try:
                    resp = self.session.get(BASE, params={
                        "serviceKey":  api_key,
                        "pageNo":      1,
                        "numOfRows":   100,
                        "type":        "json",
                        "ncsCdLst":    ncs,
                        "workRgnLst":  region,
                        "hireTypeLst": "R1010",
                        "recrutSe":    "R2010",      # 신입 우선
                        "pbancEndYmd": (datetime.date.today() + datetime.timedelta(days=90)).strftime("%Y%m%d"),
                        "pbancBgngYmd": (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y%m%d"),
                    }, timeout=15)

                    if resp.status_code != 200:
                        continue

                    data  = resp.json()
                    items = (data.get("result") or data.get("data") or
                             data.get("items") or data.get("recruitmentList") or [])
                    if isinstance(items, dict):
                        items = items.get("item") or items.get("list") or []

                    for item in items:
                        title = (item.get("recrutPbancTtl") or item.get("title") or "").strip()
                        inst  = (item.get("instNm") or item.get("org") or "").strip()
                        key   = title[:20]
                        if not title or key in seen:
                            continue
                        seen.add(key)
                        jobs.append({
                            "title":    title,
                            "org":      inst,
                            "end":      item.get("pbancEndYmd",""),
                            "start":    item.get("pbancBgngYmd",""),
                            "emp_type": item.get("hireTypeNmLst",""),
                            "location": item.get("workRgnNmLst",""),
                            "ncs":      item.get("ncsCdNmLst",""),
                            "url":      item.get("srcUrl","") or "https://job.alio.go.kr",
                            "source":   "alio_api",
                        })

                except Exception as e:
                    print(f"[ALIO API] 오류 ncs={ncs} region={region}: {e}")

        # 전국 + 신입+경력도 추가 조회 (충북/세종 외 공고 보완)
        try:
            resp = self.session.get(BASE, params={
                "serviceKey":   api_key,
                "pageNo":       1,
                "numOfRows":    50,
                "type":         "json",
                "hireTypeLst":  "R1010",   #정규직만
                "recrutSe":     "R2030",   # 신입+경력
                "ncsCdLst":     "R600002", # 경영.회계.사무
                "pbancEndYmd":  (datetime.date.today() + datetime.timedelta(days=90)).strftime("%Y%m%d"),
                "pbancBgngYmd": (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y%m%d"),
            }, timeout=15)
            if resp.status_code == 200:
                data  = resp.json()
                items = (data.get("result") or data.get("data") or
                         data.get("items") or data.get("recruitmentList") or [])
                if isinstance(items, dict):
                    items = items.get("item") or items.get("list") or []
                for item in items:
                    title = (item.get("recrutPbancTtl") or "").strip()
                    key   = title[:20]
                    if not title or key in seen:
                        continue
                    seen.add(key)
                    jobs.append({
                        "title":    title,
                        "org":      item.get("instNm",""),
                        "end":      item.get("pbancEndYmd",""),
                        "start":    item.get("pbancBgngYmd",""),
                        "emp_type": item.get("hireTypeNmLst",""),
                        "location": item.get("workRgnNmLst",""),
                        "ncs":      item.get("ncsCdNmLst",""),
                        "url":      item.get("srcUrl","") or "https://job.alio.go.kr",
                        "source":   "alio_api",
                    })
        except Exception as e:
            print(f"[ALIO API 보완] 오류: {e}")

        print(f"[ALIO API] {len(jobs)}개")
        return jobs

    # ── 스코어링 ─────────────────────────────────────────────────
    def score_job(self, job: dict) -> int:
        text = (job.get("title","") + " " + job.get("org","")).lower()
        score = 50
        for kw in YUBIN_KEYWORDS:
            if kw in text:
                score += 8
        for ex in YUBIN_EXCLUDE:
            if ex in text:
                score -= 25
        if any(r in text for r in ["충북","청주","충청"]):
            score += 15
        if "신입" in text:
            score += 10
        if any(k in text for k in ["공기업","공공기관","공단","공사"]):
            score += 10
        return max(0, min(100, score))

    # ── 메인 실행 ─────────────────────────────────────────────────
    def run(self) -> dict:
        print(f"[크롤러] 시작 {datetime.datetime.now().strftime('%H:%M:%S')}")

        jobs = []
        jobs.extend(self.fetch_alio())

        # 전체 중복 제거
        seen, unique = set(), []
        for j in jobs:
            key = j.get("title","")[:20]
            if key and key not in seen:
                seen.add(key)
                unique.append(j)

        # 스코어링
        for j in unique:
            j["score"]      = self.score_job(j)
            j["crawled_at"] = datetime.datetime.now().isoformat()
        scored = sorted(unique, key=lambda j: j["score"], reverse=True)

        result = {
            "total":      len(scored),
            "top":        scored[:15],
            "crawled_at": datetime.datetime.now().isoformat(),
            "date":       datetime.date.today().isoformat(),
        }

        CRAWL_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))

        # 노션 자동 저장
        try:
            from notion_sync import sully_save_crawl_results
            notion_result = sully_save_crawl_results(scored[:15])
            print(f"[노션] 추가:{notion_result['added']} 스킵:{notion_result['skipped']}")
        except Exception as e:
            print(f"[노션 저장 오류] {e}")

        # 로그 누적
        log = []
        if CRAWL_LOG.exists():
            try: log = json.loads(CRAWL_LOG.read_text())
            except: pass
        log.append({"date": result["date"], "total": result["total"], "time": result["crawled_at"]})
        CRAWL_LOG.write_text(json.dumps(log[-90:], ensure_ascii=False, indent=2))

        print(f"[크롤러] 완료 — 총 {len(scored)}개, 상위 {min(15,len(scored))}개 저장")
        return result


# ================================================================
# 스케줄러
# ================================================================
_crawler_thread: Optional[threading.Thread] = None
_last_crawl_date: Optional[str]             = None

def start_crawl_scheduler():
    global _crawler_thread

    def _loop():
        global _last_crawl_date
        _run_once()
        while True:
            now   = datetime.datetime.now()
            today = datetime.date.today().isoformat()
            if now.hour == 9 and now.minute == 0 and _last_crawl_date != today:
                _run_once()
            time.sleep(60)

    def _run_once():
        global _last_crawl_date
        today = datetime.date.today().isoformat()
        if _last_crawl_date == today:
            return
        try:
            PublicJobCrawler().run()
            _last_crawl_date = today
        except Exception as e:
            print(f"[크롤러 오류] {e}")

    _crawler_thread = threading.Thread(target=_loop, daemon=True)
    _crawler_thread.start()
    print("🔍 크롤 스케줄러 시작 (매일 09:00 자동 실행)")


def get_crawl_result() -> dict:
    if CRAWL_FILE.exists():
        try: return json.loads(CRAWL_FILE.read_text())
        except: pass
    return {"total": 0, "top": [], "crawled_at": None, "date": None}


# ================================================================
# 단독 실행
# ================================================================
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    result = PublicJobCrawler().run()
    print(f"\n=== 결과 ===\n총 {result['total']}개")
    for j in result["top"][:5]:
        print(f"  [{j['score']}점] {j['title']} — {j['org']} ({j['source']})")