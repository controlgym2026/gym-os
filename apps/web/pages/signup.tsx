import { useState, type FormEvent } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { supabase } from "@/lib/supabaseClient";
import { apiFetch } from "@/lib/api";

// Read by index.tsx after email-confirmation + first login, when bootstrap
// couldn't happen immediately after signUp() below.
const PENDING_GYM_NAME_KEY = "gym-os:pending-gym-name";

export default function Signup() {
  const router = useRouter();
  const [gymName, setGymName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "working" | "check-email">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setStatus("working");

    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      // Without this, Supabase falls back to the project's dashboard-configured
      // Site URL (Authentication -> URL Configuration) for the confirmation
      // link's redirect_to — which defaults to http://localhost:3000 and is
      // the same regardless of which environment the user actually signed up
      // from. window.location.origin makes it follow the real environment
      // (localhost in dev, the real deployed origin in prod) instead.
      options: { emailRedirectTo: window.location.origin },
    });

    if (signUpError) {
      setError(signUpError.message);
      setStatus("idle");
      return;
    }

    if (data.session) {
      // Email confirmation is off (or already satisfied) — bootstrap now.
      try {
        await apiFetch("/auth/bootstrap-tenant", {
          method: "POST",
          token: data.session.access_token,
          body: { gym_name: gymName },
        });
        router.push("/");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not create your gym");
        setStatus("idle");
      }
      return;
    }

    // Email confirmation required — bootstrap happens on first login (index.tsx).
    try {
      window.localStorage.setItem(PENDING_GYM_NAME_KEY, gymName);
    } catch {
      // localStorage unavailable (private mode, etc.) — non-fatal, index.tsx
      // just asks for the gym name again on first login.
    }
    setStatus("check-email");
  }

  if (status === "check-email") {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <p className="max-w-sm text-center">
          Check <strong>{email}</strong> for a confirmation link, then{" "}
          <Link className="underline" href="/login">
            log in
          </Link>
          . Your gym (&ldquo;{gymName}&rdquo;) is created on first login.
        </p>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <form onSubmit={handleSubmit} className="w-full max-w-sm flex flex-col gap-4">
        <h1 className="text-xl font-semibold">Create your gym</h1>
        <label className="flex flex-col gap-1">
          Gym name
          <input
            className="border rounded px-3 py-2"
            value={gymName}
            onChange={(e) => setGymName(e.target.value)}
            required
          />
        </label>
        <label className="flex flex-col gap-1">
          Email
          <input
            type="email"
            className="border rounded px-3 py-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label className="flex flex-col gap-1">
          Password
          <input
            type="password"
            className="border rounded px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
        </label>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={status === "working"}
          className="rounded bg-foreground text-background py-2 disabled:opacity-50"
        >
          {status === "working" ? "Creating…" : "Sign up"}
        </button>
        <Link className="text-sm underline text-center" href="/login">
          Already have an account? Log in
        </Link>
      </form>
    </main>
  );
}
