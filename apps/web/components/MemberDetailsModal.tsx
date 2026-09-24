import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import MemberPhoto from "./MemberPhoto";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { Member, MembershipPlan, Payment, Subscription, TransactionType } from "@/lib/types";

type View = "details" | "early-renew" | "edit" | "history";

const TYPE_LABEL: Record<TransactionType, string> = {
  admission: "Admission",
  renewal: "Renewal",
  due_payment: "Due Payment",
};

function shortId(id: string) {
  return id.slice(0, 8).toUpperCase();
}

function digitsOnly(phone: string) {
  return phone.replace(/\D/g, "");
}

function daysLeft(endDate: string): number {
  const ms = new Date(endDate).getTime() - new Date().setHours(0, 0, 0, 0);
  return Math.ceil(ms / 86_400_000);
}

export default function MemberDetailsModal({
  memberId,
  onClose,
  onChanged,
}: {
  memberId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { session } = useAuth();
  const [view, setView] = useState<View>("details");
  const [member, setMember] = useState<Member | null>(null);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [plans, setPlans] = useState<MembershipPlan[]>([]);
  const [transactions, setTransactions] = useState<Payment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const current = subscriptions[0] ?? null;
  const activePlans = plans.filter((p) => p.is_active);
  const planName = (planId: string) => plans.find((p) => p.id === planId)?.name ?? planId;

  async function load() {
    if (!session) return;
    const token = session.access_token;
    const [m, subs, plansData, txns] = await Promise.all([
      apiFetch<Member>(`/members/${memberId}`, { token }),
      apiFetch<Subscription[]>(`/members/${memberId}/subscriptions`, { token }),
      apiFetch<MembershipPlan[]>("/membership-plans?include_inactive=true", { token }),
      apiFetch<Payment[]>(`/members/${memberId}/transactions`, { token }),
    ]);
    setMember(m);
    setSubscriptions(subs);
    setPlans(plansData);
    setTransactions(txns);
  }

  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : "Could not load member"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memberId, session]);

  async function refresh() {
    await load();
    onChanged();
  }

  async function handleTogglePause() {
    if (!session || !current) return;
    setBusy(true);
    setError(null);
    try {
      const nextStatus = current.status === "ACTIVE" ? "FROZEN" : "ACTIVE";
      await apiFetch(`/subscriptions/${current.id}`, {
        method: "PATCH",
        token: session.access_token,
        body: { status: nextStatus },
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update subscription");
    } finally {
      setBusy(false);
    }
  }

  if (error && !member) {
    return (
      <ModalShell onClose={onClose}>
        <p className="text-red-600 text-sm">{error}</p>
      </ModalShell>
    );
  }

  if (!member) {
    return (
      <ModalShell onClose={onClose}>
        <p>Loading…</p>
      </ModalShell>
    );
  }

  return (
    <ModalShell onClose={onClose}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <MemberPhoto path={member.photo_url} name={member.name} size={56} />
        <div className="flex-1">
          <h2 className="text-lg font-semibold text-gray-900">{member.name}</h2>
          <p className="text-xs text-gray-500">#{shortId(member.id)}</p>
        </div>
        {member.phone && (
          <div className="flex gap-2">
            <a
              href={`tel:${member.phone}`}
              title="Call"
              className="w-8 h-8 rounded-full border flex items-center justify-center hover:bg-gray-50"
            >
              📞
            </a>
            <a
              href={`sms:${member.phone}`}
              title="Message"
              className="w-8 h-8 rounded-full border flex items-center justify-center hover:bg-gray-50"
            >
              💬
            </a>
            <a
              href={`https://wa.me/${digitsOnly(member.phone)}`}
              target="_blank"
              rel="noopener noreferrer"
              title="WhatsApp"
              className="w-8 h-8 rounded-full border border-emerald-600 text-emerald-700 flex items-center justify-center hover:bg-emerald-50"
            >
              🟢
            </a>
          </div>
        )}
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {view === "details" && (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-gray-200 p-3">
            {current ? (
              <>
                <p className="font-medium text-gray-900">{planName(current.plan_id)}</p>
                <p className="text-sm text-gray-500">
                  {current.start_date} → {current.end_date ?? "—"}
                </p>
                <p className="text-sm text-gray-500">
                  {current.end_date
                    ? `${daysLeft(current.end_date)} days left`
                    : current.sessions_remaining !== null
                      ? `${current.sessions_remaining} sessions left`
                      : ""}
                  {current.due_amount > 0 && (
                    <span className="text-amber-600 font-medium"> · ₹{current.due_amount} due</span>
                  )}
                </p>
              </>
            ) : (
              <p className="text-sm text-gray-500">No active plan</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setView("early-renew")}
              className="rounded border px-3 py-2 text-sm text-left hover:bg-gray-50"
            >
              🔁 Early Renew
            </button>
            <button
              onClick={() => setView("edit")}
              disabled={!current}
              className="rounded border px-3 py-2 text-sm text-left hover:bg-gray-50 disabled:opacity-40"
            >
              ✏️ Edit Membership
            </button>
            <button
              onClick={handleTogglePause}
              disabled={busy || !current || (current.status !== "ACTIVE" && current.status !== "FROZEN")}
              className="rounded border px-3 py-2 text-sm text-left hover:bg-gray-50 disabled:opacity-40"
            >
              {current?.status === "FROZEN" ? "▶️ Resume Membership" : "⏸️ Pause Membership"}
            </button>
            <button
              onClick={() => setView("history")}
              className="rounded border px-3 py-2 text-sm text-left hover:bg-gray-50"
            >
              🧾 Transaction History
            </button>
          </div>

          <Link href={`/members/${member.id}`} className="text-sm underline text-emerald-700 text-center">
            View full profile (attendance, biometric enrollment)
          </Link>
        </div>
      )}

      {view === "early-renew" && (
        <EarlyRenewForm
          memberId={member.id}
          current={current}
          plans={activePlans}
          onCancel={() => setView("details")}
          onDone={async () => {
            await refresh();
            setView("details");
          }}
        />
      )}

      {view === "edit" && current && (
        <EditMembershipForm
          subscription={current}
          plans={activePlans}
          onCancel={() => setView("details")}
          onDone={async () => {
            await refresh();
            setView("details");
          }}
        />
      )}

      {view === "history" && (
        <div className="flex flex-col gap-3">
          <button onClick={() => setView("details")} className="text-sm underline self-start">
            ← Back
          </button>
          <div className="overflow-x-auto border rounded">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-left">
                  <th className="p-2">Date</th>
                  <th className="p-2">Type</th>
                  <th className="p-2">Amount</th>
                  <th className="p-2">Method</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id} className="border-t">
                    <td className="p-2 text-gray-500 whitespace-nowrap">
                      {new Date(t.created_at).toLocaleDateString()}
                    </td>
                    <td className="p-2">{TYPE_LABEL[t.transaction_type]}</td>
                    <td className="p-2">₹{t.amount}</td>
                    <td className="p-2">{t.method}</td>
                  </tr>
                ))}
                {transactions.length === 0 && (
                  <tr>
                    <td colSpan={4} className="p-3 text-center text-gray-400">
                      No transactions yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </ModalShell>
  );
}

function ModalShell({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={onClose} className="float-right text-gray-400 hover:text-gray-700 -mt-2 -mr-2">
          ✕
        </button>
        {children}
      </div>
    </div>
  );
}

function EarlyRenewForm({
  memberId,
  current,
  plans,
  onCancel,
  onDone,
}: {
  memberId: string;
  current: Subscription | null;
  plans: MembershipPlan[];
  onCancel: () => void;
  onDone: () => void;
}) {
  const { session } = useAuth();
  const [planId, setPlanId] = useState("");
  const [amountPaid, setAmountPaid] = useState("");
  const [discount, setDiscount] = useState("0");
  const [method, setMethod] = useState<"cash" | "card" | "upi" | "other">("cash");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedPlan = plans.find((p) => p.id === planId) ?? null;

  function selectPlan(id: string) {
    setPlanId(id);
    const p = plans.find((pl) => pl.id === id);
    setAmountPaid(p ? String(p.price) : "");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!session || !selectedPlan) return;
    setSaving(true);
    setError(null);
    try {
      // Not-yet-expired current subscription -> cancel it and carry the
      // remaining time forward by starting the new one from its end_date.
      // Already expired/cancelled (or none) -> start today.
      const notYetExpired =
        current &&
        (current.status === "ACTIVE" || current.status === "FROZEN") &&
        (!current.end_date || new Date(current.end_date) >= new Date(new Date().setHours(0, 0, 0, 0)));

      let startDate: string | undefined;
      if (notYetExpired) {
        await apiFetch(`/subscriptions/${current!.id}`, {
          method: "PATCH",
          token: session.access_token,
          body: { status: "CANCELLED" },
        });
        startDate = current!.end_date ?? undefined;
      }

      const paid = Number(amountPaid) || 0;
      const dueAmount = Math.max(0, selectedPlan.price - paid);

      const newSub = await apiFetch<Subscription>(`/members/${memberId}/subscriptions`, {
        method: "POST",
        token: session.access_token,
        body: { plan_id: selectedPlan.id, start_date: startDate, due_amount: dueAmount },
      });

      if (paid > 0) {
        await apiFetch(`/subscriptions/${newSub.id}/payments`, {
          method: "POST",
          token: session.access_token,
          body: { amount: paid, method, discount_amount: Number(discount) || 0 },
        });
      }

      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not renew");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <button type="button" onClick={onCancel} className="text-sm underline self-start">
        ← Back
      </button>
      <label className="flex flex-col gap-1 text-sm">
        Plan
        <select
          className="border rounded px-2 py-1.5"
          value={planId}
          onChange={(e) => selectPlan(e.target.value)}
          required
        >
          <option value="" disabled>
            Choose a plan…
          </option>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} — ₹{p.price}
            </option>
          ))}
        </select>
      </label>
      {selectedPlan && (
        <p className="text-xs text-gray-500">
          {selectedPlan.session_limit ? `${selectedPlan.session_limit} sessions` : `${selectedPlan.duration_days} days`}{" "}
          · ₹{selectedPlan.price}
        </p>
      )}
      <label className="flex flex-col gap-1 text-sm">
        Amount paid now
        <input
          type="number"
          min={0}
          step="0.01"
          className="border rounded px-2 py-1.5"
          value={amountPaid}
          onChange={(e) => setAmountPaid(e.target.value)}
          required
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Discount
        <input
          type="number"
          min={0}
          step="0.01"
          className="border rounded px-2 py-1.5"
          value={discount}
          onChange={(e) => setDiscount(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Payment method
        <select
          className="border rounded px-2 py-1.5"
          value={method}
          onChange={(e) => setMethod(e.target.value as typeof method)}
        >
          <option value="cash">Cash</option>
          <option value="card">Card</option>
          <option value="upi">UPI</option>
          <option value="other">Other</option>
        </select>
      </label>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <button
        type="submit"
        disabled={saving || !selectedPlan}
        className="rounded bg-emerald-600 text-white py-2 text-sm disabled:opacity-50"
      >
        {saving ? "Saving…" : "Confirm renewal"}
      </button>
    </form>
  );
}

