BEGIN;
CREATE TABLE IF NOT EXISTS club.payment_providers (
 provider_code text PRIMARY KEY CHECK (provider_code ~ '^[a-z][a-z0-9_]{1,31}$'),
 display_name text NOT NULL,
 enabled boolean NOT NULL DEFAULT false,
 supports_online boolean NOT NULL DEFAULT true,
 supports_in_person boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO club.payment_providers(provider_code,display_name,supports_in_person)
VALUES ('stripe','Stripe',false),('paypal','PayPal',false),
       ('sumup','SumUp',true),('quickbooks_payments','QuickBooks Payments',false)
ON CONFLICT(provider_code) DO NOTHING;
CREATE TABLE IF NOT EXISTS club.payment_attempts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 invoice_id uuid NOT NULL REFERENCES club.renewal_invoices(id),
 provider_code text NOT NULL REFERENCES club.payment_providers(provider_code),
 external_session_id text,
 idempotency_key uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
 currency char(3) NOT NULL DEFAULT 'GBP',
 requested_pence bigint NOT NULL CHECK(requested_pence>0),
 state text NOT NULL DEFAULT 'created'
 CHECK(state IN ('created','pending','succeeded','failed','cancelled','expired')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(provider_code,external_session_id)
);
CREATE TABLE IF NOT EXISTS club.provider_transactions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 invoice_id uuid NOT NULL REFERENCES club.renewal_invoices(id),
 attempt_id uuid REFERENCES club.payment_attempts(id),
 provider_code text NOT NULL REFERENCES club.payment_providers(provider_code),
 external_transaction_id text NOT NULL,
 transaction_type text NOT NULL CHECK(transaction_type IN ('payment','refund','dispute','fee','adjustment')),
 currency char(3) NOT NULL DEFAULT 'GBP',
 gross_pence bigint NOT NULL,
 verified boolean NOT NULL DEFAULT false,
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(provider_code,external_transaction_id,transaction_type),
 CHECK((transaction_type='payment' AND gross_pence>0) OR
       (transaction_type IN ('refund','fee') AND gross_pence<=0) OR
       transaction_type IN ('dispute','adjustment'))
);
CREATE TABLE IF NOT EXISTS club.provider_event_inbox (
 provider_code text NOT NULL REFERENCES club.payment_providers(provider_code),
 event_id text NOT NULL,
 external_transaction_id text,
 event_type text NOT NULL,
 payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[0-9a-f]{64}$'),
 verified boolean NOT NULL DEFAULT false,
 processed boolean NOT NULL DEFAULT false,
 received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(provider_code,event_id)
);
CREATE TABLE IF NOT EXISTS club.provider_payouts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 provider_code text NOT NULL REFERENCES club.payment_providers(provider_code),
 external_payout_id text NOT NULL,
 gross_pence bigint NOT NULL,
 fees_pence bigint NOT NULL DEFAULT 0 CHECK(fees_pence>=0),
 net_pence bigint NOT NULL,
 currency char(3) NOT NULL DEFAULT 'GBP',
 reconciled_at timestamptz,
 UNIQUE(provider_code,external_payout_id),
 CHECK(net_pence=gross_pence-fees_pence)
);
-- Only PostgreSQL owner can currently write these tables.
-- No provider credentials live in this schema; use a dedicated protected secret store.
REVOKE ALL ON ALL TABLES IN SCHEMA club FROM PUBLIC,clubmgr;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA club FROM PUBLIC,clubmgr;
GRANT SELECT ON club.current_members TO clubmgr;
COMMIT;
