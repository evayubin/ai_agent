from __future__ import annotations  # Python 3.9 이하 타입 힌트 호환 (반드시 첫 줄)

import os
import re
import warnings
import faiss
from pathlib import Path
from dataclasses import dataclass, field
from collections import deque
from typing import Optional
from dotenv import load_dotenv

# 환경 설정
warnings.filterwarnings("ignore")
load_dotenv()

from pypdf import PdfReader
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# ================================================================
# [섹션 0] 유빈 프로필 & 스코어링 설정 (여기만 수정하면 됩니다)
# ================================================================

@dataclass
class YubinProfile:
    """유빈 님의 스펙 및 선호 조건 — 값 변경 시 스코어링 자동 반영"""
    name: str             = "임유빈"
    birth_year: int       = 1995          # 만 나이 계산용 (34세 이하 청년 가점)
    toeic: int            = 780           # 현재 토익 점수
    opic: str             = "IH"          # 현재 오픽 점수(토익점수환산가능성추가)
    preferred_region: str = "충북"        # 선호 근무 지역
    home_region: str      = "충북"        # 생활권 (감점 기준)

# 가점/감점 규칙 테이블 — (설명, 점수, 매칭 키워드 목록) 형태
BONUS_RULES = [
    {
        "label":    "지역 가점 (충북/지역인재)",
        "score":    +20,
        "keywords": ["충북", "충청북도", "이전 공공기관", "지역인재", "혁신도시"],
    },
    {
        "label":    "경력 적합도 (국제협력/사업관리)",
        "score":    +30,
        "keywords": ["KOICA", "코이카", "국제협력", "연수 운영", "연수운영",
                     "사업관리", "ODA", "해외사업"],
    },
    {
        "label":    "전공·자격 매칭 (스페인어/중남미/한국어교육)",
        "score":    +15,
        "keywords": ["스페인어", "중남미", "한국어 교육", "한국어교육",
                     "한국어교원", "한국어강사", "언어교육"],
    },
    {
    "label":    "OPIc 어학 가점 (IH → 토익 800 수준 인정)",
    "score":    +15,
    "keywords": ["OPIc", "오픽", "영어 말하기", "어학 우대", "토익 환산"],
    },
    {
        "label":    "청년 가점 (만 34세 이하)",
        "score":    +5,
        "keywords": ["청년", "만 34세", "만34세", "만 39세 이하", "청년인재"],
    },
]

PENALTY_RULES = [
    {
        "label":    "어학 컷오프 (토익 800 이상 고정)",
        "score":    -50,
        "keywords": ["토익 800", "토익800", "TOEIC 800", "토익 850", "토익 900",
                     "토익 750"],   # 780 미만 조건도 포함
        "message":  "⚠️  도전적 공고 — 어학 점수 보완 필요 (현재 {toeic}점)",
    },
    {
        "label":    "수도권/원거리 근무지",
        "score":    -10,
        "keywords": ["서울", "경기", "인천", "수도권", "세종", "대전광역시"],
        "message":  "📍 근무지가 생활권({home})과 멀 수 있습니다.",
    },
]

# ================================================================
# [섹션 1] 스코어링 엔진 (규칙 기반 + 메시지 생성)
# ================================================================

@dataclass
class ScoreResult:
    """스코어링 결과 컨테이너"""
    total_score: int             = 0
    matched_bonuses: list        = field(default_factory=list)   # [(label, score)]
    matched_penalties: list      = field(default_factory=list)   # [(label, score, message)]
    grade: str                   = ""    # S / A / B / C / D
    verdict: str                 = ""    # 최종 판정 메시지
    recommendation: str          = ""    # 추천 액션


