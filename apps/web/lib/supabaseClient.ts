import { createClient } from "@supabase/supabase-js";

// Env values pasted into a hosting dashboard easily pick up a trailing newline,
// a line wrap or an invisible character (zero-width space, BOM). The anon key
// ends up in request headers, where any of those makes the browser's fetch
// throw "Invalid value" — so keep only the characters a JWT can contain.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.replace(/[^A-Za-z0-9._-]/g, "");

if (!supabaseUrl || !supabaseAnonKey) {
  // Fail loudly at load time rather than with a cryptic fetch error the
  // first time a page calls supabase.auth.* — see apps/web/.env.example.
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set (see apps/web/.env.example)",
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
