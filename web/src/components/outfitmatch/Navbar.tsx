"use client";

import { motion } from "framer-motion";
import { Sparkles, Heart, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./ThemeToggle";

type View = "home" | "quiz" | "results" | "chat";

export function Navbar({
  view,
  onNavigate,
}: {
  view: View;
  onNavigate: (v: View) => void;
}) {
  const links: { key: View; label: string }[] = [
    { key: "home", label: "Trang chủ" },
    { key: "quiz", label: "Quiz phong cách" },
    { key: "results", label: "Gợi ý outfit" },
    { key: "chat", label: "Chat Stylist" },
  ];

  return (
    <header className="sticky top-0 z-50 border-b border-border/40 bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <button
          onClick={() => onNavigate("home")}
          className="group flex items-center gap-2"
          aria-label="OutfitMatch home"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand text-brand-foreground shadow-sm transition-transform group-hover:scale-105">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="flex flex-col items-start leading-none">
            <span className="font-display text-lg font-bold tracking-tight text-ink">
              OutfitMatch
            </span>
            <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              AI Stylist
            </span>
          </div>
        </button>

        {/* Nav links — desktop */}
        <nav className="hidden items-center gap-1 md:flex">
          {links.map((l) => {
            const active = view === l.key;
            return (
              <button
                key={l.key}
                onClick={() => onNavigate(l.key)}
                className={`relative rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "text-brand"
                    : "text-ink/70 hover:text-ink"
                }`}
              >
                {l.label}
                {active && (
                  <motion.span
                    layoutId="nav-underline"
                    className="absolute inset-x-3 -bottom-0.5 h-0.5 rounded-full bg-brand"
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  />
                )}
              </button>
            );
          })}
        </nav>

        {/* Actions */}
        <div className="flex items-center gap-1.5">
          <ThemeToggle />
          <Button
            variant="ghost"
            size="sm"
            className="hidden gap-1.5 text-ink/70 hover:text-brand sm:flex"
            onClick={() => onNavigate("results")}
          >
            <Heart className="h-3.5 w-3.5" />
            Đã lưu
          </Button>
          <Button
            size="sm"
            className="gap-1.5 bg-brand text-brand-foreground shadow-sm hover:bg-brand-deep"
            onClick={() => onNavigate("quiz")}
          >
            Bắt đầu
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Mobile nav */}
      <nav className="flex items-center gap-1 overflow-x-auto border-t border-border/40 px-4 py-2 md:hidden">
        {links.map((l) => {
          const active = view === l.key;
          return (
            <button
              key={l.key}
              onClick={() => onNavigate(l.key)}
              className={`whitespace-nowrap rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                active
                  ? "bg-brand text-brand-foreground"
                  : "bg-secondary/60 text-ink/70"
              }`}
            >
              {l.label}
            </button>
          );
        })}
      </nav>
    </header>
  );
}
