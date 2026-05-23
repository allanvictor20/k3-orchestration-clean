/**
 * sse.ts — SSE connection manager for real-time workflow progress.
 * Connects to Python's /orchestrate/stream/{workflow_id} endpoint.
 */

export interface WorkflowEvent {
  event: string;
  workflow_id: string;
  subtask_id?: string;
  provider?: string;
  task_type?: string;
  description?: string;
  latency_ms?: number;
  tokens?: number;
  success?: boolean;
  error?: string;
  final_output_preview?: string;
  total_cost_usd?: number;
  total_latency_ms?: number;
  providers_used?: string[];
  input_language?: string;
  output_language?: string;
}

export type WorkflowEventHandler = (event: WorkflowEvent) => void;

export function subscribeToWorkflow(
  workflowId: string,
  onEvent: WorkflowEventHandler,
  onComplete?: () => void,
  onError?: (error: string) => void
): () => void {
  const source = new EventSource(`/orchestrate/stream/${workflowId}`);

  const eventTypes = [
    "heartbeat",
    "task_started",
    "provider_selected",
    "retry_triggered",
    "task_completed",
    "merge_started",
    "merge_completed",
    "workflow_completed",
    "workflow_failed",
    "progress",
  ];

  eventTypes.forEach((eventType) => {
    source.addEventListener(eventType, (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        onEvent({ event: eventType, ...data });

        if (eventType === "workflow_completed") {
          source.close();
          onComplete?.();
        } else if (eventType === "workflow_failed") {
          source.close();
          onError?.(data.error || "Workflow failed");
        }
      } catch {
        // ignore keepalive parse errors
      }
    });
  });

  source.onerror = () => {
    source.close();
    onError?.("Connection lost");
  };

  return () => source.close();
}
