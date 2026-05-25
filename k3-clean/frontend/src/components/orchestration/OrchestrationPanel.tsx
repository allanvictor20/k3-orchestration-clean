import { useEffect, useRef, useState } from "react";
import {
  runOrchestration,
  sendSessionPrompt,
  createSession,
  getSession,
  type OrchestrationResponse,
  type Session,
  type SessionMessage,
} from "@/lib/api";
import { LanguageSelector }  from "./LanguageSelector";
import { WorkflowProgress }  from "./WorkflowProgress";
import { SessionHistory }    from "./SessionHistory";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  input_language?: string;
  output_language?: string;
  workflow_id?: string;
  providers_used?: string[];
  total_cost_usd?: number;
  total_latency_ms?: number;
  created_at: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic:  "Claude",
  openai:     "GPT-4o",
  perplexity: "Perplexity",
  gemini:     "Gemini",
  sunbird:    "Sunbird",
};

const PROVIDER_COLORS: Record<string, string> = {
  anthropic:  "#f5835a",
  openai:     "#16a34a",
  perplexity: "#7c3aed",
  gemini:     "#4a90d9",
  sunbird:    "#e8a020",
};

const LANG_NAMES: Record<string, string> = {
  en: "English", lg: "Luganda", sw: "Swahili",
  ach: "Acholi", nyn: "Runyankole", kin: "Kinyarwanda",
};

