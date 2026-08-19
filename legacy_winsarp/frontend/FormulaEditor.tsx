import { useRef, useState, useCallback } from "react";
import Editor, { OnMount, BeforeMount } from "@monaco-editor/react";
import { winsarpLanguage, winsarpTheme, winsarpThemeLight } from "./winsarpLanguage";

interface ValidationIssue {
  severity: string;
  message: string;
  line: number;
}

interface ValidationResult {
  valid: boolean;
  issues: ValidationIssue[];
}

interface FormulaEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string;
  label?: string;
  isDarkMode?: boolean;
  onValidate?: (value: string) => Promise<ValidationResult>;
}

export default function FormulaEditor({
  value,
  onChange,
  readOnly = false,
  height = "300px",
  label,
  isDarkMode = true,
  onValidate,
}: FormulaEditorProps) {
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const [copied, setCopied] = useState(false);
  const [errorCount, setErrorCount] = useState(0);
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [showIssues, setShowIssues] = useState(false);

  const handleBeforeMount: BeforeMount = useCallback((monaco) => {
    monaco.languages.register({ id: "winsarp" });
    monaco.languages.setMonarchTokensProvider("winsarp", winsarpLanguage);
    monaco.editor.defineTheme("winsarp-dark", winsarpTheme);
    monaco.editor.defineTheme("winsarp-light", winsarpThemeLight);
  }, []);

  const handleMount: OnMount = useCallback((editor, monaco) => {
    editorRef.current = editor;

    const updateErrors = () => {
      const model = editor.getModel();
      if (!model) return;
      const markers = monaco.editor.getModelMarkers({ resource: model.uri });
      setErrorCount(markers.length);
    };

    editor.onDidChangeModelDecorations(updateErrors);
    updateErrors();
  }, []);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  };

  const handleValidate = async () => {
    if (!onValidate || validating) return;
    setValidating(true);
    setShowIssues(true);
    try {
      const result = await onValidate(value);
      setValidationResult(result);
    } catch {
      setValidationResult({ valid: false, issues: [{ severity: "error", message: "Errore di connessione al server", line: 0 }] });
    } finally {
      setValidating(false);
    }
  };

  const errorIssues = validationResult?.issues.filter(i => i.severity === "error") ?? [];
  const warningIssues = validationResult?.issues.filter(i => i.severity === "warning") ?? [];

  return (
    <div className="space-y-2">
      {label && (
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400">
            {label}
          </label>
          <div className="flex items-center gap-3">
            {validationResult && !showIssues && (
              <span className={`text-xs ${validationResult.valid ? "text-green-500" : "text-red-400"}`}>
                {validationResult.valid ? "OK" : `${errorIssues.length} error${errorIssues.length !== 1 ? "i" : "e"}`}
              </span>
            )}
            {errorCount > 0 && (
              <span className="text-xs text-amber-400">
                {errorCount} validation {errorCount === 1 ? "issue" : "issues"}
              </span>
            )}
            {onValidate && (
              <button
                onClick={handleValidate}
                disabled={validating}
                className={`text-xs transition font-medium ${validating ? "text-gray-400 cursor-not-allowed" : "text-emerald-500 hover:text-emerald-400"}`}
              >
                {validating ? "Verifica..." : "Verifica"}
              </button>
            )}
            <button
              onClick={handleCopy}
              className="text-xs text-blue-400 hover:text-blue-300 transition font-medium"
            >
              {copied ? "Copiato!" : "Copia"}
            </button>
          </div>
        </div>
      )}

      {validationResult && showIssues && (
        <div className={`rounded-lg border p-3 text-xs space-y-1 ${
          validationResult.valid
            ? "border-green-500/30 bg-green-500/5 text-green-600 dark:text-green-400"
            : "border-red-500/30 bg-red-500/5 text-red-600 dark:text-red-400"
        }`}>
          <div className="flex items-center justify-between">
            <span className="font-semibold">
              {validationResult.valid ? "Formula valida" : `${errorIssues.length} error${errorIssues.length !== 1 ? "i" : ""}${warningIssues.length ? `, ${warningIssues.length} warning` : ""}`}
            </span>
            <button onClick={() => setShowIssues(false)} className="opacity-60 hover:opacity-100">&times;</button>
          </div>
          {!validationResult.valid && (
            <ul className="list-disc list-inside space-y-0.5 mt-1">
              {errorIssues.map((issue, i) => (
                <li key={i}>
                  {issue.line > 0 && <span className="opacity-60">Riga {issue.line}: </span>}
                  {issue.message}
                </li>
              ))}
              {warningIssues.map((issue, i) => (
                <li key={`w-${i}`} className="opacity-70">
                  {issue.line > 0 && <span className="opacity-60">Riga {issue.line}: </span>}
                  ⚠ {issue.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="border border-gray-200 dark:border-white/[0.06] rounded-xl overflow-hidden transition focus-within:border-blue-500/50">
        <Editor
          height={height}
          defaultLanguage="winsarp"
          defaultValue=""
          value={value}
          onChange={(v) => {
            onChange?.(v || "");
            setValidationResult(null);
            setShowIssues(false);
          }}
          beforeMount={handleBeforeMount}
          onMount={handleMount}
          theme={isDarkMode ? "winsarp-dark" : "winsarp-light"}
          options={{
            readOnly,
            minimap: { enabled: false },
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace",
            lineNumbers: "on",
            renderLineHighlight: "line",
            scrollBeyondLastLine: false,
            wordWrap: "on",
            tabSize: 2,
            automaticLayout: true,
            padding: { top: 12, bottom: 12 },
            bracketPairColorization: { enabled: true },
            folding: true,
            foldingHighlight: true,
            glyphMargin: false,
            lineDecorationsWidth: 8,
            lineNumbersMinChars: 3,
          }}
        />
      </div>
    </div>
  );
}
