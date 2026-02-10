import streamlit as st
import streamlit.components.v1 as components
import fitz  # PyMuPDF
import google.generativeai as genai
import re
import json
import genanki
import tempfile
import os
import uuid
import concurrent.futures
import random
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from openai import OpenAI
from docx import Document
from pptx import Presentation
from difflib import SequenceMatcher
import subprocess
import shutil
import base64
import zipfile
import xml.etree.ElementTree as ET
import importlib.util
import hashlib

# Optional markdown renderer for Obsidian view
try:
    import markdown as md
    MARKDOWN_AVAILABLE = True
except Exception:
    MARKDOWN_AVAILABLE = False

# FSRS (optional)
try:
    from fsrs import Scheduler, Card, Rating, ReviewLog
    FSRS_AVAILABLE = True
except Exception:
    FSRS_AVAILABLE = False

# ============================================================================
# 초기 설정
# ============================================================================
st.set_page_config(page_title="의대생 AI 튜터", page_icon="🧬", layout="wide")
QUESTION_BANK_FILE = "questions.json"
EXAM_HISTORY_FILE = "exam_history.json"
USER_SETTINGS_FILE = "user_settings.json"
def get_query_param(name, default=None):
    try:
        params = st.query_params
        if name in params:
            val = params[name]
            if isinstance(val, list):
                return val[0] if val else default
            return val
        return default
    except Exception:
        try:
            params = st.experimental_get_query_params()
            return params.get(name, [default])[0]
        except Exception:
            return default

safe_param = get_query_param("safe", None)
ping_param = get_query_param("ping", "0")

DEBUG_MODE = str(ping_param) == "1"
if DEBUG_MODE:
    st.write("✅ DEBUG: app.py loaded")
    st.write(f"Streamlit version: {st.__version__}")
    st.write(f"safe_param={safe_param}")
    st.stop()

LOCK_SAFE = str(safe_param) == "1"
LOCK_THEME = str(safe_param) == "0"

if "theme_enabled" not in st.session_state:
    st.session_state.theme_enabled = False if safe_param is None else LOCK_THEME

# Session State 초기화
if "current_question_idx" not in st.session_state:
    st.session_state.current_question_idx = 0
if "exam_questions" not in st.session_state:
    st.session_state.exam_questions = []
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}
if "exam_started" not in st.session_state:
    st.session_state.exam_started = False
if "exam_finished" not in st.session_state:
    st.session_state.exam_finished = False
if "exam_mode" not in st.session_state:
    st.session_state.exam_mode = "시험모드"
if "exam_type" not in st.session_state:
    st.session_state.exam_type = "객관식"
if "auto_next" not in st.session_state:
    st.session_state.auto_next = False
if "auto_advance_guard" not in st.session_state:
    st.session_state.auto_advance_guard = None
if "revealed_answers" not in st.session_state:
    st.session_state.revealed_answers = set()
if "explanation_default" not in st.session_state:
    st.session_state.explanation_default = False
if "exam_stats_applied" not in st.session_state:
    st.session_state.exam_stats_applied = False
if "graded_questions" not in st.session_state:
    st.session_state.graded_questions = set()
# (trend_days retained for future use)
if "trend_days" not in st.session_state:
    st.session_state.trend_days = 14
if "wrong_priority" not in st.session_state:
    st.session_state.wrong_priority = "오답 횟수"
if "current_exam_meta" not in st.session_state:
    st.session_state.current_exam_meta = {}
if "exam_history_saved" not in st.session_state:
    st.session_state.exam_history_saved = False
if "obsidian_path" not in st.session_state:
    st.session_state.obsidian_path = ""
if "dual_exam_text" not in st.session_state:
    st.session_state.dual_exam_text = ""
if "dual_exam_images" not in st.session_state:
    st.session_state.dual_exam_images = []
if "dual_exam_page_text" not in st.session_state:
    st.session_state.dual_exam_page_text = []
if "dual_match_scores" not in st.session_state:
    st.session_state.dual_match_scores = {}
if "wrong_weight_recent" not in st.session_state:
    st.session_state.wrong_weight_recent = 0.7
if "wrong_weight_count" not in st.session_state:
    st.session_state.wrong_weight_count = 0.3
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "Light"
if "theme_bg" not in st.session_state:
    st.session_state.theme_bg = "Gradient"
if "last_action_notice" not in st.session_state:
    st.session_state.last_action_notice = ""
if "heatmap_bins" not in st.session_state:
    st.session_state.heatmap_bins = [0, 1, 3, 6, 10]
if "heatmap_colors" not in st.session_state:
    st.session_state.heatmap_colors = ["#ffffff", "#d7f3f0", "#b2e9e3", "#7fd6cc", "#4fc1b6", "#1f8e86"]
if "profile_name" not in st.session_state:
    st.session_state.profile_name = "default"
if "select_placeholder_exam" not in st.session_state:
    st.session_state.select_placeholder_exam = "선택하세요"
if "select_placeholder_study" not in st.session_state:
    st.session_state.select_placeholder_study = "선택하세요"
if "past_exam_text" not in st.session_state:
    st.session_state.past_exam_text = ""
if "past_exam_items" not in st.session_state:
    st.session_state.past_exam_items = []
if "past_exam_file" not in st.session_state:
    st.session_state.past_exam_file = ""
if "past_exam_images" not in st.session_state:
    st.session_state.past_exam_images = []
if "image_display_width" not in st.session_state:
    st.session_state.image_display_width = 520
if "past_exam_anchors" not in st.session_state:
    st.session_state.past_exam_anchors = {}

