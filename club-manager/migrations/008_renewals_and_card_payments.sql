BEGIN;
CREATE TABLE IF NOT EXISTS club.renewal_campaigns (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 renewal_year integer NOT NULL UNIQUE CHECK(renewal_year BETWEEN 2020 AND 2200),
 state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','approved','sending','closed')),
 approved_by text, approved_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(state='draft' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS club.renewal_items (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 campaign_id uuid NOT NULL REFERENCES club.renewal_campaigns(id),
 member_id uuid NOT NULL REFERENCES club.member_profiles(id),
 charge_kind text NOT NULL CHECK(charge_kind IN ('membership','yard','mooring','clubhouse')),
 source_id uuid, description text NOT NULL,
 amount_pence bigint NOT NULL CHECK(amount_pence>=0),
 UNIQUE(campaign_id,member_id,charge_kind,source_id)
);
CREATE TABLE IF NOT EXISTS club.renewal_invoices (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 campaign_id uuid NOT NULL REFERENCES club.renewal_campaigns(id),
 member_id uuid NOT NULL REFERENCES club.member_profiles(id),
 amount_pence bigint NOT NULL CHECK(amount_pence>=0),
 amount_paid_pence bigint NOT NULL DEFAULT 0 CHECK(amount_paid_pence>=0),
 state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','issued','part_paid','paid','void','disputed')),
 issued_at timestamptz, settled_at timestamptz,
 UNIQUE(campaign_id,member_id),
 CHECK(amount_paid_pence<=amount_pence)
);
CREATE TABLE IF NOT EXISTS club.renewal_invoice_lines (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 invoice_id uuid NOT NULL REFERENCES club.renewal_invoices(id),
 item_id uuid NOT NULL UNIQUE REFERENCES club.renewal_items(id)
);
CREATE TABLE IF NOT EXISTS club.renewal_notices (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 invoice_id uuid NOT NULL REFERENCES club.renewal_invoices(id),
 channel text NOT NULL CHECK(channel IN ('email','joomla','post')),
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','sent','failed','cancelled')),
 destination_ref text, send_after timestamptz NOT NULL DEFAULT now(),
 sent_at timestamptz, attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count>=0),
 UNIQUE(invoice_id,channel)
);
CREATE TABLE IF NOT EXISTS club.checkout_requests (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 invoice_id uuid NOT NULL REFERENCES club.renewal_invoices(id),
 provider text NOT NULL DEFAULT 'stripe' CHECK(provider IN ('stripe')),
 amount_pence bigint NOT NULL CHECK(amount_pence>0),
 currency char(3) NOT NULL DEFAULT 'GBP',
 provider_session_id text UNIQUE,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','created','completed','expired','cancelled')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS club.payment_receipts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 invoice_id uuid NOT NULL REFERENCES club.renewal_invoices(id),
 provider text NOT NULL CHECK(provider IN ('stripe')),
 provider_payment_id text NOT NULL,
 amount_pence bigint NOT NULL CHECK(amount_pence>0),
 currency char(3) NOT NULL DEFAULT 'GBP',
 received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(provider,provider_payment_id)
);
CREATE TABLE IF NOT EXISTS club.payment_webhook_inbox (
 provider text NOT NULL,
 provider_event_id text NOT NULL,
 event_type text NOT NULL,
 state text NOT NULL DEFAULT 'received' CHECK(state IN ('received','validated','processed','rejected')),
 payload_digest text NOT NULL,
 received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(provider,provider_event_id)
);
-- Only an already independently verified Stripe payment may be settled.
-- Gateway verifies signature and fetches authoritative amount/currency/session.
-- This primitive assumes that independent verification has happened upstream.
CREATE OR REPLACE FUNCTION club.apply_verified_card_payment(
 p_invoice uuid,p_provider_payment_id text,p_amount bigint,p_currency char(3)
) RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE inv record; existing uuid; next_paid bigint;
BEGIN
 IF p_amount<=0 OR p_currency <> 'GBP' OR p_provider_payment_id IS NULL OR length(trim(p_provider_payment_id))<4
 THEN RAISE EXCEPTION 'Invalid payment proof'; END IF;
 SELECT * INTO inv FROM club.renewal_invoices WHERE id=p_invoice FOR UPDATE;
 IF NOT FOUND OR inv.state NOT IN ('issued','part_paid') THEN
   RAISE EXCEPTION 'Invoice not payable';
 END IF;
 SELECT id INTO existing FROM club.payment_receipts
  WHERE provider='stripe' AND provider_payment_id=p_provider_payment_id;
 IF existing IS NOT NULL THEN RETURN 'duplicate'; END IF;
 next_paid:=inv.amount_paid_pence+p_amount;
 IF next_paid>inv.amount_pence THEN RAISE EXCEPTION 'Payment exceeds outstanding amount'; END IF;
 INSERT INTO club.payment_receipts(invoice_id,provider,provider_payment_id,amount_pence,currency)
 VALUES(p_invoice,'stripe',p_provider_payment_id,p_amount,p_currency);
 UPDATE club.renewal_invoices SET amount_paid_pence=next_paid,
 state=CASE WHEN next_paid=amount_pence THEN 'paid' ELSE 'part_paid' END,
 settled_at=CASE WHEN next_paid=amount_pence THEN clock_timestamp() ELSE NULL END
 WHERE id=p_invoice;
 RETURN 'applied';
END $$;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='club_payment_processor') THEN
  CREATE ROLE club_payment_processor NOLOGIN;
 END IF;
END $$;
GRANT USAGE ON SCHEMA club TO club_payment_processor;
REVOKE EXECUTE ON FUNCTION club.apply_verified_card_payment(uuid,text,bigint,character) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION club.apply_verified_card_payment(uuid,text,bigint,character) TO club_payment_processor;
REVOKE ALL ON ALL TABLES IN SCHEMA club FROM PUBLIC,clubmgr;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA club FROM PUBLIC,clubmgr;
GRANT SELECT ON club.current_members TO clubmgr;
COMMIT;
