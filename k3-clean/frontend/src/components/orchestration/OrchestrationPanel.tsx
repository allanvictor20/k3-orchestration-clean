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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROVIDER_LABELS: Record<string, string> = {
  anthropic:  "Claude",
  openai:     "GPT-4o",
  perplexity: "Perplexity",
  gemini:     "Gemini",
  sunbird:    "Sunbird",
};

const LANG_NAMES: Record<string, string> = {
  en: "English", lg: "Luganda", sw: "Swahili",
  ach: "Acholi", nyn: "Runyankole", kin: "Kinyarwanda",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function OrchestrationPanel() {
  const [messages,       setMessages]       = useState<Message[]>([]);
  const [prompt,         setPrompt]         = useState("");
  const [inputLanguage,  setInputLanguage]  = useState("en");
  const [outputLanguage, setOutputLanguage] = useState("en");
  const [isLoading,      setIsLoading]      = useState(false);
  const [activeWorkflowId, setActiveWorkflowId] = useState<string | null>(null);
  const [activeSession,  setActiveSession]  = useState<Session | null>(null);
  const [showSidebar,    setShowSidebar]    = useState(true);
  const [error,          setError]          = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef    = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ---------------------------------------------------------------------------
  // Session management
  // ---------------------------------------------------------------------------

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

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------

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
          activeSession.id,
          userPrompt,
          inputLanguage,
          outputLanguage
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

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex h-full bg-[#0d0d0d] text-[#ccc] font-sans">

      {/* Sidebar */}
      {showSidebar && (
        <div className="w-56 flex-shrink-0">
          <SessionHistory
            activeSessionId={activeSession?.id ?? null}
            onSelectSession={handleSelectSession}
            onNewSession={handleNewSession}
          />
        </div>
      )}

      {/* Main panel */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Top bar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-[#1e1e1e] bg-[#111]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowSidebar((v) => !v)}
              className="text-[#555] hover:text-[#aaa] text-sm transition-colors"
              title="Toggle sidebar"
            >
              ☰
            </button>
            <span className="text-xs font-medium text-[#555]">
              {activeSession ? activeSession.title : "K3 Orchestration"}
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

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-[#2a2a2a] text-sm mt-20">
              <div className="text-3xl mb-3">◈</div>
              <div className="text-[#444]">Multi-model AI orchestration</div>
              <div className="text-xs mt-1 text-[#333]">
                Claude · GPT-4o · Perplexity · Gemini · Sunbird
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-3.5 py-2.5 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-[#1a1a1a] text-[#ddd] border border-[#2a2a2a]"
                    : "bg-[#111] text-[#ccc]"
                }`}
              >
                {/* Language badge */}
                {msg.role === "assistant" && msg.output_language && msg.output_language !== "en" && (
                  <div className="text-[10px] text-[#555] mb-1.5">
                    Response in {LANG_NAMES[msg.output_language] ?? msg.output_language}
                  </div>
                )}

                <div className="whitespace-pre-wrap">{msg.content}</div>

                {/* Metadata */}
                {msg.role === "assistant" && msg.providers_used && (
                  <div className="mt-2 pt-2 border-t border-[#1e1e1e] flex flex-wrap gap-2 text-[10px] text-[#444]">
                    <span>
                      {msg.providers_used.map((p) => PROVIDER_LABELS[p] ?? p).join(" · ")}
                    </span>
                    {msg.total_latency_ms && (
                      <span>{(msg.total_latency_ms / 1000).toFixed(1)}s</span>
                    )}
                    {msg.total_cost_usd !== undefined && msg.total_cost_usd > 0 && (
                      <span>${msg.total_cost_usd.toFixed(4)}</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Live progress */}
          {isLoading && (
            <WorkflowProgress
              workflowId={activeWorkflowId}
              isRunning={isLoading}
            />
          )}

          {/* Error */}
          {error && (
            <div className="text-xs text-red-400 bg-red-950/20 border border-red-900/30 rounded px-3 py-2">
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="border-t border-[#1e1e1e] bg-[#111] px-4 py-3">
          <div className="flex gap-2 items-end">
            <textarea
              ref={textareaRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                inputLanguage === "lg" ? "Wandiika wano mu Luganda…"
                : inputLanguage === "sw" ? "Andika hapa kwa Kiswahili…"
                : "Type your prompt… (Shift+Enter for new line)"
              }
              disabled={isLoading}
              rows={3}
              className="flex-1 bg-[#0d0d0d] border border-[#222] rounded-lg px-3 py-2.5 text-sm text-[#ccc] placeholder-[#333] resize-none focus:outline-none focus:border-[#333] disabled:opacity-50 leading-relaxed"
            />
            <button
              onClick={() => void handleSubmit()}
              disabled={isLoading || !prompt.trim()}
              className="flex-shrink-0 bg-[#1a1a1a] hover:bg-[#222] border border-[#2a2a2a] text-[#888] hover:text-[#ccc] disabled:opacity-30 disabled:cursor-not-allowed px-4 py-2.5 rounded-lg text-sm transition-colors"
            >
              {isLoading ? "…" : "Send"}
            </button>
          </div>
          <div className="mt-1.5 text-[10px] text-[#333] text-right">
            Enter to send · Shift+Enter for new line
          </div>
        </div>
      </div>
    </div>
  );
}
