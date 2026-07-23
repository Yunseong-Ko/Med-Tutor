-- P:accine 3-week MVP Postgres schema
-- Goal: one complete loop from real question solving to professor-readable item analytics.

create extension if not exists pgcrypto;

create table if not exists app_users (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid unique,
  display_name text not null,
  role text not null check (role in ('student', 'faculty', 'ta', 'admin')),
  cohort text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists courses (
  id text primary key,
  title text not null,
  curriculum_year integer,
  term text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists exams (
  id text primary key,
  course_id text references courses(id) on delete set null,
  title text not null,
  exam_kind text not null default 'course_exam',
  exam_date date,
  source_file text,
  question_count integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists questions (
  id text primary key,
  exam_id text not null references exams(id) on delete cascade,
  question_number integer not null,
  stem text not null,
  stimulus text,
  answer_keys text[] not null default '{}',
  explanation jsonb not null default '{}'::jsonb,
  labels jsonb not null default '{}'::jsonb,
  source_meta jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (exam_id, question_number)
);

create table if not exists choices (
  id uuid primary key default gen_random_uuid(),
  question_id text not null references questions(id) on delete cascade,
  choice_number integer not null check (choice_number > 0),
  choice_text text not null,
  is_correct boolean not null default false,
  explanation text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (question_id, choice_number)
);

create table if not exists question_media (
  id uuid primary key default gen_random_uuid(),
  question_id text not null references questions(id) on delete cascade,
  media_id text not null,
  media_role text not null default 'stimulus' check (media_role in ('stimulus', 'explanation')),
  file_path text not null,
  caption text,
  modality text,
  display_order integer not null default 1,
  created_at timestamptz not null default now(),
  unique (question_id, media_id)
);

create table if not exists practice_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references app_users(id) on delete cascade,
  mode text not null default 'study' check (mode in ('study', 'exam', 'review')),
  exam_id text references exams(id) on delete set null,
  course_id text references courses(id) on delete set null,
  label_filter jsonb not null default '{}'::jsonb,
  started_at timestamptz not null default now(),
  ended_at timestamptz
);

create table if not exists attempts (
  id uuid primary key default gen_random_uuid(),
  session_id uuid references practice_sessions(id) on delete set null,
  user_id uuid not null references app_users(id) on delete cascade,
  question_id text not null references questions(id) on delete cascade,
  attempt_number integer not null default 1 check (attempt_number > 0),
  selected_choice_numbers integer[] not null default '{}',
  is_correct boolean not null,
  time_ms integer not null default 0 check (time_ms >= 0),
  revealed_explanation boolean not null default false,
  answered_at timestamptz not null default now(),
  client_meta jsonb not null default '{}'::jsonb,
  unique (session_id, question_id, attempt_number)
);

create index if not exists idx_questions_exam_number
  on questions (exam_id, question_number);

create index if not exists idx_questions_labels_gin
  on questions using gin (labels);

create index if not exists idx_choices_question_number
  on choices (question_id, choice_number);

create index if not exists idx_attempts_question_answered
  on attempts (question_id, answered_at desc);

create index if not exists idx_attempts_user_answered
  on attempts (user_id, answered_at desc);

create index if not exists idx_attempts_session
  on attempts (session_id);

create or replace view v_professor_item_report as
select
  q.exam_id,
  q.id as question_id,
  q.question_number,
  q.labels,
  count(a.id) as attempt_count,
  round(100.0 * avg(case when a.is_correct then 1 else 0 end), 1) as correct_rate_pct,
  round(avg(a.time_ms) / 1000.0, 1) as avg_time_sec
from questions q
left join attempts a on a.question_id = q.id
where q.is_active = true
group by q.exam_id, q.id, q.question_number, q.labels;

create or replace view v_item_choice_distribution as
select
  q.exam_id,
  q.id as question_id,
  q.question_number,
  c.choice_number,
  c.choice_text,
  c.is_correct,
  count(a.id) filter (where c.choice_number = any(a.selected_choice_numbers)) as selected_count,
  count(a.id) as attempt_count,
  round(
    100.0 * count(a.id) filter (where c.choice_number = any(a.selected_choice_numbers))
    / nullif(count(a.id), 0),
    1
  ) as selected_pct
from questions q
join choices c on c.question_id = q.id
left join attempts a on a.question_id = q.id
where q.is_active = true
group by q.exam_id, q.id, q.question_number, c.choice_number, c.choice_text, c.is_correct;

create or replace view v_student_label_accuracy as
select
  a.user_id,
  coalesce(q.labels ->> 'course', q.labels ->> 'subject', '미분류') as course_label,
  coalesce(q.labels ->> 'major_category', q.labels ->> 'unit', '미분류') as major_category,
  coalesce(q.labels ->> 'subtopic', q.labels ->> 'minor_category', '미분류') as subtopic,
  count(a.id) as attempt_count,
  round(100.0 * avg(case when a.is_correct then 1 else 0 end), 1) as correct_rate_pct,
  round(avg(a.time_ms) / 1000.0, 1) as avg_time_sec
from attempts a
join questions q on q.id = a.question_id
where q.is_active = true
group by a.user_id, course_label, major_category, subtopic;

-- Professor demo query: the most common wrong choices by exam.
-- Replace :exam_id with an actual exam id in the application layer.
/*
select
  d.question_number,
  d.choice_number,
  d.choice_text,
  d.selected_count,
  d.attempt_count,
  d.selected_pct
from v_item_choice_distribution d
where d.exam_id = :exam_id
  and d.is_correct = false
  and d.attempt_count >= 3
order by d.selected_pct desc nulls last, d.selected_count desc, d.question_number;
*/

-- Student weakness query: lowest accuracy labels for one learner.
-- Replace :user_id with the authenticated user id.
/*
select
  course_label,
  major_category,
  subtopic,
  attempt_count,
  correct_rate_pct,
  avg_time_sec
from v_student_label_accuracy
where user_id = :user_id
  and attempt_count >= 3
order by correct_rate_pct asc, attempt_count desc
limit 10;
*/
