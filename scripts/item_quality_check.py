#!/usr/bin/env python3
"""문항 품질 자동 스캐너 — item-writing 결함 검사(규칙 기반).

근거: Tarrant 2006(Nurse Educ Today), Costello 2018(BMC Res Notes),
      Haladyna 계열 item-writing 가이드라인. MCQ의 46~50%가 결함을 가진다는 문헌에 대응.
자동 검출 가능한 결함만 규칙화하고, 각 문항에 item_quality를 부착한다(사람 검토 보조).

사용: python3 scripts/item_quality_check.py <extracted_json...>  [--commit]
"""

import re
import sys
import json
from pathlib import Path

NEG = re.compile(r"아닌\s*것|않는\s*것|옳지\s*않|틀린\s*것|거리가\s*먼|해당(하지|되지)\s*않|부적절한\s*것|잘못된\s*것")
ABS = re.compile(r"항상|절대|반드시|결코|전혀|무조건|모든\s*경우")
VAGUE = re.compile(r"대개|보통|흔히|가끔|종종|일반적으로")
ALLNONE = re.compile(r"위(의|)\s*모(두|든)|모두\s*(맞|옳|해당)|정답\s*없음|해당\s*없음|답\s*없음")
AGE = re.compile(r"\d+\s*(세|개월|주|일)")
VITALS = re.compile(r"혈압|맥박|호흡|체온|mmHg|℃")
URGENCY = re.compile(r"즉시|먼저|우선|응급|지체\s*없이|지체하지\s*말고|가장\s*먼저")
SPECIALTY = re.compile(
    r"(?:내과|외과|소아과|산부인과|신경과|정신과|정형외과|피부과|안과|이비인후과|"
    r"순환기|소화기|호흡기|내분비|신장|류마티스|혈액종양|감염|종양)학?적(?:으로|인)?|"
    r"(?:내과|외과|소아과|산부인과|신경과|정신과|정형외과|피부과|안과|이비인후과)\s*(?:외래|병동|의사|협의)"
)
DIRECT_DIAGNOSIS = re.compile(
    r"(?:으로|로)\s*(?:확진|진단)(?:되|받)|"
    r"확정\s*진단|확진된|진단은\s*[^?.\n]{1,30}(?:이다|였다)"
)
PATHOLOGY_CUE = re.compile(r"조직\s*검사|생검|병리\s*소견|면역\s*염색|조직학적")
CONFIRMATORY_CUE = re.compile(r"확진\s*검사|특이도|특이적\s*소견|진단\s*기준을?\s*만족|진단되")
COVER_TARGET = re.compile(
    r"진단|검사|처치|치료|약물|기전|원인|위험\s*인자|합병증|예후|경과|중증도|병기|예방|판독|의미|해석"
)
OPTION_DEPENDENT_LEAD_IN = re.compile(r"다음\s*중|어느\s*것|옳은\s*것|적절한\s*것")
THROMBOLYSIS_OPTION = re.compile(
    r"혈전\s*용해|알테플라제|alteplase|thrombol|fibrinol",
    re.IGNORECASE,
)
RECENT_SURGERY_CONTEXT = re.compile(
    r"(?:최근\s*)?(?:수술|시술|치환술|절제술|개두술|surgery|operation)\s*(?:후|뒤|이후|이내|recent)|"
    r"(?:수술|시술|치환술|절제술|개두술)\s*후\s*\d+\s*(?:시간|일|주|개월)",
    re.IGNORECASE,
)
DISCLOSURE_QC_FLAWS = {
    "diagnosis_leak",
    "overdetermined_diagnosis",
    "target_already_resolved",
    "redundant_confirmatory_evidence",
    "rag_to_stem_copy",
    "unsupported_precision",
    "task_evidence_mismatch",
    "malicious_red_herring",
    "missing_disclosure_plan",
    "disclosure_budget_exceeded",
    "patient_characteristic_bias",
}
NEGATED_FINDING = re.compile(
    r"([0-9A-Za-z가-힣_\-/ ]{2,30}?)(?:은|는|이|가|소견은)?\s*"
    r"(?:없다|없었다|관찰되지\s*않았다|음성이다|정상이다)"
)

