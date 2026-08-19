"""Validator per sintassi WinSarp compatta - approccio rilassato."""

import re
from legacy_winsarp.core.winsarp.linter import LintIssue

class LarkFormulaValidator:
    """Valida formule WinSarp compatte in modo rilassato."""

    def validate(self, formula: str) -> list[LintIssue]:
        """Valida una formula. Ritorna lista di LintIssue."""
        issues: list[LintIssue] = []

        if not formula or not formula.strip():
            return issues

        # 1. Paren balance check (fondamentale per WinSarp)
        issues.extend(self._check_paren_balance(formula))

        # 2. Syntax check rilassato (nessun parser formale Lark)
        issues.extend(self._check_illegal_patterns(formula))

        return issues

    @staticmethod
    def _check_paren_balance(formula: str) -> list[LintIssue]:
        depth = 0
        for i, ch in enumerate(formula):
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            if depth < 0:
                return [LintIssue("error", "L003", f"Parentesi chiusa senza apertura alla posizione {i}", line=0)]
        # depth > 0 è accettato in WinSarp per le formule ((...))
        return []

    @staticmethod
    def _check_illegal_patterns(formula: str) -> list[LintIssue]:
        """Controlla pattern sintatticamente impossibili per WinSarp."""
        issues = []

        # Doppi operatori illegali
        if re.search(r'>>|<<|==|&&|\|\|', formula):
            issues.append(LintIssue("error", "L005", "Operatore doppio non valido (es. >>)", line=0))

        # Spazi illegali dentro label o campi (es: { 80 1 })
        # NOTA: WinSarp spesso accetta spazi all'interno delle graffe (es. { 801 }),
        # quindi questo controllo va fatto con cautela.

        return issues

    def has_errors(self, formula: str) -> bool:
        return any(i.severity == "error" for i in self.validate(formula))

