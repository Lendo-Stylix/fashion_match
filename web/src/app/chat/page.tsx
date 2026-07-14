"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";

type OutfitCard = {
  outfit_id: string;
  explanation_vi: string;
  price_total_vnd: number;
  items: { item_id: string; category: string; title_vi: string; price_vnd: number; store_name: string; image_path: string }[];
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

    try {
      const resp = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg }),
      });

      if (!resp.body) throw new Error("No response body");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let botText = "";
      let currentEventType = "";
      let outfits: OutfitCard[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE: each event is "event:type\ndata:payload\n\n"
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || ""; // keep incomplete chunk

        for (const part of parts) {
          const lines = part.split("\n");
          let eventType = "";
          let data = "";
          for (const line of lines) {
            if (line.startsWith("event:")) eventType = line.slice(6).trim();
            else if (line.startsWith("data:")) data = line.slice(5).trim();
          }

          if (eventType === "token") {
            botText += data;
            setCurrentText(botText);
          } else if (eventType === "outfit_cards") {
            try {
              const parsed = JSON.parse(data);
              if (Array.isArray(parsed)) outfits = parsed;
              else if (parsed.outfits) outfits = parsed.outfits;
              setPendingOutfits(outfits);
            } catch { /* ignore parse errors */ }
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
        { role: "bot", text: botText, outfits: outfits.length > 0 ? outfits : undefined },
      ]);
    } catch (err) {
      console.error("Chat error:", err);
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: "Sorry, I encountered an error. Please try again." },
      ]);
    } finally {
      setIsStreaming(false);
      setCurrentText("");
      setPendingOutfits([]);
    }
  }, [input, isStreaming]);

  function renderOutfitCard(card: OutfitCard) {
    return (
      <div className="border rounded-lg p-4 shadow-sm bg-white mt-2">
        <p className="font-bold text-lg">{card.outfit_id}</p>
        <p className="text-sm text-gray-600 mb-2">{card.explanation_vi}</p>
        <p className="text-sm font-semibold">Total: {card.price_total_vnd.toLocaleString()} VND</p>
        <div className="grid grid-cols-2 gap-2 mt-2">
          {card.items.map((item) => (
            <div key={item.item_id} className="text-xs border rounded p-2">
              <p className="font-medium capitalize">{item.category}</p>
              <p>{item.title_vi}</p>
              <p className="text-gray-500">{item.store_name} - {item.price_vnd.toLocaleString()} VND</p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <main className="flex min-h-screen flex-col p-4 md:p-8">
      <nav className="flex items-center gap-4 mb-4">
        <Link href="/" className="text-sm hover:underline">Home</Link>
        <h1 className="text-2xl font-bold">Chat with Stylist</h1>
      </nav>

      <div className="flex-1 overflow-y-auto mb-4 space-y-4 max-w-3xl mx-auto w-full">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`rounded-lg p-4 ${msg.role === "user" ? "bg-blue-50 ml-16" : "bg-gray-50 mr-16"}`}
          >
            <p className="text-sm font-semibold mb-1">
              {msg.role === "user" ? "You" : "OutfitMatch Stylist"}
            </p>
            <p className="whitespace-pre-wrap">{msg.text}</p>
            {msg.outfits?.map((card) => renderOutfitCard(card))}
          </div>
        ))}

        {isStreaming && (currentText || pendingOutfits.length > 0) && (
          <div className="bg-gray-50 mr-16 rounded-lg p-4">
            <p className="text-sm font-semibold mb-1">OutfitMatch Stylist</p>
            <p className="whitespace-pre-wrap">{currentText}</p>
            {pendingOutfits.map((card) => renderOutfitCard(card))}
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="flex gap-2 max-w-3xl mx-auto w-full">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          disabled={isStreaming}
          placeholder="Ask about outfits, styles, occasions..."
          className="flex-1 rounded-lg border px-4 py-2 focus:ring-2 focus:ring-blue-400 disabled:opacity-50"
        />
        <button
          onClick={sendMessage}
          disabled={isStreaming || !input.trim()}
          className="rounded-lg bg-blue-600 px-6 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </main>
  );
}