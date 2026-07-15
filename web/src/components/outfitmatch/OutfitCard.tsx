"use client";

import { motion } from "framer-motion";
import { ExternalLink, ShoppingBag, Heart, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { vnd, compactVND, type Outfit } from "@/lib/api";

// Color swatches for category placeholders
const CAT_COLORS: Record<string, string> = {
  top: "oklch(0.72 0.10 75)",
  shirt: "oklch(0.80 0.06 90)",
  pants: "oklch(0.50 0.08 140)",
  skirt: "oklch(0.65 0.13 320)",
  dress: "oklch(0.62 0.16 38)",
  outerwear: "oklch(0.38 0.12 32)",
  shoes: "oklch(0.30 0.04 55)",
  accessory: "oklch(0.78 0.08 90)",
};

const CAT_LABEL: Record<string, string> = {
  top: "Áo thun",
  shirt: "Sơ mi",
  pants: "Quần dài",
  skirt: "Chân váy",
  dress: "Đầm",
  outerwear: "Áo khoác",
  shoes: "Giày",
  accessory: "Phụ kiện",
};

function ColorDot({ color }: { color?: string }) {
  // Map color name to a hex swatch; fallback brand
  const map: Record<string, string> = {
    Beige: "#D4C5A0",
    Cream: "#F4ECD8",
    Black: "#1A1A1A",
    White: "#FAFAFA",
    Terracotta: "#A0522D",
    Sage: "#9CAF88",
    Navy: "#1B2845",
    Burgundy: "#5C1A1B",
    Camel: "#C19A6B",
    Charcoal: "#36454F",
  };
  const hex = color ? map[color] : "var(--brand)";
  return (
    <span
      className="inline-block h-3 w-3 rounded-full border border-border/80"
      style={{ background: hex }}
      aria-hidden
    />
  );
}

function ItemTile({
  item,
  index,
}: {
  item: Outfit["items"][number];
  index: number;
}) {
  const bg = CAT_COLORS[item.category] ?? "var(--brand)";
  return (
    <motion.a
      href={item.product_url || "#"}
      target="_blank"
      rel="noreferrer"
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, delay: index * 0.05 }}
      className="group relative flex flex-col overflow-hidden rounded-md border border-border/60 bg-card/60 transition-colors hover:border-brand/40"
    >
      {/* Image placeholder — gradient + category label */}
      <div
        className="relative aspect-[4/5] w-full overflow-hidden"
        style={{
          background: `linear-gradient(140deg, ${bg} 0%, oklch(0.94 0.018 70) 100%)`,
        }}
      >
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-display text-2xl font-semibold text-white/80 drop-shadow-sm">
            {CAT_LABEL[item.category]?.[0] ?? "•"}
          </span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/30 to-transparent px-2 py-1.5">
          <p className="text-[10px] font-medium uppercase tracking-wider text-white/90">
            {CAT_LABEL[item.category] ?? item.category}
          </p>
        </div>
        {item.color && (
          <div className="absolute right-1.5 top-1.5 flex items-center gap-1 rounded-full bg-white/80 px-1.5 py-0.5 backdrop-blur-sm">
            <ColorDot color={item.color} />
            <span className="text-[9px] font-medium text-ink">
              {item.color}
            </span>
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-0.5 p-2">
        <p className="line-clamp-1 text-xs font-medium text-ink">
          {item.title_vi}
        </p>
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">
            {item.store_name}
          </span>
          <span className="font-mono text-[11px] font-semibold text-brand">
            {compactVND(item.price_vnd)}
          </span>
        </div>
      </div>
    </motion.a>
  );
}

export function OutfitCard({ outfit, index = 0 }: { outfit: Outfit; index?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, delay: index * 0.08 }}
    >
      <Card className="group overflow-hidden border-border/60 bg-card/80 p-0 transition-all duration-300 hover:-translate-y-1 hover:border-brand/40 hover:shadow-xl hover:shadow-brand/5">
        {/* Header strip */}
        <div className="flex items-center justify-between border-b border-border/60 bg-secondary/40 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[11px] font-semibold tracking-wider text-brand">
              {outfit.outfit_id}
            </span>
            {outfit.score !== undefined && (
              <Badge
                variant="outline"
                className="h-5 gap-0.5 border-brand/30 bg-brand-soft/40 px-1.5 text-[10px] font-medium text-brand-deep"
              >
                <Sparkles className="h-2.5 w-2.5" />
                {(outfit.score * 100).toFixed(0)}% match
              </Badge>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-brand"
            aria-label="Lưu outfit"
          >
            <Heart className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Tags */}
        {outfit.tags && outfit.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 px-4 pt-3">
            {outfit.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-border/60 bg-background/60 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Items grid */}
        <div className="grid grid-cols-3 gap-1.5 p-3 sm:grid-cols-4">
          {outfit.items.map((item, i) => (
            <ItemTile key={item.item_id} item={item} index={i} />
          ))}
        </div>

        {/* Explanation */}
        <div className="px-4 pb-3">
          <p className="text-[13px] leading-relaxed text-ink/80">
            {outfit.explanation_vi}
          </p>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border/60 bg-secondary/30 px-4 py-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Tổng giá trị
            </p>
            <p className="font-mono text-base font-bold text-ink">
              {vnd(outfit.price_total_vnd)}
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 border-brand/40 text-brand-deep hover:bg-brand hover:text-brand-foreground"
          >
            <ShoppingBag className="h-3.5 w-3.5" />
            Mua ngay
            <ExternalLink className="h-3 w-3" />
          </Button>
        </div>
      </Card>
    </motion.div>
  );
}
