import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/router";
import NavBar from "@/components/NavBar";
import MemberPhoto from "@/components/MemberPhoto";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { Attendance, Member, MembershipPlan, Payment, Subscription } from "@/lib/types";

const FREEZE_RESUME_CANCEL: Record<string, string[]> = {
  ACTIVE: ["FROZEN", "CANCELLED"],
  FROZEN: ["ACTIVE", "CANCELLED"],
  EXPIRED: [],
  CANCELLED: [],
};

function fmtDate(s: string | null) {
  return s ? new Date(s).toLocaleDateString() : "—";
}

export default function MemberProfilePage() {
  const router = useRouter();
  const memberId = typeof router.query.id === "string" ? router.query.id : null;
  const { session, loading } = useAuth();

  const [member, setMember] = useState<Member | null>(null);
  const [plans, setPlans] = useState<MembershipPlan[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [attendance, setAttendance] = useState<Attendance[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [checkInResult, setCheckInResult] = useState<string | null>(null);

  // start-subscription form
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [newSubDueAmount, setNewSubDueAmount] = useState("0");
  const [startingSub, setStartingSub] = useState(false);

  // log-payment form
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"cash" | "card" | "upi" | "other">("cash");
  const [gatewayRef, setGatewayRef] = useState("");
  const [isDuePayment, setIsDuePayment] = useState(false);
  const [loggingPayment, setLoggingPayment] = useState(false);

  // biometric enrollment form
  const [pin, setPin] = useState("");
  const [consent, setConsent] = useState(false);
  const [savingBiometric, setSavingBiometric] = useState(false);

  const planName = (planId: string) => plans.find((p) => p.id === planId)?.name ?? planId;

  async function loadAll(token: string, id: string) {
    const [m, subs, att, plansData] = await Promise.all([
      apiFetch<Member>(`/members/${id}`, { token }),
      apiFetch<Subscription[]>(`/members/${id}/subscriptions`, { token }),
      apiFetch<Attendance[]>(`/members/${id}/attendance`, { token }),
      apiFetch<MembershipPlan[]>("/membership-plans", { token }),
    ]);
    setMember(m);
    setPin(m.biometric_ref ?? "");
    setConsent(m.biometric_consent);
    setSubscriptions(subs);
    setAttendance(att);
    setPlans(plansData);

    const current = subs[0]; // most recent, subs are already sorted desc
    if (current) {
      setPayments(await apiFetch<Payment[]>(`/subscriptions/${current.id}/payments`, { token }));
    } else {
      setPayments([]);
    }
  }

  useEffect(() => {
    if (session && memberId) {
      loadAll(session.access_token, memberId).catch((e) =>
        setError(e instanceof Error ? e.message : "Could not load member"),
      );
    }
  }, [session, memberId]);

  const current = subscriptions[0] ?? null;
  const hasActive = current?.status === "ACTIVE" || current?.status === "FROZEN";

  async function handleCheckIn() {
    if (!session || !memberId) return;
    setCheckInResult(null);
    try {
      await apiFetch("/attendance/check-in", {
        method: "POST",
        token: session.access_token,
        body: { member_id: memberId, source: "manual" },
      });
      setCheckInResult("Checked in.");
      await loadAll(session.access_token, memberId);
    } catch (err) {
      setCheckInResult(err instanceof Error ? err.message : "Check-in failed");
    }
  }

  async function handleStartSubscription(e: FormEvent) {
    e.preventDefault();
    if (!session || !memberId || !selectedPlanId) return;
    setStartingSub(true);
    setError(null);
    try {
      await apiFetch(`/members/${memberId}/subscriptions`, {
        method: "POST",
        token: session.access_token,
        body: { plan_id: selectedPlanId, due_amount: Number(newSubDueAmount) || 0 },
      });
      setSelectedPlanId("");
      setNewSubDueAmount("0");
      await loadAll(session.access_token, memberId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start subscription");
    } finally {
      setStartingSub(false);
    }
  }

  async function handleStatusChange(newStatus: string) {
    if (!session || !memberId || !current) return;
    setError(null);
    try {
      await apiFetch(`/subscriptions/${current.id}`, {
        method: "PATCH",
        token: session.access_token,
        body: { status: newStatus },
      });
      await loadAll(session.access_token, memberId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update subscription");
    }
  }

  async function handleLogPayment(e: FormEvent) {
    e.preventDefault();
    if (!session || !memberId || !current) return;
    setLoggingPayment(true);
    setError(null);
    try {
      await apiFetch(`/subscriptions/${current.id}/payments`, {
        method: "POST",
        token: session.access_token,
        body: {
          amount: Number(amount),
          method,
          gateway_ref: gatewayRef || undefined,
          status: "completed",
          is_due_payment: isDuePayment,
        },
      });
      setAmount("");
      setGatewayRef("");
      setIsDuePayment(false);
      await loadAll(session.access_token, memberId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log payment");
    } finally {
      setLoggingPayment(false);
    }
  }

  async function handleSaveBiometric(e: FormEvent) {
    e.preventDefault();
    if (!session || !memberId) return;
    setSavingBiometric(true);
    setError(null);
    try {
      await apiFetch(`/members/${memberId}`, {
        method: "PATCH",
        token: session.access_token,
        body: { biometric_ref: pin || null, biometric_consent: pin ? consent : undefined },
      });
      await loadAll(session.access_token, memberId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save biometric enrollment");
    } finally {
      setSavingBiometric(false);
    }
  }

  if (loading || !session || !memberId) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  if (error && !member) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <p className="text-red-600 text-sm max-w-sm text-center">{error}</p>
      </main>
    );
  }

  if (!member) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  return (
    <>
      <NavBar />
      <main className="max-w-2xl mx-auto p-6 flex flex-col gap-6">
        <div className="flex items-center gap-4">
          <MemberPhoto path={member.photo_url} size={64} />
          <div className="flex-1">
            <h1 className="text-xl font-semibold">{member.name}</h1>
            <p className="text-sm opacity-70">{member.phone || "—"} · {member.email || "—"}</p>
          </div>
          <button
            onClick={handleCheckIn}
            className="rounded bg-foreground text-background px-3 py-1.5 text-sm"
          >
            Check in
          </button>
        </div>
        {checkInResult && <p className="text-sm">{checkInResult}</p>}
        {error && <p className="text-red-600 text-sm">{error}</p>}

        <section className="border rounded p-4 flex flex-col gap-3">
          <h2 className="font-semibold">Biometric enrollment</h2>
          <p className="text-sm opacity-70">
            Enroll the member&rsquo;s face on the terminal itself first (its keypad/screen assigns a PIN), then
            enter that same PIN here.
          </p>
          <form onSubmit={handleSaveBiometric} className="flex flex-wrap gap-3 items-end">
            <label className="flex flex-col gap-1 text-sm">
              Device PIN
              <input
                className="border rounded px-3 py-2 w-32"
                value={pin}
                onChange={(e) => setPin(e.target.value)}
                placeholder="e.g. 1001"
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                disabled={!pin}
              />
              Member has consented to biometric check-in
            </label>
            <button
              type="submit"
              disabled={savingBiometric || (!!pin && !consent)}
              className="rounded bg-foreground text-background px-3 py-1.5 text-sm disabled:opacity-50"
            >
              {savingBiometric ? "Saving…" : "Save"}
            </button>
          </form>
          {member.biometric_consent_at && (
            <p className="text-xs opacity-60">
              Consent recorded {new Date(member.biometric_consent_at).toLocaleString()}
            </p>
          )}
        </section>

        <section className="border rounded p-4 flex flex-col gap-3">
          <h2 className="font-semibold">Subscription</h2>
          {current ? (
            <>
              <p className="text-sm">
                <strong>{planName(current.plan_id)}</strong> — {current.status}
                <br />
                {current.end_date
                  ? `ends ${fmtDate(current.end_date)}`
                  : current.sessions_remaining !== null
                    ? `${current.sessions_remaining} sessions remaining`
                    : ""}
                {current.due_amount > 0 && (
                  <>
                    {" · "}
                    <span className="text-amber-600 font-medium">₹{current.due_amount} due</span>
                  </>
                )}
              </p>
              <div className="flex gap-2">
                {(FREEZE_RESUME_CANCEL[current.status] ?? []).map((next) => (
                  <button
                    key={next}
                    onClick={() => handleStatusChange(next)}
                    className="rounded border px-3 py-1.5 text-sm"
                  >
                    {next === "FROZEN" ? "Freeze" : next === "ACTIVE" ? "Resume" : "Cancel"}
                  </button>
                ))}
              </div>

              <h3 className="font-medium text-sm mt-2">Log a payment</h3>
              <form onSubmit={handleLogPayment} className="flex flex-wrap gap-2 items-end">
                <label className="flex flex-col gap-1 text-sm">
                  Amount
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    className="border rounded px-2 py-1 w-28"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    required
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  Method
                  <select
                    className="border rounded px-2 py-1"
                    value={method}
                    onChange={(e) => setMethod(e.target.value as typeof method)}
                  >
                    <option value="cash">Cash</option>
                    <option value="card">Card</option>
                    <option value="upi">UPI</option>
                    <option value="other">Other</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  Reference (optional)
                  <input
                    className="border rounded px-2 py-1"
                    value={gatewayRef}
                    onChange={(e) => setGatewayRef(e.target.value)}
                  />
                </label>
                {current.due_amount > 0 && (
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={isDuePayment}
                      onChange={(e) => setIsDuePayment(e.target.checked)}
                    />
                    Paying down the due balance
                  </label>
                )}
                <button
                  type="submit"
                  disabled={loggingPayment}
                  className="rounded bg-foreground text-background px-3 py-1.5 text-sm disabled:opacity-50"
                >
                  {loggingPayment ? "Saving…" : "Log payment"}
                </button>
              </form>

              {payments.length > 0 && (
                <ul className="text-sm divide-y border rounded mt-1">
                  {payments.map((p) => (
                    <li key={p.id} className="p-2 flex justify-between">
                      <span>₹{p.amount} · {p.method}{p.gateway_ref ? ` · ${p.gateway_ref}` : ""}</span>
                      <span className="opacity-70">{p.status}</span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="text-sm opacity-70">No subscription yet.</p>
          )}

          {!hasActive && (
            <form onSubmit={handleStartSubscription} className="flex gap-2 items-end mt-2">
              <label className="flex flex-col gap-1 text-sm flex-1">
                Start a subscription
                <select
                  className="border rounded px-2 py-1"
                  value={selectedPlanId}
                  onChange={(e) => setSelectedPlanId(e.target.value)}
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
              <label className="flex flex-col gap-1 text-sm">
                Due amount
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  className="border rounded px-2 py-1 w-28"
                  value={newSubDueAmount}
                  onChange={(e) => setNewSubDueAmount(e.target.value)}
                />
              </label>
              <button
                type="submit"
                disabled={startingSub || !selectedPlanId}
                className="rounded bg-foreground text-background px-3 py-1.5 text-sm disabled:opacity-50"
              >
                {startingSub ? "Starting…" : "Start"}
              </button>
            </form>
          )}
        </section>

        <section className="border rounded p-4">
          <h2 className="font-semibold mb-2">Attendance history</h2>
          <ul className="text-sm divide-y">
            {attendance.map((a) => (
              <li key={a.id} className="py-1.5 flex justify-between">
                <span>{new Date(a.checked_in_at).toLocaleString()}</span>
                <span className="opacity-70">{a.source}</span>
              </li>
            ))}
            {attendance.length === 0 && <li className="py-1.5 opacity-70">No check-ins yet.</li>}
          </ul>
        </section>
      </main>
    </>
  );
}
