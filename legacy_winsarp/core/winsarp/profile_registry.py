from __future__ import annotations
import logging
from legacy_winsarp.core.winsarp.patterns import FormulaPatternLibrary

_logger = logging.getLogger(__name__)


class Profile:
    def __init__(self, name: str, keywords: list[str], description: str,
                 compact_str: str = None, ir_steps: list[str] = None,
                 pattern_codes: list[int] = None,
                 match_threshold: float = 0.8):
        self.name = name
        self.keywords = keywords
        self.description = description
        self._compact_str = compact_str
        self._ir_steps = ir_steps
        self._pattern_codes = pattern_codes or []
        self.match_threshold = match_threshold

    def matches(self, text: str) -> bool:
        low = text.lower()
        presenti = [k for k in self.keywords if k in low]
        if not self.keywords or not text.strip():
            return False
        return len(presenti) / len(self.keywords) >= self.match_threshold

    def generate(self, builder=None, clean: bool = True) -> str:
        raw = self._raw_generate(builder)
        if not clean:
            return raw
        return Profile._sanitize_compact(raw)

    def _raw_generate(self, builder=None) -> str:
        if self._compact_str:
            return self._compact_str
        if self._pattern_codes:
            library = FormulaPatternLibrary()
            parts = []
            for code in self._pattern_codes:
                pattern = library.get_pattern(code)
                if pattern and pattern.compact:
                    parts.append(pattern.compact)
            return "".join(parts)
        if self._ir_steps and builder:
            return builder.build_compact(self._ir_steps)
        if self._ir_steps:
            return "\n".join(self._ir_steps)
        return ""

    @staticmethod
    def _sanitize_compact(formula: str) -> str:
        """Rimuove commenti e normalizza operatori allo stile workbook."""
        import re
        # Rimuovi commenti inline (? ... )
        s = re.sub(r'\(\?[^)]*\)', '', formula)
        lines = []
        for l in s.split('\n'):
            stripped = l.strip()
            if stripped.startswith('?') or not stripped:
                continue
            stripped = re.sub(r'^\s*\?.*', '', stripped).rstrip()
            if stripped:
                lines.append(stripped)
        s = '\n'.join(lines)
        # Normalizza operatori orari: >|<>U|<U per confronti con orari o campi
        s = re.sub(r'(\d+) > (\x27\d{2}\.\d{2}\x27)', r'\1 >U \2', s)
        s = re.sub(r'(\d+) < (\x27\d{2}\.\d{2}\x27)', r'\1 <U \2', s)
        s = re.sub(r'(20[1-4]) < (\d{3})', r'\1 <U \2', s)
        s = re.sub(r'(20[1-4]) > (\d{3})', r'\1 >U \2', s)
        # NOTA: NON convertire 776 < '40.00' in <U — il workbook usa strict <
        # s = re.sub(r'(776) < (\x27\d{2}\.\d{2}\x27)', r'\1 <U \2', s)
        return s

    def get_ir_steps(self) -> list[str]:
        return self._ir_steps or []


# ============================================================
# DATA-DRIVEN profile definitions
# ============================================================
# How to add a new profile:
#   Add a dict to PROFILES_DATA below. That's it — no Python code.
#
#   - `compact_str`:  direct compact syntax (zero conversion errors)
#   - `pattern_codes`: reference verified formulas from the pattern library
#   - `ir_steps`:      only for complex logic needing builder.build_compact()
#
#   Use `match_threshold` to control how strictly keywords must match:
#     0.8 = strict (complex composite profiles like turnista_completo)
#     0.1 = loose (catch any keyword hit for reference templates)

