"""
logic_test_generator.py
Genera automaticamente test case (input/output) da regole espresse in linguaggio naturale.

Supporta pattern italiani:
  - "se ≤ 12 → 0, 13-15 → 15"
  - "se pausa <= 0.30 → tutto OK, altrimenti taglia a 0.30"
  - "tra 6 e 8 → 1, oltre 8 → 2"
  - "se campo X = Y allora Z, altrimenti W"
"""

import logging
import re

_logger = logging.getLogger(__name__)


class LogicTestGenerator:
    """Analizza una descrizione testuale di regole e genera test case strutturati."""

    # Pattern di range: "13-15" -> (13, 15), "≤12" -> (0, 12), ">=6" -> (6, INF)
    RANGE_PATTERN = re.compile(
        r'(?P<op>≤|<=|=|<|>=|>|tra\s+)?\s*'
        r'(?P<from>\d+(?:[.,]\d+)?)\s*'
        r'(?P<sep>-|–|′|a\s+)?\s*'
        r'(?P<to>\d+(?:[.,]\d+)?)?',
        re.IGNORECASE,
    )

    def __init__(self, field_context: dict[str, int] | None = None):
        """
        Args:
            field_context: Mappa nomi logici -> numeri campo (es. {"pausa": 800, "entrata": 251})
        """
        self.field_context = field_context or {}

    def generate_from_nl(self, nl_rule: str, output_field: int = 800) -> list[dict]:
        """Parsa una regola in linguaggio naturale e produce logic_tests.

        Args:
            nl_rule: Testo regola, es. "se pausa ≤ 12 → 0, 13-15 → 15"
            output_field: Campo su cui applicare il risultato

        Returns:
            Lista di dict con chiavi 'input' (dict) e 'output' (dict), pronti per logic_tests
        """
        tests: list[dict] = []
        clauses = self._split_clauses(nl_rule)

        for clause in clauses:
            inputs = self._parse_condition(clause["condizione"], output_field)
            if not inputs:
                continue

            outputs = self._parse_consequence(clause["conseguenza"], output_field)
            if not outputs:
                continue

            for inp in inputs:
                tests.append({"input": inp, "output": outputs})

        if not tests:
            _logger.warning("Nessun test generato da: %s", nl_rule)

        return tests

    def _split_clauses(self, text: str) -> list[dict]:
        """Divide una regola in clausole condizione→conseguenza.

        Esempi:
          "se ≤12 = 0, 13-15 = 15"
          "se pausa <= 0.30 → tutto OK, altrimenti → taglia"
        """
        text = text.strip().lower()
        clauses: list[dict] = []

        # Separa per virgole che separano clausole (non dentro parentesi)
        segments = re.split(r'(?:,\s*|;\s*)', text)

        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue

            # "altrimenti X" -> condizione null (else/fallback)
            if seg.startswith("altrimenti") or seg.startswith("else"):
                conseq = re.sub(r'^(?:altrimenti|else)\s*[=:→»\-]?\s*', '', seg).strip()
                clauses.append({"condizione": None, "conseguenza": conseq})
                continue

            # "se X = Y" oppure "X = Y"
            # Cerca separatore: →, = (se non parte di ≤, ≥), :
            # NOTA: NON usare - come separatore per non rompere range "13-15"
            sep_match = re.search(r'[=:→»]\s*(?!=|>|<)', seg)
            if sep_match:
                cond_part = seg[: sep_match.start()].strip()
                conseq_part = seg[sep_match.end():].strip()
            elif "→" in seg:
                parts = seg.split("→", 1)
                cond_part = parts[0].strip()
                conseq_part = parts[1].strip()
            else:
                continue

            # Pulisci "se" iniziale
            cond_clean = re.sub(r'^se\s+', '', cond_part).strip()

            clauses.append({"condizione": cond_clean, "conseguenza": conseq_part})

        return clauses

    def _parse_condition(self, cond_text: str | None, output_field: int) -> list[dict] | None:
        """Converte una condizione testuale in input dict per il simulatore.

        Esempi:
          "≤12"       -> [{"800": "0"}, {"800": "6"}, {"800": "12"}]
          "13-15"     -> [{"800": "13"}, {"800": "14"}, {"800": "15"}]
          "pausa > 30" -> [{"800": "31"}, {"800": "45"}]
          None/else   -> [{"800": "999"}]  # valore per else
        """
        if cond_text is None:
            return [{str(output_field): "999"}]

        # Risolvi contesto: sostituisci nomi logici con numeri campo
        resolved = cond_text
        for log_name, num in self.field_context.items():
            resolved = re.sub(r'\b' + re.escape(log_name) + r'\b', str(num), resolved)

        # Estrai campo, operatore, e range di valori
        # Pattern: [campo] [op] [valore o range]
        m = re.match(
            r'(?:campo\s+)?(?P<field>\d{1,4})\s*'
            r'(?P<op>≤|>=|>U|>U|>U|<=|<U|>U|=|#|>|<|>=|<=)'
            r'\s*(?P<value>.+)',
            resolved,
            re.IGNORECASE,
        )
        if not m:
            # Prova senza campo esplicito: usa output_field
            m = re.match(
                r'(?P<op>≤|>=|>U|<=|<U|=|>|<|>=|<=)?\s*'
                r'(?P<value>.+)',
                resolved,
            )
            if m:
                field = str(output_field)
                op = m.group("op") or "="
                val_str = m.group("value").strip()
            else:
                return None
        else:
            field = m.group("field")
            op = m.group("op")
            val_str = m.group("value").strip()

        # Normalizza operatore
        op_map = {
            "≤": "<=", "<=": "<=", "<": "<",
            "≥": ">=", ">=": ">=", ">": ">",
            "=": "=", "==": "=", "#": "#", "!=": "#",
            ">U": ">=",
            "<U": "<=",
        }
        op = op_map.get(op, op)

        # Estrai range di test
        test_values = self._expand_test_values(val_str, op)

        tests = []
        for val in test_values:
            tests.append({field: val})

        return tests if tests else None

    def _expand_test_values(self, val_str: str, op: str) -> list[str]:
        """Espande una descrizione di valori in una lista di valori di test.

        "12"        -> ["12"]
        "13-15"     -> ["13", "14", "15"]
        "≤12"       -> ["0", "6", "12"]
        ">=6"       -> ["6", "10", "15", "20"]
        "tra 6 e 8" -> ["6", "7", "8"]
        """
        val_str = val_str.strip()

        # Range esplicito: "13-15"
        m = re.match(r'(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)', val_str)
        if m:
            try:
                from_v = self._parse_num(m.group(1))
                to_v = self._parse_num(m.group(2))
                step = 1 if to_v - from_v <= 5 else max(1, (to_v - from_v) // 3)
                return [str(v) for v in range(from_v, to_v + 1, step)]
            except ValueError:
                pass

        # "tra X e Y"
        m = re.match(r'tra\s+(\d+(?:[.,]\d+)?)\s+e\s+(\d+(?:[.,]\d+)?)', val_str)
        if m:
            try:
                from_v = self._parse_num(m.group(1))
                to_v = self._parse_num(m.group(2))
                step = max(1, (to_v - from_v) // 2)
                return [str(v) for v in range(from_v, to_v + 1, step)]
            except ValueError:
                pass

        # Se l'operatore e' gia' stato parsato, usa quello per espandere
        op_norm = op.strip()

        if op_norm in ("<=", "≤"):
            try:
                threshold = self._parse_num(val_str)
                values = [0]
                mid = threshold // 2
                if mid > 0:
                    values.append(mid)
                values.append(threshold)
                return [str(v) for v in values]
            except ValueError:
                pass

        if op_norm in (">=", "≥"):
            try:
                threshold = self._parse_num(val_str)
                return [str(threshold), str(threshold + 4), str(threshold + 10), str(threshold + 20)]
            except ValueError:
                pass

        if op_norm == ">":
            try:
                threshold = self._parse_num(val_str)
                return [str(threshold + 1), str(threshold + 5), str(threshold + 15)]
            except ValueError:
                pass

        if op_norm == "<":
            try:
                threshold = self._parse_num(val_str)
                mid = threshold // 2
                values = [0]
                if mid > 0:
                    values.append(mid)
                if threshold > 1:
                    values.append(threshold - 1)
                return [str(v) for v in values]
            except ValueError:
                pass

        # "≤12" o "<=12" (operatore incluso nel valore)
        m = re.match(r'(≤|<=)\s*(\d+(?:[.,]\d+)?)', val_str)
        if m:
            try:
                threshold = self._parse_num(m.group(2))
                values = [0]
                mid = threshold // 2
                if mid > 0:
                    values.append(mid)
                values.append(threshold)
                return [str(v) for v in values]
            except ValueError:
                pass

        # "≥6" o ">=6"
        m = re.match(r'(≥|>=)\s*(\d+(?:[.,]\d+)?)', val_str)
        if m:
            try:
                threshold = self._parse_num(m.group(2))
                return [str(threshold), str(threshold + 4), str(threshold + 10), str(threshold + 20)]
            except ValueError:
                pass

        # ">12"
        m = re.match(r'>\s*(\d+(?:[.,]\d+)?)', val_str)
        if m:
            try:
                threshold = self._parse_num(m.group(1))
                return [str(threshold + 1), str(threshold + 5), str(threshold + 15)]
            except ValueError:
                pass

        # "<12"
        m = re.match(r'<\s*(\d+(?:[.,]\d+)?)', val_str)
        if m:
            try:
                threshold = self._parse_num(m.group(1))
                mid = threshold // 2
                values = [0]
                if mid > 0:
                    values.append(mid)
                if threshold > 1:
                    values.append(threshold - 1)
                return [str(v) for v in values]
            except ValueError:
                pass

        # Valore singolo
        return [val_str]

    def _parse_consequence(self, conseq_text: str, output_field: int) -> dict | None:
        """Converte una conseguenza testuale in output dict.

        "0"          -> {str(output_field): "0"}
        "15"         -> {str(output_field): "15"}
        "tutto OK"   -> {str(output_field): "OK"}
        "taglia a 30" -> {str(output_field): "30"}
        "800 = 0"    -> {"800": "0"}
        """
        conseq_text = conseq_text.strip().lower()

        # "tutto ok", "nessun cambiamento", "invariato" -> skip (nessun output atteso)
        if re.search(r'(tutto ok|nessun cambiamento|invariato|nessuna azione)', conseq_text):
            return None

        # "taglia a X", "limita a X", "imposta X"
        m = re.search(r'(?:taglia|limita|imposta|set|arrotonda|forza)\s+(?:a\s+)?(.+)', conseq_text)
        if m:
            val = m.group(1).strip()
            val = self._normalize_val(val)
            return {str(output_field): val}

        # "campo X = Y"
        m = re.match(r'(?:campo\s+)?(\d{1,4})\s*=\s*(.+)', conseq_text)
        if m:
            field = m.group(1)
            val = self._normalize_val(m.group(2).strip())
            return {field: val}

        # "X" (valore nudo)
        val = self._normalize_val(conseq_text)
        return {str(output_field): val}

    def _normalize_val(self, val: str) -> str:
        """Normalizza un valore per il confronto nel simulatore."""
        val = val.strip().strip("'\"")
        val = val.replace(",", ".")
        if val in ("i", "vero", "true"):
            return "I"
        if val in ("z", "falso", "false", "zero"):
            return "Z"
        return val

    @staticmethod
    def _parse_num(s: str) -> int:
        """Converte stringa numerica in intero."""
        s = s.strip().replace(",", ".")
        return int(float(s))


def generate_tests_from_request(user_request: str, field_context: dict[str, int] | None = None) -> list[dict]:
    """Funzione di comodo: data una richiesta NL, genera test case.

    Args:
        user_request: Richiesta utente tipo "se pausa <= 12 min = 0, 13-30 = 15"
        field_context: Mappa nomi logici -> numeri campo

    Returns:
        Lista di dict con 'input' e 'output', pronto per logic_tests
    """
    gen = LogicTestGenerator(field_context=field_context)
    return gen.generate_from_nl(user_request)
