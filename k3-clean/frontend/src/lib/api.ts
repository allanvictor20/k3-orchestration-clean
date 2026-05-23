/**
 * api.ts — HTTP client for the K3 orchestration backend.
 * All calls go through Vite's dev proxy to http://localhost:8716.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface OrchestrationRequest {
  workflow_id?: string;
  prompt: string;
  input_language?: string;
  output_language?: string;
  session_id?: string;
}

export interface AgentResult {
  subtask_id: string;
  provider: string;
  output: string;
  latency_ms: number;
  token_usage: number;
  cost_usd: number;
  success: boolean;
  error?: string;
}

export interface OrchestrationResponse {
  workflow_id: string;
  final_output: string;
  subtask_results: AgentResult[];
  total_cost_usd: number;
  total_latency_ms: number;
  providers_used: string[];
  input_language: string;
  output_language: string;
  session_id?: string;
  created_at: string;
}

export interface Session {
  id: string;
  title: string;
  input_language: string;
  output_language: string;
  created_at: string;
  last_active: string;
  status: string;
  message_count: number;
  messages?: SessionMessage[];
}

export interface SessionMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  workflow_id?: string;
  input_language: string;
  output_language: string;
  created_at: string;
}

export interface Language {
  code: string;
  name: string;
}

export interface MCPTool {
  name: string;
  description: string;
  server: string;
}

export interface ProviderPerformanceStat {
  provider: string;
  task_type: string;
  avg_latency_ms: number;
  total_runs: number;
  successes: number;
}

// ---------------------------------------------------------------------------
// Core orchestration
// ---------------------------------------------------------------------------

export async function runOrchestration(
  request: OrchestrationRequest
): Promise<OrchestrationResponse> {
  const res = await fetch("/orchestrate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || "Orchestration failed");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

export async function createSession(params: {
  title?: string;
  input_language?: string;
  output_language?: string;
}): Promise<Session> {
  const res = await fetch("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function listSessions(): Promise<Session[]> {
  const res = await fetch("/sessions");
  if (!res.ok) throw new Error("Failed to list sessions");
  return res.json();
}

export async function getSession(sessionId: string): Promise<Session> {
  const res = await fetch(`/sessions/${sessionId}`);
  if (!res.ok) throw new Error("Session not found");
  return res.json();
}

export async function sendSessionPrompt(
  sessionId: string,
  prompt: string,
  inputLanguage?: string,
  outputLanguage?: string
): Promise<OrchestrationResponse> {
  const res = await fetch(`/sessions/${sessionId}/prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      input_language: inputLanguage,
      output_language: outputLanguage,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || "Session prompt failed");
  }
  return res.json();
}

export async function archiveSession(sessionId: string): Promise<void> {
  await fetch(`/sessions/${sessionId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Languages
// ---------------------------------------------------------------------------

export async function getSupportedLanguages(): Promise<Language[]> {
  const res = await fetch("/languages");
  if (!res.ok) return [];
  const data = await res.json();
  return data.languages || [];
}

// ---------------------------------------------------------------------------
// MCP tools
// ---------------------------------------------------------------------------

export async function listMCPTools(): Promise<MCPTool[]> {
  const res = await fetch("/mcp/tools");
  if (!res.ok) return [];
  const data = await res.json();
  return data.tools || [];
}

// ---------------------------------------------------------------------------
// Health & providers
// ---------------------------------------------------------------------------

export async function getHealth() {
  const res = await fetch("/health");
  return res.json();
}

export async function getProviderStatus() {
  const res = await fetch("/providers/status");
  return res.json();
}

export async function getProviderPerformance(taskType?: string): Promise<{ stats: ProviderPerformanceStat[] }> {
  const url = taskType
    ? `/providers/performance?task_type=${taskType}`
    : "/providers/performance";
  const res = await fetch(url);
  return res.json();
}

export async function getWorkflows(limit = 20) {
  const res = await fetch(`/workflows?limit=${limit}`);
  return res.json();
}

export async function getWorkflow(workflowId: string) {
  const res = await fetch(`/workflows/${workflowId}`);
  return res.json();
}

export async function getWorkflowAudit(workflowId: string) {
  const res = await fetch(`/workflows/${workflowId}/audit`);
  return res.json();
}
