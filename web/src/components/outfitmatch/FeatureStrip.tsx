"use client";

import { motion } from "framer-motion";
import { Brain, Network, Layers, UserCheck } from "lucide-react";

const FEATURES = [
  {
    icon: Layers,
    title: "Graph KB Builder",
    desc: "5,618 sản phẩm catalogue → 316,559 item-compat edges. Tagging tự động bằng Qwen3-VL-8B.",
    tag: "Tầng 1",
    accent: "var(--brand)",
  },
  {
    icon: Brain,
    title: "AI Stylist Qwen3-VL",
    desc: "Qwen3-VL-8B + LoRA adapter, fine-tune trên dataset grounded Việt Nam. Streaming SSE realtime.",
    tag: "Tầng 2",
    accent: "oklch(0.62 0.16 38)",
  },
  {
    icon: Network,
    title: "Retrieval Graph-First",
    desc: "Qdrant seed filter + graph traversal + post-filter. FITB Recall@5 đạt 0.98 trên benchmark.",
    tag: "Tầng 3",
    accent: "oklch(0.50 0.08 140)",
  },
  {
    icon: UserCheck,
    title: "Personalization",
    desc: "Quiz 5 câu → preference rerank + size suggestion theo dáng người và chiều cao.",
    tag: "Tầng 4",
    accent: "oklch(0.45 0.12 320)",
  },
];

export function FeatureStrip() {
  return (
    <section className="border-y border-border/40 bg-secondary/30">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8 lg:py-16">
        <div className="mb-8 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-brand">
              Kiến trúc 4 tầng
            </p>
            <h2 className="mt-1 font-display text-3xl font-bold text-ink sm:text-4xl">
              Pipeline cá nhân hoá
            </h2>
          </div>
          <p className="max-w-md text-sm text-muted-foreground">
            Từ catalogue thô đến outfit hoàn chỉnh — mỗi tầng tối ưu cho một
            khía cạnh riêng của bài toán phối đồ Việt Nam.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f, i) => {
            const Icon = f.icon;
            return (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
                className="group relative overflow-hidden rounded-xl border border-border/60 bg-card p-5 transition-all duration-300 hover:-translate-y-1 hover:border-brand/40 hover:shadow-lg"
              >
                <div
                  className="absolute inset-x-0 top-0 h-0.5 origin-left scale-x-0 transition-transform duration-500 group-hover:scale-x-100"
                  style={{ background: f.accent }}
                />
                <div className="mb-4 flex items-center justify-between">
                  <div
                    className="flex h-10 w-10 items-center justify-center rounded-lg"
                    style={{ background: `${f.accent}1a` }}
                  >
                    <Icon className="h-5 w-5" style={{ color: f.accent }} />
                  </div>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {f.tag}
                  </span>
                </div>
                <h3 className="mb-2 font-display text-lg font-semibold text-ink">
                  {f.title}
                </h3>
                <p className="text-[13px] leading-relaxed text-muted-foreground">
                  {f.desc}
                </p>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
