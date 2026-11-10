import { createClient } from "@supabase/supabase-js";

// Frontend använder Supabase bara för inloggning (ADR 0002). All data hämtas
// via backend-API:et, aldrig direkt från databasen.
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
);
