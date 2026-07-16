-- Foundry Support API schema (Contract v1 §7). Idempotent; applied on boot
-- via the maintenance (owner) connection. Request handlers connect as the
-- non-owner role `support_api_app`, so row-level security below applies to
-- every query they run; tenancy GUCs are set per transaction from the
-- verified token, never from request bodies.

CREATE TABLE IF NOT EXISTS support_conversations (
  id              text PRIMARY KEY,
  app_id          text NOT NULL,
  tenant_id       text NOT NULL,
  subject_id      text NOT NULL,
  subject_email   text,
  department      text NOT NULL,
  status          text NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','escalated','closed')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  closed_at       timestamptz,
  last_message_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conv_scope ON support_conversations (app_id, tenant_id, subject_id);
CREATE INDEX IF NOT EXISTS idx_conv_last  ON support_conversations (last_message_at);

CREATE TABLE IF NOT EXISTS support_messages (
  id              text PRIMARY KEY,
  conversation_id text NOT NULL REFERENCES support_conversations(id) ON DELETE CASCADE,
  app_id          text NOT NULL,
  tenant_id       text NOT NULL,
  sender          text NOT NULL CHECK (sender IN ('user','assistant','operator','system')),
  body            text NOT NULL,
  sources         jsonb NOT NULL DEFAULT '[]',
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON support_messages (conversation_id, created_at);

CREATE TABLE IF NOT EXISTS support_tickets (
  id              text PRIMARY KEY,
  app_id          text NOT NULL,
  tenant_id       text NOT NULL,
  conversation_id text NOT NULL REFERENCES support_conversations(id) ON DELETE CASCADE,
  department      text NOT NULL,
  summary         text NOT NULL,
  subject         jsonb NOT NULL DEFAULT '{}',
  status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open','replied','closed')),
  reply           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  replied_at      timestamptz
);
CREATE INDEX IF NOT EXISTS idx_ticket_scope ON support_tickets (app_id, tenant_id, status);

CREATE TABLE IF NOT EXISTS support_feedback (
  conversation_id text PRIMARY KEY REFERENCES support_conversations(id) ON DELETE CASCADE,
  app_id          text NOT NULL,
  tenant_id       text NOT NULL,
  rating          text NOT NULL,
  reason          text,
  comment         text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Replay protection (§2.1): jti is single-use per app; the unique index IS
-- the check — a violation on insert means replay. GC'd after ~10 minutes.
CREATE TABLE IF NOT EXISTS consumed_jtis (
  app_id      text NOT NULL,
  jti         text NOT NULL,
  consumed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (app_id, jti)
);
CREATE INDEX IF NOT EXISTS idx_jti_age ON consumed_jtis (consumed_at);

-- Token accounting for cost ceilings (§6); no transcript content in here.
CREATE TABLE IF NOT EXISTS support_usage (
  app_id          text NOT NULL,
  tenant_id       text NOT NULL,
  conversation_id text NOT NULL,
  day             date NOT NULL,
  tokens          bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (app_id, tenant_id, conversation_id, day)
);

-- Durable outbound webhook queue (§5); worker runs on the owner connection.
CREATE TABLE IF NOT EXISTS support_webhook_deliveries (
  id              text PRIMARY KEY,
  app_id          text NOT NULL,
  tenant_id       text NOT NULL DEFAULT '',
  event_type      text NOT NULL,
  dedupe_key      text NOT NULL UNIQUE,
  payload         jsonb NOT NULL,
  status          text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','delivered','failed')),
  attempts        int NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  delivered_at    timestamptz
);
CREATE INDEX IF NOT EXISTS idx_whd_due ON support_webhook_deliveries (status, next_attempt_at);

-- ---------------------------------------------------------------------------
-- Row-level security. The app role only ever sees rows matching the GUCs set
-- from the verified token; current_setting(..., true) is NULL when unset, so
-- an unset context matches nothing (fail closed).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'support_api_app') THEN
    CREATE ROLE support_api_app NOLOGIN;  -- LOGIN + password set by initdb/ops
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO support_api_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  support_conversations, support_messages, support_tickets, support_feedback,
  consumed_jtis, support_usage, support_webhook_deliveries
TO support_api_app;

ALTER TABLE support_conversations     ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_messages          ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_tickets           ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_feedback          ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_usage             ENABLE ROW LEVEL SECURITY;
ALTER TABLE consumed_jtis             ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_webhook_deliveries ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['support_conversations','support_messages',
                           'support_tickets','support_feedback','support_usage',
                           'support_webhook_deliveries'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I '
      'USING (app_id = current_setting(''support.app_id'', true) '
      '  AND tenant_id = current_setting(''support.tenant_id'', true)) '
      'WITH CHECK (app_id = current_setting(''support.app_id'', true) '
      '  AND tenant_id = current_setting(''support.tenant_id'', true))', t);
  END LOOP;
END $$;

DROP POLICY IF EXISTS app_isolation ON consumed_jtis;
CREATE POLICY app_isolation ON consumed_jtis
  USING (app_id = current_setting('support.app_id', true))
  WITH CHECK (app_id = current_setting('support.app_id', true));