# ============================================================================
# JSON 데이터 관리 함수
# ============================================================================
def load_questions() -> dict:
    """questions.json 파일 로드"""
    if os.path.exists(QUESTION_BANK_FILE):
        try:
            with open(QUESTION_BANK_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 마이그레이션: 기존 형식 확인 및 필요시 변환
                if data and isinstance(data.get("text"), list) and len(data.get("text", [])) > 0:
                    first = data["text"][0]
                    if isinstance(first, dict) and "content" in first and "type" not in first:
                        # 기존 형식 (content 필드) -> 새 형식으로 마이그레이션
                        migrate_old_format(data)
                        return load_questions()  # 다시 로드
                data = ensure_question_ids(data)
                return data
        except:
            return {"text": [], "cloze": []}
    return {"text": [], "cloze": []}

def migrate_old_format(data: dict):
    """기존 형식의 questions.json을 새 형식으로 마이그레이션"""
    try:
        migrated_text = []
        migrated_cloze = []
        
        for item in data.get("text", []):
            if isinstance(item, dict) and "content" in item:
                # 기존 형식에서 파싱
                parsed = extract_mcq_components(item["content"])
                if parsed:
                    parsed["subject"] = item.get("subject", "General")
                    parsed["date_added"] = item.get("date_added", datetime.now().isoformat())
                    migrated_text.append(parsed)
        
        for item in data.get("cloze", []):
            if isinstance(item, dict) and "content" in item:
                # Cloze 기존 형식 파싱
                content = item["content"]
                if '{{c1::' in content:
                    m = re.search(r'\{\{c1::(.+?)\}\}', content)
                    if m:
                        answer = m.group(1).strip()
                        front = re.sub(r'\{\{c1::.+?\}\}', '____', content)
                        migrated_cloze.append({
                            "type": "cloze",
                            "front": front,
                            "answer": answer,
                            "explanation": "",
                            "subject": item.get("subject", "General"),
                            "date_added": item.get("date_added", datetime.now().isoformat())
                        })
        
        # 새 형식으로 저장
        data["text"] = migrated_text
        data["cloze"] = migrated_cloze
        save_questions(data)
        
        import sys
        print(f"[MIGRATION] {len(migrated_text)}개 MCQ, {len(migrated_cloze)}개 Cloze 마이그레이션 완료", file=sys.stderr)
    except Exception as e:
        import sys
        print(f"[MIGRATION ERROR] {str(e)}", file=sys.stderr)

def save_questions(data: dict):
    """questions.json 파일 저장"""
    with open(QUESTION_BANK_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_exam_history():
    if os.path.exists(EXAM_HISTORY_FILE):
        try:
            with open(EXAM_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []
    return []

def save_exam_history(items):
    with open(EXAM_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def add_exam_history(session):
    history = load_exam_history()
    history.insert(0, session)
    save_exam_history(history[:200])
    return history

def clear_question_bank(mode="all"):
    data = load_questions()
    if mode == "mcq":
        data["text"] = []
    elif mode == "cloze":
        data["cloze"] = []
    else:
        data = {"text": [], "cloze": []}
    save_questions(data)
    return data

def clear_exam_history():
    save_exam_history([])

def load_user_settings():
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}

def save_user_settings(data):
    with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def apply_profile_settings(profile_name):
    data = load_user_settings()
    prof = data.get(profile_name)
    if not prof:
        return False
    st.session_state.heatmap_bins = prof.get("heatmap_bins", st.session_state.heatmap_bins)
    st.session_state.heatmap_colors = prof.get("heatmap_colors", st.session_state.heatmap_colors)
    st.session_state.select_placeholder_exam = prof.get("select_placeholder_exam", st.session_state.select_placeholder_exam)
    st.session_state.select_placeholder_study = prof.get("select_placeholder_study", st.session_state.select_placeholder_study)
    return True

def persist_profile_settings(profile_name):
    data = load_user_settings()
    data[profile_name] = {
        "heatmap_bins": st.session_state.heatmap_bins,
        "heatmap_colors": st.session_state.heatmap_colors,
        "select_placeholder_exam": st.session_state.select_placeholder_exam,
        "select_placeholder_study": st.session_state.select_placeholder_study,
    }
    save_user_settings(data)

def ensure_question_ids(data: dict) -> dict:
    """모든 문항에 고유 ID 부여"""
    updated = False
    for item in data.get("text", []) + data.get("cloze", []):
        if isinstance(item, dict) and "id" not in item:
            item["id"] = str(uuid.uuid4())
            updated = True
    if updated:
        save_questions(data)
    return data

def add_questions_to_bank(questions_data, mode, subject="General", unit="미분류", quality_filter=True, min_length=20, batch_id=None):
    """생성된 문제를 question bank에 추가 (구조화된 JSON 형식)
    
    Args:
        questions_data: 다음 중 하나
            - 구조화된 dict의 리스트: [{"problem": ..., "options": [...], "answer": 1, "explanation": ...}]
            - 문자열: 기존 호환성을 위함
        mode: 모드 ("📝 객관식 문제 (Case Study)" 또는 "🧩 빈칸 뚫기 (Anki Cloze)")
        subject: 과목명
        quality_filter: 품질 필터링 여부
        min_length: 최소 길이
    
    Returns:
        추가된 문제 개수
    """
    bank = load_questions()
    
    # 문자열이면 파싱 (기존 호환성)
    if isinstance(questions_data, str):
        parsed_questions = parse_generated_text_to_structured(questions_data, mode)
    else:
        parsed_questions = questions_data if isinstance(questions_data, list) else [questions_data]
    
    added_count = 0
    if not batch_id:
        batch_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]

    for q_data in parsed_questions:
        if not q_data:
            continue
        
        # 품질 필터링
        if quality_filter:
            if mode == "📝 객관식 문제 (Case Study)":
                problem_text = q_data.get("problem", "")
                if len(problem_text) < min_length:
                    continue
            else:
                front_text = q_data.get("front", "")
                if len(front_text) < min_length:
                    continue
        
        # 메타데이터 추가
        q_data["subject"] = q_data.get("subject") or subject
        q_data["unit"] = q_data.get("unit") or unit
        q_data["date_added"] = datetime.now().isoformat()
        if "id" not in q_data:
            q_data["id"] = str(uuid.uuid4())
        q_data["batch_id"] = q_data.get("batch_id") or batch_id
        
        if mode == "📝 객관식 문제 (Case Study)":
            bank["text"].append(q_data)
        else:
            bank["cloze"].append(q_data)
        
        added_count += 1
    
    save_questions(bank)
    return added_count

def add_questions_to_bank_auto(items, subject="General", unit="미분류", quality_filter=True, min_length=20, batch_id=None):
    """MCQ/Cloze 혼합 입력 자동 분류 후 저장"""
    if not batch_id:
        batch_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    mcq_items = []
    cloze_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item["subject"] = item.get("subject") or subject
        item["unit"] = item.get("unit") or unit
        item["batch_id"] = item.get("batch_id") or batch_id
        if item.get("type") == "cloze":
            cloze_items.append(item)
        else:
            mcq_items.append(item)
    added = 0
    if mcq_items:
        added += add_questions_to_bank(mcq_items, "📝 객관식 문제 (Case Study)", subject, unit, quality_filter, min_length, batch_id=batch_id)
    if cloze_items:
        added += add_questions_to_bank(cloze_items, "🧩 빈칸 뚫기 (Anki Cloze)", subject, unit, quality_filter, min_length, batch_id=batch_id)
    return added


def parse_generated_text_to_structured(text, mode):
    """생성된 텍스트를 구조화된 형식으로 파싱
    
    Returns:
        구조화된 dict의 리스트
    """
    results = []
    
    if mode == "📝 객관식 문제 (Case Study)":
        # 1) JSON 형식 우선 파싱 (Gemini/OpenAI JSON 대응)
        # 전체 텍스트가 JSON 배열/객체인 경우
        try:
            stripped = text.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    parsed = [parsed]
                if isinstance(parsed, list):
                    for item in parsed:
                        norm = normalize_mcq_item(item)
                        if norm:
                            results.append(norm)
                    if results:
                        return results
        except Exception:
            pass

        # 복수 JSON 블록이 섞여 있는 경우를 탐지
        try:
            decoder = json.JSONDecoder()
            idx = 0
            stripped = text.strip()
            while idx < len(stripped):
                if stripped[idx] not in "{[":
                    idx += 1
                    continue
                try:
                    obj, next_idx = decoder.raw_decode(stripped[idx:])
                    idx += next_idx
                    if isinstance(obj, dict):
                        obj = [obj]
                    if isinstance(obj, list):
                        for item in obj:
                            norm = normalize_mcq_item(item)
                            if norm:
                                results.append(norm)
                except Exception:
                    idx += 1
            if results:
                return results
        except Exception:
            pass

        # TSV 또는 '---' 구분자로 된 MCQ 파싱
        items = text.split("\n---\n")
        
        for item in items:
            item = item.strip()
            if not item or len(item) < 50:
                continue
            
            # TSV 형식: problem_text\texplanation
            parts = item.split('\t')
            problem_part = parts[0].strip() if parts else ""
            explanation_part = parts[1].strip() if len(parts) > 1 else ""
            
            if not problem_part:
                continue
            
            # 정답과 선지 추출
            parsed = extract_mcq_components(problem_part)
            if parsed:
                parsed["explanation"] = explanation_part
                results.append(parsed)
    else:
        # Cloze 형식: 한 줄에 하나씩
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or '{{c1::' not in line:
                continue
            
            # 해설 분리
            explanation = ""
            if '\t' in line:
                line, explanation = line.split('\t', 1)
            
            # 정답 추출
            m = re.search(r'\{\{c1::(.+?)\}\}', line)
            if not m:
                continue
            
            answer = m.group(1).strip()
            front = re.sub(r'\{\{c1::.+?\}\}', '____', line)
            
            results.append({
                "type": "cloze",
                "front": front,
                "answer": answer,
                "explanation": explanation
            })
    
    return results


def extract_mcq_components(problem_text):
    """MCQ 텍스트에서 문제, 선지, 정답을 추출
    
    Returns:
        {"type": "mcq", "problem": ..., "options": [...], "answer": ..., "explanation": ""}
        또는 None (파싱 실패 시)
    """
    try:
        # 정답 추출
        ans_match = re.search(r"정답:\s*\{\{c1::([1-5①②③④⑤]+)\}\}", problem_text)
        if not ans_match:
            return None
        
        ans_str = ans_match.group(1).strip()
        circ_to_num = {'①': '1', '②': '2', '③': '3', '④': '4', '⑤': '5'}
        answer_num = int(circ_to_num.get(ans_str, ans_str))
        
        # 선지 추출: ① ... ② ... 형식
        options = []
        opt_pattern = r'(?:①|②|③|④|⑤)\s*([^①②③④⑤\n]+?)(?=(?:①|②|③|④|⑤|$))'
        matches = re.findall(opt_pattern, problem_text)
        options = [opt.strip() for opt in matches if opt.strip()]
        
        if len(options) < 3:  # 최소 3개 이상 필요
            return None
        
        # 선지를 5개로 정규화 (부족하면 채우기)
        while len(options) < 5:
            options.append(f"보기 {len(options) + 1}")
        options = options[:5]  # 5개 초과면 자르기
        
        # 문제 텍스트 정제: 정답/선지 제거 후 스템만 남기기
        problem_clean = re.sub(r'정답:\s*\{\{c1::.+?\}\}', '', problem_text).strip()
        # 선지 시작 위치 이전만 스템으로 사용
        first_opt = re.search(r'(①|②|③|④|⑤)', problem_clean)
        if first_opt:
            stem = problem_clean[:first_opt.start()].strip()
        else:
            stem = problem_clean
        stem = re.sub(r'\s+', ' ', stem)
        if not stem:
            stem = problem_clean
        
        return {
            "type": "mcq",
            "problem": stem,
            "options": options,
            "answer": answer_num,
            "explanation": ""
        }
    except Exception as e:
        import sys
        print(f"[EXTRACT ERROR] {str(e)}", file=sys.stderr)
        return None

def parse_mcq_content(q_data: dict) -> dict:
    """저장된 MCQ 데이터를 시험 표시용으로 변환
    
    Args:
        q_data: {"type": "mcq", "problem": ..., "options": [...], "answer": ..., "explanation": ...}
    
    Returns:
        {"type": "mcq", "front": ..., "problem": ..., "options": [...], "correct": ..., "explanation": ...}
    """
    return {
        "type": "mcq",
        "raw": q_data.get("problem", ""),
        "front": q_data.get("problem", ""),
        "problem": q_data.get("problem", ""),
        "options": q_data.get("options", []),
        "correct": q_data.get("answer"),  # 숫자 형식: 1-5
        "explanation": q_data.get("explanation", ""),
        "subject": q_data.get("subject"),
        "unit": q_data.get("unit"),
        "difficulty": q_data.get("difficulty"),
        "id": q_data.get("id"),
        "fsrs": q_data.get("fsrs"),
        "note": q_data.get("note", ""),
        "images": q_data.get("images", []),
    }

def parse_cloze_content(q_data: dict) -> dict:
    """저장된 Cloze 데이터를 시험 표시용으로 변환
    
    Args:
        q_data: {"type": "cloze", "front": ..., "answer": ..., "explanation": ...}
    
    Returns:
        {"type": "cloze", "front": ..., "raw": ..., "answer": ..., "explanation": ...}
    """
    return {
        "type": "cloze",
        "raw": q_data.get("front", ""),
        "front": q_data.get("front", ""),
        "answer": q_data.get("answer", ""),
        "explanation": q_data.get("explanation", ""),
        "subject": q_data.get("subject"),
        "unit": q_data.get("unit"),
        "difficulty": q_data.get("difficulty"),
        "id": q_data.get("id"),
        "fsrs": q_data.get("fsrs"),
        "note": q_data.get("note", ""),
        "images": q_data.get("images", []),
    }

def get_question_stats():
    """저장된 문제 통계"""
    bank = load_questions()
    return {
        "total_text": len(bank.get("text", [])),
        "total_cloze": len(bank.get("cloze", []))
    }

def fuzzy_match(user_answer, correct_answer, threshold=0.8):
    """Cloze 답변 유사도 비교"""
    user_clean = re.sub(r'[^\w가-힣]', '', str(user_answer).lower())
    correct_clean = re.sub(r'[^\w가-힣]', '', correct_answer.lower())
    
    if user_clean == correct_clean:
        return True
    ratio = SequenceMatcher(None, user_clean, correct_clean).ratio()
    return ratio >= threshold

def calculate_quality_score(item_text, mode):
    """항목의 품질 점수 계산 (0~1.0)"""
    score = 0.4
    text = item_text.strip()
    text_len = len(text)
    
    # 길이 점수
    if 80 < text_len < 500:
        score += 0.25
    elif 50 < text_len < 700:
        score += 0.15
    
    # 형식 점수
    if mode == "📝 객관식 문제 (Case Study)":
        if "정답:" in text:
            score += 0.15
        options = len(re.findall(r"①|②|③|④|⑤", text))
        if options >= 3:
            score += 0.15
    else:  # Cloze
        if "{{c1::" in text:
            score += 0.3
    
    # 의학 용어 점수
    medical_keywords = ["증상", "진단", "치료", "질병", "검사", "수치", "질환", "증후군"]
    kw_count = sum(1 for kw in medical_keywords if kw in text)
    if kw_count >= 2:
        score += 0.15
    elif kw_count >= 1:
        score += 0.08
    
    if text.endswith((".", "。")):
        score += 0.08
    
    complex_chars = text.count(",") + text.count(";") + text.count("(")
    if 2 <= complex_chars <= 8:
        score += 0.05
    
    return min(max(score, 0.0), 1.0)

def auto_tag(item_text):
    """휴리스틱 기반 난이도/카테고리 태깅"""
    txt = item_text.lower()
    
    # 카테고리
    categories = []
    if any(k in txt for k in ["심장", "심근", "부정맥", "협심증"]):
        categories.append("cardio")
    if any(k in txt for k in ["폐", "호흡", "기관지", "천식"]):
        categories.append("pulmonary")
    if any(k in txt for k in ["신경", "뇌", "척추", "신경계"]):
        categories.append("neuro")
    if any(k in txt for k in ["암", "종양", "신생물"]):
        categories.append("oncology")
    if any(k in txt for k in ["신장", "신부전", "사구체"]):
        categories.append("nephro")
    if not categories:
        categories.append("general")
    
    # 난이도
    length = len(item_text)
    complexity = item_text.count(";") + item_text.count(",")
    if length < 150 and complexity < 3:
        difficulty = "⭐ 쉬움"
    elif length < 350 and complexity < 6:
        difficulty = "⭐⭐ 중간"
    else:
        difficulty = "⭐⭐⭐ 어려움"
    
    return difficulty, categories

def is_answer_correct(q, user_ans):
    if q.get("type") == "mcq":
        correct_choice = q.get("correct")
        return bool(correct_choice and user_ans == correct_choice)
    correct_text = q.get("answer")
    return bool(correct_text and isinstance(user_ans, str) and fuzzy_match(user_ans, correct_text))

def parse_iso_datetime(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            v = value.replace("Z", "+00:00")
            return datetime.fromisoformat(v)
    except Exception:
        return None
    return None

def get_fsrs_report(questions, now=None):
    if not FSRS_AVAILABLE:
        return None
    check_time = now or datetime.now(timezone.utc)
    total = len(questions)
    stats = get_fsrs_stats(questions, now=check_time)
    review_count_7d = 0
    rating_counts = {"Again": 0, "Hard": 0, "Good": 0, "Easy": 0}
    intervals = []
    last_review = None
    for q in questions:
        fsrs = q.get("fsrs") or {}
        card_data = fsrs.get("card")
        if card_data:
            try:
                card = Card.from_json(card_data)
                if hasattr(card, "interval"):
                    intervals.append(float(card.interval))
            except Exception:
                pass
        # last_rating
        last_rating = fsrs.get("last_rating")
        if last_rating in rating_counts:
            rating_counts[last_rating] += 1

        # logs
        for log in fsrs.get("logs", []) or []:
            if isinstance(log, dict):
                for key in ("review_datetime", "reviewed_at", "time", "date", "review"):
                    dt = parse_iso_datetime(log.get(key))
                    if dt:
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if (check_time - dt).days <= 7:
                            review_count_7d += 1
                        if last_review is None or dt > last_review:
                            last_review = dt
                        break
                rating = log.get("rating")
                if isinstance(rating, str) and rating in rating_counts:
                    rating_counts[rating] += 1
    avg_interval = sum(intervals) / len(intervals) if intervals else 0
    return {
        "total": total,
        "stats": stats,
        "review_count_7d": review_count_7d,
        "avg_interval": avg_interval,
        "last_review": last_review.isoformat() if last_review else None,
        "rating_counts": rating_counts,
    }

def update_question_stats(q_id, is_correct):
    bank = load_questions()
    now = datetime.now(timezone.utc).isoformat()
    for key in ("text", "cloze"):
        for item in bank.get(key, []):
            if item.get("id") == q_id:
                stats = item.get("stats") or {}
                stats["right"] = int(stats.get("right", 0))
                stats["wrong"] = int(stats.get("wrong", 0))
                if is_correct:
                    stats["right"] += 1
                else:
                    stats["wrong"] += 1
                stats["last_attempt"] = now
                history = stats.get("history") or []
                history.append({"time": now, "correct": bool(is_correct)})
                stats["history"] = history[-200:]
                item["stats"] = stats
                save_questions(bank)
                return stats
    return None

def update_question_note(q_id, note_text):
    bank = load_questions()
    for key in ("text", "cloze"):
        for item in bank.get(key, []):
            if item.get("id") == q_id:
                item["note"] = note_text
                save_questions(bank)
                return True
    return False

def delete_mcq_by_ids(ids):
    if not ids:
        return 0
    data = load_questions()
    before = len(data.get("text", []))
    data["text"] = [q for q in data.get("text", []) if q.get("id") not in ids]
    save_questions(data)
    return before - len(data.get("text", []))

def delete_mcq_by_batch(batch_id):
    if not batch_id:
        return 0
    data = load_questions()
    before = len(data.get("text", []))
    data["text"] = [q for q in data.get("text", []) if (q.get("batch_id") or "legacy") != batch_id]
    save_questions(data)
    return before - len(data.get("text", []))

def get_mcq_batches(questions):
    batches = {}
    for q in questions:
        b = q.get("batch_id") or "legacy"
        batches[b] = batches.get(b, 0) + 1
    return batches

def get_wrong_note_stats(questions):
    wrong_items = []
    total_wrong = 0
    for q in questions:
        stats = q.get("stats") or {}
        wrong = int(stats.get("wrong", 0))
        if wrong > 0:
            wrong_items.append(q)
            total_wrong += wrong
    return wrong_items, total_wrong

def sort_wrong_first(questions, mode="오답 횟수", weight_recent=0.7, weight_count=0.3):
    def last_wrong_time(q):
        stats = q.get("stats") or {}
        hist = stats.get("history") or []
        latest = None
        for entry in hist:
            if not isinstance(entry, dict):
                continue
            if entry.get("correct") is True:
                continue
            dt = parse_iso_datetime(entry.get("time"))
            if dt:
                if latest is None or dt > latest:
                    latest = dt
        return latest or datetime.min.replace(tzinfo=timezone.utc)

    def score(q):
        stats = q.get("stats") or {}
        wrong = int(stats.get("wrong", 0))
        right = int(stats.get("right", 0))
        total = wrong + right
        rate = wrong / total if total > 0 else 0
        if mode == "오답률":
            return (rate, wrong)
        if mode == "최근 오답":
            # 최근 오답일수록 높은 점수
            last_dt = last_wrong_time(q)
            days_since = (datetime.now(timezone.utc) - last_dt).days if last_dt else 9999
            recency_score = 1 / (1 + max(days_since, 0))
            combined = weight_recent * recency_score + weight_count * wrong
            return (combined, recency_score, wrong)
        return (wrong, rate)

    return sorted(questions, key=score, reverse=True)

def compute_recent_accuracy(questions, days=7, now=None):
    check_time = now or datetime.now(timezone.utc)
    cutoff = check_time - timedelta(days=days)
    correct = 0
    total = 0
    for q in questions:
        stats = q.get("stats") or {}
        hist = stats.get("history") or []
        for entry in hist:
            if not isinstance(entry, dict):
                continue
            dt = parse_iso_datetime(entry.get("time"))
            if not dt:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                total += 1
                if entry.get("correct") is True:
                    correct += 1
    accuracy = (correct / total * 100) if total > 0 else None
    return {"correct": correct, "total": total, "accuracy": accuracy}

def compute_accuracy_trend(questions, days=14, now=None):
    check_time = now or datetime.now(timezone.utc)
    start = (check_time - timedelta(days=days - 1)).date()
    buckets = {}
    for i in range(days):
        d = start + timedelta(days=i)
        buckets[d.isoformat()] = {"correct": 0, "total": 0}
    for q in questions:
        stats = q.get("stats") or {}
        hist = stats.get("history") or []
        for entry in hist:
            if not isinstance(entry, dict):
                continue
            dt = parse_iso_datetime(entry.get("time"))
            if not dt:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dkey = dt.date().isoformat()
            if dkey in buckets:
                buckets[dkey]["total"] += 1
                if entry.get("correct") is True:
                    buckets[dkey]["correct"] += 1
    series = []
    for dkey in sorted(buckets.keys()):
        total = buckets[dkey]["total"]
        acc = (buckets[dkey]["correct"] / total * 100) if total > 0 else 0
        series.append({"date": dkey, "accuracy": acc})
    return series

def compute_overall_accuracy(questions):
    right = 0
    wrong = 0
    for q in questions:
        stats = q.get("stats") or {}
        right += int(stats.get("right", 0))
        wrong += int(stats.get("wrong", 0))
    total = right + wrong
    if total == 0:
        return None
    accuracy = right / total * 100
    return {"correct": right, "wrong": wrong, "total": total, "accuracy": accuracy}

def fsrs_group_report(questions, group_key, now=None):
    if not FSRS_AVAILABLE:
        return []
    check_time = now or datetime.now(timezone.utc)
    groups = {}
    for q in questions:
        key = (q.get(group_key) or "General")
        g = groups.setdefault(key, {"due": 0, "overdue": 0, "future": 0, "new": 0, "total": 0})
        g["total"] += 1
        fsrs = q.get("fsrs") or {}
        card_data = fsrs.get("card")
        if not card_data:
            g["new"] += 1
            g["due"] += 1
            continue
        try:
            card = Card.from_json(card_data)
            if card.due <= check_time:
                g["due"] += 1
                if card.due < check_time:
                    g["overdue"] += 1
            else:
                g["future"] += 1
        except Exception:
            g["due"] += 1
    rows = []
    for k, v in sorted(groups.items(), key=lambda x: x[0]):
        rows.append({"그룹": k, **v})
    return rows

def apply_mcq_shortcut(idx):
    val = (st.session_state.get(f"shortcut_{idx}") or "").strip().upper()
    if not val:
        return
    letters = ["A", "B", "C", "D", "E"]
    sel = None
    if val in letters:
        sel = letters.index(val)
    elif val.isdigit():
        n = int(val)
        if 1 <= n <= 5:
            sel = n - 1
    labels = st.session_state.get(f"labels_real_{idx}") or []
    if sel is not None and 0 <= sel < len(labels):
        st.session_state[f"q_{idx}"] = labels[sel]

def goto_prev_question():
    st.session_state.current_question_idx = max(0, st.session_state.current_question_idx - 1)

def goto_next_question():
    total = len(st.session_state.get("exam_questions", []))
    if total:
        st.session_state.current_question_idx = min(total - 1, st.session_state.current_question_idx + 1)

def finish_exam_session():
    st.session_state.exam_finished = True

def get_unique_subjects(questions):
    subjects = sorted({(q.get("subject") or "General") for q in questions})
    return subjects

def get_unit_name(q):
    return q.get("unit") or q.get("chapter") or q.get("topic") or "미분류"

def get_units_by_subject(questions):
    mapping = {}
    for q in questions:
        subj = (q.get("subject") or "General")
        unit = get_unit_name(q)
        mapping.setdefault(subj, set()).add(unit)
    return {k: sorted(v) for k, v in mapping.items()}

def filter_questions_by_subject(questions, selected_subjects):
    if not selected_subjects:
        return questions
    return [q for q in questions if (q.get("subject") or "General") in selected_subjects]

def filter_questions_by_subject_unit(questions, selected_subjects, selected_units):
    if not selected_subjects and not selected_units:
        return questions
    filtered = []
    for q in questions:
        subj = q.get("subject") or "General"
        unit = get_unit_name(q)
        if selected_subjects and subj not in selected_subjects:
            continue
        if selected_units and unit not in selected_units:
            continue
        filtered.append(q)
    return filtered

def normalize_mcq_item(item):
    if not isinstance(item, dict):
        return None
    if "content" in item and "problem" not in item:
        parsed = extract_mcq_components(item.get("content", ""))
        if parsed:
            parsed["explanation"] = item.get("explanation", "")
            parsed["subject"] = item.get("subject")
            parsed["unit"] = item.get("unit")
            parsed["difficulty"] = item.get("difficulty")
            parsed["id"] = item.get("id")
            parsed["fsrs"] = item.get("fsrs")
            return parsed
    problem = (item.get("problem") or "").strip()
    options = item.get("options") or []
    answer = item.get("answer", 1)
    explanation = item.get("explanation", "")
    if not problem or not isinstance(options, list):
        return None
    # 옵션 길이 5로 정규화
    options = [str(opt).strip() for opt in options if str(opt).strip()]
    while len(options) < 5:
        options.append(f"보기 {len(options) + 1}")
    options = options[:5]
    try:
        answer_num = int(answer)
    except Exception:
        answer_num = 1
    if answer_num < 1 or answer_num > 5:
        answer_num = 1
    return {
        "type": "mcq",
        "problem": problem,
        "options": options,
        "answer": answer_num,
        "explanation": explanation,
        "subject": item.get("subject"),
        "unit": item.get("unit"),
        "difficulty": item.get("difficulty"),
        "id": item.get("id"),
        "fsrs": item.get("fsrs"),
    }

def normalize_cloze_item(item):
    if not isinstance(item, dict):
        return None
    if "content" in item and "front" not in item:
        # 구버전 content 필드
        content = item.get("content", "")
        if "{{c1::" in content:
            m = re.search(r'\{\{c1::(.+?)\}\}', content)
            if m:
                answer = m.group(1).strip()
                front = re.sub(r'\{\{c1::.+?\}\}', '____', content)
                return {
                    "type": "cloze",
                    "front": front,
                    "answer": answer,
                    "explanation": item.get("explanation", ""),
                    "subject": item.get("subject"),
                    "unit": item.get("unit"),
                    "difficulty": item.get("difficulty"),
                    "id": item.get("id"),
                    "fsrs": item.get("fsrs"),
                }
        return None
    front = (item.get("front") or "").strip()
    answer = (item.get("answer") or "").strip()
    explanation = item.get("explanation", "")
    if not front or not answer:
        return None
    return {
        "type": "cloze",
        "front": front,
        "answer": answer,
        "explanation": explanation,
        "subject": item.get("subject"),
        "unit": item.get("unit"),
        "difficulty": item.get("difficulty"),
        "id": item.get("id"),
        "fsrs": item.get("fsrs"),
    }

def format_explanation_text(text):
    if not text:
        return ""
    if "|" in text:
        parts = [p.strip() for p in re.split(r"\s*\|\s*", text) if p.strip()]
        if len(parts) > 1:
            return "\n".join([f"- {p}" for p in parts])
    return text

def _is_option_line(line):
    if re.match(r"^\s*[①②③④⑤]", line):
        return True
    if re.match(r"^\s*[1-5][).]", line):
        return True
    return False

def _answer_token_to_num(token):
    token = str(token).strip()
    circled = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}
    if token in circled:
        return circled[token]
    if token.isdigit():
        n = int(token)
        if 1 <= n <= 5:
            return n
    token = token.upper()
    if token in ["A", "B", "C", "D", "E"]:
        return ord(token) - ord("A") + 1
    return None

def preclean_exam_text(text):
    if not text:
        return ""
    lines = [l.rstrip() for l in text.splitlines()]

    # Find first probable question line
    q_re = re.compile(r"^\s*(?:문항|문제|Question|Q)?\s*\d{1,3}\s*[).]")
    q_alt = re.compile(r"[①②③④⑤]")
    first_idx = None
    for i, line in enumerate(lines):
        if q_re.match(line.strip()) or q_alt.search(line):
            first_idx = i
            break
    if first_idx is not None:
        lines = lines[first_idx:]

    # Remove page-only lines like "- 3 -" or empty separators
    cleaned = []
    for line in lines:
        s = line.strip()
        if not s:
            cleaned.append("")
            continue
        if re.match(r"^[-–—]{2,}$", s):
            cleaned.append("")
            continue
        if re.match(r"^[-–—]?\s*\d+\s*[-–—]?$", s):
            # page number lines
            cleaned.append("")
            continue
        cleaned.append(line)

    # Merge standalone number lines with the following text line
    merged = []
    i = 0
    num_re = re.compile(r"^\s*\d{1,3}\s*[).]?\s*$")
    while i < len(cleaned):
        line = cleaned[i]
        if num_re.match(line.strip()):
            j = i + 1
            while j < len(cleaned) and not cleaned[j].strip():
                j += 1
            if j < len(cleaned):
                merged.append(f"{line.strip()} {cleaned[j].strip()}".strip())
                i = j + 1
                continue
        merged.append(line)
        i += 1

    # Normalize excessive spaces
    merged = [re.sub(r"[ \t]+", " ", l).strip() for l in merged]
    return "\n".join([l for l in merged if l is not None]).strip()

def parse_exam_text_fuzzy(text, preclean=True):
    """기출문제 원문을 최대한 파싱해 MCQ/Cloze로 변환 (베타)"""
    if not text:
        return []
    if preclean:
        text = preclean_exam_text(text) or text

    def insert_breaks(raw):
        # Insert line breaks before common question markers to improve splitting
        raw = re.sub(r"(?<!\n)(Question\s*\d+\s*[).])", r"\n\1", raw, flags=re.IGNORECASE)
        raw = re.sub(r"(?<!\n)(문항\s*\d+\s*[).])", r"\n\1", raw)
        raw = re.sub(r"(?<!\n)(문제\s*\d+\s*[).])", r"\n\1", raw)
        raw = re.sub(r"(?<!\n)(Q\s*\d+\s*[).])", r"\n\1", raw, flags=re.IGNORECASE)
        return raw

    def split_exam_blocks_simple(raw):
        raw = insert_breaks(raw)
        pattern = re.compile(r"(?m)^\s*(?:문항|문제|Question|Q)?\s*(\d{1,3})\s*[).]\s*", re.IGNORECASE)
        matches = list(pattern.finditer(raw))
        if matches:
            blocks = []
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
                blocks.append(raw[start:end].strip())
            return blocks
        blocks = [b.strip() for b in re.split(r"\n-{3,}\n", raw) if b.strip()]
        return blocks if blocks else [raw.strip()]

    def split_blocks(raw):
        raw = insert_breaks(raw)
        pattern = re.compile(r"(?m)^\s*(?:문항|문제|Question|Q)?\s*(\d{1,3})\s*[).]\s*", re.IGNORECASE)
        matches = list(pattern.finditer(raw))
        if matches:
            blocks = []
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
                blocks.append((raw[start:end].strip(), int(m.group(1))))
            return blocks
        # fallback: split by long dashes or blank lines
        blocks = [b.strip() for b in re.split(r"\n-{3,}\n", raw) if b.strip()]
        return [(b, None) for b in blocks] if blocks else [(raw.strip(), None)]

    def extract_answer_and_explanation(block):
        ans = None
        exp_lines = []
        capturing = False
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if re.match(r"^\s*(?:문항|문제|Question|Q)?\s*\d{1,3}\s*[).]\s*", line, re.IGNORECASE):
                if capturing:
                    break
            m = re.match(r"^(정답|답)\s*[:：]?\s*(.+)$", line)
            if m:
                ans = m.group(2).strip()
                capturing = True
                continue
            m2 = re.match(r"^(해설|설명)\s*[:：]?\s*(.+)$", line)
            if m2:
                capturing = True
                exp_lines.append(m2.group(2).strip())
                continue
            if capturing:
                if _is_option_line(line):
                    continue
                exp_lines.append(line)
        exp = "\n".join([l for l in exp_lines if l]).strip()
        return ans, exp

    items = []
    for block, qnum in split_blocks(text):
        if not block:
            continue
        source_page = None
        for line in block.splitlines():
            m_page = re.match(r"^===\s*페이지\s*(\d+)\s*===", line.strip())
            if m_page:
                source_page = int(m_page.group(1))
        ans_token, explanation = extract_answer_and_explanation(block)
        # remove answer/explanation lines for stem/options parsing
        cleaned = "\n".join(
            [ln for ln in block.splitlines() if not re.match(r"^\s*(정답|답|해설|설명)\s*[:：]", ln.strip())]
        ).strip()

        # try circled options
        if "①" in cleaned:
            parts = re.split(r"[①②③④⑤]", cleaned)
            stem = parts[0].strip()
            stem = re.sub(r"^\s*(?:문항\s*)?\d+\s*[).]\s*", "", stem).strip()
            options = [p.strip() for p in parts[1:] if p.strip()]
            if len(options) >= 3:
                answer_num = _answer_token_to_num(ans_token) or 1
                items.append({
                    "type": "mcq",
                    "problem": stem,
                    "options": options[:5],
                    "answer": answer_num,
                    "explanation": explanation,
                    "page": source_page,
                    "qnum": qnum,
                })
                continue

        # try numbered options (1) 2) ...
        opt_lines = re.findall(r"(?m)^\s*[1-5][).]\s*(.+)$", cleaned)
        if len(opt_lines) >= 3:
            stem = re.split(r"(?m)^\s*[1-5][).]\s*", cleaned)[0].strip()
            stem = re.sub(r"^\s*(?:문항\s*)?\d+\s*[).]\s*", "", stem).strip()
            answer_num = _answer_token_to_num(ans_token) or 1
            items.append({
                "type": "mcq",
                "problem": stem,
                "options": [o.strip() for o in opt_lines][:5],
                "answer": answer_num,
                "explanation": explanation,
                "page": source_page,
                "qnum": qnum,
            })
            continue

        # fallback to cloze if answer exists
        if ans_token:
            answer_text = str(ans_token).strip()
            stem = re.sub(r"^\s*(?:문항\s*)?\d+\s*[).]\s*", "", cleaned).strip()
            if stem and answer_text:
                items.append({
                    "type": "cloze",
                    "front": stem,
                    "answer": answer_text,
                    "explanation": explanation,
                    "page": source_page,
                    "qnum": qnum,
                })
                continue
    return clean_parsed_items(items)

def split_exam_blocks(raw):
    if not raw:
        return []
    raw = re.sub(r"(?<!\n)(Question\s*\d+\s*[).])", r"\n\1", raw, flags=re.IGNORECASE)
    raw = re.sub(r"(?<!\n)(문항\s*\d+\s*[).])", r"\n\1", raw)
    raw = re.sub(r"(?<!\n)(문제\s*\d+\s*[).])", r"\n\1", raw)
    raw = re.sub(r"(?<!\n)(Q\s*\d+\s*[).])", r"\n\1", raw, flags=re.IGNORECASE)
    pattern = re.compile(r"(?m)^\s*(?:문항|문제|Question|Q)?\s*(\d{1,3})\s*[).]\s*", re.IGNORECASE)
    matches = list(pattern.finditer(raw))
    if matches:
        blocks = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            blocks.append(raw[start:end].strip())
        return blocks
    blocks = [b.strip() for b in re.split(r"\n-{3,}\n", raw) if b.strip()]
    return blocks if blocks else [raw.strip()]

def parse_answer_map_from_text(text):
    answer_map = {}
    for block in split_exam_blocks(text):
        if not block:
            continue
        m = re.match(r"^\s*(?:문항|문제|Question|Q)?\s*(\d{1,3})\s*[).]", block.strip(), re.IGNORECASE)
        qnum = int(m.group(1)) if m else None
        ans = None
        exp_lines = []
        for line in block.splitlines():
            l = line.strip()
            if not l:
                continue
            m_ans = re.search(r"(정답|답)\s*[:：]?\s*([①②③④⑤1-5])", l)
            if m_ans:
                ans = m_ans.group(2)
                rest = l[m_ans.end():].strip()
                if rest:
                    exp_lines.append(rest)
                continue
            m_ans2 = re.search(r"▶\s*([①②③④⑤1-5])", l)
            if m_ans2 and ans is None:
                ans = m_ans2.group(1)
                rest = l[m_ans2.end():].strip()
                if rest:
                    exp_lines.append(rest)
                continue
            m_qans = re.match(r"^\s*\d{1,3}\s*[).]?\s*([①②③④⑤1-5])\b\s*(.*)$", l)
            if m_qans and ans is None:
                ans = m_qans.group(1)
                if m_qans.group(2).strip():
                    exp_lines.append(m_qans.group(2).strip())
                continue
            if ans is None and re.match(r"^[①②③④⑤1-5]$", l):
                ans = l
                continue
            if ans is not None:
                if re.match(r"^\s*(?:문항|문제|Question|Q)?\s*\d{1,3}\s*[).]", l, re.IGNORECASE):
                    break
                exp_lines.append(l)
        if qnum and ans:
            answer_map[qnum] = {"answer": ans, "explanation": "\n".join(exp_lines).strip()}
    return answer_map

def parse_pdf_layout(pdf_bytes):
    items_all = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            width = page.rect.width
            data = page.get_text("dict")
            lines = []
            for block in data.get("blocks", []):
                for line in block.get("lines", []):
                    text = "".join(span.get("text", "") for span in line.get("spans", []))
                    text = text.strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = line.get("bbox", [0, 0, 0, 0])
                    lines.append({"text": text, "x0": x0, "x1": x1, "y0": y0})

            if not lines:
                continue

            centers = [((l["x0"] + l["x1"]) / 2) for l in lines]
            left_lines = [l for l, c in zip(lines, centers) if c < width * 0.45]
            right_lines = [l for l, c in zip(lines, centers) if c > width * 0.55]
            middle_lines = [l for l, c in zip(lines, centers) if width * 0.45 <= c <= width * 0.55]
            marker_lines = [l for l in middle_lines if re.match(r"^\s*\d{1,3}\s*[).]?\s*$", l["text"])]
            two_col = len(left_lines) >= 5 and len(right_lines) >= 5

            def merge_number_lines(ls, tol=4.0):
                num_re = re.compile(r"^\s*\d{1,3}\s*[).]?\s*$")
                merged = set()
                for i, num_line in enumerate(ls):
                    if not num_re.match(num_line["text"]):
                        continue
                    # find closest non-number line within tolerance
                    candidates = []
                    for j, other in enumerate(ls):
                        if i == j or num_re.match(other["text"]):
                            continue
                        dy = abs(other["y0"] - num_line["y0"])
                        if dy <= tol:
                            candidates.append((dy, j, other))
                    if candidates:
                        _, j, target = min(candidates, key=lambda x: x[0])
                        prefix = num_line["text"].strip()
                        if not target["text"].strip().startswith(prefix):
                            target["text"] = f"{prefix} {target['text']}".strip()
                        merged.add(i)
                return [l for idx, l in enumerate(ls) if idx not in merged]

            def build_text(ls):
                ls_sorted = sorted(ls, key=lambda x: (x["y0"], x["x0"]))
                text = "\n".join([l["text"] for l in ls_sorted])
                return f"=== 페이지 {page_idx + 1} ===\n" + text

            if two_col:
                left_text = build_text(merge_number_lines(left_lines + marker_lines))
                right_text = build_text(merge_number_lines(right_lines + marker_lines))
                items = parse_exam_text_fuzzy(left_text)
                ans_map = parse_answer_map_from_text(right_text)
                for idx, it in enumerate(items):
                    if not it.get("page"):
                        it["page"] = page_idx + 1
                    qnum = it.get("qnum")
                    if qnum in ans_map:
                        ans_token = ans_map[qnum].get("answer")
                        exp = ans_map[qnum].get("explanation") or ""
                    else:
                        # fallback: 순서 기반 매칭
                        keys = sorted(ans_map.keys())
                        ans_token = ans_map.get(keys[idx], {}).get("answer") if idx < len(keys) else None
                        exp = ans_map.get(keys[idx], {}).get("explanation") if idx < len(keys) else ""
                    if it.get("type") == "mcq" and ans_token:
                        it["answer"] = _answer_token_to_num(ans_token) or it.get("answer")
                    elif it.get("type") == "cloze" and ans_token:
                        it["answer"] = it.get("answer") or ans_token
                    if exp and not it.get("explanation"):
                        it["explanation"] = exp
                items_all.extend(items)
            else:
                full_text = build_text(lines)
                items = parse_exam_text_fuzzy(full_text)
                for it in items:
                    if not it.get("page"):
                        it["page"] = page_idx + 1
                items_all.extend(items)
        doc.close()
    except Exception:
        return []
    return clean_parsed_items(items_all)

def parse_pdf_layout_ai(pdf_bytes, ai_model, api_key=None, openai_api_key=None, hint_text=""):
    items_all = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            width = page.rect.width
            data = page.get_text("dict")
            lines = []
            for block in data.get("blocks", []):
                for line in block.get("lines", []):
                    text = "".join(span.get("text", "") for span in line.get("spans", []))
                    text = text.strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = line.get("bbox", [0, 0, 0, 0])
                    lines.append({"text": text, "x0": x0, "x1": x1, "y0": y0})
            if not lines:
                continue
            centers = [((l["x0"] + l["x1"]) / 2) for l in lines]
            left_lines = [l for l, c in zip(lines, centers) if c < width * 0.45]
            right_lines = [l for l, c in zip(lines, centers) if c > width * 0.55]
            middle_lines = [l for l, c in zip(lines, centers) if width * 0.45 <= c <= width * 0.55]
            marker_lines = [l for l in middle_lines if re.match(r"^\s*\d{1,3}\s*[).]?\s*$", l["text"])]

            def build_text(ls):
                ls_sorted = sorted(ls, key=lambda x: (x["y0"], x["x0"]))
                text = "\n".join([l["text"] for l in ls_sorted])
                return f"=== 페이지 {page_idx + 1} ===\n" + text

            left_text = build_text(left_lines + marker_lines)
            right_text = build_text(right_lines + marker_lines)
            ai_items = ai_parse_exam_layout(
                left_text,
                right_text,
                ai_model=ai_model,
                api_key=api_key,
                openai_api_key=openai_api_key,
                hint_text=hint_text
            )
            for it in ai_items:
                it["page"] = page_idx + 1
            items_all.extend(ai_items)
        doc.close()
    except Exception:
        return []
    return clean_parsed_items(items_all)

def extract_pdf_page_texts(pdf_bytes):
    texts = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for i in range(doc.page_count):
            page = doc.load_page(i)
            page_text = page.get_text().strip()
            texts.append(page_text)
        doc.close()
    except Exception:
        return []
    return texts

def match_questions_to_pages(items, page_texts):
    scores = {}
    if not items or not page_texts:
        return scores
    page_tokens = [_tokenize_for_match(t) for t in page_texts]
    for idx, item in enumerate(items):
        stem = (item.get("problem") or item.get("front") or "")
        tokens = _tokenize_for_match(stem)
        if not tokens:
            continue
        best_page = None
        best_score = 0.0
        for p_idx, pt in enumerate(page_tokens):
            inter = tokens & pt
            score = len(inter) / max(1, len(tokens))
            if score > best_score:
                best_score = score
                best_page = p_idx + 1
        if best_page:
            scores[idx] = {"page": best_page, "score": best_score}
            item["page"] = best_page
    return scores

def parse_qa_to_cloze(text):
    """정답: 패턴을 이용해 Q/A를 Cloze 형태로 변환"""
    results = []
    lines = [l.strip() for l in text.splitlines()]
    buffer_lines = []
    last_item = None
    for line in lines:
        if not line:
            continue
        if re.match(r"^(해설|설명)\s*[:：]", line):
            explanation = re.split(r"[:：]", line, 1)[1].strip()
            if last_item:
                last_item["explanation"] = explanation
            continue
        m = re.match(r"^(정답|답)\s*[:：]\s*(.+)$", line)
        if m:
            answer = m.group(2).strip()
            question = " ".join(buffer_lines).strip()
            if question and answer:
                last_item = {
                    "type": "cloze",
                    "front": question,
                    "answer": answer,
                    "explanation": ""
                }
                results.append(last_item)
            buffer_lines = []
        else:
            buffer_lines.append(line)
    return results

def apply_theme(theme_mode, bg_mode):
    # color palette
    if theme_mode == "Dark":
        base_bg = "#0b1220"
        surface = "#111827"
        surface_2 = "#0f1b30"
        text = "#f8fafc"
        subtext = "#cbd5f5"
        accent = "#7dd3fc"
        accent2 = "#fbbf24"
        border = "#1f2a44"
        lamp_glow = "radial-gradient(ellipse at center, rgba(255,204,138,0.62) 0%, rgba(255,204,138,0.35) 35%, rgba(255,204,138,0) 70%)"
    else:
        base_bg = "#f7f5f2"
        surface = "#ffffff"
        surface_2 = "#f1f5f9"
        text = "#1f2937"
        subtext = "#6b7280"
        accent = "#0ea5a4"
        accent2 = "#d97706"
        border = "#e5e7eb"
        lamp_glow = "radial-gradient(ellipse at center, rgba(255,204,138,0.0) 0%, rgba(255,204,138,0.0) 70%)"

    if bg_mode == "Grid":
        bg = "radial-gradient(circle, rgba(0,0,0,0.06) 1px, transparent 1px), linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.03) 100%)"
        bg_size = "24px 24px, auto"
    elif bg_mode == "Paper":
        bg = "linear-gradient(180deg, rgba(0,0,0,0.02) 0%, rgba(0,0,0,0.03) 100%), repeating-linear-gradient(0deg, rgba(0,0,0,0.02), rgba(0,0,0,0.02) 1px, transparent 1px, transparent 28px)"
        bg_size = "auto, auto"
    elif bg_mode == "None":
        bg = "none"
        bg_size = "auto"
    else:  # Gradient
        if theme_mode == "Dark":
            bg = (
                "radial-gradient(1px 1px at 20% 30%, rgba(255,255,255,0.8) 0, transparent 60%),"
                "radial-gradient(1px 1px at 80% 40%, rgba(255,255,255,0.6) 0, transparent 60%),"
                "radial-gradient(1.2px 1.2px at 60% 15%, rgba(255,255,255,0.7) 0, transparent 60%),"
                "radial-gradient(1px 1px at 35% 70%, rgba(255,255,255,0.5) 0, transparent 60%),"
                "radial-gradient(900px 500px at 10% 0%, rgba(29,78,216,0.25), transparent 60%),"
                "radial-gradient(800px 480px at 90% 10%, rgba(56,189,248,0.18), transparent 55%),"
                "linear-gradient(180deg, rgba(9,12,24,1) 0%, rgba(12,18,40,1) 100%)"
            )
            bg_size = "auto"
        else:
            bg = "radial-gradient(1200px 600px at 10% 0%, rgba(14,165,164,0.18), transparent 60%), radial-gradient(900px 500px at 90% 10%, rgba(217,119,6,0.14), transparent 55%)"
            bg_size = "auto"

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Plus+Jakarta+Sans:wght@400;600;700&family=Source+Serif+4:wght@400;600&display=swap');
        :root {{
            --bg: {base_bg};
            --surface: {surface};
            --surface-2: {surface_2};
            --text: {text};
            --muted: {subtext};
            --accent: {accent};
            --accent-2: {accent2};
            --border: {border};
            --radius: 14px;
        }}
        html, body, [class*="css"] {{
            font-family: 'Plus Jakarta Sans', 'Inter', 'Noto Sans KR', sans-serif;
        }}
        .stApp {{
            position: relative;
            background-color: var(--bg);
            background-image: {bg};
            background-size: {bg_size};
            color: var(--text);
        }}
        [data-testid="stHeader"] {{
            background: transparent;
        }}
        [data-testid="stSidebar"] {{
            background: var(--surface);
            border-right: 1px solid var(--border);
        }}
        .block-container {{
            padding-top: 1.5rem;
            position: relative;
            z-index: 1;
        }}
        .stMetric {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 12px 14px;
            box-shadow: 0 6px 16px rgba(0,0,0,0.04);
        }}
        .stButton>button {{
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 12px;
            padding: 0.6rem 1rem;
            font-weight: 600;
            box-shadow: 0 10px 18px rgba(14,165,164,0.18);
        }}
        .stButton>button:hover {{
            background: var(--accent-2);
            color: white;
        }}
        .stMarkdown, .stText, .stCaption {{
            color: var(--text);
        }}
        .caption-muted {{
            color: var(--muted);
        }}
        a {{
            color: var(--accent);
        }}
        .obsidian-note {{
            font-family: 'Source Serif 4', 'Noto Serif KR', serif;
            color: var(--text);
            line-height: 1.7;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 18px 20px;
            box-shadow: 0 10px 22px rgba(0,0,0,0.06);
        }}
        .hero {{
            display: grid;
            grid-template-columns: 1.2fr 0.8fr;
            gap: 28px;
            align-items: center;
            padding: 28px 0 12px 0;
        }}
        .hero h1 {{
            font-family: 'Plus Jakarta Sans', 'Noto Sans KR', sans-serif;
            font-size: 46px;
            line-height: 1.1;
            margin-bottom: 14px;
        }}
        .hero p {{
            color: var(--muted);
            font-size: 18px;
        }}
        .pill {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            border-radius: 999px;
            background: rgba(14,165,164,0.12);
            color: var(--accent);
            border: 1px solid rgba(14,165,164,0.24);
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 12px;
        }}
        .hero-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 16px;
            box-shadow: 0 12px 24px rgba(0,0,0,0.12);
        }}
        .lamp-glow {{
            position: absolute;
            top: -120px;
            left: 50%;
            width: 520px;
            height: 260px;
            transform: translateX(-50%);
            background: {lamp_glow};
            filter: blur(8px);
            opacity: 0.85;
            pointer-events: none;
            z-index: 0;
        }}
        .hero-stack {{
            display: grid;
            gap: 14px;
        }}
        .card-title {{
            font-weight: 700;
            margin-bottom: 6px;
        }}
        .card-sub {{
            color: var(--muted);
            font-size: 13px;
            margin-bottom: 8px;
        }}
        .stat-row {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            border-bottom: 1px dashed rgba(148,163,184,0.2);
        }}
        .stat-row:last-child {{
            border-bottom: none;
        }}
        .hero-actions {{
            display: flex;
            gap: 12px;
            margin-top: 16px;
        }}
        .hero-meta {{
            display: flex;
            gap: 16px;
            margin-top: 14px;
            color: var(--muted);
            font-size: 13px;
        }}
        .tag-row {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .tag {{
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(125, 211, 252, 0.12);
            border: 1px solid rgba(125, 211, 252, 0.25);
            font-size: 12px;
            color: var(--accent);
        }}
        .hero-image {{
            border-radius: 18px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.2);
            box-shadow: 0 20px 30px rgba(0,0,0,0.15);
        }}
        .btn-outline {{
            border: 1px solid var(--border);
            background: var(--surface);
            color: var(--text);
            border-radius: 999px;
            padding: 10px 16px;
            font-weight: 600;
        }}
        .btn-primary {{
            background: var(--accent);
            color: white;
            border-radius: 999px;
            padding: 10px 18px;
            font-weight: 700;
            box-shadow: 0 10px 20px rgba(14,165,164,0.25);
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 6px;
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 6px;
            border-radius: 12px;
        }}
        .stTabs [data-baseweb="tab"] {{
            padding: 8px 14px;
            border-radius: 10px;
            font-weight: 600;
        }}
        .stTabs [aria-selected="true"] {{
            background: var(--accent);
            color: white !important;
        }}
        div[data-baseweb="input"] > div {{
            background: var(--surface-2);
            border-radius: 12px;
            border: 1px solid var(--border);
        }}
        textarea, input {{
            color: var(--text) !important;
        }}
        div[data-baseweb="select"] > div {{
            background: var(--surface-2);
            border-radius: 12px;
            border: 1px solid var(--border);
        }}
        .stTextArea textarea {{
            background: var(--surface-2);
            border-radius: 12px;
            border: 1px solid var(--border);
        }}
        .stExpander {{
            border-radius: var(--radius);
            border: 1px solid var(--border);
            background: var(--surface);
        }}
        .stAlert {{
            border-radius: var(--radius);
            border: 1px solid var(--border);
            background: var(--surface);
        }}
        @media (max-width: 900px) {{
            .hero {{
                grid-template-columns: 1fr;
            }}
        }}
        .section-title {{
            font-family: 'Plus Jakarta Sans', 'Noto Sans KR', sans-serif;
            font-size: 24px;
            font-weight: 700;
            margin: 18px 0 8px 0;
        }}
        .section-sub {{
            color: var(--muted);
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

def show_action_notice():
    msg = st.session_state.get("last_action_notice", "")
    if msg:
        st.success(msg)
        st.session_state.last_action_notice = ""

def render_obsidian_html(content):
    if MARKDOWN_AVAILABLE:
        html = md.markdown(content, extensions=["fenced_code", "tables"])
    else:
        escaped = (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        html = f"<pre>{escaped}</pre>"
    components.html(
        f"<div class='obsidian-note'>{html}</div>",
        height=480,
        scrolling=True
    )

def resolve_obsidian_embeds(content, vault_path, note_path):
    note_dir = os.path.dirname(note_path) if note_path else ""

    def find_file(target):
        candidates = []
        if os.path.isabs(target):
            candidates.append(target)
        else:
            if note_dir:
                candidates.append(os.path.join(note_dir, target))
            if vault_path:
                candidates.append(os.path.join(vault_path, target))
        # try common extensions if missing
        if not os.path.splitext(target)[1]:
            for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                if note_dir:
                    candidates.append(os.path.join(note_dir, target + ext))
                if vault_path:
                    candidates.append(os.path.join(vault_path, target + ext))
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    def repl(match):
        raw = match.group(1)
        target = raw.split("|")[0].strip()
        path = find_file(target)
        if not path:
            return match.group(0)
        ext = os.path.splitext(path)[1].lower()
        if ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
            data_uri = image_to_data_uri(path)
            if not data_uri:
                return match.group(0)
            return f"<img src='{data_uri}' style='max-width:100%; border-radius:12px; margin:8px 0;'/>"
        if ext == ".pdf":
            preview = pdf_first_page_to_data_uri(path)
            if preview:
                return (
                    f"<div style='margin:8px 0;'>"
                    f"<img src='{preview}' style='max-width:100%; border-radius:12px; border:1px solid #e5e7eb;'/>"
                    f"<div style='font-size:12px; color:#6b7280; margin-top:4px;'>첨부 PDF: {os.path.basename(path)}</div>"
                    f"</div>"
                )
            return f"<div style='margin:8px 0; padding:8px 12px; border:1px solid #e5e7eb; border-radius:10px;'>첨부 PDF: {os.path.basename(path)}</div>"
        return match.group(0)

    return re.sub(r"!\[\[(.*?)\]\]", repl, content)

def image_to_data_uri(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        ext = os.path.splitext(path)[1].lower().replace(".", "")
        mime = "image/png" if ext == "png" else "image/jpeg"
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""

def pdf_first_page_to_data_uri(path):
    try:
        doc = fitz.open(path)
        if doc.page_count == 0:
            return ""
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        data = pix.tobytes("png")
        doc.close()
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""

def compute_activity_heatmap(questions, days=365, now=None):
    check_time = now or datetime.now(timezone.utc)
    start = (check_time - timedelta(days=days - 1)).date()
    buckets = {}
    for i in range(days):
        d = start + timedelta(days=i)
        buckets[d.isoformat()] = {"count": 0, "correct": 0, "total": 0}
    for q in questions:
        stats = q.get("stats") or {}
        hist = stats.get("history") or []
        for entry in hist:
            if not isinstance(entry, dict):
                continue
            dt = parse_iso_datetime(entry.get("time"))
            if not dt:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dkey = dt.date().isoformat()
            if dkey in buckets:
                buckets[dkey]["count"] += 1
                buckets[dkey]["total"] += 1
                if entry.get("correct") is True:
                    buckets[dkey]["correct"] += 1
    rows = []
    for dkey, val in buckets.items():
        d = datetime.fromisoformat(dkey).date()
        week_index = (d - start).days // 7
        rows.append({
            "date": d,
            "dow": d.weekday(),
            "week_index": week_index,
            "count": val["count"],
            "accuracy": (val["correct"] / val["total"] * 100) if val["total"] > 0 else 0
        })
    return rows

def fsrs_due(item, now=None):
    if not FSRS_AVAILABLE:
        return True
    try:
        fsrs = item.get("fsrs") or {}
        card_data = fsrs.get("card")
        if not card_data:
            return True
        card = Card.from_json(card_data)
        check_time = now or datetime.now(timezone.utc)
        return card.due <= check_time
    except Exception:
        return True

def simple_srs_due(item, now=None):
    check_time = now or datetime.now(timezone.utc)
    srs = item.get("srs") or {}
    due = parse_iso_datetime(srs.get("due"))
    return due is None or due <= check_time

def srs_due(item, now=None):
    if FSRS_AVAILABLE:
        return fsrs_due(item, now=now)
    return simple_srs_due(item, now=now)

def apply_simple_srs_rating(q_id, rating_label):
    bank = load_questions()
    now = datetime.now(timezone.utc)
    # base intervals in days
    base = {"Again": 1, "Hard": 2, "Good": 4, "Easy": 7}
    for key in ("text", "cloze"):
        for item in bank.get(key, []):
            if item.get("id") == q_id:
                srs = item.get("srs") or {}
                interval = int(srs.get("interval", 1))
                factor = {"Again": 0.5, "Hard": 1.2, "Good": 2.0, "Easy": 3.0}.get(rating_label, 2.0)
                new_interval = max(1, int(interval * factor))
                # if first time, use base
                if not srs:
                    new_interval = base.get(rating_label, 4)
                due = now + timedelta(days=new_interval)
                srs.update({
                    "interval": new_interval,
                    "due": due.isoformat(),
                    "last_rating": rating_label,
                    "last_review": now.isoformat(),
                })
                item["srs"] = srs
                save_questions(bank)
                return srs
    return None

def apply_srs_rating(q_id, rating):
    if FSRS_AVAILABLE:
        return apply_fsrs_rating(q_id, rating)
    # rating can be string label
    label = rating if isinstance(rating, str) else str(rating)
    return apply_simple_srs_rating(q_id, label)

def get_fsrs_queue(questions, now=None, limit=50):
    if not FSRS_AVAILABLE:
        return []
    check_time = now or datetime.now(timezone.utc)
    due_items = []
    for q in questions:
        fsrs = q.get("fsrs") or {}
        card_data = fsrs.get("card")
        if not card_data:
            due_items.append((q, check_time))
            continue
        try:
            card = Card.from_json(card_data)
            due_time = card.due
        except Exception:
            due_time = check_time
        if due_time <= check_time:
            due_items.append((q, due_time))
    due_items.sort(key=lambda x: x[1])
    return due_items[:limit]

def get_fsrs_stats(questions, now=None):
    if not FSRS_AVAILABLE:
        return None
    check_time = now or datetime.now(timezone.utc)
    due = 0
    overdue = 0
    future = 0
    new = 0
    for q in questions:
        fsrs = q.get("fsrs") or {}
        card_data = fsrs.get("card")
        if not card_data:
            new += 1
            due += 1
            continue
        try:
            card = Card.from_json(card_data)
            if card.due <= check_time:
                due += 1
                if card.due < check_time:
                    overdue += 1
            else:
                future += 1
        except Exception:
            due += 1
    return {
        "due": due,
        "overdue": overdue,
        "future": future,
        "new": new,
    }

def apply_fsrs_rating(q_id, rating):
    if not FSRS_AVAILABLE:
        return None
    bank = load_questions()
    now = datetime.now(timezone.utc)
    for key in ("text", "cloze"):
        for item in bank.get(key, []):
            if item.get("id") == q_id:
                card_data = (item.get("fsrs") or {}).get("card")
                if card_data:
                    try:
                        card = Card.from_json(card_data)
                    except Exception:
                        card = Card()
                else:
                    card = Card()
                scheduler = Scheduler()
                card, log = scheduler.review_card(card, rating, now)
                fsrs = item.get("fsrs") or {}
                fsrs["card"] = card.to_json()
                fsrs["last_review"] = now.isoformat()
                fsrs["last_rating"] = rating.name if hasattr(rating, "name") else str(rating)
                fsrs["due"] = card.due.isoformat()
                logs = fsrs.get("logs", [])
                try:
                    logs.append(log.to_json())
                except Exception:
                    pass
                fsrs["logs"] = logs[-50:]
                item["fsrs"] = fsrs
                save_questions(bank)
                return fsrs
    return None

# ============================================================================
# 텍스트 추출 함수
# ============================================================================
@st.cache_resource(show_spinner=False)
def get_easyocr_reader(langs):
    try:
        import easyocr
    except Exception:
        return None
    return easyocr.Reader(list(langs), gpu=False)

def available_ocr_engines():
    engines = []
    if importlib.util.find_spec("easyocr") is not None:
        engines.append("easyocr")
    return engines

def ocr_page_image_bytes(image_bytes, engine="easyocr", langs=("ko", "en")):
    if engine != "easyocr":
        raise ValueError(f"지원하지 않는 OCR 엔진: {engine}")
    reader = get_easyocr_reader(tuple(langs))
    if reader is None:
        raise ValueError("easyocr 미설치")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    try:
        results = reader.readtext(tmp_path, detail=1, paragraph=False)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    if not results:
        return ""
    def bbox_key(item):
        bbox = item[0] if isinstance(item, (list, tuple)) and item else None
        if not bbox:
            return (0, 0)
        ys = [p[1] for p in bbox]
        xs = [p[0] for p in bbox]
        return (min(ys), min(xs))
    results = sorted(results, key=bbox_key)
    lines = [r[1].strip() for r in results if len(r) > 1 and str(r[1]).strip()]
    return "\n".join(lines)

def ocr_pdf_bytes(pdf_bytes, engine="easyocr", langs=("ko", "en"), max_pages=0, zoom=2.0):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts = []
    total_pages = doc.page_count
    limit = total_pages if max_pages in (0, None) else min(total_pages, max_pages)
    for i in range(limit):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        image_bytes = pix.tobytes("png")
        page_text = ocr_page_image_bytes(image_bytes, engine=engine, langs=langs)
        if page_text.strip():
            texts.append(f"=== 페이지 {i + 1} ===")
            texts.append(page_text)
            texts.append("")
    doc.close()
    return "\n".join(texts).strip()

def data_uri_from_bytes(data, ext):
    ext = ext.lower().replace(".", "")
    if ext in ("jpg", "jpeg"):
        mime = "image/jpeg"
    elif ext == "png":
        mime = "image/png"
    elif ext == "bmp":
        mime = "image/bmp"
    elif ext == "gif":
        mime = "image/gif"
    else:
        mime = "application/octet-stream"
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def data_uri_to_bytes(uri):
    if not uri:
        return b""
    m = re.match(r"^data:.*?;base64,(.*)$", uri)
    if not m:
        return b""
    try:
        return base64.b64decode(m.group(1))
    except Exception:
        return b""

def extract_images_from_pdf_bytes(pdf_bytes, max_images=80, min_kb=20):
    images = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        seen = set()
        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            for img in page.get_images(full=True):
                xref = img[0]
                base = doc.extract_image(xref)
                if not base or "image" not in base:
                    continue
                data = base["image"]
                if len(data) < min_kb * 1024:
                    continue
                rect = None
                try:
                    rect = page.get_image_bbox(xref)
                except Exception:
                    rect = None
                h = hashlib.sha1(data).hexdigest()
                if h in seen:
                    continue
                seen.add(h)
                ext = base.get("ext", "png")
                images.append({
                    "data_uri": data_uri_from_bytes(data, ext),
                    "ext": ext,
                    "page": page_idx + 1,
                    "y": rect.y0 if rect else None,
                    "y1": rect.y1 if rect else None,
                })
                if len(images) >= max_images:
                    break
            if len(images) >= max_images:
                break
        doc.close()
    except Exception:
        return []
    return images

def extract_pdf_question_anchors(pdf_bytes):
    anchors = {}
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        q_pattern = re.compile(r"^\s*(?:문항\s*)?(\d{1,3})\s*[).]")
        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            page_anchors = []
            data = page.get_text("dict")
            for block in data.get("blocks", []):
                for line in block.get("lines", []):
                    line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                    if not line_text:
                        continue
                    m = q_pattern.match(line_text.strip())
                    if m:
                        qnum = int(m.group(1))
                        y = line.get("bbox", [0, 0, 0, 0])[1]
                        page_anchors.append({"qnum": qnum, "y": y})
            if page_anchors:
                # de-duplicate by qnum, keep first occurrence
                seen = set()
                uniq = []
                for a in sorted(page_anchors, key=lambda x: x["y"]):
                    if a["qnum"] in seen:
                        continue
                    seen.add(a["qnum"])
                    uniq.append(a)
                anchors[page_idx + 1] = uniq
        doc.close()
    except Exception:
        return {}
    return anchors

def extract_images_from_hwp_bytes(hwp_bytes, max_images=80, min_kb=10):
    tmp_path = None
    odt_path = None
    images = []
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".hwp") as tmp:
            tmp.write(hwp_bytes)
            tmp_path = tmp.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".odt") as tmp_odt:
            odt_path = tmp_odt.name

        if shutil.which("hwp5odt"):
            result = subprocess.run(["hwp5odt", "--output", odt_path, tmp_path], capture_output=True, text=True)
            if result.returncode != 0:
                return []
        else:
            return []

        with zipfile.ZipFile(odt_path) as zf:
            for name in zf.namelist():
                if not name.startswith("bindata/"):
                    continue
                data = zf.read(name)
                if len(data) < min_kb * 1024:
                    continue
                ext = os.path.splitext(name)[1].lstrip(".") or "png"
                images.append({
                    "data_uri": data_uri_from_bytes(data, ext),
                    "ext": ext,
                    "page": None,
                })
                if len(images) >= max_images:
                    break
    except Exception:
        return []
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        if odt_path and os.path.exists(odt_path):
            try:
                os.unlink(odt_path)
            except Exception:
                pass
    return images

def _tokenize_for_match(text):
    if not text:
        return set()
    tokens = re.findall(r"[A-Za-z가-힣0-9]{2,}", text.lower())
    return set(tokens)

def clean_parsed_items(items, min_stem_len=15):
    cleaned = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        typ = item.get("type")
        if typ not in ("mcq", "cloze"):
            continue
        stem = (item.get("problem") if typ == "mcq" else item.get("front")) or ""
        stem = stem.strip()
        if not stem:
            continue
        if re.match(r"^(정답|답|해설|설명)\b", stem):
            continue
        if len(stem) < min_stem_len:
            if typ == "mcq" and len(item.get("options") or []) >= 3:
                pass
            else:
                continue
        if typ == "mcq":
            if len(item.get("options") or []) < 3:
                continue
        if typ == "cloze" and not str(item.get("answer", "")).strip():
            continue
        cleaned.append(item)
    return cleaned

def ocr_images_for_matching(images, engine="easyocr", langs=("ko", "en"), max_images=30, min_len=3):
    if not images:
        return images
    count = 0
    for img in images:
        if count >= max_images:
            break
        if img.get("ocr_text"):
            continue
        data = data_uri_to_bytes(img.get("data_uri", ""))
        if not data:
            continue
        try:
            text = ocr_page_image_bytes(data, engine=engine, langs=langs)
        except Exception:
            text = ""
        if text and len(text.strip()) >= min_len:
            img["ocr_text"] = text
        else:
            img["ocr_text"] = ""
        count += 1
    return images

def ai_match_images_to_items(items, images, ai_model, api_key=None, openai_api_key=None, max_images=10):
    if not items or not images or max_images <= 0:
        return items
    # group items by page
    page_map = {}
    for idx, item in enumerate(items):
        page = item.get("page")
        page_map.setdefault(page, []).append((idx, item))

    processed = 0
    for img in images:
        if processed >= max_images:
            break
        if img.get("matched"):
            continue
        page = img.get("page")
        candidates = page_map.get(page) or []
        if not candidates:
            continue
        # build candidate list
        lines = []
        for idx, item in candidates:
            stem = item.get("problem") or item.get("front") or ""
            stem = stem.replace("\n", " ").strip()
            if len(stem) > 160:
                stem = stem[:160] + "..."
            lines.append(f"{idx}: {stem}")
        prompt = (
            "You are matching a medical exam image to the most relevant question stem. "
            "Choose the single best question index from the list below. "
            "If none match, return -1. Return ONLY the index number.\n\n"
            "Questions:\n" + "\n".join(lines)
        )
        matched_idx = None
        try:
            if ai_model == "🔵 Google Gemini":
                if not api_key:
                    continue
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                img_bytes = data_uri_to_bytes(img.get("data_uri", ""))
                response = model.generate_content([prompt, img_bytes])
                text = (response.text or "").strip()
            else:
                if not openai_api_key:
                    continue
                client = OpenAI(api_key=openai_api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": img.get("data_uri", "")}},
                        ]}
                    ],
                    temperature=0
                )
                text = (response.choices[0].message.content or "").strip()
            m = re.search(r"-?\\d+", text)
            if m:
                matched_idx = int(m.group(0))
        except Exception:
            matched_idx = None

        if matched_idx is None or matched_idx < 0 or matched_idx >= len(items):
            processed += 1
            continue
        if items[matched_idx].get("images"):
            # avoid overwriting existing images
            processed += 1
            continue
        items[matched_idx].setdefault("images", [])
        items[matched_idx]["images"].append(img.get("data_uri"))
        img["matched"] = True
        processed += 1

    return items

