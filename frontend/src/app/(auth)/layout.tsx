import { Logo } from "@/components/knoww/shell";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <div className="hidden flex-col justify-between border-r bg-card p-10 lg:flex">
        <Logo />
        <div className="max-w-md space-y-6">
          <p className="text-3xl font-semibold leading-tight tracking-tight">Not every change is meaningful. Knoww shows you the ones that are.</p>
          <ul className="space-y-3 text-sm text-muted-foreground">
            <li>Remembers what you last saw, and measures every move from there.</li>
            <li>Separates stock-specific moves from sector and market noise.</li>
            <li>Explains why it matters, and says when the data can&apos;t be trusted.</li>
          </ul>
        </div>
        <p className="text-xs text-muted-foreground">Knoww is a market-awareness tool. It does not provide investment advice.</p>
      </div>
      <main className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-6">
          <div className="lg:hidden">
            <Logo />
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
