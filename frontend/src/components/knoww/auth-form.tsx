"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { qk } from "@/lib/hooks";
import { AuthResultSchema, CredentialsSchema } from "@/lib/schemas";
import type { z } from "zod";

type AuthResult = z.infer<typeof AuthResultSchema>;

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  async function finish(res: AuthResult) {
    qc.clear();
    const next = params.get("next");
    router.replace(res.user && !res.user.onboarded ? "/onboarding" : next && next.startsWith("/") ? next : "/");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErrors({});
    if (confirming) {
      setPending(true);
      try {
        await api("/auth/confirm", { method: "POST", body: { email, code } });
        const res = await api<AuthResult>("/auth/login", { method: "POST", body: { email, password }, schema: AuthResultSchema });
        await finish(res);
      } catch (err) {
        setErrors({ form: err instanceof ApiError ? err.message : "Confirmation failed" });
      } finally {
        setPending(false);
      }
      return;
    }
    const parsed = CredentialsSchema.safeParse({ email, password });
    if (!parsed.success) {
      const fe: Record<string, string> = {};
      for (const i of parsed.error.issues) fe[String(i.path[0])] = i.message;
      if (mode === "login" && fe.password && password.length > 0) delete fe.password;
      if (Object.keys(fe).length) return setErrors(fe);
    }
    setPending(true);
    try {
      const res = await api<AuthResult>(mode === "login" ? "/auth/login" : "/auth/signup", {
        method: "POST",
        body: mode === "login" ? { email, password } : { email, password, display_name: name || undefined },
        schema: AuthResultSchema,
      });
      if (res.status === "CONFIRMATION_REQUIRED") {
        setConfirming(true);
        return;
      }
      qc.setQueryData(qk.me, res.user);
      await finish(res);
    } catch (err) {
      setErrors({ form: err instanceof ApiError ? err.message : "Something went wrong. Please retry." });
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{confirming ? "Check your email" : mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p className="text-sm text-muted-foreground">
          {confirming
            ? `We sent a confirmation code to ${email}.`
            : mode === "login"
              ? "Sign in to see what changed since you last checked."
              : "Start monitoring what matters in under a minute."}
        </p>
      </div>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {confirming ? (
          <div className="space-y-1.5">
            <Label htmlFor="code">Confirmation code</Label>
            <Input id="code" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required />
          </div>
        ) : (
          <>
            {mode === "signup" && (
              <div className="space-y-1.5">
                <Label htmlFor="name">Name (optional)</Label>
                <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? "email-err" : undefined}
                required
              />
              {errors.email && (
                <p id="email-err" className="text-xs text-down">
                  {errors.email}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? "pw-err" : undefined}
                required
              />
              {errors.password && (
                <p id="pw-err" className="text-xs text-down">
                  {errors.password}
                </p>
              )}
            </div>
          </>
        )}
        {errors.form && (
          <p role="alert" className="rounded-md bg-down/10 px-3 py-2 text-sm text-down">
            {errors.form}
          </p>
        )}
        <Button type="submit" className="w-full" size="lg" disabled={pending}>
          {pending && <Loader2 aria-hidden className="animate-spin" />}
          {confirming ? "Confirm and continue" : mode === "login" ? "Sign in" : "Create account"}
        </Button>
      </form>
      {!confirming && (
        <p className="text-center text-sm text-muted-foreground">
          {mode === "login" ? (
            <>
              New to Knoww?{" "}
              <Link href="/signup" className="font-medium text-foreground underline-offset-4 hover:underline">
                Create an account
              </Link>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <Link href="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
                Sign in
              </Link>
            </>
          )}
        </p>
      )}
    </div>
  );
}