SELF_CHECK_KEYS = (
    "undifferentiated_no_specialty_leak",
    "reasoning_hops_ge_2_real_not_recognition",
    "single_best_positive_lead_in",
    "lead_in_choice_consistent",
    "exactly_5_choices",
    "no_negative_stem",
    "no_all_or_none",
    "no_absolute_term",
    "no_vague_term",
    "key_length_rank_2_to_4_not_longest_not_shortest",
    "key_len_ratio_0_8_to_1_2",
    "key_not_most_components",
    "urgency_adverb_not_key_only",
    "no_clang_cue",
    "no_duplicate_or_overlapping_choices",
    "is_clinical_vignette_not_low_cognitive",
    "covers_the_options_passes",
    "distractors_homogeneous_same_category_and_form",
    "every_distractor_from_differential_or_misconception",
    "no_distractor_precluded_by_stem",
    "evidence_within_inherited_only",
    "cognitive_level_label_matches_actual",
)

ANSWER_DECLARATION = re.compile(
    r"(?:정답|답)\s*(?:은|:)?\s*(?:제\s*)?([1-5①②③④⑤])\s*번?",
    re.IGNORECASE,
)
HARRISON_LOCATOR = re.compile(
    r"Harrison\s*22e?.{0,20}Ch\.?\s*\d+.{0,20}p\.?\s*\d+",
    re.IGNORECASE,
)
HARRISON_MARKER = re.compile(r"(?:^|[^A-Z0-9])H([1-9]\d*)(?:$|[^A-Z0-9])")


def _flatten_explanation_text(q):
    parts = [str(q.get("explanation") or "")]
    pma = q.get("pma_solution") if isinstance(q.get("pma_solution"), dict) else {}
    for key in ("reasoning_summary", "correct_reason", "high_yield_point", "source_anchor"):
        parts.append(str(pma.get(key) or ""))
    pma_choices = pma.get("choice_explanations") if isinstance(pma.get("choice_explanations"), dict) else {}
    parts.extend(str(value or "") for value in pma_choices.values())
    for value in (q.get("choice_explanations") or {}).values() if isinstance(q.get("choice_explanations"), dict) else []:
        if isinstance(value, dict):
            parts.extend(str(value.get(key) or "") for key in ("verdict", "rationale", "explanation"))
        else:
            parts.append(str(value or ""))
    return "\n".join(parts)


def _answer_key_explanation_mismatch(q, choices, answer):
    explanations = q.get("choice_explanations") if isinstance(q.get("choice_explanations"), dict) else {}
    for key, value in explanations.items():
        if not isinstance(value, dict):
            continue
        normalized_key = str(key)
        verdict = str(value.get("model_verdict") or value.get("declared_verdict") or value.get("verdict") or "")
        if verdict == "정답" and normalized_key != answer:
            return True
        if verdict == "오답" and normalized_key == answer:
            return True

    circled = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}
    declared = {
        circled.get(match.group(1), match.group(1))
        for match in ANSWER_DECLARATION.finditer(_flatten_explanation_text(q))
    }
    if declared and (declared != {answer}):
        return True

    cognitive = q.get("cognitive_model") if isinstance(q.get("cognitive_model"), dict) else {}
    answer_concept = re.sub(r"[^0-9a-z가-힣]+", "", str(cognitive.get("answer_concept") or "").casefold())
    selected = re.sub(r"[^0-9a-z가-힣]+", "", str(choices.get(answer) or "").casefold())
    if answer_concept and selected and len(answer_concept) >= 4:
        if answer_concept not in selected and selected not in answer_concept:
            # Only reject when another option directly names the declared
            # concept.  This avoids false positives from abbreviations or
            # paraphrased treatment choices.
            other_match = any(
                answer_concept in re.sub(r"[^0-9a-z가-힣]+", "", str(text).casefold())
                for key, text in choices.items()
                if key != answer
            )
            if other_match:
                return True
    return False


