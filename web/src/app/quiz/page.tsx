"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";

type Question = {
  key: string;
  label_vi: string;
  type: string;
  options: { id: string; label_vi: string }[];
};

export default function QuizPage() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [error, setError] = useState(false);
  const router = useRouter();

  const loadQuiz = () => {
    setError(false);
    fetch(`${API_URL}/api/quiz`)
      .then((r) => r.json())
      .then((data) => setQuestions(data.questions || []))
      .catch(() => setError(true));
  };

  useEffect(() => {
    loadQuiz();
  }, []);

  function handleSelect(key: string, optionId: string, isMulti: boolean) {
    if (isMulti) {
      setAnswers((prev) => {
        const current = prev[key] || [];
        const updated = current.includes(optionId)
          ? current.filter((id: string) => id !== optionId)
          : [...current, optionId];
        return { ...prev, [key]: updated };
      });
    } else {
      setAnswers((prev) => ({ ...prev, [key]: optionId }));
    }
  }

  function handleSubmit() {
    localStorage.setItem("quiz_answers", JSON.stringify(answers));
    router.push("/results");
  }

  return (
    <main className="flex min-h-screen flex-col p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6 text-ink">Onboarding Quiz</h1>

      {error ? (
        <div
          role="alert"
          className="rounded-lg border border-border bg-brand-soft p-4 text-ink mb-6"
        >
          <p className="font-medium mb-2">Không thể tải câu hỏi từ server.</p>
          <button
            onClick={loadQuiz}
            className="rounded-lg bg-brand px-4 py-2 text-brand-ink font-medium hover:opacity-90 transition-opacity"
          >
            Thử lại
          </button>
        </div>
      ) : (
        questions.map((q, i) => (
          <div key={q.key} className="mb-6">
            <p className="font-semibold mb-2 text-ink">
              {i + 1}. {q.label_vi}
            </p>
            <div className="flex flex-wrap gap-2">
              {q.options.map((opt) => {
                const isMulti = q.type === "multi_select";
                const selected = isMulti
                  ? (answers[q.key] || []).includes(opt.id)
                  : answers[q.key] === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => handleSelect(q.key, opt.id, isMulti)}
                    className={`rounded-lg px-4 py-2 border text-sm transition-colors ${
                      selected
                        ? "bg-brand text-brand-ink border-brand"
                        : "bg-surface text-ink border-border hover:bg-brand-soft"
                    }`}
                  >
                    {opt.label_vi}
                  </button>
                );
              })}
            </div>
          </div>
        ))
      )}

      {!error && questions.length > 0 && (
        <button
          type="button"
          onClick={handleSubmit}
          className="mt-4 rounded-lg bg-brand px-6 py-3 text-brand-ink font-medium self-start hover:opacity-90 transition-opacity"
        >
          Get Recommendations
        </button>
      )}
    </main>
  );
}
