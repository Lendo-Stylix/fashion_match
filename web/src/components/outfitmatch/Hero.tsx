"use client";

import { motion } from "framer-motion";
import { ArrowRight, MessageCircle, Sparkles, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";

type View = "home" | "quiz" | "results" | "chat";

export function Hero({ onNavigate }: { onNavigate: (v: View) => void }) {
  return (
    <section className="relative overflow-hidden">
      {/* Background texture + glow */}
      <div className="paper-texture absolute inset-0 -z-10" />
      <div className="absolute -top-32 right-0 -z-10 h-[480px] w-[480px] rounded-full bg-brand/10 blur-3xl" />
      <div className="absolute -bottom-40 -left-20 -z-10 h-[380px] w-[380px] rounded-full bg-chart-3/10 blur-3xl" />

      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-28">
        <div className="grid items-center gap-12 lg:grid-cols-[1.1fr_0.9fr]">
          {/* Left — copy */}
          <div>
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="mb-5 inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand-soft/40 px-3 py-1.5"
            >
              <span className="flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-1.5 w-1.5 animate-ping rounded-full bg-brand opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-brand" />
              </span>
              <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-brand-deep">
                Powered by Qwen3-VL-8B · LoRA
              </span>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.05 }}
              className="font-display text-5xl font-bold leading-[1.05] tracking-tight text-ink sm:text-6xl lg:text-7xl"
            >
              Phối đồ{" "}
              <span className="relative inline-block">
                <span className="italic text-brand">thông minh</span>
                <svg
                  className="absolute -bottom-1 left-0 w-full text-brand/40"
                  height="6"
                  viewBox="0 0 200 6"
                  preserveAspectRatio="none"
                  aria-hidden
                >
                  <path
                    d="M0,3 Q50,0 100,3 T200,3"
                    stroke="currentColor"
                    strokeWidth="2"
                    fill="none"
                  />
                </svg>
              </span>{" "}
              theo dáng &amp; dịp
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.15 }}
              className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg"
            >
              OutfitMatch là AI Stylist cá nhân hoá cho thị trường Việt Nam —
              trả lời 5 câu hỏi, nhận outfit phù hợp dáng người, dịp đi và gu
              phong cách. Tích hợp graph KB 5,618 sản phẩm, retrieval Qdrant và
              chat streaming theo thời gian thực.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.25 }}
              className="mt-8 flex flex-wrap gap-3"
            >
              <Button
                size="lg"
                className="gap-2 bg-brand text-brand-foreground shadow-lg shadow-brand/20 hover:bg-brand-deep"
                onClick={() => onNavigate("quiz")}
              >
                Làm quiz phong cách
                <ArrowRight className="h-4 w-4" />
              </Button>
              <Button
                size="lg"
                variant="outline"
                className="gap-2 border-border bg-background/60 backdrop-blur-sm hover:bg-secondary/60"
                onClick={() => onNavigate("chat")}
              >
                <MessageCircle className="h-4 w-4" />
                Chat với Stylist
              </Button>
            </motion.div>

            {/* Stats strip */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="mt-10 grid max-w-md grid-cols-3 gap-4 border-t border-border/60 pt-6"
            >
              {[
                { v: "5,618", l: "Sản phẩm" },
                { v: "316K+", l: "Outfit edges" },
                { v: "98%", l: "FITB Recall@5" },
              ].map((s) => (
                <div key={s.l}>
                  <p className="font-display text-2xl font-bold text-ink">
                    {s.v}
                  </p>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
                    {s.l}
                  </p>
                </div>
              ))}
            </motion.div>
          </div>

          {/* Right — editorial collage */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="relative hidden aspect-[4/5] lg:block"
          >
            <EditorialCollage />
          </motion.div>
        </div>

        {/* Bottom marquee */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.5 }}
          className="mt-16 flex items-center gap-4 border-t border-border/40 pt-6"
        >
          <p className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            <Sparkles className="h-3 w-3 text-brand" />
            Đối tác
          </p>
          <div className="relative flex-1 overflow-hidden">
            <div className="flex w-max animate-marquee gap-8 pr-8">
              {[...PARTNERS, ...PARTNERS].map((p, i) => (
                <span
                  key={i}
                  className="whitespace-nowrap font-display text-lg font-semibold text-ink/40"
                >
                  {p}
                </span>
              ))}
            </div>
          </div>
          <p className="hidden items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground sm:flex">
            <TrendingUp className="h-3 w-3 text-chart-3" />
            v3.1-lite
          </p>
        </motion.div>
      </div>
    </section>
  );
}

const PARTNERS = [
  "YODY",
  "Coolmate",
  "Routine",
  "Oven",
  "Levents",
  "Maris.",
  "IVY Moda",
  "Canifa",
];

function EditorialCollage() {
  return (
    <div className="relative h-full w-full">
      {/* Magazine cover plate */}
      <motion.div
        animate={{ y: [0, -6, 0] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
        className="absolute left-0 top-8 aspect-[3/4] w-[58%] overflow-hidden rounded-sm shadow-2xl"
        style={{
          background:
            "linear-gradient(150deg, oklch(0.55 0.165 38) 0%, oklch(0.38 0.12 32) 100%)",
        }}
      >
        <div className="flex h-full flex-col justify-between p-5">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-[0.3em] text-brand-foreground/70">
              Editorial №01
            </p>
            <p className="mt-1 font-display text-2xl font-bold italic leading-tight text-brand-foreground">
              Autumn
              <br />
              Collection
            </p>
          </div>
          <div>
            <div className="h-px w-full bg-brand-foreground/30" />
            <p className="mt-2 text-[10px] uppercase tracking-[0.18em] text-brand-foreground/70">
              OutfitMatch · 2026
            </p>
          </div>
        </div>
      </motion.div>

      {/* Second plate */}
      <motion.div
        animate={{ y: [0, 6, 0] }}
        transition={{ duration: 7, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
        className="absolute right-0 top-0 aspect-[3/4] w-[45%] overflow-hidden rounded-sm shadow-xl"
        style={{
          background:
            "linear-gradient(135deg, oklch(0.94 0.035 55) 0%, oklch(0.88 0.04 50) 100%)",
        }}
      >
        <div className="flex h-full flex-col justify-end p-4">
          <p className="font-display text-xl font-bold text-brand-deep">
            Get the look
          </p>
          <p className="mt-1 text-[11px] text-brand-deep/70">
            Outfit #002 · Date Night
          </p>
        </div>
      </motion.div>

      {/* Third plate */}
      <motion.div
        animate={{ y: [0, -4, 0] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: 1 }}
        className="absolute bottom-0 right-4 aspect-square w-[40%] overflow-hidden rounded-sm shadow-lg"
        style={{
          background:
            "linear-gradient(160deg, oklch(0.50 0.08 140) 0%, oklch(0.40 0.06 145) 100%)",
        }}
      >
        <div className="flex h-full items-end p-3">
          <p className="font-mono text-[10px] uppercase tracking-wider text-white/80">
            #003 · Street Cool
          </p>
        </div>
      </motion.div>

      {/* Floating score badge */}
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.8 }}
        className="absolute -left-3 bottom-12 z-10 flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 shadow-lg"
      >
        <span className="flex h-1.5 w-1.5 rounded-full bg-chart-3" />
        <span className="text-[11px] font-medium text-ink">
          96% match · Office
        </span>
      </motion.div>
    </div>
  );
}
