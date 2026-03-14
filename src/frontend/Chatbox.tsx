import { CSSProperties, FormEvent, useEffect, useRef, useState } from "react";
import { COLORS } from "./theme/colors";
import "./Chatbox.css";

type ChatRole = "user" | "model";

interface ChatMessage {
  role: ChatRole;
  text: string;
}

const GEMINI_MODEL = "gemini-2.0-flash";

export default function Chatbox() {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "model",
      text: "Xin chao, minh la tro ly AI. Ban co the hoi ve audiobook, NLP, hoac cac tin tuc tren trang nay.",
    },
  ]);

  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!listRef.current) {
      return;
    }
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, isOpen]);

  const cssVars = {
    "--brand": COLORS.brand,
    "--brand-dark": COLORS.brandDark,
    "--surface": COLORS.surface,
    "--surface-soft": COLORS.surfaceSoft,
    "--stroke": COLORS.stroke,
    "--ink": COLORS.ink,
    "--muted": COLORS.muted,
  } as CSSProperties;

  async function askGemini(prompt: string): Promise<string> {
    const apiKey = import.meta.env.VITE_GEMINI_API_KEY;

    if (!apiKey) {
      return "Chua cau hinh API key. Hay tao file .env trong src/frontend va them: VITE_GEMINI_API_KEY=your_key";
    }

    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${apiKey}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          contents: [
            {
              role: "user",
              parts: [{ text: prompt }],
            },
          ],
        }),
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      return `Khong goi duoc Gemini API (${response.status}). ${errorText}`;
    }

    const data = await response.json();
    const text =
      data?.candidates?.[0]?.content?.parts
        ?.map((part: { text?: string }) => part.text ?? "")
        .join("")
        .trim() || "AI chua tra loi duoc. Ban thu hoi lai nhe.";

    return text;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const prompt = input.trim();

    if (!prompt || isLoading) {
      return;
    }

    setInput("");
    setIsLoading(true);
    setMessages((prev) => [...prev, { role: "user", text: prompt }]);

    try {
      const answer = await askGemini(prompt);
      setMessages((prev) => [...prev, { role: "model", text: answer }]);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Da co loi trong qua trinh goi API.";
      setMessages((prev) => [...prev, { role: "model", text: message }]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="chatbox-root" style={cssVars}>
      {isOpen ? (
        <section className="chatbox-panel">
          <header className="chatbox-header">
            <div>
              <h3 className="chatbox-title">Tro ly AI</h3>
              <p className="chatbox-subtitle">Hoi nhanh voi Gemini</p>
            </div>
            <button
              type="button"
              className="chatbox-close"
              onClick={() => setIsOpen(false)}
              aria-label="Dong hop chat"
            >
              x
            </button>
          </header>

          <div ref={listRef} className="chatbox-messages">
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`chatbox-message ${
                  message.role === "user"
                    ? "chatbox-message-user"
                    : "chatbox-message-model"
                }`}
              >
                {message.text}
              </div>
            ))}
            {isLoading ? (
              <div className="chatbox-message chatbox-message-model">Dang tra loi...</div>
            ) : null}
          </div>

          <form className="chatbox-form" onSubmit={handleSubmit}>
            <input
              className="chatbox-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Nhap cau hoi cua ban..."
            />
            <button className="chatbox-send" type="submit" disabled={isLoading}>
              Gui
            </button>
          </form>
        </section>
      ) : null}

      <button
        type="button"
        className="chatbox-fab"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label="Mo chatbox"
      >
        AI
      </button>
    </div>
  );
}