def generate_explanations_ai(items, ai_model, api_key=None, openai_api_key=None, max_items=20):
    if not items or max_items <= 0:
        return items
    count = 0
    for item in items:
        if item.get("explanation"):
            continue
        if count >= max_items:
            break
        stem = item.get("problem") or item.get("front") or ""
        opts = item.get("options") or []
        answer = item.get("answer")
        if item.get("type") == "mcq":
            answer_text = None
            if isinstance(answer, int) and 1 <= answer <= len(opts):
                answer_text = opts[answer - 1]
            prompt = (
                "다음 객관식 문제의 해설을 2~4문장으로 작성하세요. "
                "정답 근거와 핵심 포인트만 간단히 설명하세요.\n\n"
                f"문항: {stem}\n"
                f"선지: {opts}\n"
                f"정답: {answer}"
            )
        else:
            prompt = (
                "다음 주관식/빈칸 문제의 해설을 2~4문장으로 작성하세요. "
                "정답 근거와 핵심 포인트만 간단히 설명하세요.\n\n"
                f"문항: {stem}\n"
                f"정답: {answer}"
            )
        try:
            if ai_model == "🔵 Google Gemini":
                if not api_key:
                    continue
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content(prompt)
                text = (response.text or "").strip()
            else:
                if not openai_api_key:
                    continue
                client = OpenAI(api_key=openai_api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=300
                )
                text = (response.choices[0].message.content or "").strip()
            if text:
                item["explanation"] = text
                count += 1
        except Exception:
            continue
    return items