def _ontology_rag_flaws(q, choices, answer):
    flaws = []
    trace = q.get("grounding_trace") if isinstance(q.get("grounding_trace"), dict) else {}
    explanations = q.get("choice_explanations") if isinstance(q.get("choice_explanations"), dict) else {}
    if trace:
        if trace.get("all_distractors_in_scope") is not True:
            flaws.append("distractor_not_ontology_grounded")
        else:
            for key in choices:
                if key == answer:
                    continue
                row = explanations.get(key) or explanations.get(int(key)) or {}
                if not isinstance(row, dict) or not str(row.get("source_id") or row.get("misconception_id") or "").strip():
                    flaws.append("distractor_not_ontology_grounded")
                    break

    answer_level = str(trace.get("answer_concept_level") or "").strip()
    distractor_levels = {
        str((explanations.get(key) or explanations.get(int(key)) or {}).get("concept_level") or "").strip()
        for key in choices
        if key != answer and isinstance(explanations.get(key) or explanations.get(int(key)) or {}, dict)
    }
    distractor_levels.discard("")
    if answer_level and distractor_levels and any(level != answer_level for level in distractor_levels):
        flaws.append("syndrome_vs_disease_heterogeneous")

    harrison_sources = q.get("harrison_sources") if isinstance(q.get("harrison_sources"), list) else []
    if not harrison_sources:
        evidence = q.get("grounding_evidence") if isinstance(q.get("grounding_evidence"), dict) else {}
        harrison_sources = evidence.get("harrison_sources") if isinstance(evidence.get("harrison_sources"), list) else []
    ontology_item = bool(trace or q.get("disease_concept_id") or harrison_sources)
    if ontology_item:
        explanation_text = _flatten_explanation_text(q)
        cited_ids = {f"H{match.group(1)}" for match in HARRISON_MARKER.finditer(explanation_text)}
        allowed_ids = {
            str(row.get("source_id") or "")
            for row in harrison_sources
            if isinstance(row, dict) and row.get("chapter") and row.get("printed_page")
        }
        exact_locator = bool(HARRISON_LOCATOR.search(explanation_text))
        if not allowed_ids or (not exact_locator and not (cited_ids & allowed_ids)):
            flaws.append("explanation_missing_source")
        elif any(
            str(row.get("source_id") or "") in cited_ids
            and str(row.get("entailment_status") or "").strip().casefold() != "verified"
            for row in harrison_sources
            if isinstance(row, dict)
        ):
            # Retrieval membership and a page number are not semantic
            # entailment. Keep the item in faculty review until a separate
            # validator/human promotes the cited claim.
            flaws.append("explanation_source_unverified")
    return flaws


def kwords(s):
    return set(w for w in re.findall(r"[가-힣]{2,}", s or "") if len(w) >= 3)


def normalize_choices(q):
    raw = q.get("choices") or q.get("options") or {}
    if isinstance(raw, dict):
        return {
            str(i): str(raw.get(str(i)) or raw.get(i) or "").strip()
            for i in range(1, 6)
            if str(raw.get(str(i)) or raw.get(i) or "").strip()
        }
    if isinstance(raw, list):
        return {str(i): str(value or "").strip() for i, value in enumerate(raw[:5], 1) if str(value or "").strip()}
    return {}


