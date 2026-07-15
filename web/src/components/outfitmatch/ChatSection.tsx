"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Sparkles,
  User,
  Bot,
  Loader2,
  RefreshCw,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { OutfitCard } from "./OutfitCard";
import {
  streamChat,
  type Outfit,
  type ChatTurn,
} from "@/lib/api";

const SUGGESTIONS = [
  "Mặc gì đi làm mai?",
  "Outfit đi date tối nay",
  "Phối đồ old money cho nam 175cm",
  "Đi tiệc sinh nhật bạn gái",
];

export function ChatSection() {
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [pendingOutfits, setPendingOutfits] = useState<Outfit[]>([]);
  const [backendLive, setBackendLive] = useState<boolean | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamText, pendingOutfits]);

  const send = useCallback(
    async (text?: string) => {
      const message = (text ?? input).trim();
      if (!message || isStreaming) return;

      const userTurn: ChatTurn = {
        role: "user",
        text: message,
        ts: Date.now(),
      };
      setMessages((prev) => [...prev, userTurn]);
      setInput("");
      setIsStreaming(true);
      setStreamText("");
      setPendingOutfits([]);

      let botText = "";
      let outfits: Outfit[] = [];

      await streamChat(message, {
        onToken: (t) => {
          botText += t;
          setStreamText(botText);
        },
        onOutfitCards: (cards) => {
          outfits = cards;
          setPendingOutfits(cards);
        },
        onError: (err) => {
          botText += `\n[Lỗi: ${err}]`;
          setStreamText(botText);
        },
        onDone: () => {
          setBackendLive(true);
        },
      });

      // Detect mock by checking if backend was used — heuristic via timing
      // (mock always returns within ~600ms for short replies)
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: botText.trim(),
          outfits: outfits.length > 0 ? outfits : undefined,
          ts: Date.now(),
        },
      ]);
      setStreamText("");
      setPendingOutfits([]);
      setIsStreaming(false);
      inputRef.current?.focus();
    },
    [input, isStreaming]
  );

  const reset = () => {
    setMessages([]);
    setStreamText("");
    setPendingOutfits([]);
    setIsStreaming(false);
  };

  return (
    <section className="mx-auto flex max-w-4xl flex-col px-4 py-8 sm:px-6 sm:py-12 lg:px-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative flex h-10 w-10 items-center justify-center rounded-full bg-brand text-brand-foreground shadow-sm">
            <Sparkles className="h-5 w-5" />
            <span className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3">
              <span className="absolute inline-flex h-3 w-3 animate-ping rounded-full bg-chart-3 opacity-75" />
              <span className="relative inline-flex h-3 w-3 rounded-full border-2 border-background bg-chart-3" />
            </span>
          </div>
          <div>
            <h2 className="font-display text-xl font-bold text-ink">
              OutfitMatch Stylist
            </h2>
            <p className="text-[11px] text-muted-foreground">
              Qwen3-VL-8B + LoRA · Streaming SSE
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {backendLive !== null && (
            <Badge
              variant="outline"
              className={`gap-1.5 border-border/60 ${
                backendLive
                  ? "bg-chart-3/10 text-chart-3"
                  : "bg-secondary/60 text-muted-foreground"
              }`}
            >
              <span className="flex h-1.5 w-1.5 rounded-full bg-current" />
              {backendLive ? "Live" : "Demo"}
            </Badge>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={reset}
            className="h-8 w-8 text-muted-foreground hover:text-ink"
            aria-label="Xoá hội thoại"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Chat viewport */}
      <div className="flex-1 overflow-hidden rounded-2xl border border-border/60 bg-card/60 shadow-sm">
        <ScrollArea className="h-[440px] sm:h-[520px]">
          <div className="flex min-h-full flex-col gap-4 p-4 sm:p-6">
            {messages.length === 0 &&
              !isStreaming &&
              !streamText &&
              !pendingOutfits.length && (
                <WelcomeScreen onPick={send} />
              )}

            {messages.map((msg, i) => (
              <MessageBubble key={i} msg={msg} />
            ))}

            {/* Streaming bubble */}
            <AnimatePresence>
              {isStreaming &&
                (streamText || pendingOutfits.length > 0) && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="flex gap-3"
                  >
                    <Avatar role="bot" />
                    <div className="flex max-w-[80%] flex-col gap-2">
                      <div className="rounded-2xl rounded-tl-sm border border-border/60 bg-card px-4 py-3">
                        {streamText ? (
                          <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
                            {streamText}
                            <span className="caret-blink" />
                          </p>
                        ) : (
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            Đang tham vấn graph KB…
                          </div>
                        )}
                      </div>
                      {pendingOutfits.length > 0 && (
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                          {pendingOutfits.map((o, j) => (
                            <OutfitCard key={o.outfit_id} outfit={o} index={j} />
                          ))}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
            </AnimatePresence>

            <div ref={endRef} />
          </div>
        </ScrollArea>
      </div>

      {/* Suggestion chips — only when input is empty */}
      <AnimatePresence>
        {messages.length === 0 && !input && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-4 flex flex-wrap gap-2"
          >
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-full border border-border/60 bg-card px-3 py-1.5 text-xs font-medium text-ink/70 transition-colors hover:border-brand/40 hover:bg-brand-soft/40 hover:text-brand-deep"
              >
                {s}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input */}
      <div className="mt-4 flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={isStreaming}
          placeholder="Hỏi về trang phục, phong cách, dịp đi…"
          className="flex-1 rounded-full border border-border bg-card px-5 py-3 text-sm text-ink placeholder:text-muted-foreground focus:border-brand/40 focus:outline-none focus:ring-2 focus:ring-brand/30 disabled:opacity-50"
          aria-label="Tin nhắn cho stylist"
        />
        <Button
          onClick={() => send()}
          disabled={isStreaming || !input.trim()}
          size="icon"
          className="h-12 w-12 rounded-full bg-brand text-brand-foreground shadow-lg shadow-brand/20 hover:bg-brand-deep"
          aria-label="Gửi"
        >
          {isStreaming ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Send className="h-5 w-5" />
          )}
        </Button>
      </div>

      <p className="mt-3 flex items-center justify-center gap-1.5 text-[10px] text-muted-foreground">
        <Zap className="h-3 w-3 text-brand" />
        Stylist có thể gợi ý sai — hãy verify trước khi mua hàng
      </p>
    </section>
  );
}

function Avatar({ role }: { role: "user" | "bot" }) {
  if (role === "user") {
    return (
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-secondary text-ink/70">
        <User className="h-4 w-4" />
      </div>
    );
  }
  return (
    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-brand-foreground shadow-sm">
      <Bot className="h-4 w-4" />
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatTurn }) {
  const isUser = msg.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}
    >
      <Avatar role={msg.role} />
      <div
        className={`flex max-w-[80%] flex-col gap-2 ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "rounded-tr-sm bg-brand text-brand-foreground"
              : "rounded-tl-sm border border-border/60 bg-card text-ink"
          }`}
        >
          <p className="whitespace-pre-wrap">{msg.text}</p>
        </div>
        {msg.outfits && msg.outfits.length > 0 && (
          <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
            {msg.outfits.map((o, i) => (
              <OutfitCard key={o.outfit_id} outfit={o} index={i} />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function WelcomeScreen({ onPick }: { onPick: (s: string) => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center py-12 text-center"
    >
      <div className="relative mb-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-soft">
          <Sparkles className="h-7 w-7 text-brand" />
        </div>
        <motion.div
          animate={{ scale: [1, 1.15, 1], opacity: [0.5, 0, 0] }}
          transition={{ duration: 2, repeat: Infinity }}
          className="absolute inset-0 rounded-full bg-brand/30"
        />
      </div>
      <h3 className="font-display text-2xl font-bold text-ink">
        Xin chào, mình là OutfitMatch Stylist
      </h3>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
        AI được tinh chỉnh trên Qwen3-VL-8B với LoRA, hiểu thời trang Việt Nam.
        Hỏi mình về outfit cho bất kỳ dịp nào — mình sẽ tìm trong graph KB và
        trả lời streaming realtime.
      </p>
      <div className="mt-6 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        <span className="flex h-1.5 w-1.5 rounded-full bg-chart-3" />
        Sẵn sàng trò chuyện
      </div>
    </motion.div>
  );
}
