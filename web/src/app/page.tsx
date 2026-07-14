import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <h1 className="text-4xl font-bold mb-4">OutfitMatch</h1>
      <p className="text-xl mb-8">Body & Occasion-Aware Fashion Recommender</p>
      <div className="flex gap-4">
        <Link
          href="/chat"
          className="rounded bg-blue-600 px-6 py-3 text-white hover:bg-blue-700"
        >
          Chat with Stylist
        </Link>
        <Link
          href="/quiz"
          className="rounded bg-purple-600 px-6 py-3 text-white hover:bg-purple-700"
        >
          Onboarding Quiz
        </Link>
      </div>
    </main>
  );
}
