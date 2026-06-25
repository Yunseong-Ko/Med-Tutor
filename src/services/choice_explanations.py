from __future__ import annotations

import re
from typing import Any

from src.services.rag_library import search_rag_evidence


CIRCLED_TO_DIGIT = {
    "①": "1",
    "②": "2",
    "③": "3",
    "④": "4",
    "⑤": "5",
}

MARKER_RE = re.compile(r"(①|②|③|④|⑤|(?<!\d)([1-5])[\).])\s*")
COURSE_RAG_MAP = {
    "혈액": "hematology_oncology",
    "종양": "hematology_oncology",
    "hematology": "hematology_oncology",
    "oncology": "hematology_oncology",
    "신경": "neuro_special_senses",
    "특수감각": "neuro_special_senses",
    "감각기": "neuro_special_senses",
    "neuro": "neuro_special_senses",
    "neurologic": "neuro_special_senses",
    "special_senses": "neuro_special_senses",
}

NEGATIVE_STEM_PATTERNS = (
    "틀린 것은",
    "옳지 않은",
    "옳지 않는",
    "아닌 것은",
    "않은 것은",
    "부적절",
    "잘못",
    "거리가 먼",
    "해당하지",
)

# Faculty/professor comment markers that should not appear in student-facing rationale
FACULTY_COMMENT_RE = re.compile(r"@\s*[가-힣A-Za-z\s]+교수님?/@")

# Rationale phrases that are banned from student-facing output (per authoring harness)
BANNED_RATIONALE_PHRASES = (
    "정답 선지",
    "정답 선지와 더 직접적으로 연결됩니다",
    "더 직접적으로 해당합니다",
    "지문의 조건을 더 잘 만족합니다",
    "원문 해설이 짧아 검토가 필요합니다",
    "저장된 해설만으로는 배제하기 어렵습니다",
    "이 선지는 정답이 아닙니다",
    "이 선지가 정답입니다",
    "정답이 아닙니다. 이 문항의 기준은",
    "배제되는 보기입니다",
)


def normalize_answer_key(value: Any) -> str:
    text = str(value or "").strip()
    if text in CIRCLED_TO_DIGIT:
        return CIRCLED_TO_DIGIT[text]
    for marker, digit in CIRCLED_TO_DIGIT.items():
        if marker in text:
            return digit
    match = re.search(r"[1-5]", text)
    return match.group(0) if match else text


def normalize_choice_entries(question: dict[str, Any]) -> dict[str, str]:
    choices = question.get("choices") or question.get("options") or {}
    if isinstance(choices, list):
        return {str(index): str(value).strip() for index, value in enumerate(choices, start=1)}
    if isinstance(choices, dict):
        normalized: dict[str, str] = {}
        for key, value in choices.items():
            normalized[normalize_answer_key(key)] = str(value).strip()
        return dict(sorted(normalized.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 99))
    return {}


def split_marker_explanations(explanation: str) -> dict[str, str]:
    text = str(explanation or "").strip()
    matches = list(MARKER_RE.finditer(text))
    if not matches:
        return {}

    rows: dict[str, str] = {}
    for index, match in enumerate(matches):
        raw_marker = match.group(1)
        marker = CIRCLED_TO_DIGIT.get(raw_marker, normalize_answer_key(raw_marker))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip(" \n:;.-")
        if body:
            rows[marker] = body
    return rows


def split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?。！？다])\s+", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _choice_keywords(choice_text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+\-/]{2,}|[가-힣]{2,}", str(choice_text or ""))
    ignored = {
        "대한",
        "다음",
        "가장",
        "설명",
        "환자",
        "것은",
        "있는",
        "없는",
        "옳은",
        "틀린",
        "조기",
        "정상",
        "정상적",
        "정상적인",
        "유합",
        "유합은",
        "형태",
        "나타나는",
        "which",
        "following",
        "patient",
    }
    return [token.lower() for token in tokens if token.lower() not in ignored]


def find_choice_sentence(choice_text: str, explanation: str) -> str:
    keywords = [keyword for keyword in _choice_keywords(choice_text) if len(keyword) >= 4]
    if not keywords:
        return ""
    for sentence in split_sentences(explanation):
        sentence_lower = sentence.lower()
        matches = [keyword for keyword in keywords if keyword in sentence_lower]
        if len(matches) >= 2 or any(re.search(r"[a-z]", keyword) for keyword in matches):
            return sentence
    return ""


def first_sentence(text: str, *, max_chars: int = 260) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return ""
    sentence = split_sentences(cleaned)[0] if split_sentences(cleaned) else cleaned
    if len(sentence) <= max_chars:
        return sentence
    return sentence[:max_chars].rsplit(" ", 1)[0].strip() + "..."


