import { createClient } from "@supabase/supabase-js";

// Env values pasted into a hosting dashboard easily pick up a trailing newline
// or a line wrap. The anon key ends up in request headers, where any
// whitespace makes the browser's fetch throw "Invalid value" — so strip it
// (a JWT never contains whitespace).
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.replace(/\s+/g, "");

if (!supabaseUrl || !supabaseAnonKey) {
  // Fail loudly at load time rather than with a cryptic fetch error the
  // first time a page calls supabase.auth.* — see apps/web/.env.example.
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set (see apps/web/.env.example)",
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
