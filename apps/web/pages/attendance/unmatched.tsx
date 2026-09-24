import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { AttendanceUnmatched, Device, Member } from "@/lib/types";

function fmt(s: string) {
  return new Date(s).toLocaleString();
}

export default function UnmatchedAttendancePage() {
  const { session, loading } = useAuth();
  const [rows, setRows] = useState<AttendanceUnmatched[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [selectedMember, setSelectedMember] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    const token = session.access_token;
    Promise.all([
      apiFetch<AttendanceUnmatched[]>("/attendance/unmatched", { token }),
      apiFetch<Device[]>("/devices", { token }),
      apiFetch<Member[]>("/members", { token }),
    ])
      .then(([r, d, m]) => {
        setRows(r);
        setDevices(d);
        setMembers(m);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load"));
  }, [session]);

  const deviceLabel = useMemo(() => {
    const map = new Map(devices.map((d) => [d.id, d.label || d.serial_number]));
    return (id: string) => map.get(id) ?? id;
  }, [devices]);

  const memberName = useMemo(() => {
    const map = new Map(members.map((m) => [m.id, m.name]));
    return (id: string) => map.get(id) ?? id;
  }, [members]);

  const visible = rows.filter((r) => !dismissed.has(r.id));
  const unmatchedPins = visible.filter((r) => r.reason === "unmatched_pin");
  const rejected = visible.filter((r) => r.reason !== "unmatched_pin");

  function dismiss(id: string) {
    setDismissed((prev) => new Set(prev).add(id));
  }

  async function handleEnroll(row: AttendanceUnmatched) {
    const memberId = selectedMember[row.id];
    if (!session || !memberId) return;
    setBusyId(row.id);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/members/${memberId}`, {
        method: "PATCH",
        token: session.access_token,
        body: { biometric_ref: row.raw_pin, biometric_consent: true },
      });
      setNotice(`PIN ${row.raw_pin} assigned to ${memberName(memberId)}.`);
      dismiss(row.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign PIN");
    } finally {
      setBusyId(null);
    }
  }

  if (loading || !session) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold">Unmatched attendance</h1>
          <p className="text-sm opacity-70">
            Biometric pushes that couldn&rsquo;t be logged automatically. Dismissing a row here only hides it in
            this browser — the underlying record isn&rsquo;t deleted.
          </p>
        </div>

        {error && <p className="text-red-600 text-sm">{error}</p>}
        {notice && <p className="text-green-600 text-sm">{notice}</p>}

        <section className="flex flex-col gap-2">
          <h2 className="font-semibold">Unrecognized PINs ({unmatchedPins.length})</h2>
          <p className="text-sm opacity-70">
            A device pushed a check-in for a PIN that doesn&rsquo;t match any member — likely a typo during
            enrollment, or the member hasn&rsquo;t been enrolled in Gym OS yet.
          </p>
          <ul className="flex flex-col divide-y border rounded">
            {unmatchedPins.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center gap-2 p-3">
                <div className="flex flex-col text-sm flex-1 min-w-[10rem]">
                  <span className="font-medium">PIN {row.raw_pin}</span>
                  <span className="opacity-70">
                    {deviceLabel(row.device_id)} · {row.raw_timestamp} · received {fmt(row.received_at)}
                  </span>
                </div>
                <select
                  className="border rounded px-2 py-1 text-sm"
                  value={selectedMember[row.id] ?? ""}
                  onChange={(e) => setSelectedMember((prev) => ({ ...prev, [row.id]: e.target.value }))}
                >
                  <option value="" disabled>
                    Assign to member…
                  </option>
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => handleEnroll(row)}
                  disabled={!selectedMember[row.id] || busyId === row.id}
                  className="rounded bg-foreground text-background px-3 py-1.5 text-sm disabled:opacity-50"
                >
                  {busyId === row.id ? "…" : "Enroll"}
                </button>
                <button onClick={() => dismiss(row.id)} className="text-sm underline opacity-70">
                  Dismiss
                </button>
              </li>
            ))}
            {unmatchedPins.length === 0 && <li className="p-3 text-sm opacity-70">None.</li>}
          </ul>
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="font-semibold">Rejected check-ins ({rejected.length})</h2>
          <p className="text-sm opacity-70">
            The PIN matched a member, but their check-in was denied (e.g. no active subscription) — there was no
            staff at the terminal to see the error, so it landed here instead.
          </p>
          <ul className="flex flex-col divide-y border rounded">
            {rejected.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center gap-2 p-3">
                <div className="flex flex-col text-sm flex-1 min-w-[10rem]">
                  <span className="font-medium">
                    {row.member_id ? (
                      <Link href={`/members/${row.member_id}`} className="underline">
                        {memberName(row.member_id)}
                      </Link>
                    ) : (
                      "Unknown member"
                    )}
                  </span>
                  <span className="opacity-70">
                    {row.reason} · {deviceLabel(row.device_id)} · {row.raw_timestamp}
                  </span>
                </div>
                <button onClick={() => dismiss(row.id)} className="text-sm underline opacity-70">
                  Dismiss
                </button>
              </li>
            ))}
            {rejected.length === 0 && <li className="p-3 text-sm opacity-70">None.</li>}
          </ul>
        </section>
      </div>
    </Layout>
  );
}
