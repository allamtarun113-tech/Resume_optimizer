import { createClient } from "@/lib/supabase/server";
import { Dashboard } from "@/components/home/dashboard";
import { Landing } from "@/components/home/landing";

export default async function Home() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const email = data?.claims?.email as string | undefined;
  return email ? <Dashboard email={email} /> : <Landing />;
}
