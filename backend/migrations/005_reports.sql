CREATE TABLE reports (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  revision_id TEXT NOT NULL UNIQUE REFERENCES revisions(id) ON DELETE RESTRICT,
  share_token TEXT NOT NULL UNIQUE,
  snapshot_key TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT,
  UNIQUE(owner_id,id)
);
CREATE INDEX reports_owner_revision ON reports(owner_id,revision_id);

CREATE TABLE report_exports (
  report_id TEXT PRIMARY KEY REFERENCES reports(id) ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK(status IN ('queued','running','complete','failed')),
  template_version INTEGER NOT NULL DEFAULT 1,
  payload_sha256 TEXT NOT NULL,
  pdf_key TEXT,
  pdf_sha256 TEXT,
  error_text TEXT,
  attempt INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
CREATE INDEX report_exports_state ON report_exports(status,updated_at);