export function OrchestrationPanel() {
  const [messages,         setMessages]         = useState<Message[]>([]);
  const [prompt,           setPrompt]           = useState("");
  const [inputLanguage,    setInputLanguage]    = useState("en");
  const [outputLanguage,   setOutputLanguage]   = useState("en");
  const [isLoading,        setIsLoading]        = useState(false);
  const [activeWorkflowId, setActiveWorkflowId] = useState<string | null>(null);
  const [activeSession,    setActiveSession]    = useState<Session | null>(null);
  const [showSidebar,      setShowSidebar]      = useState(true);
  const [error,            setError]            = useState<string | null>(null);
  const [inputFocused,     setInputFocused]     = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef    = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [prompt]);

  async function handleNewSession() {
    const session = await createSession({
      input_language: inputLanguage,
      output_language: outputLanguage,
    });
    setActiveSession(session);
    setMessages([]);
    setActiveWorkflowId(null);
    setError(null);
  }

  async function handleSelectSession(session: Session) {
    setActiveSession(session);
    setActiveWorkflowId(null);
    setError(null);
    const detail = await getSession(session.id);
    if (detail.messages) {
      const loaded: Message[] = detail.messages.map((m: SessionMessage) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        input_language: m.input_language,
        output_language: m.output_language,
        workflow_id: m.workflow_id || undefined,
        created_at: m.created_at,
      }));
      setMessages(loaded);
      setInputLanguage(session.input_language);
      setOutputLanguage(session.output_language);
    }
  }

  async function handleSubmit() {
    if (!prompt.trim() || isLoading) return;
    const userPrompt = prompt.trim();
    setPrompt("");
    setError(null);

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: userPrompt,
      input_language: inputLanguage,
      output_language: outputLanguage,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      let response: OrchestrationResponse;
      if (activeSession) {
        setActiveWorkflowId(activeSession.id + "-pending");
        response = await sendSessionPrompt(
          activeSession.id, userPrompt, inputLanguage, outputLanguage
        );
      } else {
        const workflowId = crypto.randomUUID();
        setActiveWorkflowId(workflowId);
        response = await runOrchestration({
          workflow_id: workflowId,
          prompt: userPrompt,
          input_language: inputLanguage,
          output_language: outputLanguage,
        });
      }

      setActiveWorkflowId(response.workflow_id);

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: response.final_output,
        input_language: response.input_language,
        output_language: response.output_language,
        workflow_id: response.workflow_id,
        providers_used: response.providers_used,
        total_cost_usd: response.total_cost_usd,
        total_latency_ms: response.total_latency_ms,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);

      if (activeSession && messages.length === 0) {
        setActiveSession((s) => s ? { ...s, title: userPrompt.slice(0, 60) } : s);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setError(message);
      setMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
    } finally {
      setIsLoading(false);
      setActiveWorkflowId(null);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  }

  const isEmpty = messages.length === 0 && !isLoading;

  return (
    <div style={{
      display: "flex",
      height: "100%",
      background: "var(--bg)",
      fontFamily: "var(--font)",
    }}>

      {/* Sidebar */}
      {showSidebar && (
        <div style={{ width: "var(--sidebar-width)", flexShrink: 0 }}>
          <SessionHistory
            activeSessionId={activeSession?.id ?? null}
            onSelectSession={handleSelectSession}
            onNewSession={handleNewSession}
          />
        </div>
      )}

      {/* Main area */}
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>

        {/* Top bar */}
        <div style={{
          height: "var(--topbar-height)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 20px",
          background: "#ffffff",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button
              onClick={() => setShowSidebar((v) => !v)}
              title="Toggle sidebar"
              style={{
                width: 32, height: 32,
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
                background: "transparent",
                color: "var(--text-muted)",
                cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 16,
                transition: "all 0.15s",
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)";
              }}
            >
              ☰
            </button>
            <span style={{
              fontSize: 14, fontWeight: 500,
              color: "var(--text-secondary)",
            }}>
              {activeSession ? activeSession.title : "Maverix Orchestration"}
            </span>
          </div>
          <LanguageSelector
            inputLanguage={inputLanguage}
            outputLanguage={outputLanguage}
            onInputChange={setInputLanguage}
            onOutputChange={setOutputLanguage}
            disabled={isLoading}
          />
        </div>

        {/* Messages area */}
        <div style={{
          flex: 1,
          overflowY: "auto",
          padding: isEmpty ? 0 : "24px 0",
          display: "flex",
          flexDirection: "column",
        }}>

          {/* Empty state — centered like Gemini */}
          {isEmpty && (
            <div style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "40px 24px",
              animation: "fadeUp 0.4s ease",
            }}>
              {/* Logo */}
              <div style={{
                width: 56, height: 56,
                borderRadius: 16,
                background: "linear-gradient(135deg, #4a90d9 0%, #2d72c2 100%)",
                display: "flex", alignItems: "center", justifyContent: "center",
                marginBottom: 20,
                boxShadow: "0 4px 20px rgba(74,144,217,0.25)",
              }}>
                <span style={{ color: "#fff", fontSize: 22, fontWeight: 600, letterSpacing: "-1px" }}>Maverix</span>
              </div>

              <h1 style={{
                fontSize: 26,
                fontWeight: 400,
                color: "var(--text-primary)",
                marginBottom: 8,
                textAlign: "center",
              }}>
                What can I help you with?
              </h1>
              <p style={{
                fontSize: 14,
                color: "var(--text-muted)",
                textAlign: "center",
                maxWidth: 380,
                lineHeight: 1.6,
                marginBottom: 32,
              }}>
                Multi-model AI orchestration built for African institutions.
                Ask anything in English, Luganda, Swahili, and more.
              </p>

              {/* Provider chips */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
                {Object.entries(PROVIDER_LABELS).map(([key, label]) => (
                  <div key={key} style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "5px 12px",
                    borderRadius: "var(--radius-full)",
                    border: `1px solid ${PROVIDER_COLORS[key]}33`,
                    background: `${PROVIDER_COLORS[key]}0d`,
                    fontSize: 12, fontWeight: 500,
                    color: PROVIDER_COLORS[key],
                  }}>
                    <span style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: PROVIDER_COLORS[key], flexShrink: 0,
                    }} />
                    {label}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          {!isEmpty && (
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    padding: "16px 24px",
                    display: "flex",
                    justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                    animation: "fadeUp 0.2s ease",
                  }}
                >
                  {msg.role === "assistant" && (
                    <div style={{
                      width: 30, height: 30,
                      borderRadius: 8,
                      background: "linear-gradient(135deg, #4a90d9 0%, #2d72c2 100%)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      flexShrink: 0,
                      marginRight: 12,
                      marginTop: 2,
                    }}>
                      <span style={{ color: "#fff", fontSize: 10, fontWeight: 600 }}>Maverix</span>
                    </div>
                  )}

                  <div style={{
                    maxWidth: msg.role === "user" ? "72%" : "78%",
                    ...(msg.role === "user" ? {
                      background: "var(--blue-light)",
                      border: "1px solid #d0e6f7",
                      borderRadius: "var(--radius) var(--radius) 4px var(--radius)",
                      padding: "10px 16px",
                    } : {
                      background: "transparent",
                      padding: "2px 0",
                    }),
                  }}>
                    {msg.role === "assistant" && msg.output_language && msg.output_language !== "en" && (
                      <div style={{
                        fontSize: 11, color: "var(--text-muted)",
                        marginBottom: 6,
                        display: "flex", alignItems: "center", gap: 4,
                      }}>
                        <span>🌍</span>
                        <span>Response in {LANG_NAMES[msg.output_language] ?? msg.output_language}</span>
                      </div>
                    )}

                    <div style={{
                      fontSize: 15,
                      lineHeight: 1.65,
                      color: msg.role === "user" ? "var(--blue-mid)" : "var(--text-primary)",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}>
                      {msg.content}
                    </div>

                    {/* Metadata row */}
                    {msg.role === "assistant" && msg.providers_used && msg.providers_used.length > 0 && (
                      <div style={{
                        marginTop: 10,
                        display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8,
                      }}>
                        {msg.providers_used.map((p) => (
                          <span key={p} style={{
                            fontSize: 11, fontWeight: 500,
                            padding: "2px 8px",
                            borderRadius: "var(--radius-full)",
                            background: `${PROVIDER_COLORS[p] ?? "#8a93b0"}14`,
                            color: PROVIDER_COLORS[p] ?? "var(--text-muted)",
                            border: `1px solid ${PROVIDER_COLORS[p] ?? "#8a93b0"}2a`,
                          }}>
                            {PROVIDER_LABELS[p] ?? p}
                          </span>
                        ))}
                        {msg.total_latency_ms && (
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            {(msg.total_latency_ms / 1000).toFixed(1)}s
                          </span>
                        )}
                        {msg.total_cost_usd !== undefined && msg.total_cost_usd > 0 && (
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            ${msg.total_cost_usd.toFixed(4)}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* Live progress */}
              {isLoading && (
                <div style={{ padding: "8px 24px 8px 66px" }}>
                  <WorkflowProgress
                    workflowId={activeWorkflowId}
                    isRunning={isLoading}
                  />
                </div>
              )}

              {/* Error */}
              {error && (
                <div style={{
                  margin: "8px 24px",
                  padding: "10px 14px",
                  borderRadius: "var(--radius-sm)",
                  background: "#fef2f2",
                  border: "1px solid #fecaca",
                  color: "#dc2626",
                  fontSize: 13,
                }}>
                  {error}
                </div>
              )}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area — Gemini-style glowing search bar */}
        <div style={{
          padding: "16px 24px 20px",
          background: isEmpty ? "transparent" : "#ffffff",
          borderTop: isEmpty ? "none" : "1px solid var(--border)",
          flexShrink: 0,
        }}>
          <div style={{
            maxWidth: isEmpty ? 680 : "100%",
            margin: isEmpty ? "0 auto" : "0",
            position: "relative",
          }}>
            {/* Glow ring — shows on focus, like Gemini */}
            <div style={{
              position: "absolute",
              inset: -2,
              borderRadius: "var(--radius-lg)",
              background: inputFocused
                ? "linear-gradient(135deg, #4a90d9, #2d72c2, #f5835a)"
                : "transparent",
              opacity: inputFocused ? 0.35 : 0,
              transition: "opacity 0.3s ease",
              zIndex: 0,
              filter: "blur(8px)",
            }} />

            <div style={{
              position: "relative",
              zIndex: 1,
              background: "#ffffff",
              border: `1.5px solid ${inputFocused ? "var(--blue)" : "var(--border)"}`,
              borderRadius: "var(--radius-lg)",
              transition: "border-color 0.2s ease",
              boxShadow: inputFocused
                ? "0 0 0 4px var(--blue-glow)"
                : "0 1px 4px rgba(0,0,0,0.06)",
              display: "flex",
              flexDirection: "column",
            }}>
              <textarea
                ref={textareaRef}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={() => setInputFocused(true)}
                onBlur={() => setInputFocused(false)}
                placeholder={
                  inputLanguage === "lg" ? "Wandiika wano mu Luganda…"
                  : inputLanguage === "sw" ? "Andika hapa kwa Kiswahili…"
                  : "Ask anything…"
                }
                disabled={isLoading}
                rows={1}
                style={{
                  width: "100%",
                  background: "transparent",
                  border: "none",
                  outline: "none",
                  resize: "none",
                  padding: "14px 18px 10px",
                  fontSize: 15,
                  color: "var(--text-primary)",
                  lineHeight: 1.55,
                  minHeight: 52,
                  maxHeight: 160,
                  overflowY: "auto",
                  fontFamily: "var(--font)",
                }}
              />

              {/* Bottom row */}
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 12px 10px",
              }}>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  Enter to send · Shift+Enter for new line
                </span>
                <button
                  onClick={() => void handleSubmit()}
                  disabled={isLoading || !prompt.trim()}
                  style={{
                    height: 34,
                    padding: "0 18px",
                    borderRadius: "var(--radius-full)",
                    border: "none",
                    background: isLoading || !prompt.trim()
                      ? "var(--surface-2)"
                      : "linear-gradient(135deg, var(--blue) 0%, var(--blue-mid) 100%)",
                    color: isLoading || !prompt.trim() ? "var(--text-muted)" : "#ffffff",
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: isLoading || !prompt.trim() ? "not-allowed" : "pointer",
                    transition: "all 0.15s",
                    display: "flex", alignItems: "center", gap: 6,
                    fontFamily: "var(--font)",
                  }}
                >
                  {isLoading ? (
                    <>
                      <div style={{
                        width: 12, height: 12,
                        border: "2px solid rgba(255,255,255,0.3)",
                        borderTopColor: "var(--text-muted)",
                        borderRadius: "50%",
                        animation: "spin 0.8s linear infinite",
                      }} />
                      Working…
                    </>
                  ) : (
                    <>Send ↑</>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
