"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Navbar } from "@/components/outfitmatch/Navbar";
import { Hero } from "@/components/outfitmatch/Hero";
import { FeatureStrip } from "@/components/outfitmatch/FeatureStrip";
import { QuizSection } from "@/components/outfitmatch/QuizSection";
import { ResultsSection } from "@/components/outfitmatch/ResultsSection";
import { ChatSection } from "@/components/outfitmatch/ChatSection";
import { Footer } from "@/components/outfitmatch/Footer";

type View = "home" | "quiz" | "results" | "chat";

type Answers = Record<string, string | string[]>;

const STORAGE_KEY = "outfitmatch_quiz_answers";

export default function Home() {
  const [view, setView] = useState<View>("home");
  // Restore saved answers lazily on first render (client-only)
  const [answers, setAnswers] = useState<Answers>(() => {
    if (typeof window === "undefined") return {};
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      return stored ? (JSON.parse(stored) as Answers) : {};
    } catch {
      return {};
    }
  });

  const navigate = useCallback((v: View) => {
    setView(v);
    // Scroll to top of main content on view change
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, []);

  const handleQuizComplete = useCallback(
    (a: Answers) => {
      setAnswers(a);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(a));
      } catch {
        /* ignore */
      }
      navigate("results");
    },
    [navigate]
  );

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar view={view} onNavigate={navigate} />

      <main className="flex-1">
        <AnimatePresence mode="wait">
          {view === "home" && (
            <motion.div
              key="home"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
            >
              <Hero onNavigate={navigate} />
              <FeatureStrip />
              <HowItWorks onNavigate={navigate} />
            </motion.div>
          )}

          {view === "quiz" && (
            <motion.div
              key="quiz"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
            >
              <QuizSection onComplete={handleQuizComplete} />
            </motion.div>
          )}

          {view === "results" && (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
            >
              <ResultsSection
                answers={answers}
                onRetake={() => navigate("quiz")}
                onChat={() => navigate("chat")}
              />
            </motion.div>
          )}

          {view === "chat" && (
            <motion.div
              key="chat"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
            >
              <ChatSection />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <Footer />
    </div>
  );
}

/* ─── Home-only: How It Works section ─── */

function HowItWorks({ onNavigate }: { onNavigate: (v: View) => void }) {
  const steps = [
    {
      num: "01",
      title: "Làm quiz phong cách",
      desc: "5 câu hỏi về dáng người, chiều cao, dịp đi và gu thẩm mỹ. Mất khoảng 1 phút.",
      action: "Bắt đầu quiz",
      onClick: () => onNavigate("quiz"),
    },
    {
      num: "02",
      title: "Nhận outfit cá nhân hoá",
      desc: "Graph KB traversal + Qdrant retrieval + preference rerank — gợi ý 6 outfit phù hợp nhất.",
      action: "Xem ví dụ gợi ý",
      onClick: () => onNavigate("results"),
    },
    {
      num: "03",
      title: "Chat tinh chỉnh với Stylist",
      desc: "Trò chuyện streaming realtime với Qwen3-VL-8B + LoRA để chỉnh sửa outfit theo ý bạn.",
      action: "Mở chat",
      onClick: () => onNavigate("chat"),
    },
  ];

  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
      <div className="mb-10 text-center">
        <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-brand">
          Workflow
        </p>
        <h2 className="mt-1 font-display text-3xl font-bold text-ink sm:text-5xl">
          Cách OutfitMatch hoạt động
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-sm text-muted-foreground sm:text-base">
          Ba bước từ câu hỏi đến outfit hoàn chỉnh — được tối ưu cho thị trường
          Việt Nam và phong cách châu Á.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {steps.map((s, i) => (
          <motion.div
            key={s.num}
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: i * 0.1 }}
            className="group relative flex flex-col overflow-hidden rounded-2xl border border-border/60 bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:border-brand/40 hover:shadow-xl"
          >
            <span className="font-display text-5xl font-bold text-brand/15 transition-colors group-hover:text-brand/30">
              {s.num}
            </span>
            <h3 className="mt-2 font-display text-xl font-semibold text-ink">
              {s.title}
            </h3>
            <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
              {s.desc}
            </p>
            <button
              onClick={s.onClick}
              className="mt-4 flex items-center gap-1.5 text-sm font-medium text-brand transition-colors hover:text-brand-deep"
            >
              {s.action}
              <svg
                className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M3 8h10M9 4l4 4-4 4" />
              </svg>
            </button>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