def _labels_text(question: dict[str, Any]) -> str:
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    values: list[str] = []
    for key in ("course", "course_name", "subject", "unit", "topic", "subtopic", "question_type"):
        if labels.get(key):
            values.append(str(labels[key]))
    concept_tags = labels.get("concept_tags")
    if isinstance(concept_tags, list):
        values.extend(str(tag) for tag in concept_tags if tag)
    return " ".join(values)


def is_negative_question(question: dict[str, Any]) -> bool:
    stem = str(question.get("stem") or "")
    return any(pattern in stem for pattern in NEGATIVE_STEM_PATTERNS)


def is_craniosynostosis_question(question: dict[str, Any]) -> bool:
    choices = " ".join(normalize_choice_entries(question).values())
    haystack = " ".join(
        str(value or "")
        for value in (
            question.get("stem"),
            question.get("stimulus"),
            question.get("explanation"),
            choices,
        )
    )
    return bool(
        re.search(
            r"두개유합증|craniosynostosis|cranial\s+vault|두개천장|시상봉합|sagittal\s+suture",
            haystack,
            flags=re.I,
        )
    )


def infer_rag_course_id(question: dict[str, Any], explicit_course_id: str | None = None) -> str | None:
    if explicit_course_id:
        value = str(explicit_course_id).strip()
        return value or None
    haystack = " ".join(
        str(value or "")
        for value in (
            question.get("course_id"),
            question.get("source_exam"),
            question.get("stem"),
            question.get("stimulus"),
            _labels_text(question),
        )
    ).lower()
    for needle, course_id in COURSE_RAG_MAP.items():
        if needle.lower() in haystack:
            return course_id
    return None


def _rag_query_for_choice(question: dict[str, Any], choice_text: str) -> str:
    # Keep the query narrow. Long stems add many generic terms and often pull
    # unrelated neighboring chunks from lecture summaries.
    choice_terms = " ".join(_choice_keywords(choice_text))
    stem_terms = " ".join(_choice_keywords(question.get("stem") or "")[:8])
    parts = [
        _labels_text(question),
        choice_text,
        choice_terms,
        stem_terms,
    ]
    explanation = str(question.get("explanation") or "").strip()
    if 12 <= len(explanation) <= 180:
        parts.append(explanation)
    return re.sub(r"\s+", " ", " ".join(str(part or "") for part in parts)).strip()[:360]


def _looks_like_weak_snippet(snippet: str, choice_text: str) -> bool:
    text = str(snippet or "").strip()
    if len(text) < 24:
        return True
    if any(marker in text for marker in ("교수님", " - ", "出出", "曰:", "학습부원")) and len(text) < 120:
        return True
    choice_terms = [term for term in _choice_keywords(choice_text) if len(term) >= 3]
    if choice_terms:
        lower = text.lower()
        if not any(term in lower for term in choice_terms):
            return True
    return False


def _choice_evidence(
    question: dict[str, Any],
    choice_text: str,
    *,
    course_id: str | None,
    limit: int = 2,
) -> list[dict[str, Any]]:
    if not course_id:
        return []
    query = _rag_query_for_choice(question, choice_text)
    if not query:
        return []
    try:
        payload = search_rag_evidence(query, course_id=course_id, limit=limit)
    except (FileNotFoundError, ValueError):
        return []
    evidence_rows = [
        {
            "title": result.get("title"),
            "source_type": result.get("source_type"),
            "source_name": result.get("source_name"),
            "page_start": result.get("page_start"),
            "page_end": result.get("page_end"),
            "score": result.get("score"),
            "snippet": first_sentence(result.get("snippet") or result.get("text") or "", max_chars=260),
        }
        for result in payload.get("results", [])[:limit]
        if result.get("snippet") or result.get("text")
    ]
    strong_rows = [row for row in evidence_rows if not _looks_like_weak_snippet(row.get("snippet", ""), choice_text)]
    return strong_rows