def _contains_any(text: str, keywords: list) -> bool:
    """공고 텍스트에 키워드 중 하나라도 포함되면 True"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _resolve_toeic_penalty(keywords: list, profile: YubinProfile) -> bool:
    """
    토익 컷오프 감점 특수 처리:
    공고에 명시된 토익 기준이 유빈 님 점수(780)보다 높을 때만 감점.
    """
    import re as _re
    toeic_pattern = _re.compile(r"토익\s*(\d{3})")
    for kw in keywords:
        m = toeic_pattern.search(kw)
        if m and int(m.group(1)) > profile.toeic:
            return True
        # 숫자 없는 키워드는 단순 포함 여부로 판단
        if not _re.search(r"\d", kw):
            return True
    return False


def calculate_score(job_text: str, profile: YubinProfile) -> ScoreResult:
    """
    공고 텍스트 + 유빈 프로필을 받아 가점/감점을 계산하고
    ScoreResult를 반환합니다.
    """
    result = ScoreResult()

    # ── 가점 계산 ─────────────────────────────────────────
    for rule in BONUS_RULES:
        if "청년" in rule["label"]:
            import datetime
            age = datetime.date.today().year - profile.birth_year
            if age > 34 and not _contains_any(job_text, rule["keywords"]):
                continue

        if _contains_any(job_text, rule["keywords"]):
            result.total_score += rule["score"]
            result.matched_bonuses.append((rule["label"], rule["score"]))

    # ── 감점 계산 ─────────────────────────────────────────
    for rule in PENALTY_RULES:
        hit = False
        if "어학" in rule["label"]:
            hit = _resolve_toeic_penalty(rule["keywords"], profile)
        else:
            hit = _contains_any(job_text, rule["keywords"])

        if hit:
            result.total_score += rule["score"]
            msg = rule["message"].format(
                toeic=profile.toeic,
                home=profile.home_region
            )
            result.matched_penalties.append((rule["label"], rule["score"], msg))

    # ── OPIc → 토익 환산 보정 ────────────────────────────
    OPIC_TO_TOEIC = {
        "AL": 900, "IH": 820, "IM3": 780,
        "IM2": 740, "IM1": 700, "IL": 600,
    }
    opic_equiv = OPIC_TO_TOEIC.get(profile.opic.upper(), 0)

    for i, (label, score, msg) in enumerate(result.matched_penalties):
        if "어학" in label:
            m = re.search(r"토익\s*(\d{3})", msg + label)
            cutoff = int(m.group(1)) if m else 800
            if opic_equiv >= cutoff:
                result.total_score -= score  # 음수 score를 다시 빼면 원복
                result.matched_penalties[i] = (
                    label,
                    0,
                    f"✅ OPIc {profile.opic} → 토익 {opic_equiv} 환산, 어학 기준 충족으로 감점 면제"
                )
            break

    # ── 등급 산정 ─────────────────────────────────────────
    s = result.total_score
    if   s >= 60: result.grade = "S"
    elif s >= 40: result.grade = "A"
    elif s >= 20: result.grade = "B"
    elif s >= 0:  result.grade = "C"
    else:         result.grade = "D"

    # ── 최종 판정 메시지 ──────────────────────────────────
    grade_msg = {
        "S": "🏆 최우선 지원 대상 — 지금 바로 서류 준비 시작!",
        "A": "✅ 적극 권장 — 이번 주 안에 지원하세요.",
        "B": "👀 지원 가능 — 추가 스펙 보완 병행 권장.",
        "C": "⚡ 도전 가능 — 부족한 부분을 명확히 파악 후 지원.",
        "D": "❌ 현시점 지원 비추 — 스펙 보완 후 재검토.",
    }
    result.verdict        = grade_msg[result.grade]
    result.recommendation = _build_recommendation(result, profile)

    return result


def _build_recommendation(result: ScoreResult, profile: YubinProfile) -> str:
    """스코어 결과 기반 맞춤 액션 메시지 생성"""
    lines = []
    for label, score, msg in result.matched_penalties:
        lines.append(msg)
    if not lines:
        lines.append("✔️  현재 스펙으로 지원 자격 충족")
    return " | ".join(lines)


def format_score_report(result: ScoreResult, job_title: str = "") -> str:
    """스코어 결과를 보기 좋게 포매팅"""
    sep = "─" * 50
    header = f"📊 스코어링 결과: {job_title}" if job_title else "📊 스코어링 결과"
    lines = [
        sep,
        header,
        f"   총점: {result.total_score:+d}점  |  등급: {result.grade}  |  {result.verdict}",
        "",
    ]

    if result.matched_bonuses:
        lines.append("   ✅ 가점 항목:")
        for label, score in result.matched_bonuses:
            lines.append(f"      + {score:+d}점  {label}")

    if result.matched_penalties:
        lines.append("   ⚠️  감점 항목:")
        for label, score, msg in result.matched_penalties:
            lines.append(f"      {score:+d}점  {label}")
            lines.append(f"         → {msg}")

    if not result.matched_bonuses and not result.matched_penalties:
        lines.append("   (매칭된 가점/감점 항목 없음)")

    lines.append(sep)
    return "\n".join(lines)


# ================================================================
# [섹션 2] 벡터 저장소 & LLM 초기화
# ================================================================

embeddings_model = OpenAIEmbeddings()
embedding_size   = 1536

index        = faiss.IndexFlatL2(embedding_size)
vectorstore  = FAISS(
    embedding_function=embeddings_model,
    index=index,
    docstore=InMemoryDocstore({}),
    index_to_docstore_id={}
)

llm    = ChatOpenAI(model="gpt-4o", temperature=0.1)
parser = StrOutputParser()

# ================================================================
# [섹션 3] PDF 파서
# ================================================================

def parse_job_pdf(pdf_path: str) -> dict:
    """공고 PDF → 텍스트 추출 + 핵심 섹션 구조화"""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    reader    = PdfReader(str(path))
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    section_patterns = {
        "자격요건":   r"(응시\s*자격|지원\s*자격|자격\s*요건)(.*?)(우대|가산|직무|접수|$)",
        "우대사항":   r"(우대\s*사항|우대\s*조건)(.*?)(자격|직무|접수|가산|$)",
        "가산점":     r"(가산점|가산\s*자격)(.*?)(우대|직무|접수|제출|$)",
        "직무기술서": r"(직무\s*기술서|NCS\s*직무|담당\s*업무)(.*?)(자격|우대|접수|$)",
        "접수기간":   r"(원서\s*접수|접수\s*기간|지원\s*기간)(.*?)(\n{2,}|마감|$)",
    }

    sections: dict = {}
    for key, pattern in section_patterns.items():
        match = re.search(pattern, full_text, re.DOTALL | re.IGNORECASE)
        sections[key] = match.group(2).strip()[:800] if match else "해당 섹션 없음"

    return {
        "raw_text":    full_text,
        "sections":    sections,
        "page_count":  len(reader.pages),
        "source_file": path.name,
    }


def summarize_pdf_sections(parsed: dict) -> str:
    lines = [f"[출처: {parsed['source_file']} / {parsed['page_count']}페이지]"]
    for name, content in parsed["sections"].items():
        lines.append(f"\n## {name}\n{content}")
    return "\n".join(lines)


# ================================================================
# [섹션 4] LangChain 체인 정의
# ================================================================

# ── 체인 1: 태스크 생성 ──────────────────────────────────────────
task_creation_chain = PromptTemplate(
    template="""당신은 공기업 채용 전략 전문가입니다.
