"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import { Activity, Bell, Eye, LayoutDashboard, List, LogOut, Moon, Search, Settings, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/radix";
import { DemoButton } from "@/components/knoww/demo";
import { StockSearch } from "@/components/knoww/search";
import { api, ApiError } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useMe, useNotifications, useReadNotification } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Command Center", short: "Home", icon: LayoutDashboard },
  { href: "/watchlists", label: "Watchlists", short: "Lists", icon: List },
  { href: "/changes", label: "Changes", short: "Changes", icon: Eye },
  { href: "/system", label: "System health", short: "System", icon: Activity },
  { href: "/settings", label: "Settings", short: "Settings", icon: Settings },
];

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <span aria-hidden className="grid size-7 place-items-center rounded-lg bg-primary text-[13px] font-bold text-primary-foreground">K</span>
      <span>knoww</span>
    </span>
  );
}

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const dark = mounted && resolvedTheme === "dark";
  return (
    <Button variant="ghost" size="icon" aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} onClick={() => setTheme(dark ? "light" : "dark")}>
      {dark ? <Sun aria-hidden /> : <Moon aria-hidden />}
    </Button>
  );
}

function Notifications() {
  const { data } = useNotifications();
  const read = useReadNotification();
  const router = useRouter();
  const unread = data?.unread ?? 0;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
          <Bell aria-hidden />
          {unread > 0 && (
            <span className="num absolute -right-0.5 -top-0.5 grid min-w-4 place-items-center rounded-full bg-high px-1 text-[10px] font-semibold text-white">{unread}</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-80">
        <div className="flex items-center justify-between px-2 py-1.5">
          <DropdownMenuLabel className="p-0">Notifications</DropdownMenuLabel>
          {unread > 0 && (
            <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={() => read.mutate("all")}>
              Mark all read
            </button>
          )}
        </div>
        <DropdownMenuSeparator />
        {!data?.items.length && <p className="px-2 py-6 text-center text-xs text-muted-foreground">Knoww only notifies you about meaningful changes. Nothing yet.</p>}
        {data?.items.slice(0, 8).map((n) => (
          <DropdownMenuItem
            key={n.id}
            className="flex-col items-start gap-0.5"
            onSelect={() => {
              if (!n.read_at) read.mutate(n.id);
              if (n.symbol) router.push(`/stocks/${n.symbol}`);
            }}
          >
            <span className={cn("text-sm", !n.read_at && "font-semibold")}>{n.title}</span>
            <span className="line-clamp-2 text-xs text-muted-foreground">{n.body}</span>
            <span className="text-[11px] text-muted-foreground">{timeAgo(n.created_at)}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const { data: me, error, isLoading } = useMe();
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [error, pathname, router]);
  useEffect(() => {
    if (me && !me.onboarded) router.replace("/onboarding");
  }, [me, router]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function signOut() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    qc.clear();
    router.replace("/login");
  }

  if (isLoading || !me || !me.onboarded) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 p-6" aria-busy>
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[232px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-dvh flex-col border-r bg-card/50 px-3 py-5 lg:flex">
        <Link href="/" className="px-2">
          <Logo />
        </Link>
        <p className="mt-1 px-2 text-xs text-muted-foreground">Know what matters.</p>
        <nav aria-label="Main" className="mt-6 flex flex-col gap-0.5">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={isActive(pathname, n.href) ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                isActive(pathname, n.href) && "bg-accent font-medium text-foreground",
              )}
            >
              <n.icon aria-hidden className="size-4" />
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-2 px-2 text-xs text-muted-foreground">
          <p>Knoww highlights changes worth investigating. It does not give buy or sell advice.</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur sm:px-6">
          <Link href="/" className="lg:hidden">
            <Logo />
          </Link>
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className="ml-auto flex h-9 items-center gap-2 rounded-md border bg-card px-3 text-sm text-muted-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring lg:ml-0 lg:w-80"
            aria-label="Search stocks"
          >
            <Search aria-hidden className="size-4" />
            <span className="hidden sm:inline">Search stocks</span>
            <kbd className="ml-auto hidden rounded border bg-muted px-1.5 text-[10px] font-medium lg:inline">Ctrl K</kbd>
          </button>
          <div className="flex items-center gap-1 lg:ml-auto">
            <DemoButton />
            <Notifications />
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Account menu">
                  <span className="grid size-7 place-items-center rounded-full bg-secondary text-xs font-semibold uppercase">{(me.display_name ?? me.email)[0]}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuLabel>
                  <span className="block text-foreground">{me.display_name ?? "Your account"}</span>
                  <span className="block font-normal">{me.email}</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => router.push("/settings")}>
                  <Settings aria-hidden /> Settings
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={signOut}>
                  <LogOut aria-hidden /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 pt-6 sm:px-6 lg:pb-10">
          {children}
        </main>
      </div>

      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t bg-background/95 backdrop-blur lg:hidden">
        {NAV.filter((n) => n.href !== "/system").map((n) => (
          <Link
            key={n.href}
            href={n.href}
            aria-current={isActive(pathname, n.href) ? "page" : undefined}
            className={cn("flex flex-col items-center gap-0.5 py-2.5 text-[11px] text-muted-foreground", isActive(pathname, n.href) && "text-foreground")}
          >
            <n.icon aria-hidden className="size-5" />
            {n.short}
          </Link>
        ))}
      </nav>
      <StockSearch open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  );
}