def generate_single_explanation_ai(item, ai_model, api_key=None, openai_api_key=None):
    if not item:
        return ""
    stem = item.get("problem") or item.get("front") or ""
    opts = item.get("options") or []
    answer = item.get("answer")
    if item.get("type") == "mcq":
        prompt = (
            "다음 객관식 문제의 해설을 2~4문장으로 작성하세요. "
            "정답 근거와 핵심 포인트만 간단히 설명하세요.\n\n"
            f"문항: {stem}\n"
            f"선지: {opts}\n"
            f"정답: {answer}"
        )
    else:
        prompt = (
            "다음 주관식/빈칸 문제의 해설을 2~4문장으로 작성하세요. "
            "정답 근거와 핵심 포인트만 간단히 설명하세요.\n\n"
            f"문항: {stem}\n"
            f"정답: {answer}"
        )
    try:
        if ai_model == "🔵 Google Gemini":
            if not api_key:
                return ""
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            return (response.text or "").strip()
        else:
            if not openai_api_key:
                return ""
            client = OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            return (response.choices[0].message.content or "").strip()
    except Exception:
        return ""

def update_question_explanation(q_id, explanation_text):
    if not q_id:
        return False
    bank = load_questions()
    for key in ("text", "cloze"):
        for item in bank.get(key, []):
            if item.get("id") == q_id:
                item["explanation"] = explanation_text
                save_questions(bank)
                return True
    return False

def _extract_json_candidates(raw):
    if not raw:
        return []
    raw = raw.strip()
    candidates = []
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if fence:
        candidates.append(fence.group(1).strip())
    candidates.append(raw)
    arr = re.search(r"\[\s*\{[\s\S]+?\}\s*\]", raw)
    if arr:
        candidates.append(arr.group(0))
    obj = re.search(r"\{[\s\S]+\}", raw)
    if obj:
        candidates.append(obj.group(0))
    return candidates

def _parse_json_from_text(raw):
    for cand in _extract_json_candidates(raw):
        try:
            data = json.loads(cand)
            return data
        except Exception:
            continue
    return None

def ai_parse_exam_layout(left_text, right_text, ai_model, api_key=None, openai_api_key=None, hint_text=""):
    if not left_text or len(left_text.strip()) < 20:
        return []
    prompt = (
        "아래 LEFT/RIGHT 텍스트에서 시험 문항을 JSON 배열로 추출하세요. 오직 JSON만 출력하세요.\n"
        "LEFT에는 문항/선지가 있고, RIGHT에는 정답/해설(또는 요약)이 있습니다.\n"
        "RIGHT는 '▶ ⑤' 또는 '정답: ⑤' 같은 형식일 수 있으니 이를 정답으로 사용하세요.\n"
        "문항 번호가 보이면 qnum에 넣고, 없으면 순서대로 매칭하세요.\n"
        "형식:\n"
        "{\n"
        "  \"type\": \"mcq\" 또는 \"cloze\",\n"
        "  \"problem\": (mcq용 질문 본문),\n"
        "  \"front\": (cloze용 질문 본문),\n"
        "  \"options\": [\"선지1\", \"선지2\", ...] (mcq일 때만),\n"
        "  \"answer\": 정답 (mcq는 1-5 정수, cloze는 문자열),\n"
        "  \"explanation\": 해설(없으면 \"\"),\n"
        "  \"qnum\": 문항 번호(있으면 숫자)\n"
        "}\n"
        "[LEFT]\n"
    )
    if hint_text:
        prompt = f"[문서 구조 힌트]\n{hint_text}\n\n" + prompt
    prompt += left_text[:20000] + "\n\n[RIGHT]\n" + (right_text[:20000] if right_text else "")
    try:
        if ai_model == "🔵 Google Gemini":
            if not api_key:
                return []
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            raw = response.text or ""
        else:
            if not openai_api_key:
                return []
            client = OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4000
            )
            raw = response.choices[0].message.content or ""
        data = _parse_json_from_text(raw)
        if isinstance(data, dict):
            data = data.get("items") or data.get("questions") or data.get("data") or []
        if not isinstance(data, list):
            return []
        return clean_parsed_items(data)
    except Exception:
        return []

def ai_parse_exam_text(text, ai_model, api_key=None, openai_api_key=None, max_items=60, hint_text="", return_raw=False):
    if not text or len(text.strip()) < 20:
        return ([], "") if return_raw else []
    prompt = (
        "아래 텍스트에서 시험 문항을 JSON 배열로 추출하세요. 오직 JSON만 출력하세요.\n"
        "각 항목 형식:\n"
        "{\n"
        "  \"type\": \"mcq\" 또는 \"cloze\",\n"
        "  \"problem\": (mcq용 질문 본문),\n"
        "  \"front\": (cloze용 질문 본문),\n"
        "  \"options\": [\"선지1\", \"선지2\", ...] (mcq일 때만),\n"
        "  \"answer\": 정답 (mcq는 1-5 정수, cloze는 문자열),\n"
        "  \"explanation\": 해설(없으면 \"\"),\n"
        "  \"page\": 페이지 번호(텍스트에 '=== 페이지 N ===' 표기가 있으면 활용),\n"
        "  \"qnum\": 문항 번호(있으면 숫자)\n"
        "}\n"
        f"최대 {max_items}개까지만 출력하세요.\n"
        "문항이 겹치지 않도록 정확히 분리하세요.\n\n"
        "[원문]\n"
    )
    if hint_text:
        prompt = f"[문서 구조 힌트]\n{hint_text}\n\n" + prompt
    try:
        if ai_model == "🔵 Google Gemini":
            if not api_key:
                return ([], "") if return_raw else []
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt + text[:30000])
            raw = response.text or ""
        else:
            if not openai_api_key:
                return ([], "") if return_raw else []
            client = OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt + text[:30000]}],
                temperature=0.2,
                max_tokens=4000
            )
            raw = response.choices[0].message.content or ""

        data = _parse_json_from_text(raw)
        if data is None:
            return ([], raw) if return_raw else []
        if isinstance(data, dict):
            data = data.get("items") or data.get("questions") or data.get("data") or []
        if not isinstance(data, list):
            return ([], raw) if return_raw else []
        items = clean_parsed_items(data)
        return (items, raw) if return_raw else items
    except Exception:
        return ([], "") if return_raw else []

def ai_parse_exam_block(block_text, ai_model, api_key=None, openai_api_key=None, hint_text="", return_raw=False):
    if not block_text or len(block_text.strip()) < 10:
        return (None, "") if return_raw else None
    prompt = (
        "아래 텍스트에서 문항 1개를 JSON 객체로 추출하세요. 오직 JSON만 출력하세요.\n"
        "형식:\n"
        "{\n"
        "  \"type\": \"mcq\" 또는 \"cloze\",\n"
        "  \"problem\": (mcq용 질문 본문),\n"
        "  \"front\": (cloze용 질문 본문),\n"
        "  \"options\": [\"선지1\", \"선지2\", ...] (mcq일 때만),\n"
        "  \"answer\": 정답 (mcq는 1-5 정수, cloze는 문자열),\n"
        "  \"explanation\": 해설(없으면 \"\")\n"
        "}\n"
    )
    if hint_text:
        prompt += f"\n[문서 구조 힌트]\n{hint_text}\n"
    prompt += "\n[원문]\n"
    try:
        if ai_model == "🔵 Google Gemini":
            if not api_key:
                return (None, "") if return_raw else None
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt + block_text[:15000])
            raw = response.text or ""
        else:
            if not openai_api_key:
                return (None, "") if return_raw else None
            client = OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt + block_text[:15000]}],
                temperature=0.2,
                max_tokens=1200
            )
            raw = response.choices[0].message.content or ""
        data = _parse_json_from_text(raw)
        if not isinstance(data, dict):
            return (None, raw) if return_raw else None
        items = clean_parsed_items([data])
        item = items[0] if items else None
        return (item, raw) if return_raw else item
    except Exception:
        return (None, "") if return_raw else None

def should_attach_image(item):
    text = (item.get("problem") or item.get("front") or "")
    text = text.lower()
    keywords = [
        "x-ray", "xray", "ct", "mri", "us", "ultrasound", "sonography", "radiograph",
        "영상", "영상소견", "영상 소견", "사진", "그림", "figure", "fig.", "영상에서", "사진을 보고", "영상학적"
    ]
    return any(k in text for k in keywords)

def auto_attach_images_to_items(items, images, strategy="page", max_per_question=1, anchors=None, min_score=0.2, only_if_keyword=False):
    if not items or not images:
        return items
    if max_per_question < 1:
        return items

    if strategy == "sequential":
        img_idx = 0
        for item in items:
            if item.get("images"):
                continue
            attach = []
            for _ in range(max_per_question):
                if img_idx >= len(images):
                    break
                attach.append(images[img_idx]["data_uri"])
                img_idx += 1
            if attach:
                item["images"] = attach
        return items

    if strategy == "layout" and anchors:
        # build intervals per page: [qnum, start_y, end_y)
        intervals = {}
        for page, arr in anchors.items():
            if not arr:
                continue
            arr_sorted = sorted(arr, key=lambda x: x["y"])
            page_intervals = []
            for idx, a in enumerate(arr_sorted):
                start = a["y"]
                end = arr_sorted[idx + 1]["y"] if idx + 1 < len(arr_sorted) else float("inf")
                page_intervals.append({"qnum": a["qnum"], "start": start, "end": end})
            intervals[page] = page_intervals

        image_map = {}
        for img in images:
            page = img.get("page")
            y = img.get("y")
            if page not in intervals or y is None:
                continue
            for seg in intervals[page]:
                if seg["start"] <= y < seg["end"]:
                    key = (page, seg["qnum"])
                    image_map.setdefault(key, []).append(img["data_uri"])
                    break

        for item in items:
            if item.get("images"):
                continue
            if only_if_keyword and not should_attach_image(item):
                continue
            page = item.get("page")
            qnum = item.get("qnum")
            if page is None or qnum is None:
                continue
            key = (page, qnum)
            imgs = image_map.get(key) or []
            if imgs:
                item["images"] = imgs[:max_per_question]
        return items

    if strategy == "page":
        page_to_images = {}
        for img in images:
            page = img.get("page")
            page_to_images.setdefault(page, []).append(img["data_uri"])
        for item in items:
            if item.get("images"):
                continue
            if only_if_keyword and not should_attach_image(item):
                continue
            page = item.get("page")
            candidates = page_to_images.get(page) or []
            if candidates:
                item["images"] = candidates[:max_per_question]
        return items

    if strategy == "ocr":
        # build token sets per item
        item_tokens = []
        for item in items:
            text = " ".join([
                item.get("problem") or item.get("front") or "",
                " ".join(item.get("options", []) or []),
                item.get("explanation") or ""
            ])
            item_tokens.append(_tokenize_for_match(text))

        def item_key(i):
            return f"{items[i].get('page')}_{items[i].get('qnum')}_{i}"

        attached = {}
        for i, item in enumerate(items):
            attached[item_key(i)] = list(item.get("images", [])) if item.get("images") else []

        for img in images:
            ocr_text = img.get("ocr_text", "") or ""
            tokens_img = _tokenize_for_match(ocr_text)
            if not tokens_img:
                continue
            best_idx = None
            best_score = 0.0
            for i, tokens in enumerate(item_tokens):
                if not tokens:
                    continue
                if only_if_keyword and not should_attach_image(items[i]):
                    continue
                # prefer same page if available
                if img.get("page") and items[i].get("page") and img.get("page") != items[i].get("page"):
                    continue
                overlap = len(tokens_img & tokens) / max(1, len(tokens_img))
                if overlap > best_score:
                    best_score = overlap
                    best_idx = i
            if best_idx is None or best_score < min_score:
                continue
            key = item_key(best_idx)
            if img["data_uri"] in attached[key]:
                continue
            if len(attached[key]) >= max_per_question:
                continue
            attached[key].append(img["data_uri"])

        for i, item in enumerate(items):
            key = item_key(i)
            if attached.get(key):
                item["images"] = attached[key]
        return items

    return items

def extract_text_from_pdf(uploaded_file, enable_ocr=True, ocr_engine="auto", ocr_langs=("ko", "en"), ocr_max_pages=0, min_text_len=200, include_page_markers=False):
    """PDF에서 텍스트 추출"""
    try:
        pdf_bytes = uploaded_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for i, page in enumerate(doc):
            page_text = page.get_text()
            if include_page_markers:
                text += f"=== 페이지 {i + 1} ===\n"
            text += page_text
            if include_page_markers:
                text += "\n"
        doc.close()
        if len(text.strip()) >= min_text_len:
            return text
        # OCR fallback (스캔 PDF 등)
        if not enable_ocr:
            return text
        engines = available_ocr_engines()
        if not engines:
            return text
        try:
            engine = engines[0] if ocr_engine == "auto" else ocr_engine
            ocr_text = ocr_pdf_bytes(pdf_bytes, engine=engine, langs=ocr_langs, max_pages=ocr_max_pages)
            return ocr_text if ocr_text.strip() else text
        except Exception:
            return text
    except Exception as e:
        raise ValueError(f"PDF 처리 실패: {str(e)}")

def extract_text_from_docx(uploaded_file):
    """Word (.docx)에서 텍스트 추출"""
    try:
        doc = Document(uploaded_file)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text += cell.text + "\n"
        return text
    except Exception as e:
        raise ValueError(f"Word 문서 처리 실패: {str(e)}")

def extract_text_from_pptx(uploaded_file):
    """PowerPoint (.pptx)에서 텍스트 추출"""
    try:
        prs = Presentation(uploaded_file)
        text = ""
        for slide_num, slide in enumerate(prs.slides, 1):
            text += f"\n=== 슬라이드 {slide_num} ===\n"
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
        return text
    except Exception as e:
        raise ValueError(f"PowerPoint 처리 실패: {str(e)}")

