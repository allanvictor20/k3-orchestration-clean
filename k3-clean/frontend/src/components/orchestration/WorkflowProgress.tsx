import { useEffect, useRef, useState } from "react";
import { subscribeToWorkflow, type WorkflowEvent } from "@/lib/sse";

interface SubtaskProgress {
  subtask_id: string;
  provider: string;
  task_type: string;
  status: "pending" | "running" | "done" | "failed";
  latency_ms?: number;
}

interface Props {
  workflowId: string | null;
  isRunning: boolean;
}

const PROVIDER_COLORS: Record<string, string> = {
  anthropic:  "#f5835a",
  openai:     "#16a34a",
  perplexity: "#7c3aed",
  gemini:     "#4a90d9",
  sunbird:    "#e8a020",
};

const PROVIDER_LABELS: Record<string, string> = {
  anthropic:  "Claude",
  openai:     "GPT-4o",
  perplexity: "Perplexity",
  gemini:     "Gemini",
  sunbird:    "Sunbird",
};

export function WorkflowProgress({ workflowId, isRunning }: Props) {
  const [subtasks, setSubtasks] = useState<SubtaskProgress[]>([]);
  const [phase, setPhase]       = useState("");
  const [events, setEvents]     = useState<string[]>([]);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!workflowId || !isRunning) return;
    setSubtasks([]);
    setEvents([]);
    setPhase("Starting…");

    const unsub = subscribeToWorkflow(workflowId, (event: WorkflowEvent) => {
      switch (event.event) {
        case "provider_selected":
          setSubtasks((prev) => {
            if (prev.find((s) => s.subtask_id === event.subtask_id)) return prev;
            return [...prev, {
              subtask_id: event.subtask_id!,
              provider: event.provider!,
              task_type: "",
              status: "pending",
            }];
          });
          setPhase("Planning…");
          break;

        case "task_started":
          setSubtasks((prev) => prev.map((s) =>
            s.subtask_id === event.subtask_id
              ? { ...s, status: "running", task_type: event.task_type || "" }
              : s
          ));
          setPhase("Working on it…");
          addEvent(`${PROVIDER_LABELS[event.provider!] ?? event.provider} → ${event.task_type}`);
          break;

        case "task_completed":
          setSubtasks((prev) => prev.map((s) =>
            s.subtask_id === event.subtask_id
              ? { ...s, status: event.success ? "done" : "failed", latency_ms: event.latency_ms }
              : s
          ));
          addEvent(
            event.success
              ? `${PROVIDER_LABELS[event.provider!] ?? event.provider} finished (${event.latency_ms}ms)`
              : `${event.provider} failed: ${event.error}`
          );
          break;

        case "retry_triggered":
          addEvent(`Retrying with ${event.provider}…`);
          break;

        case "merge_started":
          setPhase("Putting it all together…");
          addEvent("Combining all results…");
          break;

        case "workflow_completed":
          setPhase("Done");
          addEvent(`Completed in ${((event.total_latency_ms ?? 0) / 1000).toFixed(1)}s`);
          break;

        case "workflow_failed":
          setPhase("Something went wrong");
          addEvent(`Error: ${event.error}`);
          break;
      }
    });

    cleanupRef.current = unsub;
    return () => unsub();
  }, [workflowId, isRunning]);

  function addEvent(msg: string) {
    setEvents((prev) => [...prev.slice(-20), msg]);
  }

  if (!workflowId && !isRunning) return null;

  const isDone = phase === "Done";
  const isFailed = phase === "Something went wrong";

  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: "var(--radius)",
      background: "#ffffff",
      padding: "14px 16px",
      display: "flex",
      flexDirection: "column",
      gap: 10,
      animation: "fadeUp 0.2s ease",
    }}>
      {/* Phase indicator */}
      {phase && (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {isRunning && !isDone && !isFailed && (
            <div style={{
              width: 16, height: 16, borderRadius: "50%",
              border: "2px solid var(--blue-light)",
              borderTopColor: "var(--blue)",
              animation: "spin 0.8s linear infinite",
              flexShrink: 0,
            }} />
          )}
          {isDone && (
            <div style={{
              width: 16, height: 16, borderRadius: "50%",
              background: "#dcfce7",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, color: "#16a34a",
            }}>✓</div>
          )}
          {isFailed && (
            <div style={{
              width: 16, height: 16, borderRadius: "50%",
              background: "#fee2e2",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, color: "#dc2626",
            }}>✗</div>
          )}
          <span style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500 }}>
            {phase}
          </span>
        </div>
      )}

      {/* Subtask pills */}
      {subtasks.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {subtasks.map((s) => {
            const color = PROVIDER_COLORS[s.provider] ?? "#8a93b0";
            const label = PROVIDER_LABELS[s.provider] ?? s.provider;
            return (
              <div
                key={s.subtask_id}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  fontSize: 12, fontWeight: 500,
                  padding: "4px 10px",
                  borderRadius: "var(--radius-full)",
                  border: `1px solid ${color}33`,
                  background: `${color}12`,
                  color: s.status === "running" ? color : "var(--text-muted)",
                  transition: "all 0.2s",
                }}
              >
                {s.status === "running" && (
                  <span style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: color,
                    animation: "pulse-dot 1s ease infinite",
                    flexShrink: 0,
                  }} />
                )}
                {s.status === "done" && (
                  <span style={{ color: "#16a34a", fontSize: 11 }}>✓</span>
                )}
                {s.status === "failed" && (
                  <span style={{ color: "#dc2626", fontSize: 11 }}>✗</span>
                )}
                <span style={{ color }}>{label}</span>
                {s.task_type && (
                  <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>· {s.task_type}</span>
                )}
                {s.latency_ms && (
                  <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                    {(s.latency_ms / 1000).toFixed(1)}s
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Event log - just last 3 */}
      {events.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {events.slice(-3).map((msg, i) => (
            <div key={i} style={{ fontSize: 11, color: "var(--text-muted)" }}>
              {msg}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
