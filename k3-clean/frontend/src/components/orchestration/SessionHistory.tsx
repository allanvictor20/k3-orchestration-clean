import { useEffect, useState } from "react";
import { listSessions, archiveSession, type Session } from "@/lib/api";

interface Props {
  activeSessionId: string | null;
  onSelectSession: (session: Session) => void;
  onNewSession: () => void;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1)  return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const LANG_FLAGS: Record<string, string> = {
  en: "🇬🇧", lg: "🇺🇬", sw: "🇹🇿", ach: "🇺🇬", nyn: "🇺🇬", kin: "🇷🇼",
};

export function SessionHistory({ activeSessionId, onSelectSession, onNewSession }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading]   = useState(true);

  const refresh = () => {
    listSessions()
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15_000);
    return () => clearInterval(id);
  }, []);

  async function handleArchive(e: React.MouseEvent, sessionId: string) {
    e.stopPropagation();
    await archiveSession(sessionId);
    refresh();
  }

  return (
    <div className="flex flex-col h-full bg-[#111] border-r border-[#1e1e1e]">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-[#1e1e1e]">
        <span className="text-[10px] font-medium text-[#666] uppercase tracking-widest">
          Sessions
        </span>
        <button
          onClick={onNewSession}
          className="text-xs text-[#555] hover:text-[#aaa] px-1.5 py-0.5 rounded hover:bg-[#1e1e1e] transition-colors"
          title="New session"
        >
          + New
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="text-xs text-[#444] text-center py-8">Loading…</div>
        ) : sessions.length === 0 ? (
          <div className="text-xs text-[#444] text-center py-8 px-3">
            No sessions yet.
          </div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.id}
              onClick={() => onSelectSession(session)}
              className={`group flex flex-col gap-0.5 px-3 py-2.5 cursor-pointer border-b border-[#1a1a1a] transition-colors ${
                activeSessionId === session.id
                  ? "bg-[#1e1e1e] border-l-2 border-l-amber-600"
                  : "hover:bg-[#161616]"
              }`}
            >
              <div className="flex items-start justify-between gap-1">
                <span className="text-xs text-[#ccc] leading-tight line-clamp-2 flex-1">
                  {session.title}
                </span>
                <button
                  onClick={(e) => handleArchive(e, session.id)}
                  className="opacity-0 group-hover:opacity-100 text-[#444] hover:text-[#888] text-xs transition-all ml-1 flex-shrink-0"
                  title="Archive"
                >
                  ×
                </button>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-[#555]">
                <span>{timeAgo(session.last_active)}</span>
                <span>·</span>
                <span>{session.message_count} msgs</span>
                {session.input_language !== "en" && (
                  <span title={session.input_language}>
                    {LANG_FLAGS[session.input_language] ?? "🌍"}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
