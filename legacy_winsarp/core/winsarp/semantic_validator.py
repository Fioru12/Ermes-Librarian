"""
semantic_validator.py
Validatore semantico dichiarativo per SpecificaFormula.
Controlla la compatibilità campo/operatore, range di scrittura,
e vincoli strutturali SENZA eseguire l'IR.

Non richiede il simulatore — opera a livello di specifica JSON.
"""

import logging
import re
from typing import Any

from legacy_winsarp.core.winsarp.field_registry import (
    FIELD_TYPE_APPOGGIO,
    FIELD_TYPE_CALCOLATA,
    FIELD_TYPE_CAUSALE,
    FIELD_TYPE_FLAG,
    FIELD_TYPE_K_TOTALE,
    FIELD_TYPE_PREVISIONALE,
    FIELD_TYPE_SISTEMA,
    FIELD_TYPE_TIMBRATURA,
    FIELD_TYPE_TOTALE,
    registry as field_registry,
)

_logger = logging.getLogger(__name__)


class SemanticIssue:
    """Un singolo issue di validazione semantica."""
    def __init__(self, severity: str, message: str, field: int | str | None = None):
        self.severity = severity  # "error" o "warning"
        self.message = message
        self.field = field

    def __str__(self) -> str:
        prefix = f"[campo {self.field}] " if self.field else ""
        return f"{self.severity.upper()}: {prefix}{self.message}"

    def __repr__(self) -> str:
        return f"SemanticIssue({self.severity}, {self.message!r}, field={self.field})"