PROFILES_DATA = [
    # ------------------------------------------------------------------
    # turnista_completo — complex composite: 5 (ric.turno) + 1020 + 3001
    # ------------------------------------------------------------------
    {
        "name": "turnista_completo",
        "match_threshold": 0.8,
        "keywords": [
            "turnista", "due intervalli", "pausa pranzo",
            "straordinario", "maggiorazioni",
        ],
        "description": (
            "Turnista con due intervalli, pausa pranzo, straordinario e maggiorazioni. "
            "Architettura: 5 (ric. turno) + 1020 (costr. intervalli) + 3001 (elab. FG)."
        ),
        "ir_steps": [
            "# --- IG: AZZERAMENTI INIZIALI ---",
            "RESET 900", "RESET 800", "RESET 801", "RESET 802",
            "RESET 803", "RESET 804",

            "# --- IG: RICONOSCIMENTO TURNO su prima entrata (field 200) ---",
            "IF 200 > Z THEN",
            "  IF 200 > '04.00' AND 200 < '09.00' THEN",
            "    SET 900 = '1'", "    SET 58 = 'MATT'",
            "    SET 111 = '06'", "    SET 141 = '14'",
            "    RESET 112", "RESET 142",
            "    SET 100 = I",
            "  ENDIF",
            "  IF 200 > '12.00' AND 200 < '17.00' THEN",
            "    SET 900 = '2'", "    SET 58 = 'POME'",
            "    SET 111 = '14'", "    SET 141 = '22'",
            "    RESET 112", "RESET 142",
            "    SET 100 = I",
            "  ENDIF",
            "  IF 200 > '20.00' AND 200 < '23.59' THEN",
            "    SET 900 = '3'", "    SET 58 = 'NOTT'",
            "    SET 111 = '22'", "    SET 141 = '06'",
            "    RESET 112", "RESET 142",
            "    SET 100 = I",
            "  ENDIF",
            "ENDIF",

            "# --- DG: COSTRUZIONE DUE INTERVALLI da timbrature dirette (200-204) ---",
            "RESET 251", "RESET 271", "RESET 252", "RESET 272",
            "# Primo intervallo: entrata=200, uscita=201",
            "IF 200 > Z AND 201 > Z THEN",
            "  IF 200 < 141 THEN",
            "    SET 251 = 111",
            "    SET 271 = 141",
            "  ELSE",
            "    SET 251 = 112",
            "    SET 271 = 142",
            "  ENDIF",
            "ENDIF",
            "# Secondo intervallo: entrata=202, uscita=203",
            "IF 202 > Z AND 203 > Z THEN",
            "  IF 202 < 141 THEN",
            "    SET 252 = 111",
            "    SET 272 = 141",
            "  ELSE",
            "    SET 252 = 112",
            "    SET 272 = 142",
            "  ENDIF",
            "ENDIF",

            "# --- FG: ELABORAZIONE ---",
            "IF 50 = '2' THEN",
            "  RESET 788", "  RESET 790",
            "  RESET 774", "RESET 775", "RESET 776",
            "ENDIF",
            "IF 51 = I AND 52 = I THEN", "  RESET 783", "ENDIF",
            "IF 55 = I THEN", "  P 3009", "ENDIF",
            "K 3 A 4", "RESET 4", "RESET 5",
            "K 775 A 3 A 4 A 608 A 609",

            "# Arrotondamento ore date-based",
            "IF 300 < '20230601' THEN", "  P 3002", "ENDIF",
            "IF 300 > U '20230601' THEN", "  P 3003", "ENDIF",

            "# AUTS (autorizzazioni straordinario)",
            "P 3017",

            "# Elaborazione straordinario e maggiorazioni",
            "K 788 A 608 A 609 S 608 S 609 A 3",
            "P 3005", "P 3014", "P 3004", "P 3015",
            "K 776 A 3 A 902 A 903 A 608 A 609",

            "# Cap su 776 (non superare 40h o ore contrattuali 1391)",
            "IF 50 = I AND 776 < '40.00' AND 1391 = Z THEN",
            "  SET 5 = '40.00' - 776",
            "ENDIF",
            "IF 50 = I AND 776 < 1391 AND 1391 > Z THEN",
            "  SET 5 = 1391 - 776",
            "ENDIF",

            "# Accumulatori ore",
            "K 602 A 3", "K 626 A 902 A 903",
            "K 627 A 904 A 908", "K 612 A 906",
            "K 611 A 907 A 915", "K 615 A 914",
            "K 614 A 909", "K 616 A 910",
            "K 604 A 612 A 611 A 615 A 614 A 616",
            "K 783 A 610", "K 601 A 602 A 604",

            "# Totale settimanale K711",
            "IF 50 = '2' THEN", "  RESET 711", "ENDIF",
            "K 711 A 601 A 608",

            "# Reset campi output",
            "P 3030",
            "RESET 901", "RESET 902", "RESET 903",
            "RESET 904", "RESET 905", "RESET 906",
            "RESET 907", "RESET 908", "RESET 909",
            "RESET 910", "RESET 911", "RESET 912",
            "RESET 913", "RESET 914", "RESET 915",
            "RESET 916", "RESET 917", "RESET 918",
            "RESET 919", "RESET 920", "RESET 922",
            "RESET 928", "RESET 929",

            "# Anti-loop (K900 - I)",
            "IF 50 = I OR 300 = 302 OR 300 = 311 THEN",
            "  K 900 S I",
            "ENDIF",
            "VF",
        ],
    },
]


def detect_profile(user_request: str) -> Profile | None:
    for profile in PROFILES:
        if profile.matches(user_request):
            _logger.info("Profile matched: %s (keywords: %s)", profile.name, profile.keywords)
            return profile
    return None


# Build Profile objects from data
PROFILES: list[Profile] = []
for defn in PROFILES_DATA:
    ir_steps = defn.pop("ir_steps", None)
    compact_str = defn.pop("compact_str", None)
    pattern_codes = defn.pop("pattern_codes", None)
    PROFILES.append(
        Profile(
            **defn,
            ir_steps=ir_steps,
            compact_str=compact_str,
            pattern_codes=pattern_codes,
        )
    )
