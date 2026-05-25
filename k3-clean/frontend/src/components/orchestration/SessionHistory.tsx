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
    <div style={{
      display: "flex",
      flexDirection: "column",
      height: "100%",
      background: "#ffffff",
      borderRight: "1px solid var(--border)",
    }}>
      {/* Header */}
      <div style={{
        padding: "14px 16px 12px",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {/* K3 logo mark */}
          <div style={{
            width: 26, height: 26,
            borderRadius: 7,
            background: "linear-gradient(135deg, var(--blue) 0%, var(--blue-mid) 100%)",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <span style={{ color: "#fff", fontSize: 11, fontWeight: 600, letterSpacing: "-0.5px" }}>K3</span>
          </div>
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>
            Conversations
          </span>
        </div>
        <button
          onClick={onNewSession}
          title="New conversation"
          style={{
            width: 28, height: 28,
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border)",
            background: "var(--surface-2)",
            color: "var(--text-secondary)",
            cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18, lineHeight: 1,
            transition: "all 0.15s",
          }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLButtonElement).style.background = "var(--blue-light)";
            (e.currentTarget as HTMLButtonElement).style.color = "var(--blue)";
            (e.currentTarget as HTMLButtonElement).style.borderColor = "#c5d9ef";
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)";
            (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
            (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
          }}
        >
          +
        </button>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "32px 0", color: "var(--text-muted)", fontSize: 13 }}>
            Loading…
          </div>
        ) : sessions.length === 0 ? (
          <div style={{ textAlign: "center", padding: "40px 16px", color: "var(--text-muted)", fontSize: 13, lineHeight: 1.6 }}>
            <div style={{ fontSize: 24, marginBottom: 8 }}>💬</div>
            No conversations yet.<br />
            Start a new one above.
          </div>
        ) : (
          sessions.map((session) => {
            const isActive = activeSessionId === session.id;
            return (
              <div
                key={session.id}
                onClick={() => onSelectSession(session)}
                className="group"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 3,
                  padding: "9px 10px",
                  borderRadius: "var(--radius-sm)",
                  cursor: "pointer",
                  marginBottom: 2,
                  background: isActive ? "var(--blue-light)" : "transparent",
                  borderLeft: isActive ? "3px solid var(--blue)" : "3px solid transparent",
                  transition: "all 0.12s",
                  position: "relative",
                }}
                onMouseEnter={e => {
                  if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "var(--surface-2)";
                }}
                onMouseLeave={e => {
                  if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "transparent";
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 4 }}>
                  <span style={{
                    fontSize: 13,
                    fontWeight: isActive ? 500 : 400,
                    color: isActive ? "var(--blue-mid)" : "var(--text-primary)",
                    lineHeight: 1.35,
                    flex: 1,
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                  }}>
                    {session.title}
                  </span>
                  <button
                    onClick={(e) => handleArchive(e, session.id)}
                    title="Delete"
                    style={{
                      opacity: 0,
                      flexShrink: 0,
                      width: 18, height: 18,
                      borderRadius: 4,
                      border: "none",
                      background: "transparent",
                      color: "var(--text-muted)",
                      cursor: "pointer",
                      fontSize: 14,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      transition: "opacity 0.15s",
                    }}
                    className="session-delete-btn"
                  >
                    ×
                  </button>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-muted)" }}>
                  <span>{timeAgo(session.last_active)}</span>
                  <span>·</span>
                  <span>{session.message_count} msgs</span>
                  {session.input_language !== "en" && (
                    <span>{LANG_FLAGS[session.input_language] ?? "🌍"}</span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      <style>{`
        .group:hover .session-delete-btn { opacity: 1 !important; }
      `}</style>
    </div>
  );
}