def component_count(text):
    """Estimate how many coordinated actions/concepts an option contains.

    This intentionally stays conservative: only explicit coordinators, list
    punctuation, or repeated action nouns increase the count.
    """
    value = str(text or "").strip()
    if not value:
        return 0
    structural_value = re.sub(r"(?<=\d),(?=\d)", "", value)
    coordinators = len(re.findall(r"\s(?:및|그리고|후|뒤|동시에)\s|[가-힣](?:와|과)\s+|[+,;·]", structural_value))
    action_nouns = len(re.findall(r"투여|시행|삽입|제거|중단|관찰|전원|협의|수술|검사|처치|치료", value))
    return 1 + coordinators + max(0, action_nouns - 1)


def key_length_rank(choice_map, answer):
    if answer not in choice_map or len(choice_map) != 5:
        return None
    lengths = {key: len(re.sub(r"\s+", "", value)) for key, value in choice_map.items()}
    return 1 + sum(length > lengths[answer] for length in lengths.values())


def distractor_precluded(stem, choice_map, answer, q):
    explanations = q.get("choice_explanations") or (q.get("pma_solution") or {}).get("choice_explanations") or {}
    for key, text in choice_map.items():
        if key == answer:
            continue
        explanation = explanations.get(key) or explanations.get(int(key)) if isinstance(explanations, dict) else ""
        if isinstance(explanation, dict):
            explanation = " ".join(str(value) for value in explanation.values())
        if re.search(r"지문|문두|stem", str(explanation), re.I) and re.search(r"배제|맞지\s*않|없으므로|정상이므로", str(explanation)):
            return True
        choice_words = kwords(text)
        for match in NEGATED_FINDING.finditer(stem):
            if choice_words & kwords(match.group(1)):
                return True
    return False


