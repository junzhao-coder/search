-- S2 initial schema (contract §1/§2, tables required by the S2-B1 import+query scope).
-- Draft/feedback/search_coverage/expense tables are intentionally NOT created yet (later stages).

CREATE TABLE source (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  channel TEXT NOT NULL CHECK (channel IN ('manual','xianyu','xiaohongshu','bilibili','other')),
  access_mode TEXT NOT NULL CHECK (access_mode IN ('manual_import','auto_read','official_api','unknown')),
  access_verified TEXT NOT NULL CHECK (access_verified IN ('yes','no','unknown')),
  fields_available TEXT,
  rate_limit_note TEXT,
  cost_note TEXT,
  terms_note TEXT,
  last_success_at TEXT,
  last_error_at TEXT,
  last_error TEXT,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE import_batch (
  id TEXT PRIMARY KEY,
  file_name TEXT,
  format TEXT NOT NULL CHECK (format IN ('csv','json')),
  format_version INTEGER NOT NULL DEFAULT 1,
  mode TEXT NOT NULL CHECK (mode IN ('atomic','partial','validate')),
  encoding TEXT,
  status TEXT NOT NULL CHECK (status IN ('committed','rejected','partial_committed','validated')),
  rows_total INTEGER NOT NULL DEFAULT 0,
  rows_created INTEGER NOT NULL DEFAULT 0,
  rows_duplicate INTEGER NOT NULL DEFAULT 0,
  rows_version_added INTEGER NOT NULL DEFAULT 0,
  rows_suspect INTEGER NOT NULL DEFAULT 0,
  rows_rejected INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE candidate (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  identity_key TEXT NOT NULL,
  identity_source TEXT NOT NULL CHECK (identity_source IN ('demand_native_id','demand_url','title')),
  category TEXT,
  use_case TEXT,
  delivery_form TEXT,
  notes TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending','testable','explore','stale','archived')),
  status_reason TEXT NOT NULL,
  status_updated_at TEXT NOT NULL,
  manual_override TEXT NOT NULL DEFAULT 'none' CHECK (manual_override IN ('none','explore','archived')),
  override_reason TEXT,
  override_at TEXT,
  title_norm_hash TEXT NOT NULL,
  data_origin TEXT NOT NULL CHECK (data_origin IN ('real','synthetic')),
  import_batch_id TEXT REFERENCES import_batch(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_candidate_identity ON candidate(data_origin, identity_key);
CREATE INDEX ix_candidate_status ON candidate(status);
CREATE INDEX ix_candidate_title_hash ON candidate(title_norm_hash);

CREATE TABLE demand_signal (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  source_id TEXT NOT NULL REFERENCES source(id),
  native_id TEXT,
  url TEXT NOT NULL,
  url_norm TEXT NOT NULL,
  identity_key TEXT NOT NULL,
  identity_source TEXT NOT NULL CHECK (identity_source IN ('demand_native_id','demand_url')),
  excerpt TEXT NOT NULL,
  signal_kind TEXT NOT NULL CHECK (signal_kind IN ('seller_promo','specific_ask','want_to_buy','business_record','other')),
  engagement_json TEXT,
  published_at TEXT,
  published_date TEXT,
  observed_at TEXT NOT NULL,
  observed_at_source TEXT NOT NULL CHECK (observed_at_source IN ('source','import_time')),
  original_author TEXT,
  is_repost INTEGER NOT NULL DEFAULT 0 CHECK (is_repost IN (0,1)),
  origin_group_key TEXT,
  origin_group_basis TEXT CHECK (origin_group_basis IS NULL OR origin_group_basis IN ('detected','manual')),
  content_hash TEXT NOT NULL,
  version_no INTEGER NOT NULL DEFAULT 1,
  superseded_by TEXT REFERENCES demand_signal(id),
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  data_origin TEXT NOT NULL CHECK (data_origin IN ('real','synthetic')),
  import_batch_id TEXT REFERENCES import_batch(id),
  CHECK (published_at IS NULL OR published_date IS NULL)
);

CREATE UNIQUE INDEX ux_demand_strong ON demand_signal(data_origin, source_id, identity_key, content_hash);
CREATE INDEX ix_demand_candidate ON demand_signal(candidate_id);
CREATE INDEX ix_demand_identity ON demand_signal(data_origin, source_id, identity_key);

CREATE TABLE evidence (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  evidence_type TEXT NOT NULL CHECK (evidence_type IN ('demand','supply_distribution','cost','platform_policy','validity','other')),
  demand_signal_id TEXT REFERENCES demand_signal(id),
  source_id TEXT REFERENCES source(id),
  source_url TEXT NOT NULL,
  native_id TEXT,
  excerpt TEXT NOT NULL,
  fact_kind TEXT NOT NULL CHECK (fact_kind IN ('fact','estimate','assumption')),
  observed_at TEXT NOT NULL,
  expires_at TEXT,
  invalidated_at TEXT,
  invalid_reason TEXT,
  supersedes_id TEXT REFERENCES evidence(id),
  data_origin TEXT NOT NULL CHECK (data_origin IN ('real','synthetic')),
  import_batch_id TEXT REFERENCES import_batch(id),
  created_at TEXT NOT NULL,
  CHECK (invalidated_at IS NULL OR invalid_reason IS NOT NULL)
);

CREATE UNIQUE INDEX ux_evidence_from_signal ON evidence(demand_signal_id) WHERE demand_signal_id IS NOT NULL;
CREATE INDEX ix_evidence_candidate ON evidence(candidate_id, evidence_type);

CREATE TABLE supply_offer (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  provider_name TEXT NOT NULL,
  provider_url TEXT NOT NULL,
  url_norm TEXT NOT NULL,
  native_id TEXT,
  origin_type TEXT NOT NULL CHECK (origin_type IN ('original_author','official','open_repo','distributor','self_made','unknown')),
  format_version TEXT NOT NULL DEFAULT '',
  unit_price_minor INTEGER CHECK (unit_price_minor IS NULL OR unit_price_minor >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  price_basis TEXT CHECK (price_basis IS NULL OR price_basis IN ('one_time','per_unit','subscription')),
  price_valid_until TEXT,
  license_summary TEXT,
  license_scope_note TEXT,
  license_evidence_url TEXT,
  license_evidence_id TEXT REFERENCES evidence(id),
  downloadable TEXT NOT NULL CHECK (downloadable IN ('yes','no','unknown')),
  commercial_allowed TEXT NOT NULL CHECK (commercial_allowed IN ('yes','no','unknown')),
  redistribute_allowed TEXT NOT NULL CHECK (redistribute_allowed IN ('yes','no','unknown')),
  resale_allowed TEXT NOT NULL CHECK (resale_allowed IN ('yes','no','unknown')),
  sample_checked TEXT NOT NULL DEFAULT 'none' CHECK (sample_checked IN ('none','partial','checked')),
  sample_note TEXT,
  status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','verified','invalid','stale')),
  last_checked_at TEXT,
  check_note TEXT,
  data_origin TEXT NOT NULL CHECK (data_origin IN ('real','synthetic')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (sample_checked = 'none' OR sample_note IS NOT NULL)
);

CREATE UNIQUE INDEX ux_supply_strong ON supply_offer(data_origin, candidate_id, url_norm, format_version);
CREATE INDEX ix_supply_candidate ON supply_offer(candidate_id);

CREATE TABLE cost_item (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  supply_offer_id TEXT REFERENCES supply_offer(id),
  role TEXT NOT NULL CHECK (role IN ('sale_price','procurement','platform_fee','payment_fee','acquisition','refund_reserve','manual_labor','other')),
  basis TEXT NOT NULL CHECK (basis IN ('per_order','one_time','recurring')),
  value_kind TEXT CHECK (value_kind IS NULL OR value_kind IN ('money','rate','minutes')),
  money_minor INTEGER CHECK (money_minor IS NULL OR money_minor >= 0),
  rate_bp INTEGER CHECK (rate_bp IS NULL OR (rate_bp >= 0 AND rate_bp <= 10000)),
  minutes INTEGER CHECK (minutes IS NULL OR (minutes >= 0 AND minutes <= 1440)),
  hourly_rate_minor INTEGER CHECK (hourly_rate_minor IS NULL OR hourly_rate_minor >= 0),
  period TEXT CHECK (period IS NULL OR period IN ('monthly','quarterly','yearly')),
  variant TEXT NOT NULL DEFAULT 'base',
  currency TEXT NOT NULL DEFAULT 'CNY',
  fact_kind TEXT NOT NULL CHECK (fact_kind IN ('fact','estimate','assumption')),
  source_evidence_id TEXT REFERENCES evidence(id),
  assumption_note TEXT,
  valid_until TEXT,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  supersedes_id TEXT REFERENCES cost_item(id),
  data_origin TEXT NOT NULL CHECK (data_origin IN ('real','synthetic')),
  created_at TEXT NOT NULL,
  CHECK (
    (value_kind = 'money' AND money_minor IS NOT NULL AND rate_bp IS NULL AND minutes IS NULL)
    OR (value_kind = 'rate' AND rate_bp IS NOT NULL AND money_minor IS NULL AND minutes IS NULL)
    OR (value_kind = 'minutes' AND minutes IS NOT NULL AND money_minor IS NULL AND rate_bp IS NULL)
    OR (value_kind IS NULL AND money_minor IS NULL AND rate_bp IS NULL AND minutes IS NULL)
  ),
  CHECK (value_kind <> 'rate' OR basis = 'per_order'),
  CHECK (value_kind <> 'minutes' OR role = 'manual_labor'),
  CHECK (hourly_rate_minor IS NULL OR role = 'manual_labor'),
  CHECK (role <> 'sale_price' OR value_kind IS NULL OR value_kind = 'money'),
  CHECK (basis <> 'recurring' OR period IS NOT NULL)
  -- NOTE: 'assumption' rows without assumption_note are storable by design (contract §4.3:
  -- "假设未说明" does not count as evidence; G3 enforces the note at gate admission).
);

CREATE UNIQUE INDEX ux_cost_active ON cost_item(candidate_id, role, basis, variant) WHERE is_active = 1;
CREATE INDEX ix_cost_candidate ON cost_item(candidate_id);

CREATE TABLE gate_review (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  gate TEXT NOT NULL CHECK (gate IN ('demand','supply_distribution','cost','platform_policy')),
  seq INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('unverified','verified','failed','expired')),
  evidence_id TEXT REFERENCES evidence(id),
  supply_offer_id TEXT REFERENCES supply_offer(id),
  applies_to_platform TEXT,
  applies_to_version TEXT,
  verified_by TEXT NOT NULL CHECK (verified_by IN ('user','system_rule')),
  verified_at TEXT NOT NULL,
  expires_at TEXT,
  note TEXT,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_gate_seq ON gate_review(candidate_id, gate, seq);
CREATE INDEX ix_gate_candidate ON gate_review(candidate_id, gate, seq);

CREATE TABLE review_item (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('dup_suspect','gate_expired','supply_invalid','evidence_expired','license_changed','cost_changed','import_warning')),
  ref_type TEXT NOT NULL CHECK (ref_type IN ('candidate','demand_signal','evidence','supply_offer','cost_item')),
  ref_id TEXT NOT NULL,
  ref_gate TEXT,
  ref_id_b TEXT,
  reason TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open','resolved_merged','resolved_distinct','resolved_recheck','dismissed')),
  blocking INTEGER NOT NULL DEFAULT 0 CHECK (blocking IN (0,1)),
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  note TEXT,
  data_origin TEXT NOT NULL CHECK (data_origin IN ('real','synthetic'))
);

CREATE UNIQUE INDEX ux_review_open ON review_item(kind, ref_type, ref_id, COALESCE(ref_gate,''), COALESCE(ref_id_b,'')) WHERE status = 'open';
CREATE INDEX ix_review_status ON review_item(status);

CREATE TABLE import_row_result (
  id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES import_batch(id),
  row_no INTEGER NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('created','duplicate_skipped','version_added','suspect_review','warning','rejected')),
  record_type TEXT CHECK (record_type IS NULL OR record_type IN ('candidate','demand_signal','evidence','supply_offer','cost_item')),
  record_id TEXT,
  reason_code TEXT,
  reason_detail TEXT
);

CREATE INDEX ix_row_result_batch ON import_row_result(batch_id, row_no);

CREATE TABLE run_record (
  id TEXT PRIMARY KEY,
  parent_run_id TEXT REFERENCES run_record(id),
  run_type TEXT NOT NULL CHECK (run_type IN ('import','collect','pipeline','summary','recompute','backup')),
  trigger TEXT NOT NULL CHECK (trigger IN ('manual','scheduled','system')),
  logical_date TEXT NOT NULL,
  source_id TEXT REFERENCES source(id),
  status TEXT NOT NULL CHECK (status IN ('running','ok','partial','failed','interrupted','skipped_duplicate')),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  items_found INTEGER NOT NULL DEFAULT 0,
  items_new INTEGER NOT NULL DEFAULT 0,
  items_dup INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT,
  notes TEXT
);

CREATE UNIQUE INDEX ux_run_daily ON run_record(run_type, logical_date, COALESCE(source_id,'')) WHERE run_type IN ('collect','pipeline','summary','backup');
CREATE INDEX ix_run_started ON run_record(started_at);

CREATE TABLE idempotency_key (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  client_ref TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_json TEXT NOT NULL,
  record_id TEXT,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_idem_scope_ref ON idempotency_key(scope, client_ref);

INSERT OR IGNORE INTO source(id,name,channel,access_mode,access_verified,fields_available,terms_note,enabled,created_at,updated_at)
VALUES ('s_manual','manual_import','manual','manual_import','yes','用户人工整理的 CSV/JSON 字段','人工导入为本系统保底路径；不代表任何平台自动读取可用','1','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z');

INSERT OR IGNORE INTO source(id,name,channel,access_mode,access_verified,fields_available,terms_note,enabled,created_at,updated_at)
VALUES ('s_xianyu','xianyu','xianyu','manual_import','yes','公开协议文本；商品页为 JS 空壳','A 报告：未核实到发现型自动入口；仅人工导入','1','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z');

INSERT OR IGNORE INTO source(id,name,channel,access_mode,access_verified,fields_available,terms_note,enabled,created_at,updated_at)
VALUES ('s_xhs','xiaohongshu','xiaohongshu','manual_import','yes','需登录；规则页为 SPA 空壳','A 报告：未核实到发现型自动入口；仅人工导入','1','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z');

INSERT OR IGNORE INTO source(id,name,channel,access_mode,access_verified,fields_available,terms_note,enabled,created_at,updated_at)
VALUES ('s_bili','bilibili','bilibili','manual_import','yes','搜索接口 -412；详情接口为 S3 候选','A 报告：详情接口未接入；本轮不启用自动读取','1','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z');
