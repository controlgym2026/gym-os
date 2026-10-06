-- Gym OS — Phase 6 finance parity, part 1: new income transaction types.
--
-- Split into its own migration/transaction on purpose: Postgres won't let
-- ALTER TYPE ... ADD VALUE and anything that USES the new value (an insert,
-- a cast in a CHECK constraint, etc.) run in the same transaction — see the
-- 20260924142811 migration's notes on the same enum for the precedent. Part
-- 2 (20261006090001) does the rest of this phase's schema work and must run
-- after this one has actually committed.

alter type public.payment_transaction_type add value 'pt';
alter type public.payment_transaction_type add value 'service';
alter type public.payment_transaction_type add value 'product';