def scan_item(q):
    stem = str(q.get("stem") or q.get("problem") or "")
    lead_in = str(q.get("lead_in") or "")
    full_stem = f"{stem} {lead_in}".strip()
    choices = normalize_choices(q)
    ans = str(q.get("answer") or "")
    flaws = []
    disclosure_plan = q.get("evidence_disclosure_plan") if isinstance(q.get("evidence_disclosure_plan"), dict) else {}
    assessment_task = str(
        q.get("target_axis_type")
        or disclosure_plan.get("assessment_task")
        or q.get("question_type")
        or ""
    ).strip().lower()
    diagnosis_is_assessment_target = assessment_task in {"diagnosis", "diagnostic"}
    latent_diagnosis_required = bool(disclosure_plan.get("latent_diagnosis_required"))

    # 1) 부정 문두
    if NEG.search(full_stem):
        flaws.append("negative_stem")
    # 2) 선지 개수 <5
    ch = [choices.get(k) for k in ("1", "2", "3", "4", "5") if choices.get(k)]
    if len(ch) < 5:
        flaws.append("fewer_than_5_choices")
    # 3) all/none of the above
    if any(ALLNONE.search(c or "") for c in ch):
        flaws.append("all_or_none_of_above")
    # 4) 선지 절대어
    if any(ABS.search(c or "") for c in ch):
        flaws.append("absolute_term_in_option")
    # 5) 선지 모호어
    if any(VAGUE.search(c or "") for c in ch):
        flaws.append("vague_term_in_option")
    # 6) 정답 길이 순위: 5지 중 독보적 최장/최단이면 단서가 된다.
    length_rank = key_length_rank(choices, ans)
    if length_rank is not None:
        lens = {key: len(re.sub(r"\s+", "", value)) for key, value in choices.items()}
        correct_len = lens[ans]
        other_lens = [value for key, value in lens.items() if key != ans]
        short_atomic_labels = (
            all(component_count(value) == 1 for value in choices.values())
            and max(lens.values()) <= 12
        )
        if not short_atomic_labels:
            if correct_len > max(other_lens):
                flaws.extend(["longest_is_key", "key_length_rank"])
            elif correct_len < min(other_lens):
                flaws.extend(["shortest_is_key", "key_length_rank"])
    # 7) 문두 단서 누출(정답 선지의 특이 단어가 문두에도 등장)
    if ans in choices:
        overlap = kwords(choices[ans]) & kwords(full_stem)
        # 흔한 임상어 제외 위해 3글자↑ 명사만, 2개↑ 겹치면 의심
        if len(overlap) >= 2:
            flaws.append("clang_cue_stem_option")
        # Recent major surgery is both a VTE risk factor and a clinically
        # important fibrinolysis contraindication/relative contraindication.
        # It cannot be used as harmless background when systemic thrombolysis
        # is presented as an unambiguous single best answer.
        if THROMBOLYSIS_OPTION.search(choices[ans]) and RECENT_SURGERY_CONTEXT.search(full_stem):
            flaws.append("answer_contraindicated_by_stem")
    # 8) 중복/포함 선지
    texts = [re.sub(r"\s+", "", c or "") for c in ch]
    if len(set(texts)) < len(texts):
        flaws.append("duplicate_choices")
    # 9) 저인지수준 의심(임상 비네트 아님: 나이·활력징후 없음 + 짧은 문두)
    cognitive_low = not (AGE.search(full_stem) or VITALS.search(full_stem)) and len(full_stem) < 60

    # 10) 정답이 가장 포괄적인 선지라는 형태 단서
    if ans in choices and len(choices) == 5:
        counts = {key: component_count(value) for key, value in choices.items()}
        others = [value for key, value in counts.items() if key != ans]
        if counts[ans] >= 2 and others and counts[ans] > max(others):
            flaws.append("most_components_is_key")

    # 11) 긴급 부사가 정답에만 들어가는 언어 단서
    if ans in choices and URGENCY.search(choices[ans]):
        if not any(URGENCY.search(value) for key, value in choices.items() if key != ans):
            flaws.append("urgency_adverb_only_in_key")

    # 12) 확정 진단 노출 또는 독립적 확정 단서 복합은 실질 1-hop으로 본다.
    if (
        (DIRECT_DIAGNOSIS.search(full_stem) and (diagnosis_is_assessment_target or latent_diagnosis_required))
        or (PATHOLOGY_CUE.search(full_stem) and CONFIRMATORY_CUE.search(full_stem) and diagnosis_is_assessment_target)
    ):
        flaws.append("over_cueing")

    # 13) stem이 이미 배제한 소견을 근거로 삼는 오답(보수적 휴리스틱)
    if distractor_precluded(full_stem, choices, ans, q):
        flaws.append("no_distractor_precluded_by_stem")

    # 14) reveal_specialty=false 기본값에 어긋나는 분과/확정진단 누설
    reveal_specialty = bool(q.get("reveal_specialty", False))
    if not reveal_specialty and (
        SPECIALTY.search(full_stem)
        or (DIRECT_DIAGNOSIS.search(full_stem) and latent_diagnosis_required)
    ):
        flaws.append("specialty_leak")

    # 15) 선지를 가려도 요구되는 답의 범주가 문두에 명확해야 한다.
    lead = lead_in or (re.split(r"(?<=[?.])\s+", stem.strip())[-1] if stem.strip() else "")
    covers = bool(COVER_TARGET.search(lead))
    if not covers or (OPTION_DEPENDENT_LEAD_IN.search(lead) and not COVER_TARGET.search(lead)):
        flaws.append("covers_the_options")

    # 16) Ontology/RAG에서 stem으로 공개한 단서 계획의 구조화 QC 결과.
    for flag in disclosure_plan.get("qc_flags") or []:
        normalized_flag = str(flag).strip()
        if normalized_flag in DISCLOSURE_QC_FLAWS:
            flaws.append(normalized_flag)
    if disclosure_plan.get("target_already_resolved"):
        flaws.append("target_already_resolved")
    if disclosure_plan and disclosure_plan.get("status") == "blocked" and not disclosure_plan.get("qc_flags"):
        flaws.append("disclosure_plan_blocked")

    # Do not trust the model's self-check.  Reconcile the persisted answer key
    # with both structured verdicts and textual declarations deterministically.
    if _answer_key_explanation_mismatch(q, choices, ans):
        flaws.append("answer_key_explanation_mismatch")

    # Verify ontology provenance, choice-level homogeneity, and exact Harrison
    # source membership from the stored item record (not from model confidence).
    flaws.extend(_ontology_rag_flaws(q, choices, ans))

    flaws = list(dict.fromkeys(flaws))
    return {
        "flaws": flaws,
        "flaw_count": len(flaws),
        "cognitive_low_suspect": cognitive_low,
        "key_length_rank": length_rank,
    }


