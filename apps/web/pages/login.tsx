import { useState, type FormEvent } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { supabase } from "@/lib/supabaseClient";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setWorking(true);
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    setWorking(false);
    if (signInError) {
      setError(signInError.message);
      return;
    }
    router.push("/");
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <form onSubmit={handleSubmit} className="w-full max-w-sm flex flex-col gap-4">
        <h1 className="text-xl font-semibold">Log in</h1>
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
          />
        </label>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={working}
          className="rounded bg-foreground text-background py-2 disabled:opacity-50"
        >
          {working ? "Logging in…" : "Log in"}
        </button>
        <Link className="text-sm underline text-center" href="/signup">
          Need an account? Sign up
        </Link>
      </form>
    </main>
  );
}
