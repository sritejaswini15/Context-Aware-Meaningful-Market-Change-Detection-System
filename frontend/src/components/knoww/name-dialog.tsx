"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/primitives";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/radix";
import { WatchlistNameSchema } from "@/lib/schemas";

export function NameDialog({
  open,
  onOpenChange,
  title,
  initial = "",
  submitLabel,
  pending,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  initial?: string;
  submitLabel: string;
  pending: boolean;
  onSubmit: (name: string) => void;
}) {
  const [name, setName] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (o) {
          setName(initial);
          setError(null);
        }
      }}
    >
      <DialogContent>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            const parsed = WatchlistNameSchema.safeParse(name);
            if (!parsed.success) return setError(parsed.error.issues[0]?.message ?? "Invalid name");
            onSubmit(parsed.data);
          }}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>Group stocks the way you think about them, such as &quot;Core holdings&quot; or &quot;Semiconductors&quot;.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="wl-name">Name</Label>
            <Input id="wl-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus aria-invalid={!!error} aria-describedby={error ? "wl-err" : undefined} />
            {error && (
              <p id="wl-err" className="text-xs text-down">
                {error}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending && <Loader2 aria-hidden className="animate-spin" />}
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
