"use client";

import { useState, useEffect } from "react";

type Outfit = {
  outfit_id: string;
  explanation_vi: string;
  price_total_vnd: number;
  items: { item_id: string; category: string; title_vi: string; price_vnd: number; store_name: string; product_url: string; image_path: string }[];
};

export default function ResultsPage() {
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("quiz_answers");
    if (!stored) {
      setLoading(false);
      return;
    }
    const answers = JSON.parse(stored);

    fetch("http://localhost:8000/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        occasion: answers.occasions?.[0] || "daily",
        quiz_answers: answers,
      }),
    })
      .then((r) => r.json())
      .then((data) => {
        setOutfits(data.outfits || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p>Loading recommendations...</p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col p-8">
      <h1 className="text-2xl font-bold mb-6">Your Outfits</h1>
      {outfits.length === 0 ? (
        <p>No outfits found. Try completing the quiz first.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {outfits.map((outfit) => (
            <div key={outfit.outfit_id} className="border rounded p-4 shadow">
              <p className="font-bold text-lg mb-2">
                {outfit.outfit_id}
              </p>
              <p className="text-sm text-gray-600 mb-2">
                {outfit.explanation_vi}
              </p>
              <p className="text-sm font-semibold mb-1">
                Total: {outfit.price_total_vnd.toLocaleString()} VND
              </p>
              <div className="mt-2 space-y-1">
                {outfit.items.map((item) => (
                  <div key={item.item_id} className="text-xs border-t pt-1">
                    <p className="font-medium">
                      {item.category}: {item.title_vi}
                    </p>
                    <p className="text-gray-500">
                      {item.store_name} — {item.price_vnd.toLocaleString()} VND
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
