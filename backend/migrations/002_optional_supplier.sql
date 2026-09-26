-- Analysis now starts with images; an assigned supplier is optional even at finalization.
-- The migrator temporarily disables FK checks for this table rebuild, then runs foreign_key_check before commit.

CREATE TABLE lots_rebuilt (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  supplier_id TEXT,
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
INSERT INTO lots_rebuilt SELECT * FROM lots;
DROP TRIGGER supplier_code_frozen;
DROP TABLE lots;
ALTER TABLE lots_rebuilt RENAME TO lots;
CREATE INDEX lots_owner_supplier ON lots(owner_id, supplier_id);
CREATE INDEX lots_owner_date ON lots(owner_id, first_finalized_date);
CREATE TRIGGER current_revision_guard BEFORE UPDATE OF current_revision_id ON lots
WHEN NEW.current_revision_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM revisions r WHERE r.id=NEW.current_revision_id
  AND r.lot_id=NEW.id AND r.owner_id=NEW.owner_id AND r.state='finalized'
) BEGIN SELECT RAISE(ABORT,'current revision must be finalized for this lot'); END;
CREATE TRIGGER supplier_code_frozen BEFORE UPDATE OF code ON suppliers
WHEN OLD.code<>NEW.code AND EXISTS(SELECT 1 FROM lots WHERE supplier_id=OLD.id)
BEGIN SELECT RAISE(ABORT,'supplier code is already issued'); END;

CREATE TABLE anonymous_lot_sequences (
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  local_date TEXT NOT NULL,
  last_issued INTEGER NOT NULL CHECK(last_issued > 0),
  PRIMARY KEY(owner_id, local_date)
);

ALTER TABLE photos ADD COLUMN canonical_key TEXT;
ALTER TABLE photos ADD COLUMN media_type TEXT;
ALTER TABLE photos ADD COLUMN byte_size INTEGER;
ALTER TABLE revision_photos ADD COLUMN upload_key TEXT;
CREATE UNIQUE INDEX revision_photo_upload_key ON revision_photos(revision_id, upload_key)
  WHERE upload_key IS NOT NULL;
