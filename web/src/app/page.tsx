import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 md:p-24">
      <h1 className="text-4xl font-bold mb-4 text-ink">OutfitMatch</h1>
      <p className="text-xl mb-8 text-muted">
        Body &amp; Occasion-Aware Fashion Recommender
      </p>
      <div className="flex flex-wrap justify-center gap-4">
        <Link
          href="/chat"
          className="rounded-lg bg-brand px-6 py-3 text-brand-ink font-medium hover:opacity-90 transition-opacity"
        >
          Chat with Stylist
        </Link>
        <Link
          href="/quiz"
          className="rounded-lg border border-border bg-surface px-6 py-3 text-ink font-medium hover:bg-brand-soft transition-colors"
        >
          Onboarding Quiz
        </Link>
      </div>
    </main>
  );
}
