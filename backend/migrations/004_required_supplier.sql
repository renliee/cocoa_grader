-- Enforce supplier-first writes without rewriting evidence in previously saved records.
CREATE TRIGGER lot_supplier_required_insert BEFORE INSERT ON lots
WHEN NEW.supplier_id IS NULL OR NEW.supplier_id=''
BEGIN SELECT RAISE(ABORT,'supplier required for a new lot'); END;

CREATE TRIGGER lot_supplier_required_update BEFORE UPDATE OF supplier_id ON lots
WHEN NEW.supplier_id IS NULL OR NEW.supplier_id=''
BEGIN SELECT RAISE(ABORT,'supplier cannot be removed from a lot'); END;

CREATE TRIGGER finalize_supplier_required BEFORE UPDATE OF state ON revisions
WHEN NEW.state='finalized' AND NOT EXISTS (
  SELECT 1 FROM lots l JOIN suppliers s ON s.id=l.supplier_id AND s.owner_id=l.owner_id
  WHERE l.id=NEW.lot_id AND l.owner_id=NEW.owner_id
)
BEGIN SELECT RAISE(ABORT,'supplier required before finalization'); END;
