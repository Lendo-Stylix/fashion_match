"use client";

import { Sparkles, Github, Heart } from "lucide-react";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-border/60 bg-secondary/30">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid gap-8 md:grid-cols-[1.5fr_1fr_1fr_1fr]">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand text-brand-foreground">
                <Sparkles className="h-3.5 w-3.5" />
              </div>
              <div className="leading-none">
                <p className="font-display text-lg font-bold text-ink">
                  OutfitMatch
                </p>
                <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  AI Stylist v3.1-lite
                </p>
              </div>
            </div>
            <p className="mt-4 max-w-xs text-[13px] leading-relaxed text-muted-foreground">
              AI Stylist cá nhân hoá phong cách châu Á cho thị trường Việt Nam.
              Kiến trúc 4 tầng, graph KB là đường dẫn chính.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {["Next.js 16", "TypeScript", "Tailwind 4", "Qwen3-VL-8B", "FastAPI"].map(
                (t) => (
                  <span
                    key={t}
                    className="rounded-full border border-border/60 bg-background/60 px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                  >
                    {t}
                  </span>
                )
              )}
            </div>
          </div>

          {/* Product */}
          <div>
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-ink">
              Sản phẩm
            </p>
            <ul className="space-y-2 text-[13px] text-muted-foreground">
              <li>Quiz phong cách</li>
              <li>Gợi ý outfit</li>
              <li>Chat Stylist</li>
              <li>Size suggestion</li>
            </ul>
          </div>

          {/* Tech */}
          <div>
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-ink">
              Kiến trúc
            </p>
            <ul className="space-y-2 text-[13px] text-muted-foreground">
              <li>Graph KB Builder</li>
              <li>Stylist Qwen3-VL</li>
              <li>Retrieval Qdrant</li>
              <li>Personalization Quiz</li>
            </ul>
          </div>

          {/* Team */}
          <div>
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-ink">
              Đội ngũ
            </p>
            <ul className="space-y-2 text-[13px] text-muted-foreground">
              <li>
                <span className="font-medium text-ink/80">Nhật Quang</span>
                <br />
                <span className="text-[11px]">Data / KB</span>
              </li>
              <li>
                <span className="font-medium text-ink/80">Đình Lộc</span>
                <br />
                <span className="text-[11px]">Model / Stylist</span>
              </li>
              <li>
                <span className="font-medium text-ink/80">Hữu Hoàng</span>
                <br />
                <span className="text-[11px]">Retrieval / UI</span>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-border/60 pt-6 sm:flex-row">
          <p className="text-[11px] text-muted-foreground">
            © 2026 OutfitMatch · Built with{" "}
            <Heart className="inline h-3 w-3 text-brand" /> on Next.js 16 +
            Qwen3-VL
          </p>
          <a
            href="https://github.com/Lendo-Stylix/fashion_match"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:text-brand"
          >
            <Github className="h-3.5 w-3.5" />
            Lendo-Stylix/fashion_match
          </a>
          <span className="hidden text-[10px] text-muted-foreground sm:inline">
            2 themes: Editorial Light + Luxury Dark
          </span>
        </div>
      </div>
    </footer>
  );
}