def _choice_explanations(q):
    value = q.get("choice_explanations") or (q.get("pma_solution") or {}).get("choice_explanations") or {}
    return value if isinstance(value, dict) else {}


def _all_distractors_have_misconceptions(q):
    answer = str(q.get("answer") or "")
    explanations = _choice_explanations(q)
    for key in ("1", "2", "3", "4", "5"):
        if key == answer:
            continue
        value = explanations.get(key) or explanations.get(int(key))
        if not isinstance(value, dict):
            return False
        if not str(value.get("misconception") or value.get("misconception_id") or value.get("why_attractive") or "").strip():
            return False
    return True


def _key_length_ratio(q):
    choices = normalize_choices(q)
    answer = str(q.get("answer") or "")
    if answer not in choices or len(choices) != 5:
        return None
    lengths = {key: len(re.sub(r"\s+", "", value)) for key, value in choices.items()}
    other_lengths = [value for key, value in lengths.items() if key != answer]
    if not other_lengths or not sum(other_lengths):
        return None
    if all(component_count(value) == 1 for value in choices.values()) and max(lengths.values()) <= 12:
        # Atomic drug/test/disease labels remain homogeneous even when their
        # lexical lengths differ (e.g. imatinib vs allogeneic HSCT).
        return 1.0
    return lengths[answer] / (sum(other_lengths) / len(other_lengths))


def evaluate_self_check(q, quality=None):
    """Re-evaluate the 22 generation checks, overriding model claims where possible."""
    quality = quality or scan_item(q)
    model_claims = q.get("self_check") if isinstance(q.get("self_check"), dict) else {}
    checks = {key: bool(model_claims.get(key, False)) for key in SELF_CHECK_KEYS}
    flaws = set(quality.get("flaws") or [])
    choices = normalize_choices(q)
    cognitive_model = q.get("cognitive_model") if isinstance(q.get("cognitive_model"), dict) else {}
    disclosure_plan = q.get("evidence_disclosure_plan") if isinstance(q.get("evidence_disclosure_plan"), dict) else {}
    grounding_trace = q.get("grounding_trace") if isinstance(q.get("grounding_trace"), dict) else {}
    ratio = _key_length_ratio(q)
    reasoning_hops = q.get("reasoning_hops", 0)
    try:
        reasoning_hops = int(reasoning_hops)
    except (TypeError, ValueError):
        reasoning_hops = 0

    checks.update(
        {
            "undifferentiated_no_specialty_leak": "specialty_leak" not in flaws,
            "reasoning_hops_ge_2_real_not_recognition": (
                reasoning_hops >= 2
                and bool(
                    cognitive_model.get("decision_cues")
                    or cognitive_model.get("answer_concept")
                    or disclosure_plan.get("selected_for_stem")
                )
                and "over_cueing" not in flaws
                and "target_already_resolved" not in flaws
            ),
            "single_best_positive_lead_in": "negative_stem" not in flaws,
            "lead_in_choice_consistent": (
                bool(model_claims.get("lead_in_choice_consistent", False))
                and "answer_contraindicated_by_stem" not in flaws
                and "answer_key_explanation_mismatch" not in flaws
            ),
            "exactly_5_choices": len(choices) == 5,
            "no_negative_stem": "negative_stem" not in flaws,
            "no_all_or_none": "all_or_none_of_above" not in flaws,
            "no_absolute_term": "absolute_term_in_option" not in flaws,
            "no_vague_term": "vague_term_in_option" not in flaws,
            "key_length_rank_2_to_4_not_longest_not_shortest": not bool(
                {"longest_is_key", "shortest_is_key", "key_length_rank"} & flaws
            ),
            "key_len_ratio_0_8_to_1_2": ratio is not None and 0.8 <= ratio <= 1.2,
            "key_not_most_components": "most_components_is_key" not in flaws,
            "urgency_adverb_not_key_only": "urgency_adverb_only_in_key" not in flaws,
            "no_clang_cue": "clang_cue_stem_option" not in flaws,
            "no_duplicate_or_overlapping_choices": "duplicate_choices" not in flaws,
            "is_clinical_vignette_not_low_cognitive": not bool(quality.get("cognitive_low_suspect")),
            "covers_the_options_passes": "covers_the_options" not in flaws,
            "every_distractor_from_differential_or_misconception": (
                _all_distractors_have_misconceptions(q)
                and (not grounding_trace or bool(grounding_trace.get("all_distractors_in_scope")))
                and "distractor_not_ontology_grounded" not in flaws
            ),
            "no_distractor_precluded_by_stem": "no_distractor_precluded_by_stem" not in flaws,
            "evidence_within_inherited_only": (
                bool(grounding_trace.get("answer_evidence_in_scope"))
                and "explanation_missing_source" not in flaws
                and "explanation_source_unverified" not in flaws
                if grounding_trace
                else bool(model_claims.get("evidence_within_inherited_only", False))
            ),
            "cognitive_level_label_matches_actual": (
                bool(str(q.get("cognitive_level") or "").strip())
                and not bool(quality.get("cognitive_low_suspect"))
            ),
        }
    )
    if "syndrome_vs_disease_heterogeneous" in flaws:
        checks["distractors_homogeneous_same_category_and_form"] = False
    return checks