def _compose_evidence_rationale(
    *,
    question: dict[str, Any],
    choice_text: str,
    is_correct: bool,
    is_negative: bool,
    evidence: list[dict[str, Any]],
    correct_rationale: str,
) -> str:
    evidence_sentence = first_sentence(evidence[0].get("snippet", ""), max_chars=220) if evidence else ""
    has_placeholder_anchor = "저장된 정답 근거가 부족" in correct_rationale or "확인이 필요" in correct_rationale
    correct_anchor = first_sentence(correct_rationale, max_chars=180)
    topic = _label_value(question, "subtopic") or _label_value(question, "topic") or _label_value(question, "major_category") or "이 단원"
    assessment = _label_value(question, "assessment_domain") or _question_focus(question)
    frame = f"{topic}에서 {assessment}을 판단할 때"
    if is_negative:
        if is_correct:
            if correct_anchor and not has_placeholder_anchor:
                return (
                    f"{choice_text}에서 확인해야 할 핵심은 {frame}의 기준입니다. "
                    f"원자료 근거는 {correct_anchor}이며, 이 설명에서는 개념·시점·기전 중 어느 부분이 그 기준과 어긋나는지 짚어야 합니다."
                )
            if evidence_sentence:
                return (
                    f"{choice_text}는 {frame} 함께 확인해야 하는 개념입니다. "
                    f"근거 DB에서는 {evidence_sentence}가 확인되므로, 이 진술의 어느 부분이 해당 원칙과 달라지는지 비교해야 합니다."
                )
        if evidence_sentence:
            return (
                f"{choice_text}는 {frame} 배경이 되는 개념입니다. "
                f"근거 DB에서는 {evidence_sentence}가 확인되며, 이 원칙을 기준으로 진술의 정확성을 판단합니다."
            )
        return (
            f"{choice_text}는 {frame} 함께 검토해야 하는 개념입니다. "
            "해당 진술이 어느 조건에서 성립하는지 강의록 근거를 연결해 보강해야 합니다."
        )
    if is_correct:
        if evidence_sentence:
            if has_placeholder_anchor:
                return (
                    f"{choice_text}는 {frame} 핵심이 되는 개념입니다. "
                    f"근거 DB에서는 {evidence_sentence}가 확인됩니다."
                ).strip()
            return (
                f"{choice_text}는 {frame} 핵심이 되는 개념입니다. "
                f"{first_sentence(correct_rationale, max_chars=180)} "
                f"근거 DB에서도 {evidence_sentence}"
            ).strip()
        return first_sentence(correct_rationale, max_chars=360)
    # Incorrect choice: explain the concept, then contrast it with the question's judging frame.
    if evidence_sentence:
        if has_placeholder_anchor:
            return (
                f"{choice_text}는 {evidence_sentence}와 관련된 개념입니다. "
                f"다만 이 문항은 {frame} 필요한 단서를 묻고 있으므로, 이 개념이 지문 조건을 설명하는지 따로 구분해야 합니다."
            )
        return (
            f"{choice_text}는 {evidence_sentence}와 관련된 개념이지만, "
            f"이 문항에서는 {correct_anchor}라는 기준과 구별해야 합니다."
        )
    if correct_anchor:
        return (
            f"{choice_text}는 {frame} 함께 비교해야 하는 개념입니다. "
            f"이 문항의 판단 기준은 {correct_anchor}이므로, 두 개념이 어떤 상황에서 달라지는지 설명해야 합니다."
        )
    return (
        f"{choice_text}는 {frame} 함께 검토해야 하는 개념입니다. "
        "이 개념이 지문 조건과 맞지 않는 이유를 강의록 근거로 보강해야 합니다."
    )


def _question_focus(question: dict[str, Any]) -> str:
    stem = str(question.get("stem") or "")
    if re.search(r"가장\s*흔한\s*원인", stem):
        return "가장 흔한 원인"
    if re.search(r"초기\s*처치|우선.*처치|가장\s*적절한\s*처치", stem):
        return "가장 적절한 초기 처치"
    if re.search(r"치료|처방|투여", stem):
        return "가장 적절한 치료"
    if re.search(r"진단|의심", stem):
        return "가장 가능성 높은 진단"
    if re.search(r"검사|소견", stem):
        return "가장 중요한 검사/소견"
    if is_negative_question(question):
        return "틀린 진술"
    return "지문이 묻는 핵심 기준"


def _label_value(question: dict[str, Any], key: str) -> str:
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    return str(labels.get(key) or "").strip()


