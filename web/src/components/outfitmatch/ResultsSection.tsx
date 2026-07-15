"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  RefreshCw,
  AlertCircle,
  Loader2,
  ShoppingBag,
  ArrowRight,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { OutfitCard } from "./OutfitCard";
import {
  fetchRecommendations,
  type Outfit,
  type RecommendResponse,
} from "@/lib/api";

function SkeletonCard() {
  return (
    <div className="overflow-hidden rounded-xl border border-border/60 bg-card">
      <div className="flex items-center justify-between border-b border-border/60 bg-secondary/40 px-4 py-2.5">
        <div className="h-3 w-20 shimmer rounded" />
        <div className="h-5 w-16 shimmer rounded-full" />
      </div>
      <div className="grid grid-cols-3 gap-1.5 p-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="aspect-[4/5] shimmer rounded-md" />
        ))}
      </div>
      <div className="space-y-2 px-4 pb-3">
        <div className="h-3 w-full shimmer rounded" />
        <div className="h-3 w-2/3 shimmer rounded" />
      </div>
      <div className="flex items-center justify-between border-t border-border/60 bg-secondary/30 px-4 py-3">
        <div className="space-y-1">
          <div className="h-2 w-12 shimmer rounded" />
          <div className="h-4 w-20 shimmer rounded" />
        </div>
        <div className="h-8 w-24 shimmer rounded-md" />
      </div>
    </div>
  );
}

export function ResultsSection({
  answers,
  onRetake,
  onChat,
}: {
  answers: Record<string, any>;
  onRetake: () => void;
  onChat: () => void;
}) {
  const [data, setData] = useState<RecommendResponse | null>(null);
  const [source, setSource] = useState<"backend" | "mock" | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [sortBy, setSortBy] = useState<"score" | "price-asc" | "price-desc">(
    "score"
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const { data, source } = await fetchRecommendations(answers);
      setData(data);
      setSource(source);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [answers]);

  useEffect(() => {
    load();
  }, [load]);

  const outfits: Outfit[] = (() => {
    if (!data?.outfits) return [];
    const list = [...data.outfits];
    if (sortBy === "score") {
      list.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    } else if (sortBy === "price-asc") {
      list.sort((a, b) => a.price_total_vnd - b.price_total_vnd);
    } else {
      list.sort((a, b) => b.price_total_vnd - a.price_total_vnd);
    }
    return list;
  })();

  return (
    <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      {/* Header */}
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-brand">
            Recommendations
          </p>
          <h2 className="mt-1 font-display text-3xl font-bold text-ink sm:text-4xl">
            Outfit cho bạn
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {data?.outfits?.length ?? 0} outfit được chọn lọc theo quiz của bạn
            {data?.meta?.occasion && ` · dịp ${data.meta.occasion}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
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
          <Button
            variant="outline"
            size="sm"
            onClick={onRetake}
            className="gap-1.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Làm lại quiz
          </Button>
        </div>
      </div>

      {/* Filter bar */}
      {!loading && !error && outfits.length > 0 && (
        <div className="mb-6 flex items-center gap-2 overflow-x-auto border-b border-border/40 pb-3">
          <span className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            <SlidersHorizontal className="h-3 w-3" />
            Sắp xếp
          </span>
          {[
            { key: "score", label: "Match score" },
            { key: "price-asc", label: "Giá tăng dần" },
            { key: "price-desc", label: "Giá giảm dần" },
          ].map((opt) => (
            <button
              key={opt.key}
              onClick={() => setSortBy(opt.key as typeof sortBy)}
              className={`whitespace-nowrap rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                sortBy === opt.key
                  ? "bg-brand text-brand-foreground"
                  : "bg-secondary/60 text-ink/70 hover:bg-secondary"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}

      {/* Body */}
      {loading ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-destructive/30 bg-destructive/5 px-6 py-16 text-center">
          <AlertCircle className="h-10 w-10 text-destructive" />
          <p className="mt-4 font-medium text-ink">
            Không thể tải gợi ý. Vui lòng thử lại.
          </p>
          <Button onClick={load} className="mt-4 gap-2">
            <RefreshCw className="h-4 w-4" />
            Thử lại
          </Button>
        </div>
      ) : outfits.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-secondary/30 px-6 py-20 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-soft">
            <ShoppingBag className="h-6 w-6 text-brand" />
          </div>
          <p className="mt-4 font-medium text-ink">
            Chưa có outfit nào được gợi ý
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Hoàn thành quiz để nhận đề xuất cá nhân hoá
          </p>
          <Button onClick={onRetake} className="mt-4 gap-2 bg-brand">
            <Sparkles className="h-4 w-4" />
            Làm quiz ngay
          </Button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {outfits.map((o, i) => (
              <OutfitCard key={o.outfit_id} outfit={o} index={i} />
            ))}
          </div>

          {/* CTA to chat */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mt-12 flex flex-col items-center justify-between gap-4 rounded-2xl border border-brand/30 bg-brand-soft/40 p-6 sm:flex-row sm:p-8"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand text-brand-foreground">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="font-display text-lg font-semibold text-ink">
                  Muốn chỉnh sửa outfit?
                </p>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  Chat trực tiếp với OutfitMatch Stylist để tinh chỉnh theo ý
                  bạn.
                </p>
              </div>
            </div>
            <Button
              onClick={onChat}
              className="gap-2 bg-brand text-brand-foreground shadow-lg shadow-brand/20 hover:bg-brand-deep"
            >
              Chat với Stylist
              <ArrowRight className="h-4 w-4" />
            </Button>
          </motion.div>
        </>
      )}

      {loading && (
        <div className="mt-8 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Đang tham chiếu graph KB…
        </div>
      )}
    </section>
  );
}