def validate_nbme_hard_rules(q, quality=None, self_check=None):
    """Validate the numbered 20-rule checklist from the generation guideline."""
    quality = quality or scan_item(q)
    self_check = self_check or evaluate_self_check(q, quality)
    flaws = set(quality.get("flaws") or [])
    choices = normalize_choices(q)
    answer = str(q.get("answer") or "")
    try:
        reasoning_hops = int(q.get("reasoning_hops") or 0)
    except (TypeError, ValueError):
        reasoning_hops = 0
    explanations = _choice_explanations(q)
    distractor_count = sum(1 for key in choices if key != answer)
    attractive_count = 0
    for key in choices:
        if key == answer:
            continue
        value = explanations.get(key) or explanations.get(int(key))
        if isinstance(value, dict) and str(value.get("why_attractive") or value.get("misconception") or "").strip():
            attractive_count += 1

    checklist = {
        "01_no_specialty_leak": self_check["undifferentiated_no_specialty_leak"],
        "02_reasoning_hops_ge_2": reasoning_hops >= 2,
        "03_real_multistep_not_recognition": self_check["reasoning_hops_ge_2_real_not_recognition"],
        "04_single_best_positive_lead_in": self_check["single_best_positive_lead_in"],
        "05_exactly_5_choices": self_check["exactly_5_choices"],
        "06_no_all_or_none": self_check["no_all_or_none"],
        "07_no_absolute_or_vague_terms": self_check["no_absolute_term"] and self_check["no_vague_term"],
        "08_no_clang_or_duplicate_choices": self_check["no_clang_cue"] and self_check["no_duplicate_or_overlapping_choices"],
        "09_clinical_vignette_not_low_cognitive": self_check["is_clinical_vignette_not_low_cognitive"],
        "10_key_length_balanced": (
            self_check["key_length_rank_2_to_4_not_longest_not_shortest"]
            and self_check["key_len_ratio_0_8_to_1_2"]
        ),
        "11_key_not_most_components": self_check["key_not_most_components"],
        "12_urgency_not_key_only": self_check["urgency_adverb_not_key_only"],
        "13_grounded_distractors_with_rationales": (
            distractor_count == 4
            and attractive_count == 4
            and self_check["every_distractor_from_differential_or_misconception"]
        ),
        "14_homogeneous_choices": self_check["distractors_homogeneous_same_category_and_form"],
        "15_no_precluded_distractor": self_check["no_distractor_precluded_by_stem"],
        "16_lead_in_choice_consistent": self_check["lead_in_choice_consistent"],
        "17_answer_evidence_inherited": self_check["evidence_within_inherited_only"],
        "18_common_high_stakes_problem": bool((q.get("self_check") or {}).get("common_high_stakes_problem", False)),
        "19_cognitive_label_matches": self_check["cognitive_level_label_matches_actual"],
        "20_review_gate_and_all_self_checks": (
            bool(q.get("needs_review"))
            and not bool(q.get("gen_ready"))
            and all(self_check.values())
        ),
    }
    return {
        "checklist": checklist,
        "failed_rules": [key for key, passed in checklist.items() if not passed],
        "passed_count": sum(1 for passed in checklist.values() if passed),
        "total_count": len(checklist),
        "manual_review_rules": ["14_homogeneous_choices", "16_lead_in_choice_consistent", "18_common_high_stakes_problem"],
        "scanner_flaws": sorted(flaws),
    }


