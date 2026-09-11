import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  // Fail loudly at load time rather than with a cryptic fetch error the
  // first time a page calls supabase.auth.* — see apps/web/.env.example.
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set (see apps/web/.env.example)",
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
