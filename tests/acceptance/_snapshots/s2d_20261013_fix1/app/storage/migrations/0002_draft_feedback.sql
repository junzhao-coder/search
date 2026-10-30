-- S2-B2: draft + feedback tables (contract §1.7/§1.8). Versioned; does not touch 0001 objects.

CREATE TABLE draft (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  kind TEXT NOT NULL CHECK (kind IN ('listing_copy','reply','delivery_note')),
  method TEXT NOT NULL CHECK (method IN ('template','model_assisted')),
  body TEXT NOT NULL,
  evidence_refs_json TEXT,
  status TEXT NOT NULL CHECK (status IN ('draft','final')),
  model_name TEXT,
  template_version TEXT,
  data_origin TEXT NOT NULL CHECK (data_origin IN ('real','synthetic')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX ix_draft_candidate ON draft(candidate_id, created_at);

CREATE TABLE feedback (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  kind TEXT NOT NULL CHECK (kind IN ('inquiry','sale','refund','expense','manual_time','note')),
  order_ref TEXT,
  related_feedback_id TEXT REFERENCES feedback(id),
  occurred_at TEXT NOT NULL,
  quantity INTEGER CHECK (quantity IS NULL OR quantity > 0),
  unit_price_minor INTEGER CHECK (unit_price_minor IS NULL OR unit_price_minor >= 0),
  amount_minor INTEGER CHECK (amount_minor IS NULL OR amount_minor >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  expense_kind TEXT CHECK (expense_kind IS NULL OR expense_kind IN ('procurement','platform','acquisition','run','other')),
  expense_basis TEXT CHECK (expense_basis IS NULL OR expense_basis IN ('per_order','one_time','recurring')),
  refund_state TEXT CHECK (refund_state IS NULL OR refund_state IN ('pending','settled')),
  predicted_net_per_order_minor INTEGER,
  predicted_snapshot_at TEXT,
  actual_net_per_order_minor INTEGER,
  actual_complete INTEGER CHECK (actual_complete IS NULL OR actual_complete IN (0,1)),
  actual_minutes INTEGER CHECK (actual_minutes IS NULL OR (actual_minutes >= 0 AND actual_minutes <= 1440)),
  actual_hourly_rate_minor INTEGER CHECK (actual_hourly_rate_minor IS NULL OR actual_hourly_rate_minor >= 0),
  note TEXT,
  data_origin TEXT NOT NULL CHECK (data_origin IN ('real','synthetic')),
  created_at TEXT NOT NULL,
  CHECK (kind <> 'refund' OR (refund_state IS NOT NULL AND related_feedback_id IS NOT NULL)),
  CHECK (kind <> 'expense' OR expense_kind IS NOT NULL),
  CHECK (kind <> 'manual_time' OR actual_minutes IS NOT NULL),
  CHECK (kind = 'manual_time' OR (actual_minutes IS NULL AND actual_hourly_rate_minor IS NULL)),
  CHECK (kind = 'refund' OR refund_state IS NULL)
);

CREATE INDEX ix_feedback_candidate ON feedback(candidate_id, kind, occurred_at);
CREATE UNIQUE INDEX ux_feedback_sale_order ON feedback(candidate_id, order_ref) WHERE kind = 'sale' AND order_ref IS NOT NULL;