def apply_generation_quality_gate(q):
    quality = scan_item(q)
    self_check = evaluate_self_check(q, quality)
    hard_rules = validate_nbme_hard_rules(q, quality, self_check)
    quality["self_check_passed"] = sum(1 for passed in self_check.values() if passed)
    quality["self_check_total"] = len(self_check)
    quality["hard_rule_checklist"] = hard_rules["checklist"]
    quality["hard_rule_failures"] = hard_rules["failed_rules"]
    quality["hard_rule_passed"] = hard_rules["passed_count"]
    quality["hard_rule_total"] = hard_rules["total_count"]
    quality["manual_review_rules"] = hard_rules["manual_review_rules"]
    q["self_check"] = self_check
    q["item_quality"] = quality
    q["needs_review"] = True
    q["gen_ready"] = False
    reasons = q.get("review_reasons") if isinstance(q.get("review_reasons"), list) else []
    if quality["flaw_count"]:
        reasons.append("item_quality_flaws")
    if hard_rules["failed_rules"]:
        reasons.append("nbme_hard_rule_failures")
    q["review_reasons"] = sorted({str(reason) for reason in reasons if str(reason).strip()})
    return q


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    commit = "--commit" in sys.argv
    if not args:
        # 기본: 합성 + 1차 임종평
        base = Path("data_private/course_exams/extracted")
        args = [str(p) for p in list(base.glob("SYNTH_2026_MOCK_*.json")) + list(base.glob("COMPREHENSIVE_2026_1CHA_*.json"))]
    import collections
    grand = collections.Counter()
    for fp in args:
        p = Path(fp)
        d = json.loads(p.read_text(encoding="utf-8"))
        qs = d.get("questions", [])
        flagged = 0
        fc = collections.Counter()
        for q in qs:
            iq = scan_item(q)
            if commit:
                q["item_quality"] = iq
            if iq["flaw_count"] or iq["cognitive_low_suspect"]:
                flagged += 1
            for f in iq["flaws"]:
                fc[f] += 1
                grand[f] += 1
            if iq["cognitive_low_suspect"]:
                fc["cognitive_low_suspect"] += 1
                grand["cognitive_low_suspect"] += 1
        if commit:
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{p.stem}: {len(qs)}문항 · 플래그 {flagged} · {dict(fc)}")
    print("\n=== 전체 결함 분포 ===")
    for f, c in grand.most_common():
        print(f"  {f}: {c}")


if __name__ == "__main__":
    raise SystemExit(main())
