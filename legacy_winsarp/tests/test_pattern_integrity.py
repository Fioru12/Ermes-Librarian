"""
Test di integrita' pattern: confronta i compact di formula_patterns.py
con le formule reali dei file sorgente.

Scopo: garantire che i pattern codificati corrispondano
esattamente alle formule reali in produzione.
"""

import re
from pathlib import Path

from legacy_winsarp.core.winsarp.patterns import FormulaPatternLibrary

WORKBOOK_PATH = Path(__file__).parent.parent / "documenti" / "WinSarp" / "WinSarp_Formule.txt"
FORMULE_PATH = Path(__file__).parent.parent / "documenti" / "WinSarp" / "FormuleWinsarp.txt"
EXCLUDED_CODES = {3020, 2125}  # Placeholder noti, volutamente vuoti


def _extract_compacts_from_workbook(text: str) -> dict[int, str]:
    """Estrae sintassi compatta dal workbook WinSarp_Formule.txt."""
    compacts: dict[int, str] = {}
    lines = text.splitlines()
    in_compact_block = False
    current_code = 0
    compact_lines = []

    for i, line in enumerate(lines):
        m = re.search(r'<a\s+name="(\d+)">', line)
        if m:
            current_code = int(m.group(1))
            continue

        stripped = line.strip()

        if stripped.startswith("```") and not in_compact_block:
            prev = lines[i - 1].strip() if i > 0 else ""
            if "compressa" in prev.lower() or "compatta" in prev.lower():
                in_compact_block = True
                compact_lines = []
            continue

        if stripped.startswith("```") and in_compact_block:
            in_compact_block = False
            if current_code > 0 and compact_lines:
                compact = "".join(compact_lines)
                compact = compact.replace(" ", "").replace(";", "").replace("\n", "")
                compact = re.sub(r"VF[A-Z]{4,}", "VF", compact)
                compact = re.sub(r"\)[A-Z]{4,}", ")", compact)
                compacts[current_code] = compact
            current_code = 0
            compact_lines = []
            continue

        if in_compact_block:
            stripped = re.sub(r"\?(?![(])[^(]*", "", stripped)
            compact_lines.append(stripped)

    return compacts


def _normalize(s: str) -> str:
    """Normalizza per confronto: spazi, apici uniformati."""
    s = s.replace(" ", "").replace(";", "").replace("\n", "").replace("\r", "")
    s = s.replace('"', "'")
    return s


# ── Test ──

class TestPatternIntegrity:
    def test_all_patterns_have_compact(self):
        """Ogni pattern (esclusi placeholder) deve avere compact non vuoto."""
        lib = FormulaPatternLibrary()
        empty = []
        for code, p in lib.PATTERNS.items():
            if code in EXCLUDED_CODES:
                continue
            if not p.compact:
                empty.append(f"{code} ({p.name})")
        assert not empty, "Pattern con compact vuoto:\n" + "\n".join(empty)

    def test_workbook_loadable(self):
        """Il workbook deve esistere ed essere leggibile."""
        assert WORKBOOK_PATH.exists(), f"Workbook non trovato: {WORKBOOK_PATH}"
        text = WORKBOOK_PATH.read_text(encoding="utf-8")
        assert len(text) > 1000, "Workbook troppo corto"

    def test_workbook_compacts_match(self):
        """I compact del workbook (dove presenti) devono corrispondere
        esattamente ai compact in FormulaPatternLibrary."""
        lib = FormulaPatternLibrary()
        text = WORKBOOK_PATH.read_text(encoding="utf-8")
        wb_compacts = _extract_compacts_from_workbook(text)

        mismatches = []
        for code, wb_compact in wb_compacts.items():
            if code in EXCLUDED_CODES:
                continue
            p = lib.get_pattern(code)
            if p is None:
                mismatches.append(f"{code}: nel workbook ma non in libreria")
                continue
            if not p.compact:
                mismatches.append(f"{code}: compact vuoto in libreria")
                continue
            if _normalize(p.compact) != _normalize(wb_compact):
                mismatches.append(
                    f"{code} ({p.name}): differenza\n"
                    f"  LIBRERIA:  {p.compact[:150]}\n"
                    f"  WORKBOOK:  {wb_compact[:150]}"
                )

        assert not mismatches, (
            f"\n=== {len(mismatches)} discrepanze workbook ===\n" + "\n\n".join(mismatches[:5])
        )

    def test_no_ellipsis_in_compacts(self):
        """Nessun compact deve contenere '...' (abbreviazioni)."""
        lib = FormulaPatternLibrary()
        for code, p in lib.PATTERNS.items():
            if p.compact and "..." in p.compact:
                assert False, f"Pattern {code}: compact contiene '...': {p.compact[:100]}"

    @staticmethod
    def _formula_codes_in_file(path: Path) -> set[int]:
        """Estrae i codici formula presenti in un file."""
        text = path.read_text(encoding="utf-8")
        codes = set()
        # Formato: "formula N" (FormuleWinsarp.txt) oppure <a name="N"> (WinSarp_Formule.txt)
        for m in re.finditer(r'formula\s+(\d+)|<a\s+name="(\d+)">', text):
            codes.add(int(m.group(1) or m.group(2)))
        return codes

    def test_source_coverage(self):
        """Tutti i pattern devono avere corrispondenza in almeno una fonte."""
        lib = FormulaPatternLibrary()
        form_codes = self._formula_codes_in_file(FORMULE_PATH)
        wb_codes = self._formula_codes_in_file(WORKBOOK_PATH)
        all_source_codes = form_codes | wb_codes

        missing = []
        for code in sorted(lib.PATTERNS):
            if code in EXCLUDED_CODES:
                continue
            if code not in all_source_codes:
                missing.append(f"{code} ({lib.PATTERNS[code].name})")

        assert not missing, (
            "Pattern senza corrispondenza in nessun file sorgente:\n" + "\n".join(missing)
        )

    def test_compact_syntax_valid(self):
        """Verifica sintassi minima: nessun carattere chiaramente invalido."""
        lib = FormulaPatternLibrary()
        invalid = []
        for code, p in lib.PATTERNS.items():
            if not p.compact:
                continue
            c = p.compact
            # Nessun carattere di controllo (tranne newline/return)
            if any(ord(ch) < 32 and ch not in '\n\r' for ch in c):
                invalid.append(f"{code}: carattere di controllo nel compact")
            # Non deve iniziare con spazio
            if c != c.lstrip():
                invalid.append(f"{code}: compact inizia con spazio")
        assert not invalid, "\n".join(invalid)