function EditMembershipForm({
  subscription,
  plans,
  onCancel,
  onDone,
}: {
  subscription: Subscription;
  plans: MembershipPlan[];
  onCancel: () => void;
  onDone: () => void;
}) {
  const { session } = useAuth();
  const [planId, setPlanId] = useState(subscription.plan_id);
  const [startDate, setStartDate] = useState(subscription.start_date);
  const [endDate, setEndDate] = useState(subscription.end_date ?? "");
  const [dueAmount, setDueAmount] = useState(String(subscription.due_amount));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`/subscriptions/${subscription.id}`, {
        method: "PATCH",
        token: session.access_token,
        body: {
          plan_id: planId !== subscription.plan_id ? planId : undefined,
          start_date: startDate !== subscription.start_date ? startDate : undefined,
          end_date: endDate !== (subscription.end_date ?? "") ? endDate || null : undefined,
          due_amount: Number(dueAmount) !== subscription.due_amount ? Number(dueAmount) : undefined,
        },
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update membership");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <button type="button" onClick={onCancel} className="text-sm underline self-start">
        ← Back
      </button>
      <p className="text-xs text-gray-500">For correcting mistakes — not the normal renewal flow.</p>
      <label className="flex flex-col gap-1 text-sm">
        Plan
        <select className="border rounded px-2 py-1.5" value={planId} onChange={(e) => setPlanId(e.target.value)}>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Start date
        <input
          type="date"
          className="border rounded px-2 py-1.5"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        End date
        <input
          type="date"
          className="border rounded px-2 py-1.5"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Due amount
        <input
          type="number"
          min={0}
          step="0.01"
          className="border rounded px-2 py-1.5"
          value={dueAmount}
          onChange={(e) => setDueAmount(e.target.value)}
        />
      </label>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <button type="submit" disabled={saving} className="rounded bg-emerald-600 text-white py-2 text-sm disabled:opacity-50">
        {saving ? "Saving…" : "Save changes"}
      </button>
    </form>
  );
}
