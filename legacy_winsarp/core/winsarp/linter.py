"""
core/linter.py
WinSarp static semantic linter.

Analizza step IR e formula compatta per errori semantici:
  - R/P target inesistenti nel workbook
  - Vxx label scope (definite ma mai usate, usate ma mai definite)
  - Field initialization violations (lettura prima di scrittura)
  - Loop detection (chiamate R/P circolari)
  - Codice irraggiungibile (dopo R/P/VF incondizionato)
  - VF mancante o extra
  - Type checking flag vs numerico
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

_logger = logging.getLogger(__name__)


class LintIssue:
    """Singolo issue di linting."""

    def __init__(self, severity: str, code: str, message: str, line: int = 0):
        self.severity = severity
        self.code = code
        self.message = message
        self.line = line

    def __str__(self):
        loc = f" [L{self.line}]" if self.line else ""
        return f"{self.severity.upper()} [{self.code}]: {self.message}{loc}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "line": self.line,
        }


class WinSarpLinter:
    """Linter semantico per formule WinSarp.

    Usage:
        linter = WinSarpLinter(valid_codici={5, 10, 100, ...})
        issues = linter.lint_ir(steps_list)
        issues += linter.lint_compact(formula_str)
    """

    LABEL_PATTERN = re.compile(r'\bV(\d{2})\b')
    R_P_PATTERN = re.compile(r'\b([RP])\s*(\d{2,5})\b')
    SET_PATTERN = re.compile(r'SET\s+(\d+)\s*=\s*(.+)', re.IGNORECASE)
    RESET_PATTERN = re.compile(r'RESET\s+(\d+)', re.IGNORECASE)
    FIELD_REF = re.compile(r'(?<!\w)(\d{2,4})(?!\w)')
    K_PATTERN = re.compile(r'K\s+(\d+)\s', re.IGNORECASE)
    IF_COND_PATTERN = re.compile(r'IF\s+(.+?)\s+THEN\s*$', re.IGNORECASE)

    def __init__(self, valid_codici: set[int] | None = None):
        self.valid_codici = valid_codici or set()

    # ---- IR-level lint ----

    def lint_ir(self, steps: list[str]) -> list[LintIssue]:
        """Lint su step IR strutturati (pre-compattazione)."""
        issues: list[LintIssue] = []

        if not steps:
            issues.append(LintIssue("error", "E001", "Nessuno step IR"))
            return issues

        issues.extend(self._check_vf_termination(steps))
        issues.extend(self._check_unreachable_code(steps))
        issues.extend(self._check_r_p_targets_ir(steps))
        issues.extend(self._check_vxx_labels_ir(steps))
        issues.extend(self._check_field_init(steps))
        issues.extend(self._check_flag_type_mismatch(steps))
        issues.extend(self._check_if_then_else_balance(steps))
        issues.extend(self._check_loop_detection(steps))

        return issues

    def lint_compact(self, formula: str) -> list[LintIssue]:
        """Lint su formula compatta (post-compattazione)."""
        issues: list[LintIssue] = []

        if not formula.strip():
            issues.append(LintIssue("error", "E001", "Formula compatta vuota"))
            return issues

        issues.extend(self._check_r_p_targets_compact(formula))
        issues.extend(self._check_vxx_labels_compact(formula))
        issues.extend(self._check_i_z_quoting_compact(formula))
        issues.extend(self._check_reserved_fields_compact(formula))

        return issues

    # ---- Check implementazioni ----

    def _check_vf_termination(self, steps: list[str]) -> list[LintIssue]:
        """Verifica che la formula termini con VF o R/P (salto finale)."""
        issues: list[LintIssue] = []
        last = ""
        for s in reversed(steps):
            s = s.strip()
            if s and not s.startswith("#") and not s.startswith("//") and not s.startswith("COMMENT"):
                last = s
                break
        if not last:
            issues.append(LintIssue("warning", "W001", "Formula senza istruzioni, impossibile verificare terminazione"))
            return issues
        if last.upper() not in ("VF", "VU") and not last.upper().startswith("R ") and not last.upper().startswith("P "):
            issues.append(LintIssue("warning", "W001", "L'ultima istruzione non e' VF, VU, R o P — possibile terminazione mancante", line=len(steps)))
        return issues

    def _check_unreachable_code(self, steps: list[str]) -> list[LintIssue]:
        """Codice dopo VF/R/P incondizionato (non dentro IF) e' irraggiungibile."""
        issues: list[LintIssue] = []
        depth = 0
        for i, s in enumerate(steps):
            s = s.strip()
            if not s:
                continue
            if s.startswith("IF ") and s.endswith(" THEN"):
                depth += 1
            elif s == "ENDIF":
                depth -= 1
            elif depth == 0:
                upper = s.upper()
                if upper == "VF" or upper == "VU" or upper.startswith("R ") or upper.startswith("P "):
                    for j in range(i + 1, len(steps)):
                        sj = steps[j].strip()
                        if sj and not sj.startswith("#") and not sj.startswith("//") and not sj.startswith("COMMENT"):
                            issues.append(LintIssue("warning", "W002", f"Codice irraggiungibile dopo '{s}': '{sj}'", line=j + 1))
                            break
        return issues

    def _check_r_p_targets_ir(self, steps: list[str]) -> list[LintIssue]:
        """Controlla che R/P punti a formule esistenti nel workbook."""
        issues: list[LintIssue] = []
        for i, s in enumerate(steps):
            for m in self.R_P_PATTERN.finditer(s):
                target = int(m.group(2))
                if self.valid_codici and target not in self.valid_codici:
                    issues.append(LintIssue(
                        "warning", "W003",
                        f"{m.group(1)}{target} -> formula #{target} inesistente nel workbook (possibile riferimento esterno)",
                        line=i + 1,
                    ))
        return issues

    def _check_r_p_targets_compact(self, formula: str) -> list[LintIssue]:
        """Controlla R/P in formula compatta."""
        issues: list[LintIssue] = []
        for m in re.finditer(r'\b([RP])(\d{2,5})\b', formula):
            target = int(m.group(2))
            if self.valid_codici and target not in self.valid_codici:
                issues.append(LintIssue(
                    "warning", "W003",
                    f"{m.group(1)}{target} -> formula #{target} inesistente nel workbook",
                ))
        return issues

    def _check_vxx_labels_ir(self, steps: list[str]) -> list[LintIssue]:
        """Analizza Vxx label: definite vs referenziate."""
        defined: set[str] = set()
        referenced: set[str] = set()

        for s in steps:
            s = s.strip()
            # MARK label  -> definizione
            if s.upper().startswith("MARK "):
                label = s[5:].strip().rstrip(":")
                if label.upper() not in ("VF", "VU"):
                    defined.add(label.upper())
            # GOTO label -> riferimento
            if s.upper().startswith("GOTO "):
                label = s[5:].strip()
                if label.upper() not in ("VF", "VU"):
                    referenced.add(label.upper())
            # Riferimenti Vxx nudi
            for m in self.LABEL_PATTERN.finditer(s):
                vxx = f"V{m.group(1)}"
                if vxx.upper() in ("VF", "VU"):
                    continue
                ctx_before = s[max(0, m.start() - 5):m.start()].strip()
                # Se preceduto da MARK -> definizione
                if ctx_before.upper() == "MARK" or ctx_before.upper().endswith("MARK"):
                    defined.add(vxx.upper())
                # Se preceduto da GOTO -> riferimento
                elif ctx_before.upper() == "GOTO" or ctx_before.upper().endswith("GOTO"):
                    referenced.add(vxx.upper())
                else:
                    referenced.add(vxx.upper())

        issues: list[LintIssue] = []
        # Label referenziate ma mai definite
        for vxx in sorted(referenced - defined):
            issues.append(LintIssue("error", "E010", f"Label {vxx} referenziata ma mai definita (MARK mancante)"))
        # Label definite ma mai usate (solo warning)
        for vxx in sorted(defined - referenced):
            issues.append(LintIssue("warning", "W010", f"Label {vxx} definita (MARK) ma mai referenziata (GOTO)"))
        return issues

    def _check_vxx_labels_compact(self, formula: str) -> list[LintIssue]:
        """Analizza Vxx in formula compatta: label dopo ((...)) sono target."""
        defined: set[str] = set()
        referenced: set[str] = set()

        for m in self.LABEL_PATTERN.finditer(formula):
            vxx = f"V{m.group(1)}"
            if vxx in ("VF", "VU"):
                continue
            pos = m.start()
            ctx_before = formula[max(0, pos - 10):pos].strip()
            if ctx_before.endswith("))"):
                referenced.add(vxx)
            elif ctx_before.endswith(")"):
                referenced.add(vxx)
            else:
                defined.add(vxx)

        issues: list[LintIssue] = []
        for vxx in sorted(referenced - defined):
            issues.append(LintIssue("warning", "W011", f"Label {vxx} referenziata come target di salto ma mai definita nella formula"))
        for vxx in sorted(defined - referenced):
            issues.append(LintIssue("warning", "W012", f"Label {vxx} definita ma mai usata come target"))
        return issues

    def _check_field_init(self, steps: list[str]) -> list[LintIssue]:
        """Verifica che i campi siano inizializzati prima di essere letti.

        Scansione lineare: tiene traccia dei campi scritti (SET/RESET/K/CAMPO70)
        e segnala warning per campi letti (in IF, SET = {N}, K A/S val) prima
        di essere scritti.
        """
        issues: list[LintIssue] = []
        written: set[int] = set()

        for i, s in enumerate(steps):
            s = s.strip()
            if not s:
                continue

            # Estrai scritture
            m = self.SET_PATTERN.match(s)
            if m:
                written.add(int(m.group(1)))

            m = self.RESET_PATTERN.match(s)
            if m:
                written.add(int(m.group(1)))

            m = self.K_PATTERN.match(s)
            if m:
                written.add(int(m.group(1)))

            if s.upper().startswith("CAMPO70 "):
                written.add(73)

            def _is_quoted(text: str, pos: int) -> bool:
                """True se la posizione e' dentro una stringa quotata."""
                before = text[:pos]
                in_sq = before.count("'") % 2 == 1
                in_dq = before.count('"') % 2 == 1
                return in_sq or in_dq

            # Estrai letture in SET (= ...)
            if s.upper().startswith("SET "):
                eq_pos = s.find("=")
                if eq_pos >= 0:
                    val_part = s[eq_pos + 1:]
                    for fm in re.finditer(r'\b(\d{2,4})\b', val_part):
                        if _is_quoted(s, eq_pos + 1 + fm.start()):
                            continue
                        f = int(fm.group(1))
                        if f not in written and (100 <= f < 600 or 800 <= f < 1000):
                            issues.append(LintIssue(
                                "warning", "W020",
                                f"Campo {f} letto in SET prima di essere inizializzato",
                                line=i + 1,
                            ))

            # Letture in IF
            if s.upper().startswith("IF ") and s.endswith(" THEN"):
                cond = s[3:-5].strip()
                for fm in re.finditer(r'\b(\d{2,4})\b', cond):
                    if _is_quoted(s, 3 + fm.start()):
                        continue
                    f = int(fm.group(1))
                    if f not in written and (100 <= f < 600 or 800 <= f < 1000):
                        issues.append(LintIssue(
                            "warning", "W020",
                            f"Campo {f} letto in IF prima di essere inizializzato",
                            line=i + 1,
                        ))

            # Letture in {N} deref
            for fm in re.finditer(r'\{\s*(\d{2,4})\s*\}', s):
                if _is_quoted(s, fm.start()):
                    continue
                f = int(fm.group(1))
                if f not in written and (100 <= f < 600 or 800 <= f < 1000):
                    issues.append(LintIssue(
                        "warning", "W020",
                        f"Campo {f} dereferenziato con {{}} prima di essere inizializzato",
                        line=i + 1,
                    ))

        return issues

    def _check_flag_type_mismatch(self, steps: list[str]) -> list[LintIssue]:
        """Controlla che I/Z non siano usati come valori numerici e viceversa."""
        issues: list[LintIssue] = []

        for i, s in enumerate(steps):
            s = s.strip()
            # SET N = I / SET N = Z su campo che non e' flag
            if s.upper().startswith("SET "):
                eq_pos = s.find("=")
                if eq_pos >= 0:
                    lhs = s[3:eq_pos].strip()
                    rhs = s[eq_pos + 1:].strip()
                    if rhs.upper() in ("I", "Z"):
                        lhs_int = re.match(r'\d+', lhs)
                        if lhs_int and int(lhs_int.group()) not in (*range(50, 60), 684, 900):
                            issues.append(LintIssue(
                                "warning", "W030",
                                f"Assegnazione flag {rhs} a campo {lhs}: I/Z e' booleano, usare solo su campi flag (50-59, 684, 900)",
                                line=i + 1,
                            ))
                    # Flag usato come numerico
                    if "I" in rhs.upper() or "Z" in rhs.upper():
                        pass

            # IF N = valore numerico specifico su campo flag
            if s.upper().startswith("IF ") and s.endswith(" THEN"):
                cond = s[3:-5].strip()
                m = re.match(r'(\d+)\s*[=#]\s*(\d+)', cond)
                if m:
                    lhs = int(m.group(1))
                    rhs = int(m.group(2))
                    if lhs in (*range(50, 60), 684) and rhs not in (0, 1, 7):
                        issues.append(LintIssue(
                            "info", "I031",
                            f"Confronto numerico {rhs} su campo flag {lhs}: I/Z sarebbe piu' idiomatico",
                            line=i + 1,
                        ))

        return issues

    def _check_if_then_else_balance(self, steps: list[str]) -> list[LintIssue]:
        """Verifica bilanciamento IF/ENDIF."""
        issues: list[LintIssue] = []
        depth = 0
        for i, s in enumerate(steps):
            s = s.strip()
            if s.startswith("IF ") and s.endswith(" THEN"):
                depth += 1
            elif s == "ENDIF":
                depth -= 1
                if depth < 0:
                    issues.append(LintIssue("error", "E040", "ENDIF senza IF corrispondente", line=i + 1))
        if depth > 0:
            issues.append(LintIssue("error", "E040", f"Mancano {depth} ENDIF"))
        return issues

    def _check_loop_detection(self, steps: list[str]) -> list[LintIssue]:
        """Rileva potenziali loop in chiamate R/P.

        Funziona a livello IR: se una formula chiama R/P se stessa
        (stesso target in due punti diversi) potrebbe indicare un loop.
        Questo e' un controllo leggero; la vera analisi circolare
        richiede FormulaDependencyGraph.
        """
        issues: list[LintIssue] = []
        calls: dict[int, list[int]] = defaultdict(list)

        for i, s in enumerate(steps):
            for m in self.R_P_PATTERN.finditer(s):
                target = int(m.group(2))
                calls[target].append(i + 1)

        for target, lines in calls.items():
            if len(lines) > 1:
                issues.append(LintIssue(
                    "info", "I050",
                    f"Chiamata R/P a #{target} ripetuta {len(lines)} volte (righe {lines}) — possibile loop, verificare",
                ))
        return issues

    def _check_i_z_quoting_compact(self, formula: str) -> list[LintIssue]:
        """Controlla I/Z quotati in formula compatta."""
        issues: list[LintIssue] = []
        if re.search(r"""['"]I['"]""", formula):
            issues.append(LintIssue("error", "E060", "I quotato ('I' o \"I\"): I e' flag booleano, non stringa"))
        if re.search(r"""['"]Z['"]""", formula):
            issues.append(LintIssue("error", "E060", "Z quotato ('Z' o \"Z\"): Z e' flag booleano, non stringa"))
        return issues

    def _check_reserved_fields_compact(self, formula: str) -> list[LintIssue]:
        """Controlla campi riservati in formula compatta."""
        issues: list[LintIssue] = []
        reserved_patterns = [
            (r'\(\s*(?:7|8|9|1[0-9])\s*[=AS]', "Campi 7-19 riservati", "error"),
            (r'\(\s*(?:3|4)\s*[=AS]', "Campi 3 (ore ordinarie) o 4 (straordinarie): modificati solo in FG", "warning"),
            (r'\(\s*K(?:603|604|608|609)\s*[AS]', "K603-K609 non modificabili direttamente (usa K601/K602 invece)", "warning"),
        ]
        for pat, msg, sev in reserved_patterns:
            if re.search(pat, formula):
                issues.append(LintIssue(sev, "E070", msg))
        return issues

    def lint_all(self, steps: list[str] | None = None, formula: str | None = None) -> list[LintIssue]:
        """Lint combinato: IR steps + formula compatta."""
        issues: list[LintIssue] = []
        if steps is not None:
            issues.extend(self.lint_ir(steps))
        if formula is not None:
            issues.extend(self.lint_compact(formula))
        return issues

    def format_report(self, issues: list[LintIssue]) -> str:
        """Formatta una lista di issue in stringa leggibile."""
        if not issues:
            return "Nessun problema di linting rilevato."
        lines = [f"Linting: {len(issues)} issue(s) trovati\n"]
        for iss in issues:
            lines.append(f"  {iss}")
        return "\n".join(lines)

    def has_errors(self, issues: list[LintIssue]) -> bool:
        """True se c'e' almeno un issue di severity 'error'."""
        return any(iss.severity == "error" for iss in issues)