def _concept_tags(question: dict[str, Any]) -> list[str]:
    labels = question.get("labels") if isinstance(question.get("labels"), dict) else {}
    tags = labels.get("concept_tags")
    if not isinstance(tags, list):
        return []
    seen: set[str] = set()
    output: list[str] = []
    for tag in tags:
        value = str(tag or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _compact_concept_path(question: dict[str, Any]) -> str:
    parts = [
        _label_value(question, "major_category"),
        _label_value(question, "topic"),
        _label_value(question, "subtopic"),
    ]
    return " > ".join(part for part in parts if part)


def _task_description(question: dict[str, Any]) -> str:
    question_type = _label_value(question, "question_type")
    domain = _label_value(question, "assessment_domain")
    focus = _question_focus(question)
    if question_type == "image_interpretation":
        return f"제시자료와 지문 단서를 함께 읽어 {domain or focus}을 판단합니다."
    if question_type == "clinical_reasoning":
        return f"임상 상황에서 {domain or focus}에 맞는 선택지를 고릅니다."
    if question_type == "knowledge_recall":
        return f"{domain or focus}에 필요한 핵심 개념을 정확히 구분합니다."
    if question_type:
        return f"{question_type} 형식으로 {domain or focus}을 확인합니다."
    return f"{focus}을 기준으로 선지를 비교합니다."


def _decision_rule(question: dict[str, Any], answer: str, choices: dict[str, str]) -> str:
    answer_text = choices.get(answer, "")
    topic = _label_value(question, "topic")
    subtopic = _label_value(question, "subtopic")
    domain = _label_value(question, "assessment_domain")
    concept = subtopic or topic or answer_text or _question_focus(question)
    if is_negative_question(question):
        return f"{concept}에 대한 진술 중 개념·시점·적응증·기전이 틀어진 부분을 찾습니다."
    if domain:
        return f"{concept}에서 {domain}을 판단하는 데 필요한 결정 기준을 찾습니다."
    return f"{concept}와 가장 잘 맞는 선지를 선택합니다."


def build_question_understanding(question: dict[str, Any], answer: str, choices: dict[str, str]) -> dict[str, Any]:
    """Build the question-level interpretation used before writing choice explanations."""
    concept_path = _compact_concept_path(question)
    tags = _concept_tags(question)
    answer_text = choices.get(answer, "")
    asked_concept = _label_value(question, "subtopic") or _label_value(question, "topic") or answer_text
    focus = _question_focus(question)
    return {
        "concept_path": concept_path,
        "major_category": _label_value(question, "major_category"),
        "topic": _label_value(question, "topic"),
        "subtopic": _label_value(question, "subtopic"),
        "assessment_domain": _label_value(question, "assessment_domain"),
        "question_type": _label_value(question, "question_type"),
        "polarity": "negative" if is_negative_question(question) else "positive",
        "asked_concept": asked_concept,
        "focus": focus,
        "task": _task_description(question),
        "decision_rule": _decision_rule(question, answer, choices),
        "answer_choice": answer,
        "answer_concept": answer_text,
        "concept_tags": tags[:8],
        "explanation_plan": [
            "문항이 묻는 개념과 평가 항목을 먼저 정한다.",
            "각 선지의 핵심 개념을 먼저 설명한다.",
            "같은 판단 기준에서 지문 조건과 맞는 부분과 어긋나는 부분을 구분한다.",
            "해설 본문에는 답 번호 비교가 아니라 학생이 외워야 할 개념을 남긴다.",
        ],
    }


def _autonomic_dysreflexia_rationale(
    *,
    choice_text: str,
    correct_choice_text: str,
    is_correct: bool,
) -> str:
    lower_choice = choice_text.lower()
    if is_correct:
        return (
            "방광팽창 또는 도뇨관 폐쇄와 같은 방광 자극은 척수손상 환자에서 "
            "자율신경 이상반사증을 유발하는 가장 흔한 원인입니다. 따라서 "
            "'가장 흔한 원인'을 묻는 이 문항에서는 방광팽창이 정답입니다."
        )
    if re.search(r"fecal|대변|매복", lower_choice):
        return (
            "대변매복은 장 자극으로 자율신경 이상반사증을 유발할 수 있습니다. "
            "하지만 이 문항은 단순 유발 가능성이 아니라 '가장 흔한 원인'을 묻고 있으며, "
            "최빈 원인은 방광팽창과 같은 방광 자극입니다."
        )
    if re.search(r"pressure|압박|injury", lower_choice):
        return (
            "압박손상은 척수손상 환자에서 관리해야 할 중요한 합병증이지만, "
            "자율신경 이상반사증의 가장 흔한 유발 요인으로 묻는 경우에는 "
            "방광팽창이 더 직접적인 정답입니다."
        )
    if re.search(r"scrotal|torsion|음낭|꼬임", lower_choice):
        return (
            "음낭꼬임은 급성 통증을 유발할 수 있으나, 척수손상 환자의 "
            "자율신경 이상반사증에서 전형적으로 가장 흔한 원인으로 묻는 항목은 아닙니다. "
            "이 문항의 핵심은 방광 자극입니다."
        )
    if re.search(r"toenail|발톱|내향성", lower_choice):
        return (
            "내향성발톱 같은 말초 통증 자극도 이론적으로 유해 자극이 될 수 있지만, "
            "자율신경 이상반사증의 가장 흔한 원인을 묻는 문항에서는 방광팽창을 우선 선택해야 합니다."
        )
    return (
        f"{choice_text}도 척수손상 환자의 유해 자극으로 고려될 수 있지만, "
        f"이 문항의 정답 기준은 '가장 흔한 원인'입니다. 그 기준에서는 {correct_choice_text}가 가장 직접적으로 해당합니다."
    )


def _autonomic_dysreflexia_learning_points(
    *,
    choice_text: str,
    is_correct: bool,
) -> list[dict[str, str]]:
    lower_choice = choice_text.lower()
    if is_correct:
        return [
            {"label": "개념", "body": "자율신경 이상반사증은 대개 T6 이상 척수손상에서 병변 아래쪽 유해 자극이 과도한 교감신경 반응을 일으키는 상태입니다."},
            {"label": "정답 근거", "body": "방광팽창, 요정체, 도뇨관 폐쇄 같은 방광 자극은 가장 흔하고 먼저 확인해야 하는 trigger입니다."},
            {"label": "기억 포인트", "body": "AD 의심 시 우선 앉히고 혈압을 확인한 뒤 방광 문제를 먼저 해결합니다."},
        ]
    if re.search(r"fecal|대변|매복", lower_choice):
        return [
            {"label": "개념", "body": "대변매복은 장 팽창·직장 자극을 통해 AD를 유발할 수 있는 실제 trigger입니다."},
            {"label": "왜 헷갈리는가", "body": "AD의 유발 요인을 묻는 문항이면 bowel problem도 맞는 후보가 될 수 있습니다."},
            {"label": "배제 기준", "body": "이 문항은 '가장 흔한 원인'을 묻기 때문에, bowel trigger보다 urinary trigger인 방광팽창이 우선입니다."},
            {"label": "기억 포인트", "body": "AD trigger는 bladder first, bowel second 순서로 떠올리면 안전합니다."},
        ]
    if re.search(r"pressure|압박|injury", lower_choice):
        return [
            {"label": "개념", "body": "압박손상은 척수손상 환자의 주요 합병증이며 통증성 피부 자극이 AD를 유발할 수 있습니다."},
            {"label": "왜 헷갈리는가", "body": "병변 아래쪽 피부 자극도 AD trigger가 될 수 있다는 점에서 완전히 무관한 보기는 아닙니다."},
            {"label": "배제 기준", "body": "가장 흔한 원인을 묻는 경우에는 피부 자극보다 방광팽창·도뇨관 폐쇄 같은 비뇨기계 자극이 우선입니다."},
            {"label": "기억 포인트", "body": "욕창은 척수손상 관리 포인트, AD 최빈 trigger는 방광 문제입니다."},
        ]
    if re.search(r"scrotal|torsion|음낭|꼬임", lower_choice):
        return [
            {"label": "개념", "body": "음낭꼬임은 급성 음낭 통증과 고환 허혈을 일으키는 응급질환입니다."},
            {"label": "왜 헷갈리는가", "body": "통증성 자극이라는 점에서는 AD의 유해 자극 범주와 연결될 수 있습니다."},
            {"label": "배제 기준", "body": "하지만 척수손상 환자의 AD에서 반복적으로 먼저 확인하는 최빈 원인은 방광팽창입니다."},
            {"label": "기억 포인트", "body": "질환 자체의 응급도와 이 문항의 빈도 기준을 분리해서 봐야 합니다."},
        ]
    if re.search(r"toenail|발톱|내향성", lower_choice):
        return [
            {"label": "개념", "body": "내향성발톱은 국소 통증·염증을 만들 수 있는 말초 유해 자극입니다."},
            {"label": "왜 헷갈리는가", "body": "AD는 병변 아래쪽의 여러 유해 자극으로 발생할 수 있어 말초 통증 자극도 후보가 됩니다."},
            {"label": "배제 기준", "body": "그러나 최빈 원인을 묻는 문항에서는 방광팽창이 내향성발톱보다 훨씬 우선입니다."},
            {"label": "기억 포인트", "body": "가능한 trigger와 가장 흔한 trigger를 구분해야 합니다."},
        ]
    return [
        {"label": "개념", "body": "AD는 병변 아래쪽 유해 자극이 과도한 교감신경 반응을 일으키는 상태입니다."},
        {"label": "배제 기준", "body": "이 문항은 가능한 trigger가 아니라 가장 흔한 trigger를 묻습니다."},
        {"label": "기억 포인트", "body": "가장 흔한 원인은 방광팽창 같은 비뇨기계 자극입니다."},
    ]


def _craniosynostosis_rationale(
    *,
    choice_text: str,
    is_correct: bool,
) -> tuple[str, str]:
    lower_choice = choice_text.lower()
    if re.search(r"cranial vault|두개천장", lower_choice):
        return (
            "두개천장(cranial vault, calvaria)은 뇌를 덮는 두개골 지붕이고, "
            "봉합선은 두개골 뼈 사이의 성장판 역할을 합니다. 두개유합증에서는 봉합이 너무 일찍 닫히면 "
            "그 봉합선에 수직인 방향의 골성장이 제한되고, 열린 봉합 방향으로 보상성 성장이 일어납니다.",
            "concept_comparison",
        )
    if re.search(r"crouzon|크루존|brachycephaly|단두", lower_choice):
        return (
            "Crouzon syndrome은 증후군성 두개유합증의 대표 질환입니다. 관상봉합, 특히 양측 관상봉합이 "
            "조기에 유합되면 두개골의 앞뒤 성장이 제한되어 전후경이 짧아지는 단두증(brachycephaly)이 "
            "나타날 수 있습니다.",
            "concept_comparison",
        )
    if re.search(r"lambdoid|삼각봉합|plagiocephaly|편평두", lower_choice):
        return (
            "Lambdoid suture는 뒤쪽 두개골에서 두정골과 후두골 사이를 잇는 봉합입니다. "
            "한쪽 lambdoid suture가 조기에 유합되면 후두부 성장이 비대칭이 되어 posterior plagiocephaly로 "
            "나타날 수 있습니다.",
            "concept_comparison",
        )
    if re.search(r"sagittal|시상봉합", lower_choice):
        return (
            "시상봉합(sagittal suture)은 양쪽 두정골 사이를 정중선에서 잇는 봉합입니다. 이 정답지 기준에서는 "
            "시상봉합의 정상 유합 시작 시점을 10세 초반으로 보므로, 정상 유합이 1세 전후에 시작된다는 서술은 "
            "너무 이릅니다. 시상봉합이 병적으로 조기 유합되면 전후로 긴 주상두(scaphocephaly)가 나타날 수 있습니다.",
            "concept_comparison",
        )
    if re.search(r"metopic|전두봉합|trigonocephaly|삼각두", lower_choice):
        return (
            "Metopic suture는 이마 중앙에서 양측 전두골 사이를 잇는 봉합입니다. 전두봉합이 조기에 유합되면 "
            "이마가 삼각형처럼 좁아지고 안와 사이가 좁아지는 trigonocephaly가 나타날 수 있습니다.",
            "concept_comparison",
        )
    if is_correct:
        return (
            "두개유합증에서는 봉합 위치, 조기 유합 시 성장 제한 방향, 결과적 두개골 형태를 함께 비교해야 합니다.",
            "concept_comparison",
        )
    return (
        "두개유합증은 봉합 위치와 조기 유합 후 나타나는 두개골 형태를 연결해 이해합니다.",
        "concept_comparison",
    )


def _craniosynostosis_learning_points(
    *,
    choice_text: str,
    is_correct: bool,
) -> list[dict[str, str]]:
    lower_choice = choice_text.lower()
    if re.search(r"cranial vault|두개천장", lower_choice):
        return [
            {"label": "두개천장", "body": "두개천장(cranial vault, calvaria)은 뇌를 덮는 두개골의 지붕 부분으로, 전두골·두정골·후두골 등이 봉합선으로 연결되어 성장합니다."},
            {"label": "봉합선", "body": "두개골 봉합선은 단순한 선이 아니라 성장판처럼 작동하는 섬유성 결합부입니다. 영아기와 소아기 두개골 성장은 이 봉합선을 통해 일어납니다."},
            {"label": "핵심 법칙", "body": "봉합이 조기에 유합되면 그 봉합선에 수직인 방향의 성장이 제한되고, 상대적으로 열린 봉합 방향으로 보상성 성장이 일어납니다."},
        ]
    if re.search(r"crouzon|크루존|brachycephaly|단두", lower_choice):
        return [
            {"label": "질환 연결", "body": "Crouzon syndrome은 craniosynostosis를 동반할 수 있는 대표적 증후군성 두개유합증입니다."},
            {"label": "형태", "body": "양측 관상봉합 유합이 있으면 앞뒤 길이가 짧고 좌우 폭이 넓은 단두증(brachycephaly) 형태가 나타날 수 있습니다."},
            {"label": "동반 소견", "body": "안구돌출, 중안면 저형성, 상악 저형성 같은 얼굴뼈 발달 이상이 함께 나타날 수 있습니다."},
        ]
    if re.search(r"lambdoid|삼각봉합|plagiocephaly|편평두", lower_choice):
        return [
            {"label": "봉합 위치", "body": "Lambdoid suture는 후두골과 두정골 사이에 있는 뒤쪽 봉합입니다."},
            {"label": "형태", "body": "한쪽 lambdoid suture가 조기에 유합되면 뒤쪽 두개골 성장이 비대칭이 되어 posterior plagiocephaly가 나타날 수 있습니다."},
            {"label": "임상 구분", "body": "위치성 사두증과 달리 lambdoid synostosis는 봉합 조기 유합에 따른 구조적 비대칭입니다."},
        ]
    if re.search(r"sagittal|시상봉합", lower_choice):
        return [
            {"label": "봉합 위치", "body": "시상봉합(sagittal suture)은 양쪽 두정골 사이를 정중선에서 잇는 봉합입니다."},
            {"label": "정상 유합", "body": "이 정답지 기준에서는 시상봉합의 정상 유합 시작 시점을 10세 초반으로 봅니다. 1세 전후 시작이라는 서술은 정상 유합 시점으로는 너무 이릅니다."},
            {"label": "조기 유합", "body": "시상봉합이 병적으로 조기 유합되면 좌우 방향 성장이 제한되고 전후 방향 성장이 상대적으로 두드러져 주상두(scaphocephaly)가 나타날 수 있습니다."},
        ]
    if re.search(r"metopic|전두봉합|trigonocephaly|삼각두", lower_choice):
        return [
            {"label": "봉합 위치", "body": "Metopic suture는 이마 중앙에서 양측 전두골 사이를 연결하는 봉합입니다."},
            {"label": "형태", "body": "Metopic suture가 조기에 유합되면 이마가 삼각형처럼 좁아지는 trigonocephaly가 나타날 수 있습니다."},
            {"label": "임상 소견", "body": "전두부 중앙 융기, 양측 전두부 협소화, 안와 사이 거리 감소가 함께 관찰될 수 있습니다."},
        ]
    return [
        {"label": "개념", "body": "두개유합증은 두개골 봉합이 정상보다 일찍 닫혀 두개골 성장 방향과 머리 모양이 달라지는 질환군입니다."},
        {"label": "검토 기준", "body": "봉합 위치, 조기 유합 시 성장 제한 방향, 결과적 두개골 형태를 각각 분리해 연결합니다."},
    ]


def _compose_choice_comparison_rationale(
    *,
    question: dict[str, Any],
    choice_text: str,
    correct_choice_text: str,
    is_correct: bool,
) -> tuple[str, str]:
    stem = str(question.get("stem") or "")
    if is_craniosynostosis_question(question):
        return _craniosynostosis_rationale(
            choice_text=choice_text,
            is_correct=is_correct,
        )
    if re.search(r"자율신경\s*이상반사|autonomic\s*dysreflexia", stem, flags=re.I):
        return (
            _autonomic_dysreflexia_rationale(
                choice_text=choice_text,
                correct_choice_text=correct_choice_text,
                is_correct=is_correct,
            ),
            "concept_comparison",
        )

    focus = _question_focus(question)
    # Generic fallback: this is only a safe placeholder for the review queue.
    # It should not pretend to be a finished medical explanation.
    topic = _label_value(question, "subtopic") or _label_value(question, "topic") or focus
    assessment = _label_value(question, "assessment_domain") or focus
    if is_correct:
        return (
            f"{correct_choice_text}는 {topic}에서 {assessment}을 판단할 때 기준이 되는 개념입니다. "
            "지문 단서와 이 개념이 연결되는 세부 근거를 보강해야 합니다.",
            "needs_manual_content",
        )
    return (
        f"{choice_text}는 {topic}과 함께 비교해야 하는 개념입니다. "
        f"{assessment}이라는 같은 기준에서 지문 조건과 맞는지 확인해야 합니다.",
        "needs_manual_content",
    )


def _existing_choice_explanations(question: dict[str, Any]) -> dict[str, str]:
    candidates = [
        question.get("choice_explanations"),
        (question.get("pma_solution") or {}).get("choice_explanations")
        if isinstance(question.get("pma_solution"), dict)
        else None,
        question.get("explanations_by_choice"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            rows: dict[str, str] = {}
            for key, value in candidate.items():
                if isinstance(value, dict):
                    body = str(
                        value.get("rationale")
                        or value.get("explanation")
                        or value.get("text")
                        or ""
                    ).strip()
                else:
                    body = str(value).strip()
                if body:
                    rows[normalize_answer_key(key)] = body
            if rows:
                return rows
        if isinstance(candidate, list):
            rows: dict[str, str] = {}
            for index, value in enumerate(candidate, start=1):
                if str(value).strip():
                    rows[str(index)] = str(value).strip()
            if rows:
                return rows
    return {}


def build_choice_explanation_draft(
    question: dict[str, Any],
    *,
    course_id: str | None = None,
    use_rag: bool = True,
) -> dict[str, Any]:
    choices = normalize_choice_entries(question)
    answer = normalize_answer_key(question.get("answer"))
    explanation = str(question.get("explanation") or "").strip()
    existing_map = _existing_choice_explanations(question)
    marker_map = split_marker_explanations(explanation)
    rag_course_id = infer_rag_course_id(question, course_id) if use_rag else None
    negative_question = is_negative_question(question)
    correct_rationale = (
        existing_map.get(answer)
        or marker_map.get(answer)
        or explanation
        or "저장된 정답 근거가 부족합니다. 강의록 또는 정답지 해설 확인이 필요합니다."
    )
    correct_choice_text = choices.get(answer, "정답 선지")
    question_understanding = build_question_understanding(question, answer, choices)

    choice_explanations: dict[str, dict[str, Any]] = {}
    needs_review_count = 0
    for key, choice_text in choices.items():
        is_correct = key == answer
        source = "existing_choice_explanation"
        rationale = existing_map.get(key, "")
        learning_points: list[dict[str, str]] = []
        evidence: list[dict[str, Any]] = []
        if not rationale:
            source = "marked_explanation"
            rationale = marker_map.get(key, "")
        if not rationale:
            source = "choice_mention"
            rationale = find_choice_sentence(choice_text, explanation)
        if use_rag:
            evidence = _choice_evidence(
                question,
                choice_text,
                course_id=rag_course_id,
                limit=2,
            )
        if not rationale and evidence:
            source = "rag_evidence_draft"
            rationale = _compose_evidence_rationale(
                question=question,
                choice_text=choice_text,
                is_correct=is_correct,
                is_negative=negative_question,
                evidence=evidence,
                correct_rationale=correct_rationale,
            )
        if not rationale and is_correct:
            source = "correct_rationale"
            if negative_question:
                rationale = (
                    f"{choice_text}에서 확인해야 할 핵심은 "
                    f"{_label_value(question, 'subtopic') or _label_value(question, 'topic') or _question_focus(question)}입니다. "
                    f"원자료 근거는 {first_sentence(correct_rationale, max_chars=180)}입니다."
                )
            else:
                rationale = correct_rationale
        if not rationale or "저장된 정답 근거가 부족" in rationale or "현재 저장된 해설" in rationale:
            rationale, source = _compose_choice_comparison_rationale(
                question=question,
                choice_text=choice_text,
                correct_choice_text=correct_choice_text,
                is_correct=is_correct,
            )
        if re.search(r"자율신경\s*이상반사|autonomic\s*dysreflexia", str(question.get("stem") or ""), flags=re.I):
            rationale, source = _compose_choice_comparison_rationale(
                question=question,
                choice_text=choice_text,
                correct_choice_text=correct_choice_text,
                is_correct=is_correct,
            )
            learning_points = _autonomic_dysreflexia_learning_points(
                choice_text=choice_text,
                is_correct=is_correct,
            )
            evidence = []
        if is_craniosynostosis_question(question):
            rationale, source = _compose_choice_comparison_rationale(
                question=question,
                choice_text=choice_text,
                correct_choice_text=correct_choice_text,
                is_correct=is_correct,
            )
            learning_points = _craniosynostosis_learning_points(
                choice_text=choice_text,
                is_correct=is_correct,
            )
            evidence = []
        # Strip faculty comment markers that must not appear in student-facing output.
        rationale = FACULTY_COMMENT_RE.sub("", rationale).strip()
        # Flag any remaining banned phrases or empty rationale for manual review.
        needs_review = source == "needs_manual_content" or not rationale or any(
            phrase in rationale for phrase in BANNED_RATIONALE_PHRASES
        )
        if not rationale:
            needs_review = True
            source = "needs_manual_review"
            rationale = (
                f"{choice_text}에 대한 개념 해설이 아직 작성되지 않았습니다. "
                f"강의록에서 {_label_value(question, 'topic') or '해당 개념'}을 확인하십시오."
            )
        if needs_review:
            needs_review_count += 1

        choice_explanations[key] = {
            "choice_number": key,
            "choice_text": choice_text,
            "is_correct": is_correct,
            "statement_status": (
                "false_statement" if negative_question and is_correct
                else "true_statement" if negative_question
                else "best_answer" if is_correct
                else "distractor"
            ),
            "rationale": rationale,
            "learning_points": learning_points,
            "source": source,
            "needs_review": needs_review,
            "evidence": evidence,
            "question_polarity": "negative" if negative_question else "positive",
        }

    return {
        "question_id": question.get("question_id") or question.get("id"),
        "answer": answer,
        "correct_rationale": correct_rationale,
        "question_understanding": question_understanding,
        "choice_explanations": choice_explanations,
        "needs_review_count": needs_review_count,
        "rag_course_id": rag_course_id,
        "question_polarity": "negative" if negative_question else "positive",
        "draft_policy": (
            "docs/Choice_Explanation_Authoring_Harness_20260620.md 기준으로 선지별 해설을 작성합니다. "
            "저장된 선지별 해설을 우선 사용하되, 의미 없는 placeholder는 금지하고 로컬 RAG 근거 또는 기존 정답지 해설로 보강합니다. "
            "negative 문항에서는 해설 본문에 판정 문장을 쓰지 않고, 각 진술의 개념·시점·기전 설명을 먼저 작성합니다."
        ),
    }