최종 목표: {objective}
최근 완료된 분석 결과: {result}
현재 남은 태스크: {task_description}
과거 완료 태스크 (중복 방지): {past_context}
채용 공고 요약: {job_posting_summary}
지원자 스코어링 결과: {score_report}

스코어링 결과를 반드시 반영하여, 합격에 필요한 후속 태스크를 생성하세요.
- 감점 항목이 있다면 해당 보완 태스크를 포함하세요.
- 가점 항목이 있다면 해당 강점을 서류에 녹이는 전략 태스크를 포함하세요.
- NCS 직무기술서 분석, 자격증 대조, 면접 준비 등도 포함하세요.

출력 형식 (번호. 태스크명 형식 엄수):
1. 태스크명
2. 태스크명
3. 태스크명
""",
    input_variables=["objective", "result", "task_description",
                     "past_context", "job_posting_summary", "score_report"]
) | llm | parser

# ── 체인 2: 우선순위 정렬 ────────────────────────────────────────
priority_chain = PromptTemplate(
    template="""당신은 채용 컨설팅 우선순위 매니저입니다.
최종 목표: {objective}
현재 태스크 리스트:
{task_names}

아래 기준으로 우선순위를 재정렬하세요.
① 응시 자격·결격 사유 검토 (지원 불가 시 즉시 중단)
② 감점 항목 보완 계획 (어학, 근무지 등)
③ 가점 항목 강화 전략 (지역인재, 경력 매칭)
④ NCS 직무 분석 및 필기 대비
⑤ 서류·면접 전략 수립

출력 형식 (번호. 태스크명 형식 엄수):
1. 태스크명
2. 태스크명
3. 태스크명
""",
    input_variables=["objective", "task_names"]
) | llm | parser

# ── 체인 3: 태스크 실행 (분석 보고서) ───────────────────────────
execution_chain = PromptTemplate(
    template="""당신은 공공기관 인사담당자 시각을 가진 채용 분석가입니다.
