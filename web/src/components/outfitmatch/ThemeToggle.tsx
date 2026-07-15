"use client";

import { useTheme } from "next-themes";
import { motion, AnimatePresence } from "framer-motion";
import { Sun, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  // next-themes returns undefined on first client render, then resolves.
  // We use that as the "mounted" signal without calling setState in an effect.
  const { theme, setTheme } = useTheme();
  const isLuxury = theme === "luxury";
  const toggle = () => setTheme(isLuxury ? "light" : "luxury");

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      className="relative h-9 w-9 overflow-hidden rounded-full border border-border/60 hover:border-brand/40 hover:bg-secondary/40"
      aria-label={isLuxury ? "Chuyển sang theme Sáng" : "Chuyển sang theme Luxury"}
      title={isLuxury ? "Theme Luxury (Đang bật)" : "Theme Sáng — bấm để bật Luxury"}
    >
      <AnimatePresence mode="wait" initial={false}>
        {isLuxury ? (
          <motion.span
            key="luxury"
            initial={{ rotate: -90, opacity: 0, scale: 0.5 }}
            animate={{ rotate: 0, opacity: 1, scale: 1 }}
            exit={{ rotate: 90, opacity: 0, scale: 0.5 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <Sparkles className="h-4 w-4 text-brand" />
          </motion.span>
        ) : (
          <motion.span
            key="light"
            initial={{ rotate: 90, opacity: 0, scale: 0.5 }}
            animate={{ rotate: 0, opacity: 1, scale: 1 }}
            exit={{ rotate: -90, opacity: 0, scale: 0.5 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <Sun className="h-4 w-4 text-brand" />
          </motion.span>
        )}
      </AnimatePresence>
    </Button>
  );
}