def main() -> None:
    """CLI entry point: linter da riga di comando.

    Usage:
        python -m legacy_winsarp.core.winsarp.linter --ir steps.txt
        python -m legacy_winsarp.core.winsarp.linter --compact formula.txt
        python -m legacy_winsarp.core.winsarp.linter --ir steps.txt --compact formula.txt
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="WinSarp Static Semantic Linter")
    parser.add_argument("--ir", type=str, help="File con step IR (uno per riga)")
    parser.add_argument("--compact", type=str, help="File con formula compatta")
    parser.add_argument("--valid-codici", type=str, help="File con codici formula validi (uno per riga)")
    args = parser.parse_args()

    if not args.ir and not args.compact:
        parser.print_help()
        sys.exit(0)

    valid_codici: set[int] = set()
    if args.valid_codici:
        with open(args.valid_codici, encoding="utf-8") as f:
            valid_codici = {int(line.strip()) for line in f if line.strip().isdigit()}

    linter = WinSarpLinter(valid_codici=valid_codici)
    issues: list[LintIssue] = []

    if args.ir:
        with open(args.ir, encoding="utf-8") as f:
            steps = [line.strip() for line in f if line.strip()]
        issues.extend(linter.lint_ir(steps))

    if args.compact:
        with open(args.compact, encoding="utf-8") as f:
            formula = f.read()
        issues.extend(linter.lint_compact(formula))

    print(linter.format_report(issues))
    if linter.has_errors(issues):
        sys.exit(1)


if __name__ == "__main__":
    main()