def extract_text_from_hwp(uploaded_file):
    """HWP (.hwp)에서 텍스트 추출 (hwp5txt 필요)"""
    tmp_path = None
    try:
        if hasattr(uploaded_file, "read"):
            data = uploaded_file.read()
        else:
            data = uploaded_file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".hwp") as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        def is_table_placeholder_text(text):
            if not text or not text.strip():
                return True
            placeholder_count = text.count("<표>")
            if placeholder_count >= 3:
                cleaned = re.sub(r"<표>", "", text)
                cleaned = re.sub(r"\s+", "", cleaned)
                if len(cleaned) < 80:
                    return True
                if not re.search(r"[①②③④⑤]|\\b정답\\b|\\b답\\b", text):
                    return True
            return False

        def extract_text_from_odt_content(xml_bytes):
            try:
                root = ET.fromstring(xml_bytes)
            except Exception:
                return ""
            ns = {
                "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
                "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
                "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
                "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
            }
            body = root.find("office:body/office:text", ns)
            if body is None:
                return ""

            def normalize_line(line):
                line = line.replace("\u00a0", " ")
                line = re.sub(r"[ \t]+", " ", line).strip()
                return line

            def cell_lines(cell):
                lines = []
                for p in cell.findall(".//text:p", ns) + cell.findall(".//text:h", ns):
                    line = normalize_line("".join(p.itertext()))
                    if line:
                        lines.append(line)
                img_count = len(cell.findall(".//draw:image", ns))
                if img_count:
                    lines.append(f"[이미지 x{img_count}]")
                return lines

            out_lines = []
            for child in body:
                if child.tag == f"{{{ns['table']}}}table":
                    for row in child.findall("table:table-row", ns):
                        row_lines = []
                        for cell in row.findall("table:table-cell", ns):
                            lines = cell_lines(cell)
                            if lines:
                                row_lines.append("\n".join(lines))
                        if row_lines:
                            out_lines.append("\n".join(row_lines))
                            out_lines.append("")
                elif child.tag in (f"{{{ns['text']}}}p", f"{{{ns['text']}}}h"):
                    line = normalize_line("".join(child.itertext()))
                    if line:
                        out_lines.append(line)
            return "\n".join(out_lines).strip()

        def extract_text_from_hwp5odt(path):
            odt_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".odt") as tmp_odt:
                    odt_path = tmp_odt.name
                def run_odt(cmd):
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise ValueError(result.stderr.strip() or "hwp5odt 변환 실패")
                    if not os.path.exists(odt_path) or os.path.getsize(odt_path) == 0:
                        raise ValueError("ODT 변환 결과가 비어있습니다.")
                if shutil.which("hwp5odt"):
                    run_odt(["hwp5odt", "--output", odt_path, path])
                else:
                    try:
                        import importlib.util
                        if importlib.util.find_spec("hwp5.hwp5odt") is not None:
                            run_odt([sys.executable, "-m", "hwp5.hwp5odt", "--output", odt_path, path])
                        else:
                            return ""
                    except Exception:
                        return ""
                with zipfile.ZipFile(odt_path) as zf:
                    xml_bytes = zf.read("content.xml")
                return extract_text_from_odt_content(xml_bytes)
            finally:
                if odt_path and os.path.exists(odt_path):
                    try:
                        os.unlink(odt_path)
                    except Exception:
                        pass

        def run_hwp5txt(cmd):
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise ValueError(result.stderr.strip() or "hwp5txt 변환 실패")
            text = result.stdout
            if not text.strip():
                raise ValueError("HWP 텍스트가 비어있습니다.")
            return text

        if shutil.which("hwp5txt"):
            text = run_hwp5txt(["hwp5txt", tmp_path])
            if not is_table_placeholder_text(text):
                return text
            odt_text = extract_text_from_hwp5odt(tmp_path)
            if odt_text:
                return odt_text
            return text

        # fallback: python -m hwp5.hwp5txt (pyhwp 설치되어 있으나 PATH에 없을 때)
        try:
            import importlib.util
            if importlib.util.find_spec("hwp5.hwp5txt") is not None:
                text = run_hwp5txt([sys.executable, "-m", "hwp5.hwp5txt", tmp_path])
                if not is_table_placeholder_text(text):
                    return text
                odt_text = extract_text_from_hwp5odt(tmp_path)
                if odt_text:
                    return odt_text
                return text
        except Exception:
            pass

        raise ValueError(
            "hwp5txt 실행 파일을 찾을 수 없습니다. "
            "pyhwp 설치 후 다시 시도하세요. (예: `python -m pip install pyhwp`)"
        )
    except Exception as e:
        raise ValueError(f"HWP 처리 실패: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

def extract_text_from_file(uploaded_file, **kwargs):
    """파일 형식에 따라 자동으로 텍스트 추출"""
    file_ext = Path(uploaded_file.name).suffix.lower()
    
    if file_ext == ".pdf":
        return extract_text_from_pdf(uploaded_file, **kwargs)
    elif file_ext == ".docx":
        return extract_text_from_docx(uploaded_file)
    elif file_ext == ".pptx":
        return extract_text_from_pptx(uploaded_file)
    elif file_ext == ".hwp":
        return extract_text_from_hwp(uploaded_file)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {file_ext}")

def parse_uploaded_question_file(uploaded_file, mode_hint="auto"):
    """사용자 업로드 문항 파일 파싱 (json/txt/tsv)"""
    ext = Path(uploaded_file.name).suffix.lower()
    content_bytes = uploaded_file.read()
    if ext == ".json":
        try:
            data = json.loads(content_bytes.decode("utf-8"))
        except Exception:
            data = json.loads(content_bytes.decode("utf-8-sig"))
        items = []
        if isinstance(data, dict) and ("text" in data or "cloze" in data):
            for it in data.get("text", []):
                norm = normalize_mcq_item(it)
                if norm:
                    items.append(norm)
            for it in data.get("cloze", []):
                norm = normalize_cloze_item(it)
                if norm:
                    items.append(norm)
        elif isinstance(data, list):
            for it in data:
                if isinstance(it, dict) and (it.get("type") == "cloze" or "front" in it or ("content" in it and "{{c1::" in str(it.get("content", "")))):
                    norm = normalize_cloze_item(it)
                else:
                    norm = normalize_mcq_item(it)
                if norm:
                    items.append(norm)
        elif isinstance(data, dict):
            if data.get("type") == "cloze" or "front" in data or ("content" in data and "{{c1::" in str(data.get("content", ""))):
                norm = normalize_cloze_item(data)
            else:
                norm = normalize_mcq_item(data)
            if norm:
                items.append(norm)
        return items

    # text/tsv/hwp
    if ext == ".hwp":
        text = extract_text_from_hwp(content_bytes)
    else:
        text = content_bytes.decode("utf-8", errors="ignore")
    if mode_hint == "auto":
        if "{{c1::" in text:
            mode_hint = "🧩 빈칸 뚫기 (Anki Cloze)"
        elif "정답" in text and not re.search(r"①|②|③|④|⑤", text):
            mode_hint = "🧩 빈칸 뚫기 (Anki Cloze)"
        else:
            mode_hint = "📝 객관식 문제 (Case Study)"

    if mode_hint == "🧩 빈칸 뚫기 (Anki Cloze)" and "{{c1::" not in text:
        qa_parsed = parse_qa_to_cloze(text)
        if qa_parsed:
            return qa_parsed
    parsed = parse_generated_text_to_structured(text, mode_hint)
    if isinstance(parsed, list) and parsed:
        return parsed
    # fallback: fuzzy parser for messy past exam text
    fuzzy = parse_exam_text_fuzzy(text)
    return fuzzy if isinstance(fuzzy, list) else []

# ============================================================================
# AI 콘텐츠 생성
# ============================================================================
PROMPT_MCQ = """
당신은 의과대학 교수입니다. 강의록을 분석하여 '임상 증례형 객관식 문제(5지 선다)'를 5문제 출제하세요.

[출제 지침]
1. 단순 암기보다 증상, 검사 소견을 보고 진단/치료를 고르는 문제 위주.
2. 각 문제마다 명확한 증례 제시.
3. 선지는 정확히 5개만 작성할 것.
4. 해설에 정답 이유와 오답 이유를 명확히 설명할 것.
5. 정확히 JSON 형식으로만 출력할 것.

[필수 출력 형식 - JSON 배열]
[
  {
    "problem": "[문제] 임상 증례... 증상 + 검사 소견 + 진단 질문",
    "options": ["선지 1", "선지 2", "선지 3", "선지 4", "선지 5"],
    "answer": 1,
    "explanation": "정답(①) 이유: ... | ②번 오답 이유: ... | ③번 오답 이유: ... | ④번 오답 이유: ... | ⑤번 오답 이유: ..."
  },
  {
    "problem": "[문제] 다른 증례...",
    "options": ["선지 1", "선지 2", "선지 3", "선지 4", "선지 5"],
    "answer": 2,
    "explanation": "..."
  }
]

[중요 규칙]:
- 반드시 유효한 JSON 배열만 출력
- answer는 1~5 숫자 (1 = ①, 2 = ②, 3 = ③, 4 = ④, 5 = ⑤)
- 각 문제는 독립적이어야 함
"""


PROMPT_CLOZE = """
당신은 의대생 튜터입니다. 텍스트에서 중요한 개념, 병명, 증상, 수치를 Anki Cloze(빈칸) 형식으로 변환하세요.

[작성 지침]
1. 문맥상 핵심 키워드를 `{{c1::정답}}`으로 감싸세요.
2. 한 줄에 하나의 사실(Fact)만 작성하세요.
3. 예시: "α-thalassemia due to a three gene deletion presents with {{c1::HbH}} disease."
4. 불필요한 서론/결론 없이 변환된 문장만 나열하세요.
"""

def build_style_instructions(style_text):
    if not style_text:
        return ""
    excerpt = style_text[:8000]
    return f"""
[기출문제 스타일 참고]
{excerpt}

[스타일 지시]
- 위 기출문제의 질문 구조, 난이도, 문장 길이, 선지 톤/표현을 최대한 모사
- 내용은 강의록 기반으로 생성
- 출력 형식 규칙은 반드시 유지
"""

def generate_content_gemini(text_content, selected_mode, num_items=5, api_key=None, style_text=None):
    """Gemini를 이용해 콘텐츠 생성"""
    if not api_key:
        return "⚠️ 왼쪽 사이드바에 Gemini API 키를 먼저 입력해주세요."
    
    if not text_content or len(text_content.strip()) < 10:
        return "⚠️ 추출된 텍스트가 너무 짧습니다. 다시 시도해주세요."
    
    style_block = build_style_instructions(style_text)
    if selected_mode == "📝 객관식 문제 (Case Study)":
        system_prompt = PROMPT_MCQ.replace("5문제", f"{num_items}문제") + style_block
    else:
        system_prompt = PROMPT_CLOZE + style_block + f"\n\n[요청] 총 {num_items}개 항목을 출력하세요. 한 줄에 하나의 항목만 작성하세요."
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(f"{system_prompt}\n\n[강의록 내용]:\n{text_content[:30000]}")
        return response.text
    except Exception as e:
        return f"❌ Gemini 생성 실패: {str(e)}"

def generate_content_openai(text_content, selected_mode, num_items=5, openai_api_key=None, style_text=None):
    """ChatGPT를 이용해 콘텐츠 생성"""
    if not openai_api_key:
        return "⚠️ 왼쪽 사이드바에 OpenAI API 키를 먼저 입력해주세요."
    
    if not text_content or len(text_content.strip()) < 10:
        return "⚠️ 추출된 텍스트가 너무 짧습니다. 다시 시도해주세요."
    
    style_block = build_style_instructions(style_text)
    if selected_mode == "📝 객관식 문제 (Case Study)":
        system_prompt = PROMPT_MCQ.replace("5문제", f"{num_items}문제") + style_block
    else:
        system_prompt = PROMPT_CLOZE + style_block + f"\n\n[요청] 총 {num_items}개 항목을 출력하세요. 한 줄에 하나의 항목만 작성하세요."
    
    try:
        import sys
        print(f"[OPENAI DEBUG] API 키 길이: {len(openai_api_key)}", file=sys.stderr)
        print(f"[OPENAI DEBUG] 텍스트 길이: {len(text_content[:30000])}", file=sys.stderr)
        
        openai_client = OpenAI(api_key=openai_api_key)
        print(f"[OPENAI DEBUG] OpenAI 클라이언트 생성 완료", file=sys.stderr)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"[강의록 내용]:\n{text_content[:30000]}"}
            ],
            temperature=0.7,
            max_tokens=4000
        )
        
        result = response.choices[0].message.content
        print(f"[OPENAI DEBUG] 응답 길이: {len(result)}", file=sys.stderr)
        
        # MCQ는 JSON으로 파싱, Cloze는 그대로 반환
        if selected_mode == "📝 객관식 문제 (Case Study)":
            result = convert_json_mcq_to_text(result, num_items)
        
        return result
    except Exception as e:
        import traceback
        error_msg = f"❌ ChatGPT 생성 실패: {str(e)}\n\n스택 트레이스:\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        return error_msg

def convert_json_mcq_to_text(json_text, num_items):
    """JSON 형식의 MCQ를 기존 텍스트 형식으로 변환"""
    import json
    import sys
    
    try:
        # JSON 파싱
        data = json.loads(json_text)
        if not isinstance(data, list):
            data = [data]
        
        print(f"[JSON PARSE] {len(data)}개 MCQ 파싱 성공", file=sys.stderr)
        
        # 텍스트 형식으로 변환
        result_lines = []
        for idx, item in enumerate(data[:num_items], 1):
            problem = item.get("problem", f"[문제] {idx}번")
            options = item.get("options", [])
            answer = item.get("answer", 1)  # 1~5 숫자
            explanation = item.get("explanation", "")
            
            # problem에 [문제]가 없으면 추가
            if "[문제]" not in problem:
                problem = f"[문제] {problem}"
            
            # MCQ 블록 구성
            block = problem + "\n\n"
            circ = ['①', '②', '③', '④', '⑤']
            for i, opt in enumerate(options[:5]):
                block += f"{circ[i]} {opt}\n"
            
            # 정답과 설명 추가
            ans_num = str(answer) if isinstance(answer, int) and 1 <= answer <= 5 else "1"
            block += f"\n정답: {{{{c1::{ans_num}}}}}\n해설: {explanation}"
            
            result_lines.append(block)
        
        # '---'으로 구분
        final_result = "\n---\n".join(result_lines)
        print(f"[JSON CONVERT] {len(result_lines)}개 MCQ 변환 완료", file=sys.stderr)
        
        return final_result
    
    except json.JSONDecodeError as e:
        print(f"[JSON ERROR] JSON 파싱 실패: {str(e)}", file=sys.stderr)
        # JSON 파싱 실패시 원본 반환 (다른 파싱 로직이 처리할 것)
        return json_text
    except Exception as e:
        print(f"[CONVERT ERROR] 변환 실패: {str(e)}", file=sys.stderr)
        return json_text


def generate_content(text_content, selected_mode, ai_model, num_items=5, api_key=None, openai_api_key=None, style_text=None):
    """선택된 AI 모델을 사용해 콘텐츠 생성"""
    if ai_model == "🔵 Google Gemini":
        return generate_content_gemini(text_content, selected_mode, num_items=num_items, api_key=api_key, style_text=style_text)
    else:  # ChatGPT
        return generate_content_openai(text_content, selected_mode, num_items=num_items, openai_api_key=openai_api_key, style_text=style_text)

def split_text_into_chunks(text, chunk_size=8000, overlap=500):
    """문자 단위로 텍스트를 분할 (중첩 포함)"""
    if chunk_size <= 0:
        return [text]
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= text_len:
            break
        start = end - overlap if end - overlap > start else end
    return chunks

def generate_content_in_chunks(text_content, selected_mode, ai_model, num_items=5, chunk_size=8000, overlap=500, api_key=None, openai_api_key=None, style_text=None):
    """텍스트를 청크로 나누어 모델 호출을 여러 번 수행
    
    Returns:
        - 객관식: 구조화된 dict 리스트 (각 dict는 {type, problem, options, answer, explanation})
        - Cloze: 구조화된 dict 리스트 (각 dict는 {type, front, answer, explanation})
    """
    import sys
    chunks = split_text_into_chunks(text_content, chunk_size=chunk_size, overlap=overlap)
    total_chunks = len(chunks)
    
    print(f"[CHUNKS DEBUG] 총 청크 수: {total_chunks}", file=sys.stderr)
    
    if total_chunks == 0:
        return []
    
    base = num_items // total_chunks
    rem = num_items % total_chunks
    items_per_chunk = [base + (1 if i < rem else 0) for i in range(total_chunks)]

    results = [None] * total_chunks
    progress_bar = st.progress(0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, total_chunks)) as ex:
        futures = {}
        for idx, chunk in enumerate(chunks):
            n = items_per_chunk[idx]
            if n <= 0:
                results[idx] = ""
                continue
            futures[ex.submit(generate_content, chunk, selected_mode, ai_model, n, api_key, openai_api_key, style_text)] = idx

        completed = 0
        for fut in concurrent.futures.as_completed(futures):
            idx = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = f"❌ 청크 처리 실패: {str(e)}"
            results[idx] = res if isinstance(res, str) else str(res)
            completed += 1
            progress_bar.progress(int(completed / total_chunks * 100))

    # 모든 청크 결과 결합
    combined = "\n".join([r for r in results if r])
    
    print(f"[COMBINED DEBUG] 청크 결과 개수: {len([r for r in results if r])}/{total_chunks}, 총 길이: {len(combined)}", file=sys.stderr)

    # 결합된 텍스트를 구조화된 형식으로 파싱
    structured_list = parse_generated_text_to_structured(combined, selected_mode)
    
    # 중복 제거
    seen = set()
    deduped = []
    for item in structured_list:
        key = str(item)  # 또는 더 정교한 키 생성
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    
    # 필요한 개수만 반환
    return deduped[:num_items]

# ============================================================================
# 사이드바 설정
# ============================================================================
with st.sidebar:
    st.header("⚙️ 설정 & 모드")
    
    st.session_state.ai_model = st.radio(
        "🤖 AI 모델 선택",
        ["🔵 Google Gemini", "🟢 OpenAI ChatGPT"]
    )
    
    st.markdown("---")
    
    if st.session_state.ai_model == "🔵 Google Gemini":
        st.session_state.api_key = st.text_input("Gemini API Key 입력", type="password")
        st.session_state.openai_api_key = None
    else:
        st.session_state.api_key = None
        st.session_state.openai_api_key = st.text_input("OpenAI API Key 입력", type="password")
    
    st.markdown("---")
    st.session_state.chunk_size = st.slider("청크 크기 (문자 수)", 2000, 30000, 8000, 500)
    st.session_state.overlap = st.slider("청크 중첩 (문자 수)", 0, 5000, 500, 100)
    
    st.markdown("---")
    st.subheader("⚙️ 필터링 옵션")
    st.session_state.enable_filter = st.checkbox("품질 필터 사용", value=True)
    st.session_state.min_length = st.slider("최소 문자 수", 10, 200, 30)
    st.session_state.auto_tag_enabled = st.checkbox("자동 난이도/카테고리 태깅", value=True)
    st.session_state.explanation_default = st.checkbox("해설 기본 열기", value=st.session_state.explanation_default)

    st.markdown("---")
    st.subheader("🎨 테마")
    if not LOCK_SAFE and not LOCK_THEME:
        st.session_state.theme_enabled = st.toggle("커스텀 테마 사용", value=st.session_state.theme_enabled)
    elif LOCK_SAFE:
        st.info("Safe mode 활성화됨 (URL에 ?safe=1).")
        st.session_state.theme_enabled = False
    elif LOCK_THEME:
        st.info("테마 강제 활성화됨 (URL에 ?safe=0).")
        st.session_state.theme_enabled = True

    if hasattr(st, "toggle"):
        dark_on = st.toggle("다크 모드", value=(st.session_state.theme_mode == "Dark"))
    else:
        dark_on = st.checkbox("다크 모드", value=(st.session_state.theme_mode == "Dark"))
    st.session_state.theme_mode = "Dark" if dark_on else "Light"
    st.session_state.theme_bg = "Gradient"

# 블록 외에서도 접근 가능하도록 로컬 변수에 할당
ai_model = st.session_state.get("ai_model", "🔵 Google Gemini")
api_key = st.session_state.get("api_key")
openai_api_key = st.session_state.get("openai_api_key")
chunk_size = st.session_state.get("chunk_size", 8000)
overlap = st.session_state.get("overlap", 500)
enable_filter = st.session_state.get("enable_filter", True)
min_length = st.session_state.get("min_length", 30)
auto_tag_enabled = st.session_state.get("auto_tag_enabled", True)

# Apply theme (skip if disabled)
THEME_ENABLED = bool(st.session_state.get("theme_enabled"))
if THEME_ENABLED:
    apply_theme(st.session_state.theme_mode, st.session_state.theme_bg)

# ============================================================================
# 메인 UI: 탭 구조
# ============================================================================
tab_home, tab_gen, tab_convert, tab_exam, tab_notes = st.tabs(["🏠 홈", "📚 문제 생성", "🧾 기출문제 변환", "🎯 실전 시험", "🗒️ 노트"])

