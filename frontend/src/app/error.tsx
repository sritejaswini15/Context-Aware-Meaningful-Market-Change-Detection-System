"use client";

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center">
      <h1 className="text-xl font-semibold">Something went wrong.</h1>
      <p className="max-w-sm text-sm text-muted-foreground">Knoww hit an unexpected error while rendering this page. Your data is safe.</p>
      <button type="button" onClick={reset} className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
        Try again
      </button>
    </main>
  );
}