최종 목표: {objective}
수행할 태스크: {task}
채용 공고 관련 원문: {job_context}
과거 분석 결과: {past_analysis}
지원자 스코어링 결과: {score_report}

스코어링 결과의 가점·감점 항목을 반드시 분석에 반영하여 아래 형식으로 보고서를 작성하세요.

[분석 결과]
(핵심 내용 — 구체적 수치·기준 포함)

[합격 전략 포인트]
(스코어링 가점 항목을 활용한 차별화 전략 포함, 지금 당장 취해야 할 액션 1~3가지)

[리스크 요소 및 보완 방안]
(감점 항목별 구체적 보완 방법 포함)
""",
    input_variables=["objective", "task", "job_context",
                     "past_analysis", "score_report"]
) | llm | parser


# ================================================================
# [섹션 5] 유틸 함수
# ================================================================

def parse_task_list(text: str) -> list:
    tasks = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line[0].isdigit():
            for sep in [".", ")"]:
                idx = line.find(sep)
                if idx != -1:
                    line = line[idx + 1:].strip()
                    break
        if line:
            tasks.append(line)
    return tasks


# ================================================================
# [섹션 6] 에이전트 메인 클래스
# ================================================================

class PublicJobAgent:
    def __init__(
        self,
        target_company: str,
        profile: Optional[YubinProfile] = None,
        pdf_path: Optional[str]         = None,
        max_iterations: int              = 5
    ):
        self.objective      = f"{target_company} 채용 공고 분석 및 맞춤형 합격 전략 수립"
        self.profile        = profile or YubinProfile()
        self.max_iterations = max_iterations
        self.task_list      = deque()
        self.completed_tasks = []
        self.vectorstore    = vectorstore
        self.iteration      = 0
        self.score_result: Optional[ScoreResult] = None   # 스코어링 결과 보관
        self.score_report:  str = "스코어링 미실행"

        # PDF 파싱
        self.job_posting_summary = "공고 PDF 미제공 — LLM 학습 데이터 기반 분석"
        self.job_raw_text        = ""
        if pdf_path:
            print(f"\n📄 공고 PDF 파싱 중: {pdf_path}")
            parsed = parse_job_pdf(pdf_path)
            self.job_posting_summary = summarize_pdf_sections(parsed)
            self.job_raw_text        = parsed["raw_text"]
            self.vectorstore.add_texts(
                [parsed["raw_text"]],
                metadatas=[{"source": parsed["source_file"]}]
            )
            print(f"   ✅ {parsed['page_count']}페이지 파싱 완료 → 벡터 저장소 인덱싱")

    # ── 스코어링 실행 ─────────────────────────────────────
    def run_scoring(self, job_text: Optional[str] = None):
        """
        공고 텍스트(또는 PDF 원문)를 기반으로 가점/감점 스코어링을 실행합니다.
        run() 호출 전에 자동 실행됩니다.
        """
        text = job_text or self.job_raw_text or self.job_posting_summary
        self.score_result = calculate_score(text, self.profile)
        self.score_report = format_score_report(self.score_result, self.objective)
        print(self.score_report)

    # ── 태스크 추가 ──────────────────────────────────────
    def add_task(self, task_name: str):
        self.task_list.append({"task_name": task_name})
        print(f"  📌 태스크 추가: {task_name}")

    # ── FAISS 검색 ───────────────────────────────────────
    def _retrieve_context(self, query: str, k: int = 2) -> str:
        try:
            docs = self.vectorstore.similarity_search(query, k=k)
            if not docs:
                return "관련 과거 분석 없음"
            return "\n---\n".join(doc.page_content[:600] for doc in docs)
        except Exception:
            return "관련 과거 분석 없음"

    # ── FAISS 저장 ───────────────────────────────────────
    def _store_result(self, task_name: str, result: str):
        self.vectorstore.add_texts(
            [f"[태스크] {task_name}\n[결과] {result}"],
            metadatas=[{"type": "analysis_result"}]
        )

    # ── 우선순위 재정렬 ──────────────────────────────────
    def _reprioritize(self):
        task_names = [t["task_name"] for t in self.task_list]
        print("\n  🔄 우선순위 재정렬 중...")
        raw = priority_chain.invoke({
            "objective":  self.objective,
            "task_names": "\n".join(f"{i+1}. {n}" for i, n in enumerate(task_names))
        })
        reordered = parse_task_list(raw)
        if reordered:
            self.task_list = deque({"task_name": n} for n in reordered)
            print(f"  정렬 결과: {reordered}")

    # ── 태스크 실행 ──────────────────────────────────────
    def _execute(self, task_name: str) -> str:
        job_context   = self._retrieve_context(task_name + " 채용 자격 조건")
        past_analysis = self._retrieve_context(task_name + " 분석 결과")

        result = execution_chain.invoke({
            "objective":    self.objective,
            "task":         task_name,
            "job_context":  job_context,
            "past_analysis":past_analysis,
            "score_report": self.score_report,   # ← 스코어링 결과 주입
        })
        self._store_result(task_name, result)
        return result

    # ── 후속 태스크 생성 ─────────────────────────────────
    def _generate_new_tasks(self, last_result: str):
        remaining    = ", ".join(t["task_name"] for t in self.task_list) or "없음"
        past_context = ", ".join(self.completed_tasks[-3:]) or "없음"

        raw = task_creation_chain.invoke({
            "objective":           self.objective,
            "result":              last_result,
            "task_description":    remaining,
            "past_context":        past_context,
            "job_posting_summary": self.job_posting_summary[:1000],
            "score_report":        self.score_report,   # ← 스코어링 결과 주입
        })

        new_tasks = parse_task_list(raw)
        print("\n  💡 후속 태스크 생성:")
        added = 0
        for task_name in new_tasks:
            if task_name not in self.completed_tasks:
                self.add_task(task_name)
                added += 1
        if added == 0:
            print("  (추가 태스크 없음 — 분석 완료)")

    # ── 메인 루프 ────────────────────────────────────────
    def run(self):
        # 스코어링 먼저 실행
        print(f"\n🏢 분석 대상: {self.objective}")
        print(f"👤 지원자: {self.profile.name}  |  토익: {self.profile.toeic}")
        print("=" * 60)

        print("\n🔢 [STEP 1] 가점/감점 스코어링 실행 중...")
        self.run_scoring()

        # D등급이면 바로 경고 후 계속 진행 (중단 여부는 사용자 선택)
        if self.score_result and self.score_result.grade == "D":
            print("\n⚠️  종합 점수가 낮습니다. 스펙 보완 후 재지원을 권장하지만 분석은 계속합니다.\n")

        print("\n🔢 [STEP 2] 에이전트 루프 시작...")

        while self.task_list:
            self.iteration += 1

            if self.iteration > self.max_iterations:
                print(f"\n🏁 최대 반복 횟수({self.max_iterations}회) 도달 — 종료합니다.")
                break

            print(f"\n[반복 {self.iteration}/{self.max_iterations}]  남은 태스크: {len(self.task_list)}개")

            if len(self.task_list) > 1:
                self._reprioritize()

            task_name = self.task_list.popleft()["task_name"]
            print(f"\n  🔎 실행 중: {task_name}")

            result = self._execute(task_name)
            self.completed_tasks.append(task_name)
            print(f"  📝 결과 (요약):\n{result[:300]}{'...' if len(result) > 300 else ''}")

            if len(self.task_list) < 2:
                self._generate_new_tasks(last_result=result)

            if not self.task_list:
                print("\n🏁 모든 태스크 완료 — 에이전트를 종료합니다.")
                break

        # 최종 요약
        print("\n" + "=" * 60)
        print("📋 완료된 분석 태스크 목록:")
        for i, t in enumerate(self.completed_tasks, 1):
            print(f"  {i}. {t}")
        print("\n📊 최종 스코어:")
        print(self.score_report)
        print("=" * 60)


# ================================================================
# 실행
# ================================================================
if __name__ == "__main__":

    # 유빈 님 프로필 (필요 시 수정)
    profile = YubinProfile(
        name          = "임유빈",
        birth_year    = 1995,
        toeic         = 780,
        opic          = "IH",
        preferred_region = "충북",
        home_region   = "충북",
    )

    agent = PublicJobAgent(
        target_company = "NIPA",
        profile        = profile,
        pdf_path       = None,        # PDF 있으면: "koica_recruit_2024.pdf"
        max_iterations = 5,
    )

    # 초기 태스크 — 응시 자격 검토 최우선
    agent.add_task("응시 자격 요건 및 결격 사유 1차 검토")
    agent.run()
