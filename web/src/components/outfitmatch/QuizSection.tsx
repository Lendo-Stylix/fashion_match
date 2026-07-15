"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Loader2,
  RefreshCw,
  Sparkles,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  fetchQuiz,
  type QuizQuestion,
  type QuizResponse,
} from "@/lib/api";

type Answers = Record<string, string | string[]>;

export function QuizSection({
  onComplete,
}: {
  onComplete: (answers: Answers) => void;
}) {
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const [source, setSource] = useState<"backend" | "mock" | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Answers>({});

  // Fetch quiz on mount (inline to satisfy react-hooks/set-state-in-effect)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data, source } = await fetchQuiz();
        if (cancelled) return;
        setQuiz(data);
        setSource(source);
        setLoading(false);
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const retry = () => {
    setLoading(true);
    setError(false);
    (async () => {
      const { data, source } = await fetchQuiz();
      setQuiz(data);
      setSource(source);
      setLoading(false);
    })();
  };

  const questions = quiz?.questions ?? [];
  const current = questions[step];
  const isLast = step === questions.length - 1;
  const progress = questions.length ? ((step + 1) / questions.length) * 100 : 0;

  const isMulti = current?.type === "multi_select";
  const currentAnswer = current ? answers[current.key] : undefined;
  const canProceed = isMulti
    ? Array.isArray(currentAnswer) && currentAnswer.length > 0
    : !!currentAnswer;

  const handleSelect = (key: string, optId: string, multi: boolean) => {
    setAnswers((prev) => {
      if (multi) {
        const cur = (Array.isArray(prev[key]) ? prev[key] : []) as string[];
        const next = cur.includes(optId)
          ? cur.filter((x) => x !== optId)
          : [...cur, optId];
        return { ...prev, [key]: next };
      }
      return { ...prev, [key]: optId };
    });
  };

  const next = () => {
    if (isLast) {
      onComplete(answers);
    } else {
      setStep((s) => s + 1);
    }
  };
  const prev = () => setStep((s) => Math.max(0, s - 1));

  if (loading) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center justify-center px-4 py-32">
        <Loader2 className="h-8 w-8 animate-spin text-brand" />
        <p className="mt-4 text-sm text-muted-foreground">
          Đang tải câu hỏi phong cách…
        </p>
      </div>
    );
  }

  if (error || !quiz) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center justify-center px-4 py-32 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="mt-4 font-medium text-ink">
          Không thể tải câu hỏi từ server.
        </p>
        <Button onClick={load} className="mt-4 gap-2">
          <RefreshCw className="h-4 w-4" />
          Thử lại
        </Button>
      </div>
    );
  }

  return (
    <section className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-brand">
            Onboarding
          </p>
          <h2 className="mt-1 font-display text-3xl font-bold text-ink sm:text-4xl">
            Quiz phong cách
          </h2>
        </div>
        {source && (
          <Badge
            variant="outline"
            className={`gap-1.5 border-border/60 ${
              source === "backend"
                ? "bg-chart-3/10 text-chart-3"
                : "bg-secondary/60 text-muted-foreground"
            }`}
          >
            <span className="flex h-1.5 w-1.5 rounded-full bg-current" />
            {source === "backend" ? "Backend Live" : "Demo Mode"}
          </Badge>
        )}
      </div>

      {/* Progress */}
      <div className="mb-8 space-y-2">
        <div className="flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          <span>
            Câu {step + 1} / {questions.length}
          </span>
          <span>{Math.round(progress)}%</span>
        </div>
        <Progress
          value={progress}
          className="h-1.5 bg-secondary [&>div]:bg-brand"
        />
      </div>

      {/* Question */}
      <AnimatePresence mode="wait">
        <motion.div
          key={current?.key}
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -24 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="space-y-6"
        >
          <div>
            <h3 className="font-display text-2xl font-semibold text-ink sm:text-3xl">
              {current?.label_vi}
            </h3>
            {current?.hint_vi && (
              <p className="mt-2 text-sm text-muted-foreground">
                {current.hint_vi}
              </p>
            )}
            {isMulti && (
              <p className="mt-1 text-[11px] font-medium uppercase tracking-wider text-brand">
                Có thể chọn nhiều
              </p>
            )}
          </div>

          {/* Options */}
          <div className="grid gap-2.5 sm:grid-cols-2">
            {current?.options.map((opt) => {
              const selected = isMulti
                ? Array.isArray(currentAnswer) && currentAnswer.includes(opt.id)
                : currentAnswer === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() =>
                    handleSelect(current.key, opt.id, isMulti)
                  }
                  className={`group relative flex items-start gap-3 rounded-lg border p-4 text-left transition-all duration-200 ${
                    selected
                      ? "border-brand bg-brand-soft/50 shadow-sm"
                      : "border-border bg-card hover:border-brand/40 hover:bg-secondary/40"
                  }`}
                >
                  <div
                    className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-all ${
                      selected
                        ? "border-brand bg-brand text-brand-foreground"
                        : "border-border text-transparent group-hover:border-brand/40"
                    }`}
                  >
                    {isMulti ? (
                      <Check className="h-3 w-3" />
                    ) : (
                      <span className="h-2 w-2 rounded-full bg-current" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-ink">{opt.label_vi}</p>
                    {opt.description_vi && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {opt.description_vi}
                      </p>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </motion.div>
      </AnimatePresence>

      {/* Navigation */}
      <div className="mt-10 flex items-center justify-between">
        <Button
          variant="ghost"
          onClick={prev}
          disabled={step === 0}
          className="gap-1.5 text-muted-foreground hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" />
          Trước
        </Button>

        <Button
          onClick={next}
          disabled={!canProceed}
          className="gap-2 bg-brand text-brand-foreground shadow-lg shadow-brand/20 hover:bg-brand-deep"
        >
          {isLast ? (
            <>
              <Sparkles className="h-4 w-4" />
              Nhận gợi ý outfit
            </>
          ) : (
            <>
              Tiếp
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </Button>
      </div>

      {/* Quick recap dots */}
      <div className="mt-6 flex items-center justify-center gap-1.5">
        {questions.map((_, i) => (
          <button
            key={i}
            onClick={() => setStep(i)}
            aria-label={`Đi tới câu ${i + 1}`}
            className={`h-1.5 rounded-full transition-all ${
              i === step
                ? "w-8 bg-brand"
                : i < step
                ? "w-1.5 bg-brand/40"
                : "w-1.5 bg-border"
            }`}
          />
        ))}
      </div>
    </section>
  );
}
