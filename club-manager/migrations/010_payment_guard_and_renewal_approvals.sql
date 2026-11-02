BEGIN;
-- A gateway-specific transaction must never settle an invoice merely because an event was received.
CREATE OR REPLACE FUNCTION club.validate_payment_attempt(p_attempt uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE a record; i record;
BEGIN
 SELECT * INTO a FROM club.payment_attempts WHERE id=p_attempt;
 IF NOT FOUND THEN RAISE EXCEPTION 'Unknown checkout attempt'; END IF;
 SELECT * INTO i FROM club.renewal_invoices WHERE id=a.invoice_id;
 IF NOT FOUND OR i.state NOT IN ('issued','part_paid') THEN
   RAISE EXCEPTION 'Invoice is not payable';
 END IF;
 IF a.currency<>'GBP' OR a.requested_pence<>(i.amount_pence-i.amount_paid_pence)
 THEN RAISE EXCEPTION 'Amount or currency mismatch'; END IF;
 RETURN true;
END $$;
-- Service permission is intentionally NOT assigned until independent provider verification exists.
REVOKE EXECUTE ON FUNCTION club.validate_payment_attempt(uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION club.validate_payment_attempt(uuid) FROM clubmgr;
-- Renewal approvals must be independent of the officer requesting distribution.
CREATE TABLE IF NOT EXISTS club.renewal_approvals (
 campaign_id uuid PRIMARY KEY REFERENCES club.renewal_campaigns(id),
 requested_by text NOT NULL,
 approved_by text NOT NULL,
 approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(requested_by <> approved_by)
);
REVOKE ALL ON club.renewal_approvals FROM PUBLIC,clubmgr;
COMMIT;
