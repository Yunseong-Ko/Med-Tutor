PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  email TEXT UNIQUE,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('student', 'ta', 'faculty', 'admin')),
  affiliation TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
  course_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  department TEXT,
  academic_year TEXT,
  term TEXT,
  created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lectures (
  lecture_id TEXT PRIMARY KEY,
  course_id TEXT NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  unit_id TEXT,
  unit_title TEXT,
  lecture_date TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_documents (
  document_id TEXT PRIMARY KEY,
  course_id TEXT REFERENCES courses(course_id) ON DELETE SET NULL,
  lecture_id TEXT REFERENCES lectures(lecture_id) ON DELETE SET NULL,
  source_type TEXT NOT NULL CHECK (
    source_type IN ('lecture', 'past_exam_style', 'evidence', 'image_upload', 'reference')
  ),
  original_name TEXT NOT NULL,
  file_path TEXT NOT NULL,
  extracted_text_path TEXT,
  file_hash TEXT,
  mime_type TEXT,
  consent_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (consent_status IN ('unknown', 'approved', 'restricted')),
  created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_source_documents_scope
  ON source_documents(course_id, lecture_id, source_type);

CREATE TABLE IF NOT EXISTS media_assets (
  asset_id TEXT PRIMARY KEY,
  source_document_id TEXT REFERENCES source_documents(document_id) ON DELETE SET NULL,
  asset_type TEXT NOT NULL CHECK (
    asset_type IN ('clinical_photo', 'radiology', 'pathology', 'ecg_eeg', 'ultrasound', 'other')
  ),
  modality TEXT,
  subject TEXT,
  unit TEXT,
  diagnosis TEXT,
  caption TEXT NOT NULL DEFAULT '',
  key_findings_json TEXT NOT NULL DEFAULT '[]',
  file_path TEXT NOT NULL,
  thumbnail_path TEXT,
  deidentified INTEGER NOT NULL DEFAULT 0 CHECK (deidentified IN (0, 1)),
  approved_for_question_use INTEGER NOT NULL DEFAULT 0 CHECK (approved_for_question_use IN (0, 1)),
  review_status TEXT NOT NULL DEFAULT 'needs_review'
    CHECK (review_status IN ('needs_review', 'approved', 'restricted')),
  faculty_note TEXT NOT NULL DEFAULT '',
  created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_media_assets_lookup
  ON media_assets(subject, unit, asset_type, modality, review_status);

CREATE TABLE IF NOT EXISTS question_sets (
  set_id TEXT PRIMARY KEY,
  course_id TEXT REFERENCES courses(course_id) ON DELETE SET NULL,
  lecture_id TEXT REFERENCES lectures(lecture_id) ON DELETE SET NULL,
  generation_mode TEXT NOT NULL CHECK (
    generation_mode IN ('text_only', 'selected_media', 'media_description', 'ai_suggested_media')
  ),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_path TEXT,
  source_document_ids_json TEXT NOT NULL DEFAULT '[]',
  review_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (review_status IN ('draft', 'faculty_review_pending', 'approved', 'archived')),
  created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_question_sets_scope
  ON question_sets(course_id, lecture_id, review_status, created_at);

CREATE TABLE IF NOT EXISTS questions (
  question_id TEXT PRIMARY KEY,
  set_id TEXT NOT NULL REFERENCES question_sets(set_id) ON DELETE CASCADE,
  course_id TEXT REFERENCES courses(course_id) ON DELETE SET NULL,
  lecture_id TEXT REFERENCES lectures(lecture_id) ON DELETE SET NULL,
  unit_id TEXT,
  question_number INTEGER,
  question_type TEXT NOT NULL CHECK (
    question_type IN ('clinical_case', 'image_based', 'basic_concept', 'mechanism', 'diagnostic', 'management', 'mixed')
  ),
  stem TEXT NOT NULL,
  answer INTEGER CHECK (answer BETWEEN 1 AND 5),
  difficulty TEXT,
  cognitive_level TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  review_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (review_status IN ('draft', 'needs_revision', 'approved', 'rejected', 'exported')),
  needs_review INTEGER NOT NULL DEFAULT 1 CHECK (needs_review IN (0, 1)),
  review_reasons_json TEXT NOT NULL DEFAULT '[]',
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questions_review
  ON questions(set_id, review_status, needs_review);

CREATE INDEX IF NOT EXISTS idx_questions_scope
  ON questions(course_id, lecture_id, unit_id, question_type);

CREATE TABLE IF NOT EXISTS choices (
  choice_id TEXT PRIMARY KEY,
  question_id TEXT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
  choice_number INTEGER NOT NULL CHECK (choice_number BETWEEN 1 AND 10),
  text TEXT NOT NULL,
  is_correct INTEGER NOT NULL DEFAULT 0 CHECK (is_correct IN (0, 1)),
  rationale TEXT NOT NULL DEFAULT '',
  UNIQUE(question_id, choice_number)
);

CREATE TABLE IF NOT EXISTS explanations (
  explanation_id TEXT PRIMARY KEY,
  question_id TEXT NOT NULL UNIQUE REFERENCES questions(question_id) ON DELETE CASCADE,
  correct_rationale TEXT NOT NULL DEFAULT '',
  image_findings TEXT NOT NULL DEFAULT '',
  wrong_choice_explanations_json TEXT NOT NULL DEFAULT '{}',
  high_yield_point TEXT NOT NULL DEFAULT '',
  trap TEXT NOT NULL DEFAULT '',
  student_summary TEXT NOT NULL DEFAULT '',
  faculty_note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS question_media (
  question_id TEXT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL REFERENCES media_assets(asset_id) ON DELETE RESTRICT,
  display_order INTEGER NOT NULL DEFAULT 1,
  role TEXT NOT NULL DEFAULT 'primary_stimulus'
    CHECK (role IN ('primary_stimulus', 'supporting', 'explanation_only')),
  match_confidence REAL,
  requires_faculty_confirmation INTEGER NOT NULL DEFAULT 1 CHECK (requires_faculty_confirmation IN (0, 1)),
  PRIMARY KEY(question_id, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_question_media_asset
  ON question_media(asset_id);

CREATE TABLE IF NOT EXISTS reference_notes (
  reference_id TEXT PRIMARY KEY,
  question_id TEXT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
  ref_no INTEGER NOT NULL,
  source TEXT NOT NULL,
  basis TEXT NOT NULL,
  source_document_id TEXT REFERENCES source_documents(document_id) ON DELETE SET NULL,
  external_url TEXT,
  url_verified_at TEXT,
  source_type TEXT NOT NULL DEFAULT 'lecture'
    CHECK (source_type IN ('lecture', 'guideline', 'journal', 'textbook', 'database', 'other')),
  verification_status TEXT NOT NULL DEFAULT 'uploaded_or_lecture'
    CHECK (
      verification_status IN ('uploaded_or_lecture', 'model_knowledge_unverified', 'verified_by_faculty')
    ),
  UNIQUE(question_id, ref_no)
);

CREATE TABLE IF NOT EXISTS concepts (
  concept_id TEXT PRIMARY KEY,
  course_id TEXT REFERENCES courses(course_id) ON DELETE SET NULL,
  lecture_id TEXT REFERENCES lectures(lecture_id) ON DELETE SET NULL,
  source_document_id TEXT REFERENCES source_documents(document_id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  source_anchor TEXT NOT NULL DEFAULT '',
  faculty_approved INTEGER NOT NULL DEFAULT 0 CHECK (faculty_approved IN (0, 1)),
  created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_concepts_scope
  ON concepts(course_id, lecture_id, faculty_approved);

CREATE TABLE IF NOT EXISTS question_concepts (
  question_id TEXT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
  concept_id TEXT NOT NULL REFERENCES concepts(concept_id) ON DELETE CASCADE,
  weight REAL NOT NULL DEFAULT 1.0,
  auto_tagged INTEGER NOT NULL DEFAULT 1 CHECK (auto_tagged IN (0, 1)),
  PRIMARY KEY(question_id, concept_id)
);

CREATE INDEX IF NOT EXISTS idx_question_concepts_concept
  ON question_concepts(concept_id);

CREATE TABLE IF NOT EXISTS concept_references (
  concept_reference_id TEXT PRIMARY KEY,
  concept_id TEXT NOT NULL REFERENCES concepts(concept_id) ON DELETE CASCADE,
  ref_no INTEGER NOT NULL,
  source TEXT NOT NULL,
  basis TEXT NOT NULL DEFAULT '',
  source_document_id TEXT REFERENCES source_documents(document_id) ON DELETE SET NULL,
  external_url TEXT,
  url_verified_at TEXT,
  verification_status TEXT NOT NULL DEFAULT 'uploaded_or_lecture'
    CHECK (
      verification_status IN ('uploaded_or_lecture', 'model_knowledge_unverified', 'verified_by_faculty')
    ),
  UNIQUE(concept_id, ref_no)
);

CREATE TABLE IF NOT EXISTS review_events (
  event_id TEXT PRIMARY KEY,
  question_id TEXT REFERENCES questions(question_id) ON DELETE CASCADE,
  set_id TEXT REFERENCES question_sets(set_id) ON DELETE CASCADE,
  actor_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  event_type TEXT NOT NULL CHECK (
    event_type IN ('created', 'edited', 'media_changed', 'approved', 'rejected', 'exported', 'commented')
  ),
  before_json TEXT,
  after_json TEXT,
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_review_events_question
  ON review_events(question_id, created_at);

CREATE TABLE IF NOT EXISTS export_artifacts (
  export_id TEXT PRIMARY KEY,
  set_id TEXT NOT NULL REFERENCES question_sets(set_id) ON DELETE CASCADE,
  export_type TEXT NOT NULL CHECK (export_type IN ('docx', 'pdf', 'xlsx', 'anki', 'json')),
  file_path TEXT NOT NULL,
  created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS assignments (
  assignment_id TEXT PRIMARY KEY,
  set_id TEXT NOT NULL REFERENCES question_sets(set_id) ON DELETE RESTRICT,
  course_id TEXT REFERENCES courses(course_id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'practice' CHECK (mode IN ('practice', 'exam', 'review')),
  opens_at TEXT,
  closes_at TEXT,
  created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS assignment_items (
  assignment_id TEXT NOT NULL REFERENCES assignments(assignment_id) ON DELETE CASCADE,
  question_id TEXT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
  display_order INTEGER NOT NULL,
  PRIMARY KEY(assignment_id, question_id)
);

CREATE TABLE IF NOT EXISTS student_response_summaries (
  summary_id TEXT PRIMARY KEY,
  assignment_id TEXT NOT NULL REFERENCES assignments(assignment_id) ON DELETE CASCADE,
  course_id TEXT REFERENCES courses(course_id) ON DELETE SET NULL,
  lecture_id TEXT REFERENCES lectures(lecture_id) ON DELETE SET NULL,
  unit_id TEXT,
  concept_tag TEXT,
  response_count INTEGER NOT NULL DEFAULT 0,
  correct_count INTEGER NOT NULL DEFAULT 0,
  anonymized_group_key TEXT NOT NULL DEFAULT 'aggregate',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_student_response_summaries_scope
  ON student_response_summaries(assignment_id, unit_id, concept_tag);
