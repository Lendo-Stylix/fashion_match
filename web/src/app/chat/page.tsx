"use client";

import { useState, useRef, useEffect } from "react";

type SSEEvent = {
  type: "token" | "thinking" | "outfit_cards" | "done" | "error";
  data: string;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<{ role: "user" | "bot"; text: string }[]>(
    []
  );
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentText, setCurrentText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentText]);

  async function sendMessage() {
    if (!input.trim() || isStreaming) return;
    const userMsg = input;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: userMsg }]);
    setIsStreaming(true);
    setCurrentText("");

    try {
      const resp = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg }),
      });

      if (!resp.body) {
        throw new Error("No response body");
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let botText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            const eventType = line.slice(6).trim();
            const nextLine = lines[lines.indexOf(line) + 1];
            if (nextLine?.startsWith("data:")) {
              const data = nextLine.slice(5).trim();
              if (eventType === "token") {
                botText += data;
                setCurrentText(botText);
              } else if (eventType === "done") {
                break;
              }
            }
          }
        }
      }

      setMessages((prev) => [...prev, { role: "bot", text: botText }]);
    } catch (err) {
      console.error("Chat error:", err);
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: "Sorry, I encountered an error." },
      ]);
    } finally {
      setIsStreaming(false);
      setCurrentText("");
    }
  }

  return (
    <main className="flex min-h-screen flex-col p-8">
      <div className="mb-4">
        <h1 className="text-2xl font-bold">Chat with Stylist</h1>
      </div>

      <div className="flex-1 overflow-y-auto mb-4 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`rounded p-4 ${
              msg.role === "user"
                ? "bg-blue-100 ml-16"
                : "bg-gray-100 mr-16"
            }`}
          >
            <p className="text-sm font-semibold mb-1">
              {msg.role === "user" ? "You" : "OutfitMatch Stylist"}
            </p>
            <p className="whitespace-pre-wrap">{msg.text}</p>
          </div>
        ))}

        {isStreaming && currentText && (
          <div className="bg-gray-100 mr-16 rounded p-4">
            <p className="text-sm font-semibold mb-1">OutfitMatch Stylist</p>
            <p className="whitespace-pre-wrap">{currentText}</p>
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          disabled={isStreaming}
          placeholder="Type your message..."
          className="flex-1 rounded border px-4 py-2 disabled:opacity-50"
        />
        <button
          onClick={sendMessage}
          disabled={isStreaming || !input.trim()}
          className="rounded bg-blue-600 px-6 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </main>
  );
}
