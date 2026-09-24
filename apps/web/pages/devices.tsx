import { useEffect, useState, type FormEvent } from "react";
import Layout from "@/components/Layout";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { Device } from "@/lib/types";

function fmtLastSeen(s: string | null) {
  return s ? new Date(s).toLocaleString() : "never";
}

export default function DevicesPage() {
  const { session, loading } = useAuth();
  const [devices, setDevices] = useState<Device[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [serialNumber, setSerialNumber] = useState("");
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadDevices(token: string) {
    setDevices(await apiFetch<Device[]>("/devices", { token }));
  }

  useEffect(() => {
    if (session) loadDevices(session.access_token).catch((e) => setError(String(e)));
  }, [session]);

  async function handleRegister(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch("/devices", {
        method: "POST",
        token: session.access_token,
        body: { serial_number: serialNumber, label },
      });
      setSerialNumber("");
      setLabel("");
      setShowForm(false);
      await loadDevices(session.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not register device");
    } finally {
      setSaving(false);
    }
  }

  async function toggleStatus(device: Device) {
    if (!session) return;
    await apiFetch(`/devices/${device.id}`, {
      method: "PATCH",
      token: session.access_token,
      body: { status: device.status === "active" ? "inactive" : "active" },
    });
    await loadDevices(session.access_token);
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
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">Devices</h1>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded bg-foreground text-background px-3 py-1.5 text-sm"
          >
            {showForm ? "Cancel" : "Register device"}
          </button>
        </div>
        <p className="text-sm opacity-70">
          Single-branch phase — every device is auto-assigned to your one branch, no branch picker needed yet.
        </p>

        {showForm && (
          <form onSubmit={handleRegister} className="flex flex-col gap-3 border rounded p-4">
            <label className="flex flex-col gap-1 text-sm">
              Serial number
              <input
                className="border rounded px-3 py-2"
                value={serialNumber}
                onChange={(e) => setSerialNumber(e.target.value)}
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Label
              <input
                className="border rounded px-3 py-2"
                placeholder="e.g. Front desk terminal"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                required
              />
            </label>
            {error && <p className="text-red-600 text-sm">{error}</p>}
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-foreground text-background py-2 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Register"}
            </button>
          </form>
        )}

        <ul className="flex flex-col divide-y border rounded">
          {devices.map((d) => (
            <li key={d.id} className="flex items-center gap-3 p-3">
              <span
                title={d.online ? "Seen in the last 10 minutes" : "Not seen recently — check power/network"}
                className={`w-2.5 h-2.5 rounded-full shrink-0 ${d.online ? "bg-green-500" : "bg-red-500"}`}
              />
              <div className="flex flex-col flex-1">
                <span className={`font-medium ${d.status === "inactive" ? "line-through opacity-50" : ""}`}>
                  {d.label || d.serial_number}
                </span>
                <span className="text-sm opacity-70">
                  {d.serial_number} · {d.vendor} · last seen {fmtLastSeen(d.last_seen_at)}
                </span>
              </div>
              <button onClick={() => toggleStatus(d)} className="text-sm underline">
                {d.status === "active" ? "Deactivate" : "Activate"}
              </button>
            </li>
          ))}
          {devices.length === 0 && <li className="p-3 text-sm opacity-70">No devices registered yet.</li>}
        </ul>
      </div>
    </Layout>
  );
}