# ============================================================================
# TAB: 홈
# ============================================================================
with tab_home:
    st.title("🏠 홈")
    show_action_notice()

    stats = get_question_stats()
    bank = load_questions()
    all_questions = bank.get("text", []) + bank.get("cloze", [])
    acc = compute_overall_accuracy(all_questions)
    acc_text = f"{acc['accuracy']:.1f}%" if acc else "—"

    if not THEME_ENABLED:
        st.info("Safe mode: 커스텀 테마/히어로를 비활성화했습니다. 사이드바에서 '커스텀 테마 사용'을 켜면 적용됩니다.")
        st.header("밤하늘처럼 맑은 의대 학습 흐름")
        st.write("강의록과 기출문제를 연결해, 학습-시험-복습을 하나의 흐름으로 만듭니다.")
        st.write(f"전체 정답률: {acc_text}")
        st.write(f"저장된 객관식: {stats['total_text']} · 저장된 빈칸: {stats['total_cloze']}")
    else:
        st.markdown(
            f"""
            <div class="lamp-glow"></div>
            <div class="hero">
              <div>
                <div class="pill">Milky Way Mode · 차분한 몰입</div>
                <h1>밤하늘처럼 맑은<br/>의대 학습 흐름</h1>
                <p>AMBOSS 스타일의 구조와 알렌의 서재처럼 고요한 몰입감. 강의록과 기출문제를 연결해, 학습-시험-복습을 하나의 흐름으로 만듭니다.</p>
                <div class="hero-actions">
                  <div class="btn-primary">문제 생성 시작</div>
                  <div class="btn-outline">실전 시험 모드</div>
                </div>
                <div class="hero-meta">
                  <span>USMLE 스타일</span>
                  <span>FSRS 복습</span>
                  <span>Obsidian 연동</span>
                </div>
              </div>
              <div class="hero-stack">
                <div class="hero-card">
                  <div class="card-title">오늘의 흐름</div>
                  <div class="stat-row"><span>전체 정답률</span><strong>{acc_text}</strong></div>
                  <div class="stat-row"><span>저장된 객관식</span><strong>{stats["total_text"]}</strong></div>
                  <div class="stat-row"><span>저장된 빈칸</span><strong>{stats["total_cloze"]}</strong></div>
                </div>
                <div class="hero-card">
                  <div class="card-title">빠른 시작</div>
                  <div class="card-sub">강의록 → 문제 생성 → 복습</div>
                  <div class="tag-row">
                    <span class="tag">Case Study</span>
                    <span class="tag">Cloze</span>
                    <span class="tag">FSRS</span>
                  </div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # 통계
    col1, col2 = st.columns(2)
    with col1:
        st.metric("저장된 객관식", stats["total_text"])
    with col2:
        st.metric("저장된 빈칸", stats["total_cloze"])

    st.markdown("---")
    st.subheader("학습 대시보드")
    wrong_items, total_wrong = get_wrong_note_stats(all_questions)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("오답 누적 문항", len(wrong_items))
    with col2:
        st.metric("오답 누적 횟수", total_wrong)
    with col3:
        st.metric("전체 문항", len(all_questions))

    # 오답노트 필터
    subjects_all = sorted({(q.get("subject") or "General") for q in all_questions}) if all_questions else []
    diffs_all = sorted({(q.get("difficulty") or "미지정") for q in all_questions}) if all_questions else []
    sel_subjects = st.multiselect("오답노트 분과 필터", subjects_all, default=subjects_all)
    sel_diffs = st.multiselect("오답노트 난이도 필터", diffs_all, default=diffs_all)
    st.session_state.wrong_priority = st.selectbox(
        "오답노트 우선순위",
        ["오답 횟수", "오답률", "최근 오답"],
        index=["오답 횟수", "오답률", "최근 오답"].index(st.session_state.wrong_priority)
    )
    if st.session_state.wrong_priority == "최근 오답":
        st.session_state.wrong_weight_recent = st.slider(
            "가중치: 최근 오답",
            0.0, 1.0, st.session_state.wrong_weight_recent, 0.05
        )
        st.session_state.wrong_weight_count = 1.0 - st.session_state.wrong_weight_recent
        st.caption(f"오답 횟수 가중치: {st.session_state.wrong_weight_count:.2f}")
    filtered_wrong = [
        q for q in wrong_items
        if (q.get("subject") or "General") in sel_subjects
        and (q.get("difficulty") or "미지정") in sel_diffs
    ]

    if filtered_wrong:
        if st.button("📌 오답노트 세션 준비", use_container_width=True, key="prepare_wrong_session"):
            # 오답 문항으로 학습 세션 준비 (실전 시험 탭에서 진행)
            parsed_selected = []
            for raw in sort_wrong_first(
                filtered_wrong,
                mode=st.session_state.wrong_priority,
                weight_recent=st.session_state.wrong_weight_recent,
                weight_count=st.session_state.wrong_weight_count
            ):
                if raw.get("type") == "cloze":
                    parsed_selected.append(parse_cloze_content(raw))
                else:
                    parsed_selected.append(parse_mcq_content(raw))
            st.session_state.exam_questions = parsed_selected[:50]
            st.session_state.current_question_idx = 0
            st.session_state.user_answers = {}
            st.session_state.exam_started = True
            st.session_state.exam_finished = False
            st.session_state.exam_mode = "학습모드"
            st.session_state.revealed_answers = set()
            st.session_state.auto_advance_guard = None
            st.session_state.exam_stats_applied = False
            st.session_state.graded_questions = set()
            st.success("오답노트 세션이 준비되었습니다. 🎯 실전 시험 탭으로 이동해 시작하세요.")
    else:
        st.info("선택한 필터에 해당하는 오답 문항이 없습니다.")

    # FSRS / SRS 상태
    st.caption(f"복습 엔진: {'FSRS' if FSRS_AVAILABLE else '기본 SRS'}")

    if FSRS_AVAILABLE and all_questions:
        with st.expander("📊 FSRS 분과/난이도 리포트", expanded=False):
            subject_rows = fsrs_group_report(all_questions, "subject")
            if subject_rows:
                st.markdown("**분과별**")
                st.dataframe(subject_rows, use_container_width=True, hide_index=True)
            difficulty_rows = fsrs_group_report(all_questions, "difficulty")
            if difficulty_rows:
                st.markdown("**난이도별**")
                st.dataframe(difficulty_rows, use_container_width=True, hide_index=True)
    elif not FSRS_AVAILABLE:
        st.info("FSRS 미설치: 기본 SRS로 동작 중입니다.")

    st.markdown("---")
    st.subheader("🧾 시험 기록")
    history = load_exam_history()
    if not history:
        st.info("저장된 시험 기록이 없습니다.")
    else:
        labels = []
        for idx, h in enumerate(history):
            ts = h.get("finished_at", "")
            acc = h.get("accuracy", 0)
            labels.append(f"{idx + 1}. {ts} | {h.get('type')} | {acc}%")
        sel = st.selectbox("기록 선택", labels, index=0)
        sel_idx = labels.index(sel)
        h = history[sel_idx]
        st.write(f"문항 수: {h.get('num_questions')} / 정답: {h.get('correct')} / 정확도: {h.get('accuracy')}%")
        if h.get("subjects"):
            st.caption(f"분과: {', '.join(h.get('subjects'))}")
        if h.get("units"):
            st.caption(f"단원: {', '.join(h.get('units'))}")

        for i, item in enumerate(h.get("items", []), 1):
            status_icon = "✅" if item.get("is_correct") else "❌"
            title = f"{status_icon} 문제 {i}"
            with st.expander(title, expanded=False):
                st.markdown(item.get("front") or "")
                if item.get("type") == "mcq":
                    opts = item.get("options") or []
                    letters = ["A", "B", "C", "D", "E"]
                    for idx_opt, opt in enumerate(opts[:5]):
                        st.write(f"{letters[idx_opt]}. {opt}")
                    user = item.get("user")
                    correct_num = item.get("correct")
                    user_display = letters[user - 1] if isinstance(user, int) and 1 <= user <= 5 else "응답 없음"
                    correct_display = letters[correct_num - 1] if isinstance(correct_num, int) and 1 <= correct_num <= 5 else "?"
                else:
                    user_display = item.get("user") or "응답 없음"
                    correct_display = item.get("answer") or ""

                st.divider()
                st.write(f"**당신의 답:** {user_display}")
                st.write(f"**정답:** {correct_display}")
                if item.get("explanation"):
                    show_exp = st.checkbox("해설 보기", value=st.session_state.explanation_default, key=f"hist_exp_{sel_idx}_{i}")
                    if show_exp:
                        st.markdown(format_explanation_text(item.get("explanation")))
                if item.get("id"):
                    note_key = f"hist_note_{sel_idx}_{i}"
                    st.text_area("메모", value=item.get("note", ""), key=note_key, height=80)
                    if st.button("메모 저장", key=f"save_hist_note_{sel_idx}_{i}"):
                        saved = update_question_note(item["id"], st.session_state.get(note_key, ""))
                        if saved:
                            st.success("메모 저장됨")

    with st.expander("🧹 데이터 관리", expanded=False):
        st.caption("주의: 삭제 작업은 되돌릴 수 없습니다.")
        confirm = st.checkbox("삭제 작업을 이해했습니다.")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("객관식 전체 삭제", use_container_width=True, disabled=not confirm):
                with st.spinner("객관식 문항 삭제 중..."):
                    clear_question_bank(mode="mcq")
                st.session_state.last_action_notice = "객관식 문항을 삭제했습니다."
                st.session_state.exam_started = False
                st.session_state.exam_questions = []
                st.session_state.user_answers = {}
                st.rerun()
        with col2:
            if st.button("빈칸 전체 삭제", use_container_width=True, disabled=not confirm):
                with st.spinner("빈칸 문항 삭제 중..."):
                    clear_question_bank(mode="cloze")
                st.session_state.last_action_notice = "빈칸 문항을 삭제했습니다."
                st.session_state.exam_started = False
                st.session_state.exam_questions = []
                st.session_state.user_answers = {}
                st.rerun()
        with col3:
            if st.button("전체 문항 삭제", use_container_width=True, disabled=not confirm):
                with st.spinner("전체 문항 삭제 중..."):
                    clear_question_bank(mode="all")
                st.session_state.last_action_notice = "모든 문항을 삭제했습니다."
                st.session_state.exam_started = False
                st.session_state.exam_questions = []
                st.session_state.user_answers = {}
                st.rerun()
        if st.button("시험 기록 삭제", use_container_width=True, disabled=not confirm):
            clear_exam_history()
            st.session_state.last_action_notice = "시험 기록을 삭제했습니다."
            st.rerun()

        st.markdown("---")
        subjects = sorted({(q.get("subject") or "General") for q in all_questions}) if all_questions else []
        sel_subjects_del = st.multiselect("분과별 삭제", subjects)
        if sel_subjects_del:
            if st.button("선택 분과 삭제", use_container_width=True, disabled=not confirm):
                data = load_questions()
                before_text = len(data.get("text", []))
                before_cloze = len(data.get("cloze", []))
                data["text"] = [q for q in data.get("text", []) if (q.get("subject") or "General") not in sel_subjects_del]
                data["cloze"] = [q for q in data.get("cloze", []) if (q.get("subject") or "General") not in sel_subjects_del]
                save_questions(data)
                deleted = (before_text - len(data.get("text", []))) + (before_cloze - len(data.get("cloze", [])))
                st.session_state.last_action_notice = f"{deleted}개 문항 삭제됨 (분과: {', '.join(sel_subjects_del)})"
                st.rerun()

    with st.expander("🗑️ 객관식 선택 삭제", expanded=False):
        bank_now = load_questions()
        mcq_list = bank_now.get("text", [])
        if not mcq_list:
            st.info("객관식 문항이 없습니다.")
        else:
            st.caption("개별 문항을 선택해 삭제할 수 있습니다.")
            st.markdown("---")
            subj = st.selectbox(
                "분과 필터",
                ["전체"] + sorted({(q.get("subject") or "General") for q in mcq_list})
            )
            search = st.text_input("문항 검색", value="")
            filtered = []
            for q in mcq_list:
                if subj != "전체" and (q.get("subject") or "General") != subj:
                    continue
                text = q.get("problem", "")
                if search and search.lower() not in text.lower():
                    continue
                filtered.append(q)
            filtered = filtered[:200]

            if hasattr(st, "data_editor"):
                rows = []
                for q in filtered:
                    qid = q.get("id")
                    if not qid:
                        continue
                    rows.append({
                        "선택": False,
                        "id": qid,
                        "분과": q.get("subject") or "General",
                        "문항": (q.get("problem") or "")[:120],
                    })
                edited = st.data_editor(
                    rows,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "id": st.column_config.TextColumn("ID", width="small"),
                        "분과": st.column_config.TextColumn("분과", width="small"),
                        "문항": st.column_config.TextColumn("문항", width="large"),
                    },
                    disabled=["id", "분과", "문항"],
                    key="mcq_delete_editor"
                )
                selected_ids = [r["id"] for r in edited if r.get("선택")]
            else:
                id_to_q = {q.get("id"): q for q in filtered if q.get("id")}
                options = list(id_to_q.keys())

                def format_item(qid):
                    q = id_to_q.get(qid) or {}
                    subj_name = q.get("subject") or "General"
                    title = (q.get("problem") or "")[:80]
                    return f"{qid[:8]} | {subj_name} | {title}"

                selected_ids = st.multiselect("개별 문항 선택", options, format_func=format_item)

            confirm_sel = st.checkbox("개별 삭제 확인", key="confirm_item_delete")
            if selected_ids:
                if st.button("선택 문항 삭제", disabled=not confirm_sel):
                    deleted = delete_mcq_by_ids(selected_ids)
                    st.session_state.last_action_notice = f"{deleted}개 문항 삭제됨"
                    st.rerun()

            st.markdown("---")
            st.caption("세트(배치) 단위 삭제")
            batches = get_mcq_batches(mcq_list)
            if batches:
                batch_labels = []
                for b, cnt in sorted(batches.items(), key=lambda x: x[0]):
                    batch_labels.append(f"{b} ({cnt}개)")
                sel_batch = st.selectbox("세트 선택", ["선택 없음"] + batch_labels)
                confirm_batch = st.checkbox("세트 삭제 확인", key="confirm_batch_delete")
                if sel_batch != "선택 없음":
                    batch_id = sel_batch.split(" (")[0]
                    if st.button("세트 삭제", disabled=not confirm_batch):
                        deleted = delete_mcq_by_batch(batch_id)
                        st.session_state.last_action_notice = f"{deleted}개 문항 삭제됨 (세트: {batch_id})"
                        st.rerun()
            else:
                st.caption("세트 정보가 없습니다.")

    st.markdown("---")
    st.subheader("학습 시각화")
    colp1, colp2, colp3 = st.columns([1, 1, 1])
    with colp1:
        st.session_state.profile_name = st.text_input(
            "설정 프리셋 이름",
            value=st.session_state.profile_name,
            help="히트맵 구간/색상 등 개인 설정을 저장해두는 기능입니다.",
        )
    with colp2:
        if st.button("불러오기"):
            loaded = apply_profile_settings(st.session_state.profile_name)
            st.session_state.last_action_notice = "프로필 설정을 불러왔습니다." if loaded else "해당 프로필이 없습니다."
            st.rerun()
    with colp3:
        if st.button("저장"):
            persist_profile_settings(st.session_state.profile_name)
            st.session_state.last_action_notice = "프로필 설정을 저장했습니다."
            st.rerun()

    st.caption("프리셋은 히트맵 구간/색상 등 개인 설정을 저장해두는 기능입니다. 이름을 적고 저장/불러오기를 눌러주세요.")
    acc = compute_overall_accuracy(all_questions)
    heat = compute_activity_heatmap(all_questions, days=365)
    with st.expander("히트맵 구간/색상 설정", expanded=False):
        st.caption("문항 수 구간을 조정하면 색 농도가 바뀝니다.")
        b1 = st.number_input("구간 1 (1회)", min_value=1, value=1)
        b2 = st.number_input("구간 2 (2~)", min_value=2, value=3)
        b3 = st.number_input("구간 3 (4~)", min_value=3, value=6)
        b4 = st.number_input("구간 4 (7~)", min_value=4, value=10)
        st.session_state.heatmap_bins = [0, b1, b2, b3, b4]
        st.session_state.heatmap_colors = [
            "#ffffff",
            st.color_picker("색상 1", value=st.session_state.heatmap_colors[1]),
            st.color_picker("색상 2", value=st.session_state.heatmap_colors[2]),
            st.color_picker("색상 3", value=st.session_state.heatmap_colors[3]),
            st.color_picker("색상 4", value=st.session_state.heatmap_colors[4]),
            st.color_picker("색상 5", value=st.session_state.heatmap_colors[5]),
        ]
    col_left, col_right = st.columns([1, 2])
    with col_left:
        st.markdown("**전체 정답률**")
        if acc:
            try:
                import pandas as pd
                import altair as alt

                df = pd.DataFrame([
                    {"label": "Correct", "value": acc["correct"]},
                    {"label": "Wrong", "value": acc["wrong"]},
                ])
                base = alt.Chart(df).mark_arc(innerRadius=60, outerRadius=100).encode(
                    theta=alt.Theta("value:Q"),
                    color=alt.Color("label:N", scale=alt.Scale(range=["#34d399", "#f87171"]), legend=None),
                    tooltip=["label:N", "value:Q"]
                )
                text = alt.Chart(pd.DataFrame([{"text": f"{acc['accuracy']:.1f}%"}])).mark_text(
                    size=26, font="IBM Plex Sans", fontWeight="600"
                ).encode(text="text:N")
                st.altair_chart((base + text).properties(width=220, height=220), use_container_width=False)
                st.caption(f"{acc['correct']}/{acc['total']} 정답")
            except Exception:
                st.metric("전체 정답률", f"{acc['accuracy']:.1f}%")
        else:
            st.info("아직 풀이 기록이 없습니다.")

    with col_right:
                    st.markdown("**학습 활동 히트맵 (최근 365일)**")
                    if heat:
                        try:
                            import pandas as pd
                            import altair as alt

                            df = pd.DataFrame(heat)
                            df["dow_label"] = df["dow"].map({0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"})
                            df["week_index"] = df["week_index"].astype(str)
                            # bucket counts for discrete colors (0 = white)
                            b = st.session_state.heatmap_bins
                            labels = ["0", f"1-{b[1]}", f"{b[1]+1}-{b[2]}", f"{b[2]+1}-{b[3]}", f"{b[3]+1}-{b[4]}", f"{b[4]+1}+"]
                            df["bucket"] = pd.cut(
                                df["count"],
                                bins=[-0.1, 0, b[1], b[2], b[3], b[4], 9999],
                                labels=labels
                            )
                            heatmap = (
                                alt.Chart(df)
                                .mark_rect(cornerRadius=0)
                                .encode(
                                    x=alt.X("week_index:O", axis=None),
                                    y=alt.Y("dow_label:O", sort=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"], axis=None),
                                    color=alt.Color(
                                        "bucket:N",
                                        scale=alt.Scale(
                                            domain=labels,
                                            range=st.session_state.heatmap_colors
                                        ),
                                        legend=None
                                    ),
                                    tooltip=["date:T", "count:Q", "accuracy:Q"]
                                )
                                .properties(width=alt.Step(12), height=alt.Step(12))
                            )
                            st.altair_chart(heatmap, use_container_width=True)
                        except Exception:
                            st.dataframe(heat, use_container_width=True, hide_index=True)

# ============================================================================
# TAB: 문제 생성
# ============================================================================
with tab_gen:
    st.title("📚 문제 생성 & 저장")
    
    # 파일 업로드
    uploaded_file = st.file_uploader("강의 자료 업로드", type=["pdf", "docx", "pptx", "hwp"])
    style_file = st.file_uploader("기출문제 스타일 업로드 (선택)", type=["pdf", "docx", "pptx", "hwp", "txt", "tsv", "json"], key="style_upload")
    style_text = None
    if style_file:
        try:
            if Path(style_file.name).suffix.lower() in [".txt", ".tsv"]:
                style_text = style_file.read().decode("utf-8", errors="ignore")
            elif Path(style_file.name).suffix.lower() == ".json":
                style_text = style_file.read().decode("utf-8", errors="ignore")
            else:
                style_text = extract_text_from_file(style_file)
        except Exception as e:
            st.warning(f"기출문제 스타일 파일 처리 실패: {str(e)}")
    
    if uploaded_file:
        st.info(f"📄 **{uploaded_file.name}** ({uploaded_file.size:,} bytes)")
        
        # 생성 설정
        col1, col2 = st.columns(2)
        with col1:
            mode = st.radio("모드", ["📝 객관식 문제 (Case Study)", "🧩 빈칸 뚫기 (Anki Cloze)"])
        with col2:
            num_items = st.slider("생성 개수", 1, 50, 10)
        
        # 저장할 과목/단원명
        col_subj, col_unit = st.columns(2)
        with col_subj:
            subject_input = st.text_input("과목명 (예: 순환기내과)", value="General")
        with col_unit:
            unit_input = st.text_input("단원명 (선택)", value="미분류")
        
        if st.button("🚀 문제 생성 시작", use_container_width=True):
            try:
                with st.spinner("📖 강의 자료 분석 중..."):
                    raw_text = extract_text_from_file(uploaded_file)
                    st.caption(f"✅ 추출됨: {len(raw_text):,} 글자")
                
                with st.spinner("⚙️ AI가 문제 생성 중... (1~2분 소요)"):
                    result = generate_content_in_chunks(
                        raw_text,
                        mode,
                        ai_model,
                        num_items=num_items,
                        chunk_size=chunk_size,
                        overlap=overlap,
                        api_key=api_key,
                        openai_api_key=openai_api_key,
                        style_text=style_text,
                    )
                
                # result는 이제 구조화된 dict 리스트
                if result and isinstance(result, list) and len(result) > 0:
                    # JSON에 저장
                    saved_count = add_questions_to_bank(result, mode, subject_input, unit_input, quality_filter=enable_filter, min_length=min_length)
                    st.success(f"✅ **{saved_count}개 문제** 생성 및 저장 완료!")
                    
                    # 통계 업데이트
                    stats = get_question_stats()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("저장된 객관식", stats["total_text"], delta="+" + str(saved_count) if "객관식" in mode else None)
                    with col2:
                        st.metric("저장된 빈칸", stats["total_cloze"], delta="+" + str(saved_count) if "빈칸" in mode else None)
                    
                    st.markdown("---")
                    
                    # 미리보기
                    with st.expander("📋 생성된 문제 미리보기 (상위 5개)", expanded=True):
                        if not result:
                            st.warning("파싱된 문제가 없습니다.")
                        else:
                            st.info(f"전체: {len(result)}개 | 저장됨: {saved_count}개")
                            for i, item_data in enumerate(result[:5], 1):
                                if item_data.get('type') == 'mcq':
                                    st.markdown(f"**문제 {i}** (객관식)")
                                    st.write(f"**문항:** {item_data.get('problem', '')[:150]}...")
                                    st.write(f"**선지:** {', '.join(item_data.get('options', [])[:3])}...")
                                    st.write(f"**정답:** {item_data.get('answer', '?')} 번")
                                else:
                                    st.markdown(f"**문제 {i}** (빈칸)")
                                    st.write(f"**내용:** {item_data.get('front', '')[:150]}...")
                                    st.write(f"**정답:** {item_data.get('answer', '?')}")
                                st.divider()
                    
                    # 다운로드 - 구조화된 JSON으로 다운로드
                    import json
                    download_data = json.dumps(result, ensure_ascii=False, indent=2)
                    st.download_button(
                        label="📥 JSON으로 다운로드",
                        data=download_data,
                        file_name="questions.json",
                        mime="application/json",
                        use_container_width=True,
                        key="download_generated_json"
                    )
                else:
                    st.error(f"❌ 생성 실패! 결과를 확인할 수 없습니다.")
                    st.write(f"반환값: {result}")
                    
            except Exception as e:
                st.error(f"❌ 오류: {str(e)}")
                import traceback
                st.error(f"상세 오류:\n{traceback.format_exc()}")

    st.markdown("---")
    st.info("기출문제 파일 변환은 **🧾 기출문제 변환** 탭에서 진행합니다.")

# ============================================================================
# TAB: 실전 시험
# ============================================================================
with tab_convert:
    st.title("🧾 기출문제 전용 변환")
    st.caption("HWP/PDF/DOCX/PPTX/TXT/TSV 파일을 기출문제 형식으로 변환하여 저장합니다.")

    with st.expander("🧩 HWP+PDF 듀얼 업로드(수동 최소화)", expanded=False):
        st.caption("HWP에서 문항 텍스트를 추출하고, PDF에서 이미지/페이지 정보를 연결합니다.")
        col_dual1, col_dual2 = st.columns(2)
        with col_dual1:
            dual_hwp = st.file_uploader("HWP 업로드 (문항 텍스트)", type=["hwp"], key="dual_hwp_upload")
        with col_dual2:
            dual_pdf = st.file_uploader("PDF 업로드 (이미지/레이아웃)", type=["pdf"], key="dual_pdf_upload")

        dual_subject = st.text_input("기본 과목명", value="General", key="dual_subject")
        dual_unit = st.text_input("기본 단원명 (선택)", value="DualUpload", key="dual_unit")

        dual_threshold = st.slider("자동 매칭 신뢰도 기준", 0.05, 0.6, 0.2, step=0.05, key="dual_threshold")

        if st.button("🔗 듀얼 자동 매칭 실행", use_container_width=True, key="dual_run"):
            if not dual_hwp or not dual_pdf:
                st.error("HWP와 PDF를 모두 업로드해주세요.")
            else:
                try:
                    dual_hwp.seek(0)
                    dual_pdf.seek(0)
                    hwp_text = extract_text_from_hwp(dual_hwp)
                    pdf_bytes = dual_pdf.getvalue()
                    page_texts = extract_pdf_page_texts(pdf_bytes)
                    images = extract_images_from_pdf_bytes(pdf_bytes)
                    anchors = extract_pdf_question_anchors(pdf_bytes)

                    # 1) HWP 텍스트로 문항 파싱
                    items = parse_exam_text_fuzzy(hwp_text)
                    items = clean_parsed_items(items)

                    # 2) 문항-페이지 매칭
                    scores = match_questions_to_pages(items, page_texts)

                    # 3) 이미지 연결 (페이지 기반)
                    items = auto_attach_images_to_items(
                        items,
                        images,
                        strategy="page",
                        max_per_question=1,
                        anchors=anchors,
                        min_score=0.2,
                        only_if_keyword=False
                    )

                    st.session_state.past_exam_items = items
                    st.session_state.past_exam_images = images
                    st.session_state.past_exam_anchors = anchors
                    st.session_state.dual_exam_text = hwp_text
                    st.session_state.dual_exam_images = images
                    st.session_state.dual_exam_page_text = page_texts
                    st.session_state.dual_match_scores = scores

                    st.success(f"듀얼 매칭 완료: {len(items)}개 문항")
                    st.rerun()
                except Exception as e:
                    st.error(f"듀얼 매칭 실패: {str(e)}")

        if st.session_state.dual_match_scores:
            weak = [i for i, v in st.session_state.dual_match_scores.items() if v.get("score", 0) < dual_threshold]
            st.caption(f"자동 매칭 신뢰도 낮음: {len(weak)}개 문항 → 아래 편집 탭에서 수동 보정하세요.")

        if st.button("📝 HWP 텍스트만 추출", use_container_width=True, key="dual_text_only"):
            if not dual_hwp:
                st.error("HWP 파일을 업로드해주세요.")
            else:
                try:
                    dual_hwp.seek(0)
                    hwp_text = extract_text_from_hwp(dual_hwp)
                    hwp_text = preclean_exam_text(hwp_text)
                    items = parse_exam_text_fuzzy(hwp_text)
                    items = clean_parsed_items(items)
                    st.session_state.past_exam_items = items
                    st.session_state.past_exam_images = []
                    st.session_state.past_exam_anchors = {}
                    st.session_state.dual_exam_text = hwp_text
                    st.success(f"HWP 텍스트 추출 완료: {len(items)}개 문항")
                    st.rerun()
                except Exception as e:
                    st.error(f"HWP 텍스트 추출 실패: {str(e)}")

    uploaded_exam = st.file_uploader(
        "기출문제 파일 업로드",
        type=["hwp", "pdf", "docx", "pptx", "txt", "tsv"],
        key="past_exam_upload"
    )

    if uploaded_exam:
        file_ext = Path(uploaded_exam.name).suffix.lower()
        ocr_enabled = True
        ocr_engine = "auto"
        ocr_langs = ("ko", "en")
        ocr_max_pages = 0
        uploaded_bytes = uploaded_exam.getvalue()

        if file_ext == ".pdf":
            with st.expander("🧠 OCR 설정 (스캔 PDF용)", expanded=False):
                ocr_enabled = st.checkbox(
                    "텍스트가 부족하면 OCR 자동 실행",
                    value=True,
                    key="past_exam_ocr_enable"
                )
                ocr_engine = st.selectbox(
                    "OCR 엔진",
                    ["auto", "easyocr"],
                    index=0,
                    key="past_exam_ocr_engine"
                )
                lang_choice = st.selectbox(
                    "언어",
                    ["한국어+영어", "영어"],
                    index=0,
                    key="past_exam_ocr_lang"
                )
                ocr_langs = ("ko", "en") if lang_choice == "한국어+영어" else ("en",)
                ocr_max_pages = st.number_input(
                    "OCR 페이지 제한 (0=전체)",
                    min_value=0,
                    max_value=500,
                    value=0,
                    step=1,
                    key="past_exam_ocr_pages"
                )

        if st.session_state.past_exam_file != uploaded_exam.name:
            st.session_state.past_exam_file = uploaded_exam.name
            st.session_state.past_exam_text = ""
            st.session_state.past_exam_items = []
            st.session_state.past_exam_images = []
            st.session_state.past_exam_anchors = {}
            st.session_state.ai_parse_raw = ""

        if not st.session_state.past_exam_text:
            try:
                if hasattr(uploaded_exam, "seek"):
                    uploaded_exam.seek(0)
                st.session_state.past_exam_text = extract_text_from_file(
                    uploaded_exam,
                    enable_ocr=ocr_enabled,
                    ocr_engine=ocr_engine,
                    ocr_langs=ocr_langs,
                    ocr_max_pages=ocr_max_pages,
                    include_page_markers=(file_ext == ".pdf")
                )
            except Exception as e:
                st.error(f"❌ 기출문제 파일 처리 실패: {str(e)}")

        if not st.session_state.past_exam_images and uploaded_bytes:
            try:
                if file_ext == ".pdf":
                    st.session_state.past_exam_images = extract_images_from_pdf_bytes(uploaded_bytes)
                    st.session_state.past_exam_anchors = extract_pdf_question_anchors(uploaded_bytes)
                elif file_ext == ".hwp":
                    st.session_state.past_exam_images = extract_images_from_hwp_bytes(uploaded_bytes)
            except Exception:
                st.session_state.past_exam_images = []

        if file_ext == ".pdf":
            engines = available_ocr_engines()
            if len(st.session_state.past_exam_text.strip()) < 200 and not engines:
                st.warning("PDF에서 텍스트가 거의 추출되지 않았습니다. OCR이 필요합니다. `python -m pip install easyocr` 설치 후 다시 시도하세요.")
            if st.button("🔁 원문 다시 추출", use_container_width=True, key="past_exam_reextract"):
                try:
                    if hasattr(uploaded_exam, "seek"):
                        uploaded_exam.seek(0)
                    st.session_state.past_exam_text = extract_text_from_file(
                        uploaded_exam,
                        enable_ocr=ocr_enabled,
                        ocr_engine=ocr_engine,
                        ocr_langs=ocr_langs,
                        ocr_max_pages=ocr_max_pages,
                        include_page_markers=True
                    )
                    st.session_state.past_exam_items = []
                    st.session_state.past_exam_images = extract_images_from_pdf_bytes(uploaded_bytes)
                    st.session_state.past_exam_anchors = extract_pdf_question_anchors(uploaded_bytes)
                except Exception as e:
                    st.error(f"❌ 원문 재추출 실패: {str(e)}")

        col1, col2 = st.columns(2)
        with col1:
            exam_subject = st.text_input("기본 과목명", value="General", key="past_exam_subject")
        with col2:
            default_unit = Path(uploaded_exam.name).stem[:50] if uploaded_exam else "미분류"
            exam_unit = st.text_input("기본 단원명 (선택)", value=default_unit, key="past_exam_unit")

        parse_mode = st.radio(
            "변환 방식",
            ["자동(기출 파서)", "Cloze(정답: 기반)", "객관식(선지 기준)"],
            horizontal=True,
            key="past_exam_mode"
        )

        st.markdown("**이미지 자동 연결**")
        auto_attach = st.checkbox("문항에 이미지 자동 연결", value=True, key="auto_attach_images")
        max_imgs = st.slider("문항당 최대 이미지 수", 0, 3, 1, key="auto_attach_max_images")
        only_attach_keyword = st.checkbox("이미지 키워드가 있는 문항만 연결", value=True, key="auto_attach_keyword_only")

        if file_ext == ".pdf":
            attach_label = st.selectbox(
                "자동 연결 방식",
                ["레이아웃 기반(권장)", "OCR 기반(텍스트 포함 이미지)", "페이지 기반"],
                index=0,
                key="auto_attach_mode"
            )
            if attach_label.startswith("OCR"):
                attach_strategy = "ocr"
                ocr_img_limit = st.slider("OCR 이미지 개수 제한", 5, 80, 20, key="ocr_img_limit")
                ocr_min_score = st.slider("매칭 기준(0~1)", 0.05, 0.6, 0.2, step=0.05, key="ocr_min_score")
            elif attach_label.startswith("페이지"):
                attach_strategy = "page"
            else:
                attach_strategy = "layout" if st.session_state.past_exam_anchors else "page"
            use_ai_match = st.checkbox("AI 이미지 매칭(보정)", value=False, key="ai_match_images")
            ai_match_limit = st.slider("AI 매칭 이미지 수", 1, 30, 8, key="ai_match_limit")
        else:
            attach_strategy = "sequential"

        st.text_area(
            "추출된 원문 (필요시 수정 가능)",
            value=st.session_state.past_exam_text,
            height=240,
            key="past_exam_text_area"
        )

        with st.expander("🤖 AI 파서 (문항 분리/정제)", expanded=False):
            st.caption("겹쳐진 문항을 분리하거나 주관식 문항을 구조화하고 싶을 때 사용합니다.")
            ai_parse_limit = st.slider("최대 문항 수", 10, 200, 60, step=10, key="ai_parse_limit")
            parse_mode_ai = st.radio("AI 파서 방식", ["전체 텍스트", "블록 분할"], horizontal=True, key="ai_parse_mode")
            hint_text = st.text_area(
                "문서 구조 힌트 (선택)",
                value="",
                placeholder="예: 2열 표 → 좌측 문항, 우측 정답/해설. 1열 표 → 문항→정답→해설 순서.",
                key="ai_parse_hint"
            )
            if file_ext == ".pdf":
                st.caption("PDF 레이아웃 파서는 2열(좌:문항/우:정답·해설) 또는 1열 구조에 최적화되어 있습니다.")
                use_ai_layout = st.checkbox(
                    "AI로 레이아웃 파서 실행(추천)",
                    value=True,
                    key="use_ai_layout_parser"
                )
                if st.button("📐 PDF 레이아웃 파서 실행", use_container_width=True, key="layout_parse_run"):
                    with st.spinner("PDF 레이아웃 분석 중..."):
                        layout_items = []
                        if use_ai_layout:
                            if st.session_state.ai_model == "🔵 Google Gemini" and not api_key:
                                st.error("Gemini API 키가 필요합니다. 사이드바에서 입력해주세요.")
                            elif st.session_state.ai_model == "🟢 OpenAI ChatGPT" and not openai_api_key:
                                st.error("OpenAI API 키가 필요합니다. 사이드바에서 입력해주세요.")
                            else:
                                layout_items = parse_pdf_layout_ai(
                                    uploaded_bytes,
                                    ai_model=st.session_state.ai_model,
                                    api_key=api_key,
                                    openai_api_key=openai_api_key,
                                    hint_text=hint_text
                                )
                        if not layout_items:
                            layout_items = parse_pdf_layout(uploaded_bytes)
                        if layout_items:
                            if auto_attach and st.session_state.past_exam_images:
                                layout_items = auto_attach_images_to_items(
                                    layout_items,
                                    st.session_state.past_exam_images,
                                    strategy=attach_strategy,
                                    max_per_question=max_imgs,
                                    anchors=st.session_state.past_exam_anchors,
                                    min_score=st.session_state.get("ocr_min_score", 0.2),
                                    only_if_keyword=only_attach_keyword
                                )
                            if st.session_state.get("ai_match_images") and st.session_state.past_exam_images:
                                layout_items = ai_match_images_to_items(
                                    layout_items,
                                    st.session_state.past_exam_images,
                                    ai_model=st.session_state.get("ai_model", "🔵 Google Gemini"),
                                    api_key=api_key,
                                    openai_api_key=openai_api_key,
                                    max_images=st.session_state.get("ai_match_limit", 8)
                                )
                            st.session_state.past_exam_items = layout_items
                            st.success(f"레이아웃 파서 완료: {len(layout_items)}개 문항")
                            st.rerun()
                        else:
                            st.warning("레이아웃 파서 결과가 비어있습니다. OCR 후 다시 시도하거나 AI 파서를 사용하세요.")
            if parse_mode_ai == "블록 분할":
                block_limit = st.slider("블록 처리 개수", 5, 200, 50, step=5, key="ai_block_limit")
            if st.button("AI 파서로 재분할", use_container_width=True, key="ai_parse_run"):
                if st.session_state.ai_model == "🔵 Google Gemini" and not api_key:
                    st.error("Gemini API 키가 필요합니다. 사이드바에서 입력해주세요.")
                elif st.session_state.ai_model == "🟢 OpenAI ChatGPT" and not openai_api_key:
                    st.error("OpenAI API 키가 필요합니다. 사이드바에서 입력해주세요.")
                else:
                    with st.spinner("AI 파서 실행 중..."):
                        source_text = st.session_state.get("past_exam_text_area", "")
                        if parse_mode_ai == "블록 분할":
                            blocks = split_exam_blocks(source_text)
                            ai_items = []
                            raw_chunks = []
                            for block in blocks[:block_limit]:
                                item, raw = ai_parse_exam_block(
                                    block,
                                    ai_model=st.session_state.ai_model,
                                    api_key=api_key,
                                    openai_api_key=openai_api_key,
                                    hint_text=hint_text,
                                    return_raw=True
                                )
                                if raw:
                                    raw_chunks.append(raw)
                                if item:
                                    ai_items.append(item)
                            ai_items = clean_parsed_items(ai_items)
                            st.session_state.ai_parse_raw = "\n\n---\n\n".join(raw_chunks)
                        else:
                            ai_items, raw = ai_parse_exam_text(
                                source_text,
                                ai_model=st.session_state.ai_model,
                                api_key=api_key,
                                openai_api_key=openai_api_key,
                                max_items=ai_parse_limit,
                                hint_text=hint_text,
                                return_raw=True
                            )
                            st.session_state.ai_parse_raw = raw
                        if ai_items:
                            if auto_attach and st.session_state.past_exam_images:
                                ai_items = auto_attach_images_to_items(
                                    ai_items,
                                    st.session_state.past_exam_images,
                                    strategy=attach_strategy,
                                    max_per_question=max_imgs,
                                    anchors=st.session_state.past_exam_anchors,
                                    min_score=st.session_state.get("ocr_min_score", 0.2)
                                )
                            st.session_state.past_exam_items = ai_items
                            st.success(f"AI 파서 완료: {len(ai_items)}개 문항")
                            st.rerun()
                        else:
                            st.warning("AI 파서 결과가 비어있습니다. 문서 구조 힌트를 더 구체적으로 입력하거나, 블록 분할 모드를 사용해보세요.")
                            raw = st.session_state.get("ai_parse_raw", "")
                            if raw:
                                with st.expander("AI 파서 원문 결과(디버그)", expanded=False):
                                    st.code(raw[:6000])

        if st.session_state.past_exam_images:
            with st.expander("🖼️ 추출된 이미지", expanded=False):
                st.caption(f"총 {len(st.session_state.past_exam_images)}개 이미지")
                cols = st.columns(4)
                for i, img in enumerate(st.session_state.past_exam_images):
                    with cols[i % 4]:
                        st.image(img.get("data_uri"), caption=f"#{i + 1}")

        if st.button("🔎 변환 미리보기", use_container_width=True, key="past_exam_preview"):
            source_text = st.session_state.get("past_exam_text_area", "").strip()
            if not source_text:
                st.error("추출된 텍스트가 비어 있습니다.")
            else:
                if parse_mode == "Cloze(정답: 기반)":
                    items = parse_qa_to_cloze(source_text)
                    if not items:
                        items = parse_generated_text_to_structured(source_text, "🧩 빈칸 뚫기 (Anki Cloze)")
                elif parse_mode == "객관식(선지 기준)":
                    if file_ext == ".pdf":
                        use_ai_layout = st.session_state.get("use_ai_layout_parser", True)
                        if use_ai_layout and ((st.session_state.ai_model == "🔵 Google Gemini" and api_key) or (st.session_state.ai_model == "🟢 OpenAI ChatGPT" and openai_api_key)):
                            items = [i for i in parse_pdf_layout_ai(
                                uploaded_bytes,
                                ai_model=st.session_state.ai_model,
                                api_key=api_key,
                                openai_api_key=openai_api_key,
                                hint_text=st.session_state.get("ai_parse_hint", "")
                            ) if i.get("type") == "mcq"]
                        else:
                            items = [i for i in parse_pdf_layout(uploaded_bytes) if i.get("type") == "mcq"]
                    else:
                        items = [i for i in parse_exam_text_fuzzy(source_text) if i.get("type") == "mcq"]
                    if not items:
                        items = parse_generated_text_to_structured(source_text, "📝 객관식 문제 (Case Study)")
                else:
                    if file_ext == ".pdf":
                        use_ai_layout = st.session_state.get("use_ai_layout_parser", True)
                        if use_ai_layout and ((st.session_state.ai_model == "🔵 Google Gemini" and api_key) or (st.session_state.ai_model == "🟢 OpenAI ChatGPT" and openai_api_key)):
                            items = parse_pdf_layout_ai(
                                uploaded_bytes,
                                ai_model=st.session_state.ai_model,
                                api_key=api_key,
                                openai_api_key=openai_api_key,
                                hint_text=st.session_state.get("ai_parse_hint", "")
                            )
                        else:
                            items = parse_pdf_layout(uploaded_bytes)
                    else:
                        items = parse_exam_text_fuzzy(source_text)
                    if not items:
                        items = parse_exam_text_fuzzy(source_text)
                    if not items:
                        items = parse_generated_text_to_structured(source_text, "📝 객관식 문제 (Case Study)")
                        if not items:
                            items = parse_qa_to_cloze(source_text)
                if items and auto_attach and st.session_state.past_exam_images:
                    if attach_strategy == "ocr":
                        st.session_state.past_exam_images = ocr_images_for_matching(
                            st.session_state.past_exam_images,
                            engine="easyocr",
                            langs=("ko", "en"),
                            max_images=st.session_state.get("ocr_img_limit", 20)
                        )
                    items = auto_attach_images_to_items(
                        items,
                        st.session_state.past_exam_images,
                        strategy=attach_strategy,
                        max_per_question=max_imgs,
                        anchors=st.session_state.past_exam_anchors,
                        min_score=st.session_state.get("ocr_min_score", 0.2),
                        only_if_keyword=only_attach_keyword
                    )
                if items and st.session_state.get("ai_match_images") and st.session_state.past_exam_images:
                    if st.session_state.ai_model == "🔵 Google Gemini" and not api_key:
                        st.error("Gemini API 키가 필요합니다. 사이드바에서 입력해주세요.")
                    elif st.session_state.ai_model == "🟢 OpenAI ChatGPT" and not openai_api_key:
                        st.error("OpenAI API 키가 필요합니다. 사이드바에서 입력해주세요.")
                    else:
                        items = ai_match_images_to_items(
                            items,
                            st.session_state.past_exam_images,
                            ai_model=st.session_state.get("ai_model", "🔵 Google Gemini"),
                            api_key=api_key,
                            openai_api_key=openai_api_key,
                            max_images=st.session_state.get("ai_match_limit", 8)
                        )
                st.session_state.past_exam_items = items if items else []

        items = st.session_state.get("past_exam_items", [])
        if items:
            st.success(f"✅ 변환된 문항: {len(items)}개")
            with st.expander("📋 변환 결과 미리보기 (상위 5개)", expanded=True):
                for i, item_data in enumerate(items[:5], 1):
                    if item_data.get("type") == "mcq":
                        st.markdown(f"**문제 {i}** (객관식)")
                        st.write(f"**문항:** {item_data.get('problem', '')[:150]}...")
                        st.write(f"**선지:** {', '.join(item_data.get('options', [])[:3])}...")
                        st.write(f"**정답:** {item_data.get('answer', '?')} 번")
                    else:
                        st.markdown(f"**문제 {i}** (빈칸)")
                        st.write(f"**내용:** {item_data.get('front', '')[:150]}...")
                        st.write(f"**정답:** {item_data.get('answer', '?')}")
                    st.divider()

            with st.expander("🛠️ 문항 편집", expanded=False):
                total_items = len(items)
                if total_items > 0:
                    start_idx = st.number_input("시작 문항", min_value=1, max_value=total_items, value=1, step=1, key="edit_start_idx")
                    end_idx = st.number_input("끝 문항", min_value=start_idx, max_value=total_items, value=min(start_idx + 9, total_items), step=1, key="edit_end_idx")
                    image_options = list(range(len(st.session_state.past_exam_images)))

                    def image_label(i):
                        img = st.session_state.past_exam_images[i]
                        page = img.get("page")
                        return f"#{i + 1} | p{page}" if page else f"#{i + 1}"

                    for i in range(start_idx - 1, end_idx):
                        item = items[i]
                        with st.container():
                            qnum_label = f"q{item.get('qnum')}" if item.get("qnum") else "q?"
                            page_label = f"p{item.get('page')}" if item.get("page") else "p?"
                            st.markdown(f"#### 문항 {i + 1} 편집 ({item.get('type')}) · {qnum_label} · {page_label}")
                            item_type = st.selectbox(
                                "유형",
                                ["mcq", "cloze"],
                                index=0 if item.get("type") == "mcq" else 1,
                                key=f"edit_type_{i}"
                            )
                            if item_type == "mcq":
                                st.text_area("문항", value=item.get("problem", ""), height=120, key=f"edit_problem_{i}")
                                opts = item.get("options", [])
                                st.text_area("선지 (한 줄에 하나)", value="\n".join(opts), height=140, key=f"edit_options_{i}")
                                ans_default = int(item.get("answer", 1)) if str(item.get("answer", "")).isdigit() else 1
                                st.selectbox("정답", [1, 2, 3, 4, 5], index=max(0, min(ans_default - 1, 4)), key=f"edit_answer_{i}")
                            else:
                                st.text_area("문항", value=item.get("front", ""), height=120, key=f"edit_front_{i}")
                                st.text_input("정답", value=item.get("answer", ""), key=f"edit_answer_{i}")
                            st.text_area("해설", value=item.get("explanation", ""), height=120, key=f"edit_expl_{i}")
                            if image_options:
                                current_images = item.get("images", [])
                                current_indices = [idx for idx, img in enumerate(st.session_state.past_exam_images) if img.get("data_uri") in current_images]

                                img_pages = sorted({img.get("page") for img in st.session_state.past_exam_images if img.get("page")})
                                page_options = ["전체"] + [f"p{p}" for p in img_pages]
                                page_filter = st.selectbox("이미지 페이지 필터", page_options, key=f"img_page_filter_{i}")
                                per_page = st.slider("페이지당 이미지", 4, 24, 8, key=f"img_per_page_{i}")

                                filtered_indices = []
                                for idx_img, img in enumerate(st.session_state.past_exam_images):
                                    page = img.get("page")
                                    if page_filter != "전체":
                                        wanted = int(page_filter.replace("p", ""))
                                        if page != wanted:
                                            continue
                                    filtered_indices.append(idx_img)

                                total_imgs = len(filtered_indices)
                                total_pages = max(1, (total_imgs + per_page - 1) // per_page)
                                page_idx = st.number_input("이미지 페이지", 1, total_pages, 1, key=f"img_page_idx_{i}")
                                start = (page_idx - 1) * per_page
                                end = start + per_page
                                subset = filtered_indices[start:end]

                                cols = st.columns(4)
                                for j, idx_img in enumerate(subset):
                                    img = st.session_state.past_exam_images[idx_img]
                                    with cols[j % 4]:
                                        st.image(img.get("data_uri"), width=140, caption=image_label(idx_img))
                                        st.checkbox(
                                            "선택",
                                            value=idx_img in current_indices,
                                            key=f"edit_img_{i}_{idx_img}"
                                        )
                            st.checkbox("이 문항 삭제", key=f"edit_delete_{i}")
                            st.divider()

                    if st.button("✅ 편집 내용 적용", use_container_width=True, key="apply_edits"):
                        new_items = []
                        for i in range(total_items):
                            if st.session_state.get(f"edit_delete_{i}"):
                                continue
                            item = items[i]
                            item_type = st.session_state.get(f"edit_type_{i}", item.get("type"))
                            if item_type == "mcq":
                                problem = st.session_state.get(f"edit_problem_{i}", item.get("problem", "")).strip()
                                options_text = st.session_state.get(f"edit_options_{i}", "\n".join(item.get("options", [])))
                                options = [o.strip() for o in options_text.splitlines() if o.strip()]
                                answer = st.session_state.get(f"edit_answer_{i}", item.get("answer", 1))
                                updated = {
                                    **item,
                                    "type": "mcq",
                                    "problem": problem,
                                    "options": options,
                                    "answer": int(answer) if str(answer).isdigit() else 1,
                                }
                            else:
                                front = st.session_state.get(f"edit_front_{i}", item.get("front", "")).strip()
                                answer = st.session_state.get(f"edit_answer_{i}", item.get("answer", "")).strip()
                                updated = {
                                    **item,
                                    "type": "cloze",
                                    "front": front,
                                    "answer": answer,
                                }
                            updated["explanation"] = st.session_state.get(f"edit_expl_{i}", item.get("explanation", "")).strip()
                            if image_options:
                                current_images = item.get("images", [])
                                current_indices = [idx for idx, img in enumerate(st.session_state.past_exam_images) if img.get("data_uri") in current_images]
                                sel_set = set(current_indices)
                                for idx_img in image_options:
                                    key = f"edit_img_{i}_{idx_img}"
                                    if key in st.session_state:
                                        if st.session_state.get(key):
                                            sel_set.add(idx_img)
                                        else:
                                            sel_set.discard(idx_img)
                                updated["images"] = [st.session_state.past_exam_images[idx]["data_uri"] for idx in sorted(sel_set)]
                            new_items.append(updated)
                        st.session_state.past_exam_items = new_items
                        st.success("편집 내용이 반영되었습니다.")
                        st.rerun()

            col_save, col_down = st.columns(2)
            with col_save:
                if st.button("💾 문항 저장", use_container_width=True, key="past_exam_save"):
                    current_items = st.session_state.get("past_exam_items", [])
                    added = add_questions_to_bank_auto(
                        current_items,
                        subject=exam_subject,
                        unit=exam_unit,
                        quality_filter=enable_filter,
                        min_length=min_length
                    )
                    st.success(f"✅ {added}개 문항 저장 완료")
            with col_down:
                download_data = json.dumps(items, ensure_ascii=False, indent=2)
                st.download_button(
                    label="📥 JSON으로 다운로드",
                    data=download_data,
                    file_name="converted_exam_questions.json",
                    mime="application/json",
                    use_container_width=True,
                    key="past_exam_download"
                )
        elif uploaded_exam:
            st.info("변환 미리보기를 눌러 문항을 생성하세요.")

with tab_exam:
    st.title("🎯 실전 모의고사")
    st.caption("이 탭은 API 키 없이도 저장된 문항으로 학습/시험이 가능합니다.")
    
    bank = load_questions()
    
    if not bank["text"] and not bank["cloze"]:
        st.warning("📌 저장된 문제가 없습니다. 먼저 **📚 문제 생성** 탭에서 문제를 생성하세요.")
    else:
        st.info("기출문제 파일 변환은 **🧾 기출문제 변환** 탭에서 진행합니다.")

        # 시험/학습 설정
        col1, col2 = st.columns(2)
        with col1:
            mode_choice = st.radio("모드", ["시험모드", "학습모드"], horizontal=True)
            with col2:
                exam_type = st.selectbox("문항 유형", ["객관식", "빈칸"])
            st.session_state.image_display_width = st.slider(
                "문항 이미지 크기(px)",
                240,
                900,
                st.session_state.image_display_width,
                step=20,
                key="image_display_width_slider"
            )

        questions_all = bank["text"] if exam_type == "객관식" else bank["cloze"]
        subjects = get_unique_subjects(questions_all)
        units_by_subject = get_units_by_subject(questions_all)
        if subjects:
            col_subj, col_unit = st.columns(2)
            with col_subj:
                subject_options = ["전체"] + subjects
                selected_subject = st.radio("과목 선택", subject_options, index=0, key="exam_subject_radio")
                selected_subjects = subjects if selected_subject == "전체" else [selected_subject]
            with col_unit:
                unit_options = sorted({u for s in selected_subjects for u in units_by_subject.get(s, [])})
                if not unit_options:
                    unit_options = ["미분류"]
                selected_units = st.multiselect("단원 선택", unit_options, default=unit_options, key="exam_unit_multi")
        else:
            selected_subjects = []
            selected_units = []

        filtered_questions = filter_questions_by_subject_unit(questions_all, selected_subjects, selected_units) if subjects else questions_all

        if mode_choice == "학습모드":
            due_only = st.checkbox("오늘 복습만", value=False)
            st.session_state.auto_next = st.checkbox("자동 다음 문제", value=st.session_state.auto_next)
            if due_only:
                filtered_questions = [q for q in filtered_questions if srs_due(q)]
            if not FSRS_AVAILABLE:
                st.info("FSRS 미설치: 기본 복습 주기(SRS)로 동작합니다.")
        else:
            st.session_state.auto_next = False

        if mode_choice == "학습모드":
            with st.expander("📅 FSRS 복습 큐", expanded=False):
                show_queue = st.checkbox("복습 큐 표시", value=False, key="show_fsrs_queue")
                if show_queue:
                    if FSRS_AVAILABLE:
                        stats = get_fsrs_stats(filtered_questions)
                        if stats:
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("오늘 복습", stats["due"])
                            with col2:
                                st.metric("연체", stats["overdue"])
                            with col3:
                                st.metric("미래", stats["future"])
                            with col4:
                                st.metric("신규", stats["new"])

                        due_list = get_fsrs_queue(filtered_questions, limit=20)
                        if not due_list:
                            st.info("오늘 복습할 문항이 없습니다.")
                        else:
                            rows = []
                            for q, due_time in due_list:
                                snippet = (q.get("problem") or q.get("front") or "").strip()
                                snippet = snippet[:80] + "..." if len(snippet) > 80 else snippet
                                rows.append({
                                    "분과": q.get("subject") or "General",
                                    "문항": snippet,
                                    "Due": due_time.isoformat()
                                })
                            st.dataframe(rows, use_container_width=True, hide_index=True)
                    else:
                        due_list = [q for q in filtered_questions if simple_srs_due(q)]
                        st.metric("오늘 복습", len(due_list))
                        if not due_list:
                            st.info("오늘 복습할 문항이 없습니다.")

            with st.expander("📈 복습 리포트", expanded=False):
                show_report = st.checkbox("리포트 표시", value=False, key="show_fsrs_report")
                if show_report:
                    if FSRS_AVAILABLE:
                        report = get_fsrs_report(filtered_questions)
                        if report:
                            st.metric("총 카드", report["total"])
                            st.metric("최근 7일 리뷰 수", report["review_count_7d"])
                            st.metric("평균 간격(일)", f"{report['avg_interval']:.1f}")
                            if report["last_review"]:
                                st.caption(f"마지막 리뷰: {report['last_review']}")

                            rating_rows = [{"평가": k, "건수": v} for k, v in report["rating_counts"].items()]
                            st.dataframe(rating_rows, use_container_width=True, hide_index=True)
                        else:
                            st.info("리포트를 생성할 수 없습니다.")
                    else:
                        st.info("기본 SRS 모드에서는 상세 리포트를 제공하지 않습니다.")

        if not filtered_questions:
            st.warning("선택한 조건에 해당하는 문제가 없습니다.")
        else:
            max_questions = len(filtered_questions)
            num_questions = st.slider("문항 수", 1, min(50, max(1, max_questions)), min(10, max_questions))

            start_label = "📝 시험 시작" if mode_choice == "시험모드" else "📖 학습 시작"
            if st.button(start_label, use_container_width=True, key="start_exam"):
                if len(filtered_questions) < num_questions:
                    st.warning(f"문제가 부족합니다. {len(filtered_questions)}개만 출제합니다.")
                    num_questions = len(filtered_questions)

                raw_selected = random.sample(filtered_questions, num_questions)
                parsed_selected = []
                for raw in raw_selected:
                    if exam_type == "객관식":
                        parsed = parse_mcq_content(raw)
                    else:
                        parsed = parse_cloze_content(raw)
                    parsed_selected.append(parsed)

                st.session_state.exam_questions = parsed_selected
                st.session_state.current_question_idx = 0
                st.session_state.user_answers = {}
                st.session_state.exam_started = True
                st.session_state.exam_finished = False
                st.session_state.exam_mode = mode_choice
                st.session_state.exam_type = exam_type
                st.session_state.auto_advance_guard = None
                st.session_state.revealed_answers = set()
                st.session_state.exam_stats_applied = False
                st.session_state.graded_questions = set()
                st.session_state.exam_history_saved = False
                st.session_state.current_exam_meta = {
                    "mode": mode_choice,
                    "type": exam_type,
                    "subjects": selected_subjects,
                    "units": selected_units,
                    "num_questions": len(parsed_selected),
                    "started_at": datetime.now(timezone.utc).isoformat()
                }
                st.session_state.nav_select = 0

        # 시험/학습 진행
        if st.session_state.exam_started and st.session_state.exam_questions:
            exam_qs = st.session_state.exam_questions
            idx = st.session_state.current_question_idx

            if st.session_state.exam_finished:
                st.markdown("## 📊 결과")

                total = len(exam_qs)
                answered = len(st.session_state.user_answers)

                # 정답 채점
                correct_count = 0
                wrong_indices = []
                for i, q in enumerate(exam_qs):
                    if i not in st.session_state.user_answers:
                        continue

                    user_ans = st.session_state.user_answers[i]
                    if is_answer_correct(q, user_ans):
                        correct_count += 1
                    else:
                        wrong_indices.append(i)

                # 통계 업데이트 (시험 결과 1회만, 이미 반영된 문항은 제외)
                if not st.session_state.exam_stats_applied:
                    for i, q in enumerate(exam_qs):
                        if i in st.session_state.user_answers and q.get("id"):
                            if q.get("id") in st.session_state.graded_questions:
                                continue
                            user_ans = st.session_state.user_answers[i]
                            is_correct = is_answer_correct(q, user_ans)
                            update_question_stats(q["id"], is_correct)
                            st.session_state.graded_questions.add(q.get("id"))
                    st.session_state.exam_stats_applied = True

                # 시험 기록 저장 (시험모드만)
                if st.session_state.exam_mode == "시험모드" and not st.session_state.exam_history_saved:
                    items = []
                    for i, q in enumerate(exam_qs):
                        user_ans = st.session_state.user_answers.get(i)
                        items.append({
                            "id": q.get("id"),
                            "type": q.get("type"),
                            "front": q.get("front"),
                            "options": q.get("options"),
                            "correct": q.get("correct"),
                            "answer": q.get("answer"),
                            "user": user_ans,
                            "is_correct": is_answer_correct(q, user_ans) if user_ans is not None else False,
                            "explanation": q.get("explanation"),
                            "subject": q.get("subject"),
                            "difficulty": q.get("difficulty"),
                            "note": q.get("note", ""),
                        })
                    meta = st.session_state.current_exam_meta or {}
                    session = {
                        "session_id": str(uuid.uuid4()),
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "mode": meta.get("mode", st.session_state.exam_mode),
                        "type": meta.get("type", st.session_state.exam_type),
                        "subjects": meta.get("subjects", []),
                        "num_questions": len(exam_qs),
                        "answered": answered,
                        "correct": correct_count,
                        "accuracy": int(correct_count / answered * 100) if answered > 0 else 0,
                        "items": items
                    }
                    add_exam_history(session)
                    st.session_state.exam_history_saved = True

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("정답", f"{correct_count}/{answered}")
                with col2:
                    st.metric("미응답", f"{total - answered}")
                with col3:
                    accuracy = int(correct_count / answered * 100) if answered > 0 else 0
                    st.metric("정확도", f"{accuracy}%")
                with col4:
                    st.metric("상태", "✅ 완료" if answered == total else "⚠️ 미완료")

                st.markdown("---")

                # 상세 보기
                letters = ['A', 'B', 'C', 'D', 'E']
                for i, q in enumerate(exam_qs, 1):
                    user_ans = st.session_state.user_answers.get(i - 1, None)
                    is_correct = False
                    correct_text = ""
                    correct_display = ""

                    if q.get('type') == 'mcq':
                        correct_num = q.get('correct')  # 숫자 형식: 1-5
                        correct_text = str(correct_num)
                        correct_display = letters[correct_num - 1] if 1 <= correct_num <= 5 else "?"
                        is_correct = (user_ans == correct_num) if user_ans else False
                        user_ans_display = letters[user_ans - 1] if user_ans and 1 <= user_ans <= 5 else "응답 없음"
                    else:
                        correct_text = q.get('answer') or ""
                        correct_display = correct_text
                        is_correct = fuzzy_match(user_ans, correct_text) if user_ans and correct_text else False
                        user_ans_display = user_ans if user_ans else "응답 없음"

                    status_icon = "✅" if is_correct else "❌"
                    with st.expander(f"{status_icon} 문제 {i}: {user_ans_display}"):
                        st.markdown(q.get('front', q.get('raw', '')))

                        if q.get('type') == 'mcq':
                            st.markdown("**선택지:**")
                            opts = q.get('options') or []
                            for idx_opt, opt in enumerate(opts[:5]):
                                label = f"{letters[idx_opt]}. {opt}"
                                st.write(label)

                        st.divider()
                        st.write(f"**당신의 답:** {user_ans_display}")
                        answer_color = "🟢" if is_correct else "🔴"
                        st.write(f"{answer_color} **정답:** {correct_display}")
                        if q.get("explanation"):
                            show_exp = st.checkbox("해설 보기", value=st.session_state.explanation_default, key=f"show_exp_{i}")
                            if show_exp:
                                st.markdown(format_explanation_text(q.get('explanation')))
                        if q.get("subject"):
                            st.caption(f"📌 {q['subject']}")
                        if q.get("unit"):
                            st.caption(f"단원: {q.get('unit')}")
                        if q.get("difficulty"):
                            st.caption(f"난이도: {q.get('difficulty', '?')}")
                        if q.get("id"):
                            note_key = f"review_note_{i}"
                            st.text_area("메모", value=q.get("note", ""), key=note_key, height=80)
                            if st.button("메모 저장", key=f"save_review_note_{i}"):
                                saved = update_question_note(q["id"], st.session_state.get(note_key, ""))
                                if saved:
                                    q["note"] = st.session_state.get(note_key, "")
                                    st.success("메모 저장됨")

                # 오답노트
                if wrong_indices:
                    if st.button("📌 오답노트로 다시 풀기"):
                        wrong_qs = [exam_qs[i] for i in wrong_indices]
                        st.session_state.exam_questions = wrong_qs
                        st.session_state.user_answers = {}
                        st.session_state.current_question_idx = 0
                        st.session_state.exam_started = True
                        st.session_state.exam_finished = False
                        st.session_state.exam_mode = "학습모드"
                        st.session_state.revealed_answers = set()
                        st.session_state.auto_advance_guard = None
                        st.session_state.exam_stats_applied = False
                        st.session_state.graded_questions = set()
                        st.rerun()

                if st.button("🔄 다시 시작"):
                    st.session_state.exam_started = False
                    st.session_state.exam_finished = False
                    st.session_state.exam_questions = []
                    st.session_state.user_answers = {}
                    st.session_state.current_question_idx = 0
                    st.rerun()



            else:
                if idx < len(exam_qs):
                    q = exam_qs[idx]
                    st.progress((idx + 1) / len(exam_qs))
                    st.caption(f"USMLE 스타일 | Question {idx + 1} of {len(exam_qs)}")
                    nav_slot = st.empty()
                    unanswered_slot = st.empty()
                    st.markdown(f"### Question {idx + 1}")

                    # 입력
                    if q.get('type') == 'mcq':
                        st.markdown(q.get('front', ''))
                        if q.get("images"):
                            st.image(q.get("images"), width=st.session_state.image_display_width)

                        st.markdown("**Select one option (A–E):**")
                        opts = q.get('options') or []
                        letters = ['A', 'B', 'C', 'D', 'E']
                        prev_ans = st.session_state.user_answers.get(idx)
                        default_index = (prev_ans - 1) if isinstance(prev_ans, int) and 1 <= prev_ans <= 5 else None
                        if opts:
                            labels_real = [f"{letters[i]}. {opts[i]}" for i in range(min(len(opts), len(letters)))]
                            st.session_state[f"labels_real_{idx}"] = labels_real
                            user_choice_label = st.radio("정답 선택:", labels_real, index=default_index, key=f"q_{idx}")
                            if user_choice_label:
                                chosen_num = letters.index(user_choice_label.split(".")[0]) + 1
                                st.session_state.user_answers[idx] = chosen_num
                            else:
                                st.session_state.user_answers.pop(idx, None)
                        else:
                            st.session_state[f"labels_real_{idx}"] = letters
                            user_choice = st.radio("정답 선택:", letters, index=default_index, key=f"q_{idx}")
                            if user_choice:
                                chosen_num = letters.index(user_choice) + 1
                                st.session_state.user_answers[idx] = chosen_num
                            else:
                                st.session_state.user_answers.pop(idx, None)

                        st.text_input(
                            "키보드 입력 (A-E 또는 1-5)",
                            key=f"shortcut_{idx}",
                            on_change=apply_mcq_shortcut,
                            args=(idx,)
                        )

                        if idx in st.session_state.user_answers:
                            your = st.session_state.user_answers[idx]
                            your_letter = letters[your - 1] if 1 <= your <= 5 else "?"
                            st.caption(f"📍 Your answer: {your_letter}")
                    else:
                        st.markdown(q.get('front', q.get('raw', '')))
                        if q.get("images"):
                            st.image(q.get("images"), width=st.session_state.image_display_width)
                        prev_text = st.session_state.user_answers.get(idx, "")
                        user_input = st.text_input("정답 입력 (한글/영문):", value=prev_text, key=f"cloze_{idx}")
                        if user_input:
                            st.session_state.user_answers[idx] = user_input

                    # 문항 이동/미응답 (답안 반영 후 갱신)
                    answered_idx = set(st.session_state.user_answers.keys())
                    nav_options = list(range(len(exam_qs)))

                    def nav_format(i):
                        status = "✅" if i in answered_idx else "○"
                        return f"{i + 1} {status}"

                    nav_idx = nav_slot.selectbox(
                        "문항 이동",
                        nav_options,
                        index=idx,
                        format_func=nav_format,
                        key="nav_select",
                    )
                    if nav_idx != idx:
                        st.session_state.current_question_idx = nav_idx

                    unanswered = [str(i + 1) for i in range(len(exam_qs)) if i not in answered_idx]
                    if unanswered:
                        unanswered_slot.caption(f"미응답: {', '.join(unanswered)}")

                    # 메모
                    if q.get("id"):
                        note_key = f"note_{idx}"
                        st.text_area("메모", value=q.get("note", ""), key=note_key, height=80)
                        if st.button("메모 저장", key=f"save_note_{idx}"):
                            saved = update_question_note(q["id"], st.session_state.get(note_key, ""))
                            if saved:
                                q["note"] = st.session_state.get(note_key, "")
                                st.success("메모 저장됨")

                    # 학습모드: 정답 확인 후 표시
                    if st.session_state.exam_mode == "학습모드" and idx in st.session_state.user_answers:
                        st.markdown("---")
                        reveal_key = f"reveal_{idx}"
                        if st.button("정답 확인", key=reveal_key):
                            st.session_state.revealed_answers.add(idx)

                        if idx in st.session_state.revealed_answers:
                            if q.get('type') == 'mcq':
                                correct_num = q.get('correct')
                                correct_display = letters[correct_num - 1] if isinstance(correct_num, int) and 1 <= correct_num <= 5 else "?"
                                is_correct = (st.session_state.user_answers[idx] == correct_num) if correct_num else False
                            else:
                                correct_text = q.get('answer') or ""
                                is_correct = fuzzy_match(st.session_state.user_answers[idx], correct_text) if correct_text else False
                                correct_display = correct_text

                            answer_color = "🟢" if is_correct else "🔴"
                            st.write(f"{answer_color} **정답:** {correct_display}")
                            # 학습모드 통계 업데이트 (1회)
                            if q.get("id") and q.get("id") not in st.session_state.graded_questions:
                                update_question_stats(q["id"], is_correct)
                                st.session_state.graded_questions.add(q.get("id"))
                            explanation_text = q.get("explanation") or q.get("rationale") or q.get("analysis") or ""
                            show_exp = st.checkbox("해설 보기", value=st.session_state.explanation_default, key=f"learn_exp_{idx}")
                            if show_exp:
                                if explanation_text.strip():
                                    st.markdown(format_explanation_text(explanation_text))
                                else:
                                    st.caption("해설이 없습니다.")
                                    if st.button("AI 해설 생성", key=f"ai_exp_{idx}"):
                                        if st.session_state.ai_model == "🔵 Google Gemini" and not api_key:
                                            st.error("Gemini API 키가 필요합니다. 사이드바에서 입력해주세요.")
                                        elif st.session_state.ai_model == "🟢 OpenAI ChatGPT" and not openai_api_key:
                                            st.error("OpenAI API 키가 필요합니다. 사이드바에서 입력해주세요.")
                                        else:
                                            with st.spinner("AI 해설 생성 중..."):
                                                text = generate_single_explanation_ai(
                                                    q,
                                                    ai_model=st.session_state.ai_model,
                                                    api_key=api_key,
                                                    openai_api_key=openai_api_key
                                                )
                                            if text:
                                                q["explanation"] = text
                                                if q.get("id"):
                                                    update_question_explanation(q["id"], text)
                                                st.success("해설이 생성되었습니다.")
                                                st.markdown(format_explanation_text(text))
                                            else:
                                                st.warning("해설 생성 실패. 다시 시도해주세요.")

                            if q.get("id"):
                                st.markdown("**복습 평가**")
                                cols = st.columns(4)
                                if cols[0].button("Again", key=f"srs_again_{idx}"):
                                    rating = Rating.Again if FSRS_AVAILABLE else "Again"
                                    srs = apply_srs_rating(q["id"], rating)
                                    if srs:
                                        q["fsrs"] = srs if FSRS_AVAILABLE else q.get("fsrs")
                                        st.success(f"다음 복습: {srs.get('due')}")
                                if cols[1].button("Hard", key=f"srs_hard_{idx}"):
                                    rating = Rating.Hard if FSRS_AVAILABLE else "Hard"
                                    srs = apply_srs_rating(q["id"], rating)
                                    if srs:
                                        q["fsrs"] = srs if FSRS_AVAILABLE else q.get("fsrs")
                                        st.success(f"다음 복습: {srs.get('due')}")
                                if cols[2].button("Good", key=f"srs_good_{idx}"):
                                    rating = Rating.Good if FSRS_AVAILABLE else "Good"
                                    srs = apply_srs_rating(q["id"], rating)
                                    if srs:
                                        q["fsrs"] = srs if FSRS_AVAILABLE else q.get("fsrs")
                                        st.success(f"다음 복습: {srs.get('due')}")
                                if cols[3].button("Easy", key=f"srs_easy_{idx}"):
                                    rating = Rating.Easy if FSRS_AVAILABLE else "Easy"
                                    srs = apply_srs_rating(q["id"], rating)
                                    if srs:
                                        q["fsrs"] = srs if FSRS_AVAILABLE else q.get("fsrs")
                                        st.success(f"다음 복습: {srs.get('due')}")

                    # 학습모드 자동 다음 문제
                    if st.session_state.exam_mode == "학습모드" and st.session_state.auto_next:
                        guard = st.session_state.auto_advance_guard
                        current_answer = st.session_state.user_answers.get(idx)
                        if current_answer and idx in st.session_state.revealed_answers and guard != (idx, str(current_answer)) and idx < len(exam_qs) - 1:
                            st.session_state.auto_advance_guard = (idx, str(current_answer))
                            st.session_state.current_question_idx += 1
                            st.rerun()

                    # 네비게이션
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.button("⬅️ 이전", on_click=goto_prev_question, disabled=idx <= 0)
                    with col2:
                        st.button("다음 ➡️", on_click=goto_next_question, disabled=idx >= len(exam_qs) - 1)
                    with col3:
                        if st.session_state.exam_mode == "시험모드":
                            if idx == len(exam_qs) - 1:
                                st.button("✅ 채점", on_click=finish_exam_session)
                        else:
                            if idx == len(exam_qs) - 1:
                                st.button("✅ 세션 종료", on_click=finish_exam_session)

# ============================================================================
# TAB: 노트
# ============================================================================
with tab_notes:
    st.title("🗒️ 노트")
    st.caption("Obsidian 노트를 연결해 열람하거나, 노트 내용으로 문제를 생성할 수 있습니다.")

    vault_path = st.text_input("Obsidian Vault 경로", value=st.session_state.obsidian_path, placeholder="/path/to/obsidian-vault")
    if vault_path:
        st.session_state.obsidian_path = vault_path

    if vault_path and os.path.isdir(vault_path):
        search = st.text_input("파일 검색", value="", key="obsidian_search")
        md_files = []
        folders = set()
        for root, _, files in os.walk(vault_path):
            for name in files:
                if name.lower().endswith(".md"):
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, vault_path)
                    parts = rel.split(os.sep)
                    if len(parts) > 1:
                        folders.add(parts[0])
                    if search and search.lower() not in rel.lower():
                        continue
                    md_files.append(rel)
        folder_list = sorted(folders)
        selected_folders = st.multiselect("폴더 필터", folder_list, default=folder_list)
        if selected_folders:
            md_files = [f for f in md_files if f.split(os.sep)[0] in selected_folders or os.sep not in f]
        md_files = sorted(md_files)[:500]
        if not md_files:
            st.info("조건에 맞는 마크다운 파일이 없습니다.")
        else:
            selected = st.selectbox("노트 선택", md_files, index=0)
            full_path = os.path.join(vault_path, selected)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

            st.markdown("**노트 미리보기**")
            view_mode = st.selectbox("보기 모드", ["Obsidian 스타일", "일반"], index=0)
            if view_mode == "Obsidian 스타일":
                rendered = resolve_obsidian_embeds(content, vault_path, full_path)
                render_obsidian_html(rendered)
                if not MARKDOWN_AVAILABLE:
                    st.info("더 나은 렌더링을 위해 `markdown` 패키지를 설치하세요.")
            else:
                st.text_area("내용", value=content, height=300)

            st.markdown("---")
            st.subheader("📌 노트로 문제 생성")
            col1, col2, col3 = st.columns(3)
            with col1:
                note_mode = st.selectbox("생성 방식", ["Cloze 자동(정답:)","AI 객관식","AI Cloze"])
            with col2:
                note_subject = st.text_input("과목명", value="General", key="note_subject")
            with col3:
                note_unit = st.text_input("단원명(선택)", value="미분류", key="note_unit")
            note_num = st.slider("문항 수", 1, 30, 10)

            if st.button("노트에서 문제 생성", use_container_width=True, key="note_generate"):
                if note_mode == "Cloze 자동(정답:)":
                    if "{{c1::" in content:
                        items = parse_generated_text_to_structured(content, "🧩 빈칸 뚫기 (Anki Cloze)")
                    else:
                        items = parse_qa_to_cloze(content)
                    if not items:
                        st.error("자동 변환에 실패했습니다. `정답:` 형식인지 확인해주세요.")
                    else:
                        added = add_questions_to_bank_auto(items, subject=note_subject, unit=note_unit, quality_filter=enable_filter, min_length=min_length)
                        st.success(f"✅ {added}개 문항 저장 완료")
                else:
                    if (note_mode.startswith("AI") and st.session_state.ai_model == "🔵 Google Gemini" and not api_key) or (note_mode.startswith("AI") and st.session_state.ai_model == "🟢 OpenAI ChatGPT" and not openai_api_key):
                        st.error("API 키가 필요합니다. 사이드바에서 입력해주세요.")
                    else:
                        mode = "📝 객관식 문제 (Case Study)" if note_mode == "AI 객관식" else "🧩 빈칸 뚫기 (Anki Cloze)"
                        result = generate_content_in_chunks(
                            content,
                            mode,
                            ai_model,
                            num_items=note_num,
                            chunk_size=chunk_size,
                            overlap=overlap,
                            api_key=api_key,
                            openai_api_key=openai_api_key,
                            style_text=None,
                        )
                        if result:
                            added = add_questions_to_bank(result, mode, note_subject, note_unit, quality_filter=enable_filter, min_length=min_length)
                            st.success(f"✅ {added}개 문항 저장 완료")
                        else:
                            st.error("문항 생성 실패")
    elif vault_path:
        st.error("유효한 Obsidian Vault 경로가 아닙니다.")
