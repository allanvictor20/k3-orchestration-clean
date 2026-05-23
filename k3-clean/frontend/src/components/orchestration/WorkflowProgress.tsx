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
  anthropic:  "#d97706",
  openai:     "#16a34a",
  perplexity: "#7c3aed",
  gemini:     "#0284c7",
  sunbird:    "#db2777",
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
          setPhase("Running…");
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
              ? `${PROVIDER_LABELS[event.provider!] ?? event.provider} done (${event.latency_ms}ms)`
              : `${event.provider} failed: ${event.error}`
          );
          break;

        case "retry_triggered":
          addEvent(`Retrying with ${event.provider}…`);
          break;

        case "merge_started":
          setPhase("Merging results…");
          addEvent("Claude is synthesising outputs…");
          break;

        case "workflow_completed":
          setPhase("Complete ✓");
          addEvent(`Done — $${event.total_cost_usd?.toFixed(4)} · ${event.total_latency_ms}ms`);
          break;

        case "workflow_failed":
          setPhase("Failed");
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

  return (
    <div className="border border-[#2a2a2a] rounded-lg bg-[#161616] p-3 space-y-2.5">
      {phase && (
        <div className="flex items-center gap-2 text-xs text-[#888]">
          {isRunning && phase !== "Complete ✓" && phase !== "Failed" && (
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
          )}
          <span>{phase}</span>
        </div>
      )}

      {subtasks.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {subtasks.map((s) => {
            const color = PROVIDER_COLORS[s.provider] ?? "#666";
            const label = PROVIDER_LABELS[s.provider] ?? s.provider;
            const icon  = s.status === "running" ? "⏳"
                        : s.status === "done"    ? "✓"
                        : s.status === "failed"  ? "✗" : "○";
            return (
              <div
                key={s.subtask_id}
                className="flex items-center gap-1.5 text-xs px-2 py-1 rounded border"
                style={{
                  borderColor: color + "44",
                  backgroundColor: color + "11",
                  color: s.status === "running" ? color : "#888",
                }}
              >
                <span>{icon}</span>
                <span style={{ color }}>{label}</span>
                {s.task_type && <span className="text-[#555]">· {s.task_type}</span>}
                {s.latency_ms && (
                  <span className="text-[#555]">{(s.latency_ms / 1000).toFixed(1)}s</span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {events.length > 0 && (
        <div className="space-y-0.5">
          {events.slice(-5).map((msg, i) => (
            <div key={i} className="text-[11px] text-[#555]">{msg}</div>
          ))}
        </div>
      )}
    </div>
  );
}
