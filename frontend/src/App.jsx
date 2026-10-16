import { useEffect, useRef, useState } from "react";

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  "https://mini-project-ai-travel-advisor.onrender.com"
).replace(/\/+$/, "");

const SUGGESTIONS = [
  "A long weekend in Lisbon",
  "Food and art in Japan",
  "A quiet beach escape",
];

function makeId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
}

function PlanSection({ title, children }) {
  if (!children) return null;

  return (
    <section className="plan-section">
      <h3>{title}</h3>
      <p>{children}</p>
    </section>
  );
}

function SourceLinks({ sources }) {
  const safeSources = Array.isArray(sources)
    ? sources.filter((source) => {
        try {
          return ["http:", "https:"].includes(new URL(source.url).protocol);
        } catch {
          return false;
        }
      })
    : [];

  if (safeSources.length === 0) return null;

  return (
    <section className="plan-section plan-sources">
      <h3>Sources</h3>
      <ul>
        {safeSources.map((source, index) => (
          <li key={`${source.url}-${index}`}>
            <a href={source.url} target="_blank" rel="noopener noreferrer">
              {source.title || source.url}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PlanDetails({ plan }) {
  return (
    <div className="plan-details">
      <h2 className="plan-title">{plan.title}</h2>
      <PlanSection title="Summary">{plan.summary}</PlanSection>
      <PlanSection title="Day-by-day itinerary">{plan.itinerary}</PlanSection>
      <PlanSection title="Practical tips">{plan.practical_tips}</PlanSection>
      <PlanSection title="Estimated budget">{plan.budget}</PlanSection>
      <SourceLinks sources={plan.sources} />
    </div>
  );
}

function AssistantMessage({ message }) {
  return (
    <article className={`message ${message.role}`}>
      <p className="message-label">
        {message.role === "user" ? "You" : "Wayfarer"}
      </p>
      <div className="message-body">
        {message.plan ? (
          <PlanDetails plan={message.plan} />
        ) : (
          <>
            <p>{message.text}</p>
            <SourceLinks sources={message.sources} />
          </>
        )}
      </div>
    </article>
  );
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [serviceStatus, setServiceStatus] = useState({
    state: "checking",
    label: "Connecting…",
  });
  const previousResponseId = useRef(null);
  const isSendingRef = useRef(false);
  const inputRef = useRef(null);
  const formRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${API_BASE}/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Service unavailable");
        setServiceStatus({ state: "online", label: "Ready to plan" });
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setServiceStatus({ state: "offline", label: "Connection unavailable" });
        }
      });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isSending]);

  async function sendMessage(value = draft) {
    const message = value.trim();
    if (!message || isSendingRef.current) return;

    isSendingRef.current = true;
    setIsSending(true);
    setMessages((current) => [
      ...current,
      { id: makeId(), role: "user", text: message },
    ]);
    setDraft("");

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          ...(previousResponseId.current
            ? { previous_response_id: previousResponseId.current }
            : {}),
        }),
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "The advisor could not answer just now. Please try again.",
        );
      }
      if (typeof data.response_id !== "string") {
        throw new Error("The API response did not match the expected format.");
      }

      previousResponseId.current = data.response_id;
      if (data.status === "needs_info" && typeof data.message === "string") {
        setMessages((current) => [
          ...current,
          {
            id: makeId(),
            role: "assistant",
            text: data.message,
            sources: data.sources,
          },
        ]);
      } else if (data.status === "complete" && data.plan?.title) {
        setMessages((current) => [
          ...current,
          { id: makeId(), role: "assistant", plan: data.plan },
        ]);
      } else {
        throw new Error("The API response did not match the expected format.");
      }
      setServiceStatus({ state: "online", label: "Ready to plan" });
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: makeId(),
          role: "assistant",
          text: `I couldn't reach the travel advisor. ${error.message}`,
        },
      ]);
      setServiceStatus({ state: "offline", label: "Connection issue" });
    } finally {
      isSendingRef.current = false;
      setIsSending(false);
      inputRef.current?.focus();
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    sendMessage();
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      formRef.current?.requestSubmit();
    }
  }

  function startNewTrip() {
    previousResponseId.current = null;
    setMessages([]);
    setDraft("");
    inputRef.current?.focus();
  }

  const isWelcome = messages.length === 0;

  return (
    <div className="layout">
      <aside className="side-panel" aria-label="Travel advisor">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">↗</span>
          <span>Wayfarer / AI</span>
        </div>
        <div className="side-copy">
          <span className="eyebrow">Your next story starts here</span>
          <h1>Take the long way.</h1>
          <p>Thoughtful itineraries, shaped around the places and little moments you love.</p>
        </div>
        <div className="side-foot">
          <span>Travel, considered</span>
          <span>Est. 2026</span>
        </div>
      </aside>

      <main className="chat-shell">
        <header className="topbar">
          <div className="service-label">
            <span className={`status-dot ${serviceStatus.state}`} aria-hidden="true" />
            <span>Travel advisor</span>
            <span className="status-text">{serviceStatus.label}</span>
          </div>
          <button
            className="reset-button"
            type="button"
            onClick={startNewTrip}
            title="Start a new trip"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New trip
          </button>
        </header>

        <section className="conversation" aria-label="Chat conversation">
          {isWelcome && (
            <div className="welcome">
              <span className="eyebrow">A good trip begins with a question</span>
              <h2>Where have you been dreaming of?</h2>
              <p>Tell me where you want to go, for how long, and what you love doing. We’ll shape a trip that feels like yours.</p>
            </div>
          )}
          <div className="messages" aria-live="polite" aria-relevant="additions text">
            {messages.map((message) => (
              <AssistantMessage key={message.id} message={message} />
            ))}
            {isSending && (
              <article className="message assistant">
                <p className="message-label">Wayfarer · thinking</p>
                <p className="typing">Finding the right words…</p>
              </article>
            )}
            <div ref={bottomRef} />
          </div>
          {isWelcome && (
            <div className="suggestions" aria-label="Suggested prompts">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  className="suggestion"
                  key={suggestion}
                  type="button"
                  disabled={isSending}
                  onClick={() => sendMessage(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </section>

        <div className="composer-wrap">
          <form className="composer" ref={formRef} onSubmit={handleSubmit}>
            <div className="input-frame">
              <textarea
                ref={inputRef}
                rows="2"
                maxLength="4000"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Tell me what kind of trip you have in mind…"
                aria-label="Your message"
                required
              />
            </div>
            <button
              className="send-button"
              type="submit"
              aria-label="Send message"
              title="Send message"
              disabled={isSending || !draft.trim()}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m22 2-7 20-4-9-9-4Z" />
                <path d="M22 2 11 13" />
              </svg>
            </button>
          </form>
          <p className="composer-note">Enter to send · Shift + Enter for a new line</p>
        </div>
      </main>
    </div>
  );
}
