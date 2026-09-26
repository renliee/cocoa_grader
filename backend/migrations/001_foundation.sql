CREATE TABLE users (
  id TEXT PRIMARY KEY,
  login TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
  created_at TEXT NOT NULL
);
CREATE TABLE sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf_token TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX sessions_user ON sessions(user_id);
CREATE TABLE suppliers (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  code TEXT NOT NULL,
  contact TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  archived_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(owner_id, code),
  UNIQUE(owner_id, id)
);
CREATE INDEX suppliers_owner_archived ON suppliers(owner_id, archived_at);
CREATE TABLE lot_sequences (
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  supplier_id TEXT NOT NULL,
  local_date TEXT NOT NULL,
  last_issued INTEGER NOT NULL CHECK(last_issued > 0),
  PRIMARY KEY(owner_id, supplier_id, local_date),
  FOREIGN KEY(owner_id, supplier_id) REFERENCES suppliers(owner_id, id) ON DELETE RESTRICT
);
CREATE TABLE lots (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  supplier_id TEXT NOT NULL,
  human_id TEXT NOT NULL,
  issue_date TEXT NOT NULL,
  sequence INTEGER NOT NULL CHECK(sequence > 0),
  current_revision_id TEXT,
  first_finalized_at TEXT,
  first_finalized_date TEXT,
  archived_at TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(owner_id, human_id),
  UNIQUE(owner_id, id),
  FOREIGN KEY(owner_id, supplier_id) REFERENCES suppliers(owner_id, id) ON DELETE RESTRICT,
  FOREIGN KEY(id, current_revision_id) REFERENCES revisions(lot_id, id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX lots_owner_supplier ON lots(owner_id, supplier_id);
CREATE INDEX lots_owner_date ON lots(owner_id, first_finalized_date);
CREATE TABLE revisions (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  lot_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('draft','finalized')),
  revision_number INTEGER,
  base_revision_id TEXT,
  weight_kg TEXT,
  notes TEXT NOT NULL DEFAULT '',
  wizard_step TEXT NOT NULL DEFAULT 'lot' CHECK(wizard_step IN ('lot','sample','result')),
  draft_version INTEGER NOT NULL DEFAULT 1,
  input_version INTEGER NOT NULL DEFAULT 0,
  selected_run_id TEXT,
  supplier_name_snapshot TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finalized_at TEXT,
  UNIQUE(lot_id, id),
  UNIQUE(lot_id, revision_number),
  FOREIGN KEY(owner_id, lot_id) REFERENCES lots(owner_id, id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX one_draft_per_lot ON revisions(lot_id) WHERE state='draft';
CREATE INDEX revisions_owner_state ON revisions(owner_id, state);
CREATE TABLE revision_governance (
  revision_id TEXT PRIMARY KEY REFERENCES revisions(id) ON DELETE RESTRICT,
  flag_reason TEXT,
  flag_notes TEXT,
  manually_excluded INTEGER NOT NULL DEFAULT 0 CHECK(manually_excluded IN (0,1)),
  exclusion_reason TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE photos (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  original_key TEXT NOT NULL,
  width INTEGER,
  height INTEGER,
  created_at TEXT NOT NULL,
  UNIQUE(owner_id, id)
);
CREATE TABLE prechecks (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  photo_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('queued','processing','ready','warning','invalid','failed')),
  manifest_key TEXT,
  manifest_sha256 TEXT,
  annotation_key TEXT,
  usable_count INTEGER CHECK(usable_count >= 0),
  excluded_count INTEGER CHECK(excluded_count >= 0),
  error_text TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT,
  UNIQUE(photo_id, id),
  FOREIGN KEY(owner_id, photo_id) REFERENCES photos(owner_id, id) ON DELETE RESTRICT
);
CREATE TABLE revision_photos (
  revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE RESTRICT,
  photo_id TEXT NOT NULL REFERENCES photos(id) ON DELETE RESTRICT,
  precheck_id TEXT NOT NULL,
  sort_order INTEGER NOT NULL,
  review_state TEXT NOT NULL CHECK(review_state IN ('pending','included','omitted')),
  PRIMARY KEY(revision_id, photo_id),
  FOREIGN KEY(photo_id, precheck_id) REFERENCES prechecks(photo_id, id) ON DELETE RESTRICT
);
CREATE TABLE analysis_runs (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE RESTRICT,
  input_version INTEGER NOT NULL,
  input_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('queued','processing','complete','failed')),
  manifest_key TEXT,
  manifest_sha256 TEXT,
  usable_count INTEGER CHECK(usable_count >= 0),
  fermented_count INTEGER CHECK(fermented_count >= 0),
  poorly_count INTEGER CHECK(poorly_count >= 0),
  excluded_count INTEGER CHECK(excluded_count >= 0),
  photo_count INTEGER CHECK(photo_count >= 0),
  error_text TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE INDEX runs_revision_status ON analysis_runs(revision_id, status);
CREATE TABLE processing_jobs (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  kind TEXT NOT NULL CHECK(kind IN ('precheck','classify')),
  target_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('queued','running','succeeded','failed','cancelled')),
  error_text TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE INDEX jobs_state ON processing_jobs(state, created_at);
CREATE TRIGGER finalized_revision_immutable BEFORE UPDATE ON revisions
WHEN OLD.state='finalized' BEGIN SELECT RAISE(ABORT,'finalized revision is immutable'); END;
CREATE TRIGGER finalized_membership_immutable_update BEFORE UPDATE ON revision_photos
WHEN (SELECT state FROM revisions WHERE id=OLD.revision_id)='finalized'
BEGIN SELECT RAISE(ABORT,'finalized membership is immutable'); END;
CREATE TRIGGER finalized_membership_immutable_delete BEFORE DELETE ON revision_photos
WHEN (SELECT state FROM revisions WHERE id=OLD.revision_id)='finalized'
BEGIN SELECT RAISE(ABORT,'finalized membership is immutable'); END;
CREATE TRIGGER completed_run_immutable BEFORE UPDATE ON analysis_runs
WHEN OLD.status='complete' BEGIN SELECT RAISE(ABORT,'completed analysis is immutable'); END;
CREATE TRIGGER current_revision_guard BEFORE UPDATE OF current_revision_id ON lots
WHEN NEW.current_revision_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM revisions r WHERE r.id=NEW.current_revision_id
  AND r.lot_id=NEW.id AND r.owner_id=NEW.owner_id AND r.state='finalized'
) BEGIN SELECT RAISE(ABORT,'current revision must be finalized for this lot'); END;
CREATE TRIGGER supplier_code_frozen BEFORE UPDATE OF code ON suppliers
WHEN OLD.code<>NEW.code AND EXISTS(SELECT 1 FROM lots WHERE supplier_id=OLD.id)
BEGIN SELECT RAISE(ABORT,'supplier code is already issued'); END;
