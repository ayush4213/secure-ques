PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS questions (
  id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  topic TEXT NOT NULL,
  difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
  question_type TEXT NOT NULL CHECK(question_type IN ('conceptual','numerical','application','reasoning')),
  text TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_question_tags ON questions(active, subject, difficulty, question_type);

CREATE TABLE IF NOT EXISTS question_options (
  id TEXT PRIMARY KEY,
  question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
  text TEXT NOT NULL,
  is_correct INTEGER NOT NULL CHECK(is_correct IN (0,1)),
  UNIQUE(question_id, text)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_correct_option_per_question
  ON question_options(question_id) WHERE is_correct = 1;
CREATE INDEX IF NOT EXISTS idx_options_question ON question_options(question_id, is_correct);

CREATE TABLE IF NOT EXISTS exam_sessions (
  id TEXT PRIMARY KEY,
  student_name TEXT NOT NULL,
  student_code TEXT NOT NULL,
  exam_goal TEXT NOT NULL,
  requirements_json TEXT NOT NULL,
  blueprint_json TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  created_at TEXT NOT NULL,
  ends_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','submitted')),
  submitted_at TEXT,
  score INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sessions_student ON exam_sessions(student_code, created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_fingerprint ON exam_sessions(fingerprint);

CREATE TABLE IF NOT EXISTS exam_items (
  session_id TEXT NOT NULL REFERENCES exam_sessions(id) ON DELETE CASCADE,
  question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
  position INTEGER NOT NULL,
  PRIMARY KEY(session_id, question_id),
  UNIQUE(session_id, position)
);
CREATE INDEX IF NOT EXISTS idx_exam_item_question ON exam_items(question_id);

CREATE TABLE IF NOT EXISTS session_options (
  session_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  option_id TEXT NOT NULL REFERENCES question_options(id) ON DELETE RESTRICT,
  position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 3),
  PRIMARY KEY(session_id, question_id, position),
  UNIQUE(session_id, question_id, option_id),
  FOREIGN KEY (session_id, question_id) REFERENCES exam_items(session_id, question_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_answers (
  session_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  option_id TEXT NOT NULL,
  answered_at TEXT NOT NULL,
  PRIMARY KEY(session_id, question_id),
  FOREIGN KEY (session_id, question_id, option_id)
    REFERENCES session_options(session_id, question_id, option_id) ON DELETE RESTRICT
);
