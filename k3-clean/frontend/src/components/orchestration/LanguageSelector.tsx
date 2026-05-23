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

const SELECT =
  "bg-[#1e1e1e] border border-[#333] text-[#ccc] text-xs rounded px-2 py-1 " +
  "focus:outline-none focus:border-[#555] disabled:opacity-50 cursor-pointer";

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
    <div className="flex items-center gap-2 text-xs text-[#888]">
      <div className="flex items-center gap-1.5">
        <span>In:</span>
        <select
          value={inputLanguage}
          onChange={(e) => onInputChange(e.target.value)}
          disabled={disabled}
          className={SELECT}
        >
          <option value="auto">Auto-detect</option>
          {languages.map((l) => (
            <option key={l.code} value={l.code}>{l.name}</option>
          ))}
        </select>
      </div>
      <span className="text-[#444]">→</span>
      <div className="flex items-center gap-1.5">
        <span>Out:</span>
        <select
          value={outputLanguage}
          onChange={(e) => onOutputChange(e.target.value)}
          disabled={disabled}
          className={SELECT}
        >
          {languages.map((l) => (
            <option key={l.code} value={l.code}>{l.name}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
