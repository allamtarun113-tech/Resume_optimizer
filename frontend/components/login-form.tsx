"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ExternalLinkIcon, InfoIcon, MailCheckIcon } from "lucide-react";
import { toast } from "sonner";
import { createClient } from "@/lib/supabase/client";
import { inboxLink, signUpOutcome } from "@/lib/signup";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type Mode = "signin" | "signup";
type Sent = { email: string; reason: "signed_up" | "not_confirmed" };

const RESEND_COOLDOWN_S = 60;

// Enable once the Google provider is configured in Supabase.
const GOOGLE_AUTH_ENABLED =
  process.env.NEXT_PUBLIC_ENABLE_GOOGLE_AUTH === "true";

export function LoginForm({ next }: { next: string }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState<Sent | null>(null);

  const callbackUrl = () =>
    `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    const supabase = createClient();

    if (mode === "signin") {
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      setLoading(false);
      if (error?.code === "email_not_confirmed") {
        // Signed up but never clicked the link: show how to confirm (and resend).
        return setSent({ email, reason: "not_confirmed" });
      }
      if (error) return toast.error(error.message);
      router.push(next);
      router.refresh();
    } else {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: callbackUrl() },
      });
      setLoading(false);
      if (error) return toast.error(error.message);
      const outcome = signUpOutcome(data);
      if (outcome === "signed_in") {
        router.push(next);
        router.refresh();
      } else if (outcome === "already_exists") {
        toast.error("User already exists. Sign in instead.");
        setMode("signin");
        setPassword("");
      } else {
        toast.success("Check your inbox to confirm your email address.", {
          duration: 10_000,
        });
        setSent({ email, reason: "signed_up" });
      }
    }
  }

  if (sent) {
    return (
      <ConfirmEmailCard
        sent={sent}
        onBack={() => {
          setSent(null);
          setMode("signin");
          setPassword("");
        }}
      />
    );
  }

  async function handleGoogle() {
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: callbackUrl() },
    });
    if (error) toast.error(error.message);
  }

  return (
    <Card className="w-full max-w-sm shadow-xl shadow-primary/5">
      <CardHeader>
        <CardTitle className="text-2xl font-semibold tracking-tight">
          {mode === "signin" ? "Welcome back" : "Create your account"}
        </CardTitle>
        <CardDescription>
          {mode === "signin"
            ? "Sign in to see your analyses."
            : "Free to use with your own OpenAI key."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete={
                mode === "signin" ? "current-password" : "new-password"
              }
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {mode === "signup" && (
            <p className="flex gap-2 rounded-lg bg-primary/5 p-3 text-xs text-muted-foreground">
              <InfoIcon className="mt-0.5 size-3.5 shrink-0 text-primary" />
              We&apos;ll email you a confirmation link. You need to click it
              before you can sign in.
            </p>
          )}
          <Button type="submit" size="lg" disabled={loading}>
            {loading
              ? "Please wait…"
              : mode === "signin"
                ? "Sign in"
                : "Sign up"}
          </Button>
        </form>
        {GOOGLE_AUTH_ENABLED && (
          <Button variant="outline" onClick={handleGoogle}>
            Continue with Google
          </Button>
        )}
        <button
          type="button"
          className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
        >
          {mode === "signin"
            ? "No account? Sign up"
            : "Already have an account? Sign in"}
        </button>
      </CardContent>
    </Card>
  );
}

function ConfirmEmailCard({
  sent,
  onBack,
}: {
  sent: Sent;
  onBack: () => void;
}) {
  const inbox = inboxLink(sent.email);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function resend() {
    setCooldown(RESEND_COOLDOWN_S);
    const { error } = await createClient().auth.resend({
      type: "signup",
      email: sent.email,
    });
    if (error) {
      setCooldown(0);
      toast.error(error.message);
    } else {
      toast.success(`Sent another confirmation link to ${sent.email}.`);
    }
  }

  return (
    <Card
      className="w-full max-w-sm shadow-xl shadow-primary/5"
      role="alertdialog"
      aria-labelledby="confirm-email-title"
    >
      <CardHeader>
        <span className="mb-2 flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <MailCheckIcon className="size-5" />
        </span>
        <CardTitle
          id="confirm-email-title"
          className="text-2xl font-semibold tracking-tight"
        >
          {sent.reason === "signed_up"
            ? "Confirm your email"
            : "Confirm your email first"}
        </CardTitle>
        <CardDescription>
          {sent.reason === "signed_up"
            ? "Your account is almost ready. "
            : "Your account isn't confirmed yet. "}
          We sent a confirmation link to <strong>{sent.email}</strong>.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <ol className="flex list-decimal flex-col gap-1.5 pl-5 text-muted-foreground">
          <li>Open your inbox for {sent.email}.</li>
          <li>
            Find the email from Resume Optimizer. It can take a minute; check
            Spam or Promotions too.
          </li>
          <li>
            Click <em>Confirm email address</em>. You&apos;ll be signed in (it
            works on any device).
          </li>
        </ol>
        {inbox && (
          <Button
            nativeButton={false}
            render={
              <a href={inbox.url} target="_blank" rel="noopener noreferrer" />
            }
          >
            Open {inbox.name}
            <ExternalLinkIcon />
          </Button>
        )}
        <Button variant="outline" onClick={resend} disabled={cooldown > 0}>
          {cooldown > 0
            ? `Resend available in ${cooldown}s`
            : "Resend confirmation email"}
        </Button>
        <Button variant="ghost" onClick={onBack}>
          Back to sign in
        </Button>
      </CardContent>
    </Card>
  );
}