class SemanticFormulaValidator:
    """Validazione semantica a livello di SpecificaFormula JSON.

    Categorie di controllo:
    1. Write-range: campi che NON possono essere scritti direttamente
       (1-6 devono usare K accumulatori, 70-79 solo via CAMPO70, ecc.)
    2. Operatore/field type: A/S solo su campi tempo, operatori numerici
       solo su campi numerici, flag I/Z non confrontabili con numeri
    3. Condizioni: operatore supportato per tipo campo, riferimenti a
       campi esistenti, validità composizione AND/OR
    """

    # Campi che non possono essere scritti direttamente (solo lettura o K)
    READONLY_FIELDS: set[int] = set(range(1, 7)) | {70, 79}
    # Campi 71-78 devono essere resettati prima di CAMPO70
    CAMPO70_TEMP_FIELDS: set[int] = set(range(71, 79))
    # Campi di sistema, sola lettura
    SYSTEM_FIELDS: set[int] = set(range(7, 20)) | set(range(90, 100))
    # Flag giorno, sola lettura (scrivibili solo da kernel WinSarp)
    DAY_FLAGS: set[int] = set(range(50, 59))

    # Operatori per tipo campo
    # Tempo (hh.mm): A (somma), S (sottrazione), confronti U, #, >, <, >=, <=
    # Numeri interi: +, -, *, /, confronti standard
    # Stringhe/causali: =, #, confronti di uguaglianza
    # Flag: I/Z, solo U (=) e # (!=)
    ALLOWED_OPS_BY_TYPE: dict[str, set[str]] = {
        FIELD_TYPE_TIMBRATURA: {"A", "S", "U", "#", ">", "<", ">=", "<=", ">U", "<U"},
        FIELD_TYPE_CALCOLATA: {"A", "S", "U", "#", ">", "<", ">=", "<=", ">U", "<U"},
        FIELD_TYPE_PREVISIONALE: {"A", "S", "U", "#", ">", "<", ">=", "<=", ">U", "<U"},
        FIELD_TYPE_TOTALE: {"A", "S", "U", "#", ">", "<", ">=", "<="},
        FIELD_TYPE_FLAG: {"U", "#", ">"},
        FIELD_TYPE_CAUSALE: {"U", "#"},
        FIELD_TYPE_APPOGGIO: {"A", "S", "U", "#", ">", "<", ">=", "<=", ">U", "<U", "+", "-", "*", "/"},
        FIELD_TYPE_SISTEMA: set(),
        FIELD_TYPE_K_TOTALE: {"A", "S"},  # solo via K accumulo
    }

    # Fornitori di operatori per i vari formati di condizione
    COND_OP_MAP: dict[str, str] = {
        "U": "U", "=": "U", "==": "U",
        "#": "#", "!=": "#",
        ">": ">", "<": "<",
        ">=": ">U", ">U": ">U",
        "<=": "<U", "<U": "<U",
    }

    def __init__(self):
        self._registry = field_registry

    def validate_spec(self, spec_data: dict) -> list[SemanticIssue]:
        """Valuta una SpecificaFormula JSON completa.

        Args:
            spec_data: Dict come prodotto dall'LLM in _build_json_prompt()

        Returns:
            Lista di SemanticIssue (vuota se tutto OK)
        """
        issues: list[SemanticIssue] = []

        # 1. Valida campi input
        for campo in spec_data.get("campi_input", []):
            self._check_field_readable(campo, issues)

        # 2. Valida campi output
        for campo in spec_data.get("campi_output", []):
            self._check_field_writable(campo, issues)

        # 3. Valida condizioni_azioni
        for idx, ca in enumerate(spec_data.get("condizioni_azioni", [])):
            cond = ca.get("condizione", "")
            if cond:
                self._check_condition(cond, idx, issues)
            azioni = ca.get("azioni", {})
            for campo_str, valore in azioni.items():
                try:
                    campo = int(campo_str)
                except (ValueError, TypeError):
                    issues.append(SemanticIssue(
                        "error", f"Chiave '{campo_str}' non è un numero di campo valido",
                        field=campo_str,
                    ))
                    continue
                self._check_field_writable(campo, issues)
                self._check_value_type(campo, valore, issues)

        # 4. Valida valori_output
        for campo_str, valore in spec_data.get("valori_output", {}).items():
            try:
                campo = int(campo_str)
            except (ValueError, TypeError):
                continue
            self._check_field_writable(campo, issues)
            self._check_value_type(campo, valore, issues)

        # 5. Valida flag_attivazione
        flag = spec_data.get("flag_attivazione")
        if flag and flag not in ("I", "Z", None):
            issues.append(SemanticIssue(
                "error", f"flag_attivazione deve essere 'I' o 'Z', non '{flag}'",
            ))

        # 6. Valida fase
        fase = spec_data.get("fase_esecuzione")
        if fase and fase not in ("IG", "DG", "FG", "SUB"):
            issues.append(SemanticIssue(
                "warning", f"fase_esecuzione '{fase}' non standard. Valori: IG, DG, FG, SUB",
            ))

        return issues

    # Mappa K-register → causale attesa (per validazione semantica)
    K_CAUSALE_MAP: dict[str, str] = {
        "611": "S", "614": "SN", "615": "SF",
        "616": "SFN", "625": "T", "626": "N", "627": "LFS",
        "612": "SP", "613": "SA", "618": "SB",
    }

    # Mappa slot causale (501-510, 561-570) → K-register correlato
    CAUSALE_SLOT_K_MAP: dict[int, str] = {
        501: "611", 561: "611",  # S
        502: "614", 562: "614",  # SN
        503: "615", 563: "615",  # SF
        504: "616", 564: "616",  # SFN
        505: "626", 565: "626",  # N
        506: "625", 566: "625",  # T
    }

    # Campi riservati non scrivibili direttamente (solo via K)
    K_ONLY_FIELDS: set[int] = set(range(601, 700))

    def validate_compact(self, formula: str) -> list[SemanticIssue]:
        """Valida sintassi compatta WinSarp già generata.

        Operazioni:
        - Estrae assegnazioni: ( N = ... )
        - Estrae reset: (!N)
        - Estrae K accumulo: ( K N A/S ... )
        - Estrae condizioni: N U val
        - Verifica ogni campo trovato
        - Controlla consistenza K-register ↔ causali slots
        """
        issues: list[SemanticIssue] = []

        # Reset: (!N)
        for m in re.finditer(r'\(!\s*(\d+)\s*\)', formula):
            campo = int(m.group(1))
            self._check_field_writable(campo, issues)

        # Assignazioni: ( N = val )
        for m in re.finditer(r'\(\s*(\d+)\s*=', formula):
            campo = int(m.group(1))
            self._check_field_writable(campo, issues)

        # K accumulo: ( K N A/S val )
        k_regs_found: set[str] = set()
        for m in re.finditer(r'K\s*(\d+)\s+([AS])\s', formula):
            campo = int(m.group(1))
            k_regs_found.add(str(campo))
            ktype = self._registry.get_k_total(campo) or self._registry.get_field(campo)
            if not ktype:
                issues.append(SemanticIssue(
                    "warning", f"K accumulo su campo {campo} non registrato", field=campo,
                ))

        # Controlla K-register noti ma senza slot causale corrispondente
        for k in k_regs_found:
            causale_attesa = self.K_CAUSALE_MAP.get(k)
            if causale_attesa:
                slot_causale = None
                slot_valore = None
                for slot, expected_k in self.CAUSALE_SLOT_K_MAP.items():
                    if expected_k == k:
                        if 501 <= slot <= 510:
                            slot_causale = slot
                        elif 561 <= slot <= 570:
                            slot_valore = slot
                # Verifica che almeno uno slot sia presente nella formula
                slot_to_check = slot_causale or slot_valore
                if slot_to_check and not re.search(rf'\(!?\s*{slot_to_check}\b', formula):
                    set_found = re.search(rf'\(\s*{slot_to_check}\s*=\s*"([^"]+)"\s*\)', formula)
                    if not set_found:
                        issues.append(SemanticIssue(
                            "warning",
                            f"K{k} ({causale_attesa}) presente ma slot {slot_to_check} non inizializzato "
                            f"— potrebbe mancare la causale corrispondente",
                            field=int(k),
                        ))

            # Controlla K601 (ore lavorate) usato in contesto non-FG (senza 3/4)
            if k == "601" and not re.search(r'[34]\s*=', formula) and not re.search(r'\(\s*[34]\s*[AS]', formula):
                issues.append(SemanticIssue(
                    "info", "K601 (ore lavorate) usato senza riferimenti a 3/4 — "
                            "verifica che sia in contesto FG", field=601,
                ))

        # Controlla: se c'è CAMPO70 99, devono esserci SET 71-78
        if re.search(r'\(\s*70\s*=\s*[\'"]?99[\'"]?\s*\)', formula):
            settati = set()
            for m in re.finditer(r'\(\s*(7[1-8])\s*=', formula):
                settati.add(int(m.group(1)))
            for n in range(71, 79):
                if n not in settati:
                    issues.append(SemanticIssue(
                        "info", f"CAMPO70 99 (diagnostico) ma campo {n} non settato — "
                                f"output potrebbe essere incompleto", field=n,
                    ))

        # Controlla: slot causale 501-510 con valore senza K corrispondente
        for m in re.finditer(r'\(\s*(5[0-5]\d)\s*=\s*"(\w+)"\s*\)', formula):
            slot = int(m.group(1))
            causale = m.group(2)
            k_atteso = self.CAUSALE_SLOT_K_MAP.get(slot)
            if k_atteso:
                causale_attesa = self.K_CAUSALE_MAP.get(k_atteso)
                if causale_attesa and causale != causale_attesa:
                    issues.append(SemanticIssue(
                        "warning",
                        f"Slot causale {slot} usa \"{causale}\" ma K{k_atteso} corrisponde a \"{causale_attesa}\"",
                        field=slot,
                    ))
                if k_atteso not in k_regs_found:
                    issues.append(SemanticIssue(
                        "info", f"Causale \"{causale}\" in slot {slot} ma K{k_atteso} mai accumulato "
                                f"— verifica accumulo ore",
                        field=slot,
                    ))

        return issues

    # ---- Controlli interni ----

    def _check_field_readable(self, campo: int, issues: list[SemanticIssue]) -> None:
        """Verifica che un campo possa essere letto."""
        info = self._registry.get_field(campo)
        if not info:
            issues.append(SemanticIssue("warning", f"Campo {campo} sconosciuto al registry", field=campo))
            return
        if info.field_type == FIELD_TYPE_SISTEMA:
            issues.append(SemanticIssue("warning", f"Campo sistema {campo} ({info.description})", field=campo))

    def _check_field_writable(self, campo: int, issues: list[SemanticIssue]) -> None:
        """Verifica che un campo possa essere scritto."""
        info = self._registry.get_field(campo)

        # Campi 1-6, 70, 79: scrivibili in contesti specifici (riproporzionamento, CAMPO70)
        if campo in self.READONLY_FIELDS:
            if campo in (70, 79):
                issues.append(SemanticIssue(
                    "error",
                    f"Campo {campo} scritto direttamente (CAMPO70 pattern). "
                    f"Verifica che sia intenzionale.",
                    field=campo,
                ))
            else:
                issues.append(SemanticIssue(
                    "error",
                    f"Campo {campo} scritto direttamente (K accumulo preferibile). "
                    f"Verifica che sia nel contesto corretto (FG/riproporzionamento).",
                    field=campo,
                ))
            return

        if campo in self.SYSTEM_FIELDS:
            issues.append(SemanticIssue(
                "error", f"Campo sistema {campo}: scritto solo in contesti specifici", field=campo,
            ))
            return

        if campo in self.DAY_FLAGS:
            issues.append(SemanticIssue(
                "error",
                f"Campo giorno {campo}: causale scritta direttamente. "
                f"Verifica che sia corretta per il contesto.",
                field=campo,
            ))
            return

        if not info:
            issues.append(SemanticIssue("warning", f"Campo {campo} sconosciuto al registry", field=campo))
            return

        # Campi totali 1-6, vanno scritti solo via K accumulo
        if info.field_type == FIELD_TYPE_TOTALE and campo <= 6:
            issues.append(SemanticIssue(
                "error",
                f"Campo totale {campo} non scrivibile direttamente. Usa K{600+campo} accumulo.",
                field=campo,
            ))

    def _check_condition(self, cond: str, idx: int, issues: list[SemanticIssue]) -> None:
        """Valuta una singola condizione logica.

        Condizioni tipo:
          "70 > 170"
          "55 = I"
          "800 <= 12"
          "50 = I AND 55 = I"
          "251 = Z OR 252 > Z"
        """
        # Separa condizioni composte da AND/E e OR/O
        sub_conds = re.split(r'\s+(?:AND|E|OR|O)\s+', cond, flags=re.IGNORECASE)

        for sub in sub_conds:
            self._check_single_condition(sub.strip(), idx, issues)

    def _check_single_condition(self, cond: str, idx: int, issues: list[SemanticIssue]) -> None:
        """Valuta una condizione atomica (es. '70 > 170', '55 = I')."""
        # Pattern: campo operatore valore
        m = re.match(
            r'(?:campo\s+|F\(\s*)?(?P<field>\d{1,4})(?:\s*\))?\s*'
            r'(?P<op>>U|<U|>=|<=|>|<|=|#|!=|U)'
            r'\s*(?P<value>.+)',
            cond,
            re.IGNORECASE,
        )
        if not m:
            issues.append(SemanticIssue(
                "warning", f"Condizione #{idx}: '{cond}' non parsabile", field=cond,
            ))
            return

        campo = int(m.group("field"))
        op = m.group("op")
        valore = m.group("value").strip().strip("'\"")

        info = self._registry.get_field(campo)
        if not info:
            issues.append(SemanticIssue(
                "warning", f"Condizione #{idx}: campo {campo} sconosciuto", field=campo,
            ))
            return

        # Mappa operatore al formato normalizzato
        op_norm = self.COND_OP_MAP.get(op, op)
        ops_valide = self.ALLOWED_OPS_BY_TYPE.get(info.field_type, set())

        if ops_valide and op_norm not in ops_valide:
            issues.append(SemanticIssue(
                "warning",
                f"Condizione #{idx}: operatore '{op}' non usuale per campo {campo} "
                f"(tipo {info.field_type}). Attesi: {ops_valide}",
                field=campo,
            ))

        # Controllo tipo valore vs tipo campo
        if info.field_type in (FIELD_TYPE_FLAG, FIELD_TYPE_CAUSALE):
            if valore.upper() not in ("I", "Z") and not valore.startswith('"') and not valore.startswith("'"):
                # Flag confrontati solo con I/Z
                if op_norm in (">", "<", ">=", "<="):
                    issues.append(SemanticIssue(
                        "warning",
                        f"Condizione #{idx}: confronto {op} con flag/causale {campo}. "
                        f"Usa solo U (=) o # (!=) con I/Z.",
                        field=campo,
                    ))
        elif info.field_type in (FIELD_TYPE_TIMBRATURA, FIELD_TYPE_CALCOLATA):
            # Campi tempo: valori dovrebbero essere orari (hh.mm)
            if valore.upper() not in ("I", "Z") and not re.match(r'^\d+[.,]?\d*$', valore):
                issues.append(SemanticIssue(
                    "warning",
                    f"Condizione #{idx}: valore '{valore}' per campo tempo {campo}. "
                    f"Aspettato orario (hh.mm).",
                    field=campo,
                ))

    def _check_value_type(self, campo: int, valore: Any, issues: list[SemanticIssue]) -> None:
        """Verifica che il valore assegnato sia compatibile col tipo campo."""
        if not isinstance(valore, str):
            valore = str(valore)

        info = self._registry.get_field(campo)
        if not info:
            return

        valore_strip = valore.strip().strip("'\"")

        if info.field_type in (FIELD_TYPE_FLAG, FIELD_TYPE_CAUSALE) and campo >= 50:
            # Flag e causali: I, Z, o stringhe causale
            if valore_strip.upper() not in ("I", "Z") and not valore_strip.startswith('"'):
                if not re.match(r'^[A-Z]{2,6}$', valore_strip):
                    issues.append(SemanticIssue(
                        "warning",
                        f"Valore '{valore}' per flag/causale {campo}. "
                        f"Aspettato I, Z, o causale (es. \"MATT\")",
                        field=campo,
                    ))

        elif info.field_type in (FIELD_TYPE_TIMBRATURA, FIELD_TYPE_CALCOLATA, FIELD_TYPE_PREVISIONALE):
            # Campi tempo
            if not re.match(r'^\d+[.,]?\d*$', valore_strip) and valore_strip.upper() not in ("I", "Z"):
                issues.append(SemanticIssue(
                    "warning",
                    f"Valore '{valore}' per campo tempo {campo}. Aspettato orario hh.mm",
                    field=campo,
                ))

    def _check_op_for_field_type(self, field: int, op: str, issues: list[SemanticIssue]) -> None:
        """Controlla se un operatore è compatibile col tipo campo."""
        info = self._registry.get_field(field)
        if not info:
            return
        ops_valide = self.ALLOWED_OPS_BY_TYPE.get(info.field_type, set())
        if ops_valide and op not in ops_valide:
            issues.append(SemanticIssue(
                "warning",
                f"Operatore '{op}' non usuale per campo {field} (tipo {info.field_type}). "
                f"Usa: {ops_valide}",
                field=field,
            ))


def valida_specifica_formula(spec_data: dict) -> list[SemanticIssue]:
    """Funzione di comodo per validare una SpecificaFormula."""
    validator = SemanticFormulaValidator()
    return validator.validate_spec(spec_data)


def valida_formula_compatta(compact: str) -> list[SemanticIssue]:
    """Funzione di comodo per validare sintassi compatta."""
    validator = SemanticFormulaValidator()
    return validator.validate_compact(compact)
