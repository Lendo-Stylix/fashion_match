"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

type Question = {
  key: string;
  label_vi: string;
  type: string;
  options: { id: string; label_vi: string }[];
};

export default function QuizPage() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const router = useRouter();

  useEffect(() => {
    fetch("http://localhost:8000/api/quiz")
      .then((r) => r.json())
      .then((data) => setQuestions(data.questions || []))
      .catch(console.error);
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
    // Store answers in localStorage and redirect to results
    localStorage.setItem("quiz_answers", JSON.stringify(answers));
    router.push("/results");
  }

  return (
    <main className="flex min-h-screen flex-col p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Onboarding Quiz</h1>

      {questions.map((q, i) => (
        <div key={q.key} className="mb-6">
          <p className="font-semibold mb-2">
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
                  onClick={() => handleSelect(q.key, opt.id, isMulti)}
                  className={`rounded px-4 py-2 border ${
                    selected
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  {opt.label_vi}
                </button>
              );
            })}
          </div>
        </div>
      ))}

      <button
        onClick={handleSubmit}
        className="mt-4 rounded bg-blue-600 px-6 py-3 text-white hover:bg-blue-700 self-start"
      >
        Get Recommendations
      </button>
    </main>
  );
}
