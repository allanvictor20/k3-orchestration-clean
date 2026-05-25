import { useEffect, useState } from "react";
import { getSupportedLanguages, type Language } from "@/lib/api";

interface Props {
  inputLanguage: string;
  outputLanguage: string;
  onInputChange: (code: string) => void;
  onOutputChange: (code: string) => void;
  disabled?: boolean;
}

const DEFAULTS: Language[] = [
  { code: "en",  name: "English" },
  { code: "lg",  name: "Luganda" },
  { code: "sw",  name: "Swahili" },
  { code: "ach", name: "Acholi" },
  { code: "nyn", name: "Runyankole" },
  { code: "kin", name: "Kinyarwanda" },
];

const selectStyle: React.CSSProperties = {
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  color: "var(--text-secondary)",
  fontSize: 12,
  fontWeight: 500,
  borderRadius: "var(--radius-full)",
  padding: "4px 10px",
  cursor: "pointer",
  outline: "none",
  appearance: "none",
  WebkitAppearance: "none",
  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%238a93b0' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 8px center",
  paddingRight: 24,
};

export function LanguageSelector({
  inputLanguage,
  outputLanguage,
  onInputChange,
  onOutputChange,
  disabled = false,
}: Props) {
  const [languages, setLanguages] = useState<Language[]>(DEFAULTS);

  useEffect(() => {
    getSupportedLanguages()
      .then((langs) => { if (langs.length > 0) setLanguages(langs); })
      .catch(() => {});
  }, []);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500 }}>In</span>
      <select
        value={inputLanguage}
        onChange={(e) => onInputChange(e.target.value)}
        disabled={disabled}
        style={{ ...selectStyle, opacity: disabled ? 0.5 : 1 }}
      >
        <option value="auto">Auto-detect</option>
        {languages.map((l) => (
          <option key={l.code} value={l.code}>{l.name}</option>
        ))}
      </select>

      <span style={{ color: "var(--text-muted)", fontSize: 13 }}>→</span>

      <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500 }}>Out</span>
      <select
        value={outputLanguage}
        onChange={(e) => onOutputChange(e.target.value)}
        disabled={disabled}
        style={{ ...selectStyle, opacity: disabled ? 0.5 : 1 }}
      >
        {languages.map((l) => (
          <option key={l.code} value={l.code}>{l.name}</option>
        ))}
      </select>
    </div>
  );
}
