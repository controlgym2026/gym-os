-- Gym OS — home dashboard + finance report (GymOps parity, phase 1)
--
-- Additive only, per the spec — no existing column touched.

-- ---------------------------------------------------------------------------
-- payment: + transaction_type, + discount_amount
-- ---------------------------------------------------------------------------
create type public.payment_transaction_type as enum ('admission', 'renewal', 'due_payment');

alter table public.payment add column transaction_type public.payment_transaction_type;
alter table public.payment add column discount_amount numeric(12, 2) not null default 0;

-- Backfill (best-effort — see the Phase report for exactly how this was
-- classified and why it's an approximation, not ground truth): per member,
-- order ALL their payments across every subscription by created_at; the
-- earliest -> 'admission', every other payment -> 'renewal'. No historical
-- payment is backfilled as 'due_payment' — nothing in the existing data
-- distinguishes "a fresh payment" from "paying down a due balance", so that
-- classification only starts applying to payments logged from here on.
-- Wrapped in a DO block — the migration runner appears to split the file on
-- bare semicolons, which breaks a plain "WITH ranked AS (...) UPDATE ...
-- FROM ranked" into two statements ("relation ranked does not exist").
-- $$-quoting keeps this whole thing as one token no naive splitter touches.
do $$
begin
  with ranked as (
    select p.id,
           row_number() over (partition by s.member_id order by p.created_at asc) as rn
    from public.payment p
    join public.subscription s on s.id = p.subscription_id
  )
  update public.payment p
  set transaction_type = (case when ranked.rn = 1 then 'admission' else 'renewal' end)::public.payment_transaction_type
  from ranked
  where ranked.id = p.id;
end $$;

-- Belt-and-suspenders: any row the join above somehow missed (shouldn't
-- happen — subscription_id is NOT NULL with a FK) still gets a value before
-- the NOT NULL below.
update public.payment set transaction_type = 'renewal' where transaction_type is null;

alter table public.payment alter column transaction_type set not null;

-- ---------------------------------------------------------------------------
-- subscription: + due_amount (money still owed on that subscription)
-- ---------------------------------------------------------------------------
alter table public.subscription add column due_amount numeric(12, 2) not null default 0;
alter table public.subscription add constraint subscription_due_amount_check check (due_amount >= 0);
