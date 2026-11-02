# Club Manager — payment provider decision register
Status: evaluation only; no live payment authority.

## Providers under consideration
- QuickBooks Payments UK (existing accounting workflow; confirm current UK contract and webhook/API access).
- Stripe Checkout (hosted checkout, verified events; existing simulated schema refers to Stripe only).
- PayPal Checkout / Advanced Credit and Debit Card Payments (different tariffs; merchant approval required).
- SumUp online checkout / payment links, plus optional in-person card terminal (online and card-present tariffs differ).

## Evaluation criteria
1. Eligibility for the sailing club's legal form (including unincorporated association if applicable).
2. Published domestic UK debit/credit card, wallet, international card, FX and refund/dispute charges; VAT treatment and payout schedules.
3. Hosted checkout and secure Joomla member portal linking; accessibility and guest payments.
4. Independent server-side confirmation of paid status; webhook validation and provider-side retrieval; idempotent receipt settlement.
5. QuickBooks Online reconciliation, accounting for gross receipts, processing fees, refunds and net payouts.
6. Ability to issue individual or household renewal invoices, membership + yard/mooring charges, reminders and payment receipts.
7. Clubhouse card-present payments and whether they can use the same merchant account.
8. Total annual processing cost evaluated on the club's expected membership/payment mix.
9. Provider data-processing terms, incident handling, secure credential storage and operational simplicity.

## Design decision
Build a provider-neutral payment_attempt, provider_transaction and webhook reconciliation interface, not a hard-coded Stripe-only API.
No live payment acceptance, merchant account creation, PCI card storage or real-member data in the development CT101.
Current migration 008 is a Stripe-specific **simulation** and is not approved as a general-purpose live settlement service.
Required before live use: narrow payment processor role, independently verified provider webhook plus API state, matching amount/currency/invoice, atomic duplicate checks, refunds, chargebacks, payout reconciliation, independent audit, and negative tests.

## Indicative published UK fees (checked November 2026; verify contracted terms)
- QuickBooks Payments UK: 1.2% + £0.20 + VAT for standard UK card (per existing research).
- Stripe Checkout standard UK domestic card: 1.5% + £0.20.
- PayPal standard commercial payment: 2.9% + £0.30; eligible advanced card pricing: 1.2% + £0.20.
- SumUp payment links: 2.50% online; separate 1.69% standard card-present fee.
Sources: https://www.paypal.com/uk/business/paypal-business-fees ; https://www.sumup.com/en-gb/payment-links/ ; https://help.sumup.com/api/hc/articles/115008338687-Pricing-and-Fees .
No provider selection or price guarantee implied.
