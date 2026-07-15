"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import { API_URL } from "@/lib/api";

type OutfitCard = {
  outfit_id: string;
  explanation_vi: string;
  price_total_vnd: number;
  items: {
    item_id: string;
    category: string;
    title_vi: string;
    price_vnd: number;
    store_name: string;
    image_path: string;
    product_url: string;
  }[];
};

type ChatMessage = {
  role: "user" | "bot";
  text: string;
  outfits?: OutfitCard[];
};

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentText, setCurrentText] = useState("");
  const [pendingOutfits, setPendingOutfits] = useState<OutfitCard[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentText]);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || isStreaming) return;
    const userMsg = input;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: userMsg }]);
    setIsStreaming(true);
    setCurrentText("");
    setPendingOutfits([]);

    let botText = "";
    let outfits: OutfitCard[] = [];
    let rafId: number | null = null;
    const scheduleFlush = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        setCurrentText(botText);
      });
    };

    try {
      const resp = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg }),
      });

      if (!resp.body) throw new Error("No response body");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE: each event is "event:type\ndata:payload\n\n"
        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() || ""; // keep incomplete chunk

        for (const part of parts) {
          const lines = part.split("\n");
          let eventType = "";
          const dataLines: string[] = [];
          for (const line of lines) {
            if (line.startsWith("event:")) eventType = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^\s/, ""));
          }
          // sse_starlette frames multi-line payloads (e.g. the outfit_cards
          // JSON array) as several "data:" lines; rejoin them before parsing.
          const data = dataLines.join("\n");

          if (eventType === "token") {
            botText += data;
            scheduleFlush();
          } else if (eventType === "outfit_cards") {
            try {
              const parsed = JSON.parse(data);
              if (Array.isArray(parsed)) outfits = parsed;
              else if (parsed.outfits) outfits = parsed.outfits;
              setPendingOutfits(outfits);
            } catch {
              /* ignore parse errors */
            }
          } else if (eventType === "error") {
            botText += "\n[Error: " + data + "]";
            setCurrentText(botText);
          } else if (eventType === "done") {
            // stream complete
          }
        }
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: botText,
          outfits: outfits.length > 0 ? outfits : undefined,
        },
      ]);
    } catch (err) {
      console.error("Chat error:", err);
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại.",
        },
      ]);
    } finally {
      if (rafId !== null) cancelAnimationFrame(rafId);
      setIsStreaming(false);
      setCurrentText("");
      setPendingOutfits([]);
    }
  }, [input, isStreaming]);

  function renderOutfitCard(card: OutfitCard) {
    return (
      <div
        key={card.outfit_id}
        className="border border-border bg-surface rounded-lg p-4 mt-2"
      >
        <p className="font-bold text-lg text-ink">{card.outfit_id}</p>
        <p className="text-sm text-muted mb-2">{card.explanation_vi}</p>
        <p className="text-sm font-semibold text-ink">
          Tổng: {card.price_total_vnd.toLocaleString()} VND
        </p>
        <div className="grid grid-cols-2 gap-2 mt-2">
          {card.items.map((item) => (
            <a
              key={item.item_id}
              href={item.product_url || "#"}
              target="_blank"
              rel="noreferrer"
              className="text-xs border border-border rounded-md p-2 hover:bg-brand-soft transition-colors"
            >
              <div
                className="h-10 w-full rounded bg-brand-soft mb-1 flex items-center justify-center text-brand font-bold"
                aria-hidden="true"
              >
                {item.category.slice(0, 2).toUpperCase()}
              </div>
              <p className="font-medium capitalize text-ink truncate">
                {item.category}
              </p>
              <p className="truncate text-ink">{item.title_vi}</p>
              <p className="text-muted">
                {item.store_name} - {item.price_vnd.toLocaleString()} VND
              </p>
            </a>
          ))}
        </div>
      </div>
    );
  }

  return (
    <main className="flex min-h-screen flex-col p-4 md:p-8">
      <nav className="flex items-center gap-4 mb-4">
        <Link href="/" className="text-sm text-brand hover:underline">
          Home
        </Link>
        <h1 className="text-2xl font-bold text-ink">Chat with Stylist</h1>
      </nav>

      <div className="flex-1 overflow-y-auto mb-4 space-y-4 max-w-3xl mx-auto w-full">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`rounded-lg p-4 ${
              msg.role === "user"
                ? "bg-brand-soft ml-16"
                : "bg-surface border border-border mr-16"
            }`}
          >
            <p className="text-sm font-semibold mb-1 text-ink">
              {msg.role === "user" ? "You" : "OutfitMatch Stylist"}
            </p>
            <p className="whitespace-pre-wrap text-ink">{msg.text}</p>
            {msg.outfits?.map((card) => renderOutfitCard(card))}
          </div>
        ))}

        {isStreaming && (currentText || pendingOutfits.length > 0) && (
          <div className="bg-surface border border-border mr-16 rounded-lg p-4">
            <p className="text-sm font-semibold mb-1 text-ink">
              OutfitMatch Stylist
            </p>
            <p className="whitespace-pre-wrap text-ink">{currentText}</p>
            {pendingOutfits.map((card) => renderOutfitCard(card))}
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="flex gap-2 max-w-3xl mx-auto w-full">
        <label htmlFor="chat-input" className="sr-only">
          Tin nhắn cho stylist
        </label>
        <input
          id="chat-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          disabled={isStreaming}
          placeholder="Hỏi về trang phục, phong cách, dịp đi..."
          className="flex-1 rounded-lg border border-border bg-surface px-4 py-2 text-ink placeholder:text-muted focus:ring-2 focus:ring-brand disabled:opacity-50"
        />
        <button
          onClick={sendMessage}
          disabled={isStreaming || !input.trim()}
          className="rounded-lg bg-brand px-6 py-2 text-brand-ink font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          Send
        </button>
      </div>
    </main>
  );
}
