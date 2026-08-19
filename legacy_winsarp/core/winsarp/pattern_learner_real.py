"""
Pattern Learner - Estrazione automatica pattern dalle formule REALI in uso.

Analizza le formule reali dell'utente (FormuleWinsarpInUso.txt) per identificare:
- Pattern strutturali reali usati in produzione
- Cluster di formule simili per categoria
- Template parametrizzabili basati su formule verificate
"""

import logging
import re
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any

from config import cfg

_logger = logging.getLogger(__name__)


@dataclass
class RealFormula:
    """Formula reale in uso."""
    code: int
    raw_code: str
    compact_code: str
    description: str = ""
    category: str = ""
    tipo: str = ""
    fields_involved: Set[int] = field(default_factory=set)
    calls: List[Tuple[str, int]] = field(default_factory=list)  # (type, target)


@dataclass
class StructuralPattern:
    """Pattern strutturale di una formula reale."""
    name: str
    structure: str
    components: List[str] = field(default_factory=list)
    field_patterns: List[int] = field(default_factory=list)
    frequency: int = 0
    example_formulas: List[int] = field(default_factory=list)


class RealPatternLearner:
    """Estrae pattern dalle formule reali in uso."""

    def __init__(self, real_formulas_path: str | None = None):
        self._formulas: List[RealFormula] = []
        self._structural_patterns: Dict[str, StructuralPattern] = {}
        self._clusters: Dict[str, List[RealFormula]] = defaultdict(list)
        self._initialized = False
        self._real_formulas_path = real_formulas_path

    def initialize(self) -> None:
        """Carica e analizza le formule reali."""
        if self._initialized:
            return

        _logger.info("Inizializzazione Real Pattern Learner...")

        # Carica formule reali
        if self._real_formulas_path:
            self._load_real_formulas(self._real_formulas_path)
        else:
            # Fallback: usa il path dell'utente
            default_path = str(Path(cfg.CATALOGO_PATH).parent / "FormuleWinsarpInUso.txt")
            if Path(default_path).exists():
                self._load_real_formulas(default_path)
            else:
                _logger.warning("File formule reali non trovato: %s", default_path)

        if self._formulas:
            self._extract_structural_patterns()
            self._cluster_formulas()
            self._initialized = True
            _logger.info(
                "Real Pattern Learner inizializzato: %d formule, %d pattern, %d cluster",
                len(self._formulas),
                len(self._structural_patterns),
                len(self._clusters)
            )

    def _load_real_formulas(self, path: str) -> None:
        """Carica formule dal file reali."""
        try:
            with open(path, encoding='utf-8') as f:
                content = f.read()

            # Parse formule
            formula_blocks = re.split(r'\nformula\s+(\d+)\s*\n', content)

            for i in range(1, len(formula_blocks), 2):
                if i + 1 >= len(formula_blocks):
                    break

                code = int(formula_blocks[i])
                raw_code = formula_blocks[i + 1]

                # Pulisci il codice
                compact_code = self._compact_code(raw_code)

                # Estrai categoria e tipo dal codice
                category, tipo = self._infer_category(code)

                formula = RealFormula(
                    code=code,
                    raw_code=raw_code,
                    compact_code=compact_code,
                    category=category,
                    tipo=tipo,
                    fields_involved=self._extract_fields(compact_code),
                    calls=self._extract_calls(compact_code)
                )

                self._formulas.append(formula)

            _logger.info("Caricate %d formule reali da %s", len(self._formulas), path)

        except Exception as e:
            _logger.error("Errore caricamento formule reali: %s", e)

    def _compact_code(self, raw: str) -> str:
        """Converte codice con spazi in formato compatto."""
        # Rimuovi commenti con ?
        lines = []
        for line in raw.split('\n'):
            if '?' in line:
                line = line.split('?')[0]
            lines.append(line)

        # Rimuovi spazi extra
        compact = ' '.join(' '.join(lines).split())

        # Rimuovi spazi attorno a operatori WinSarp
        compact = re.sub(r'\s*([()=!<>#A S \[\]])\s*', r'\1', compact)

        return compact.strip()

    def _infer_category(self, code: int) -> Tuple[str, str]:
        """Inferisce categoria e tipo dal numero formula."""
        if code <= 10:
            return "Inizio Giornata", "IG"
        elif 100 <= code <= 299:
            return "Fine Giornata", "FG"
        elif 1000 <= code <= 1999:
            return "Inizio Giornata", "IG"
        elif 2000 <= code <= 2999:
            return "Fine Giornata", "FG"
        elif 2100 <= code <= 2199:
            return "Gestione Personalizzata", "FG"
        elif 3000 <= code <= 3999:
            return "Gestione Personalizzata", "FG"
        elif 9000 <= code <= 9999:
            return "Arrotondamento", "IG"
        else:
            return "Subroutine", "SUB"

    def _extract_fields(self, code: str) -> Set[int]:
        """Estrae campi usati nella formula."""
        fields = set()
        # Trova numeri che sembrano campi (>= 50 o specifici noti)
        for match in re.finditer(r'\b(\d{2,4})\b', code):
            f = int(match.group(1))
            if f >= 50 or f in [1, 2, 3, 4, 5, 58, 100]:
                fields.add(f)
        return fields

    def _extract_calls(self, code: str) -> List[Tuple[str, int]]:
        """Estrae chiamate R/P."""
        calls = []
        for match in re.finditer(r'([RP])(\d{3,4})', code):
            calls.append((match.group(1), int(match.group(2))))
        return calls

    def _extract_structural_patterns(self) -> None:
        """Estrae pattern strutturali dalle formule reali."""
        pattern_counter = Counter()

        for formula in self._formulas:
            structure = self._analyze_structure(formula.compact_code)
            pattern_counter[structure] += 1

            if structure not in self._structural_patterns:
                self._structural_patterns[structure] = StructuralPattern(
                    name=structure,
                    structure=structure,
                    components=self._extract_components(formula.compact_code),
                    field_patterns=list(formula.fields_involved),
                    example_formulas=[formula.code]
                )
            else:
                if formula.code not in self._structural_patterns[structure].example_formulas:
                    self._structural_patterns[structure].example_formulas.append(formula.code)

        # Aggiorna frequenze
        for structure, pattern in self._structural_patterns.items():
            pattern.frequency = pattern_counter[structure]

        _logger.info("Estratti %d pattern strutturali da formule reali", len(self._structural_patterns))

    def _analyze_structure(self, code: str) -> str:
        """Analizza la struttura di una formula reale."""
        if not code:
            return "EMPTY"

        structure_parts = []

        # Rileva costrutti principali (basati su formule reali)
        if re.search(r'\([^)]*Z[^)]*\)', code):
            structure_parts.append("IF_Z")
        elif re.search(r'\([^)]*[<>#=!][^)]*\)', code):
            structure_parts.append("IF")

        if re.search(r'K\d+[AS]', code):
            structure_parts.append("K")

        if re.search(r'!\d+', code):
            structure_parts.append("RESET")

        if re.search(r'R\d+', code):
            structure_parts.append("R")

        if re.search(r'P\d+', code):
            structure_parts.append("P")

        if re.search(r'VF|VU|V\d+', code):
            structure_parts.append("V")

        if re.search(r'70=', code):
            structure_parts.append("C70")

        if not structure_parts:
            structure_parts.append("SIMPLE")

        return "_".join(sorted(structure_parts))

    def _extract_components(self, code: str) -> List[str]:
        """Estrae componenti di una formula."""
        components = []

        # IF conditions
        if_matches = re.findall(r'\([^)]*Z[^)]*\)', code)
        components.extend([f"IF_{i}" for i in range(len(if_matches))])

        # K operations
        k_matches = re.findall(r'K(\d+)[AS]', code)
        components.extend([f"K_{k}" for k in k_matches])

        # Resets
        reset_matches = re.findall(r'!(\d+)', code)
        components.extend([f"RESET_{r}" for r in reset_matches])

        # Calls
        r_matches = re.findall(r'R(\d+)', code)
        p_matches = re.findall(r'P(\d+)', code)
        components.extend([f"R_{r}" for r in r_matches])
        components.extend([f"P_{p}" for p in p_matches])

        return components

    def _cluster_formulas(self) -> None:
        """Clusterizza formule per categoria."""
        for formula in self._formulas:
            self._clusters[formula.category].append(formula)

        _logger.info("Creati %d cluster per categoria", len(self._clusters))

    def get_real_formula(self, code: int) -> RealFormula | None:
        """Ottieni formula reale per codice."""
        for formula in self._formulas:
            if formula.code == code:
                return formula
        return None

    def get_similar_real_formulas(self, formula_code: int, top_k: int = 5) -> List[Tuple[int, float]]:
        """Trova formule reali simili."""
        target = self.get_real_formula(formula_code)
        if not target:
            return []

        target_structure = self._analyze_structure(target.compact_code)
        target_fields = target.fields_involved

        similarities = []

        for formula in self._formulas:
            if formula.code == formula_code:
                continue

            structure = self._analyze_structure(formula.compact_code)
            fields = formula.fields_involved

            # Calcola similarità
            structure_match = 1.0 if structure == target_structure else 0.0
            field_overlap = len(target_fields & fields) / max(len(target_fields | fields), 1)

            similarity = 0.7 * structure_match + 0.3 * field_overlap
            similarities.append((formula.code, similarity))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    def get_template_for_category(self, category: str) -> Dict[str, Any] | None:
        """Ottieni template da formule reali per categoria."""
        formulas = self._clusters.get(category)
        if not formulas:
            return None

        # Prendi la formula più complessa come rappresentativa
        representative = max(formulas, key=lambda x: len(x.compact_code))

        # Trova campi comuni
        all_fields = [f.fields_involved for f in formulas]
        common_fields = set.intersection(*all_fields) if all_fields else set()

        return {
            "category": category,
            "template_code": representative.code,
            "template_compact": representative.compact_code,
            "template_raw": representative.raw_code,
            "common_fields": sorted(common_fields),
            "all_formulas_in_category": [f.code for f in formulas],
            "tipo": representative.tipo
        }

    def suggest_pattern_for_request(self, request_text: str) -> Dict[str, Any] | None:
        """Suggerisce pattern basato su richiesta testuale."""
        if not self._initialized:
            self.initialize()

        # Analizza richiesta per identificare categoria
        request_lower = request_text.lower()

        # Mapping keywords → categoria (basato su formule reali)
        category_keywords = {
            "Fine Giornata": ["straordinario", "straord", "extra", "maggiorazione", "turno", "fine giornata"],
            "Arrotondamento": ["arrotondamento", "arrotonda", "approssima", "quarti", "minuti"],
            "Gestione Personalizzata": ["gugest", "avispa", "personalizzata", "flusso"],
            "Inizio Giornata": ["inizio", "azzeramento", "reset", "inizializza"],
            "Subroutine": ["subroutine", "causale", "esplo", "festività"],
        }

        best_category = None
        best_score = 0

        for category, keywords in category_keywords.items():
            score = sum(1 for kw in keywords if kw in request_lower)
            if score > best_score:
                best_score = score
                best_category = category

        if best_category and best_score > 0:
            return self.get_template_for_category(best_category)

        return None

    def get_all_real_formulas(self) -> List[Dict[str, Any]]:
        """Ottieni tutte le formule reali come dizionario."""
        return [
            {
                "code": f.code,
                "compact": f.compact_code,
                "raw": f.raw_code,
                "category": f.category,
                "tipo": f.tipo,
                "fields": sorted(f.fields_involved),
                "calls": f.calls
            }
            for f in self._formulas
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Statistiche sulle formule reali."""
        return {
            "total_formulas": len(self._formulas),
            "by_category": {cat: len(formulas) for cat, formulas in self._clusters.items()},
            "by_tipo": Counter(f.tipo for f in self._formulas),
            "most_common_patterns": [
                (p.name, p.frequency, p.example_formulas[:3])
                for p in sorted(self._structural_patterns.values(), key=lambda x: x.frequency, reverse=True)[:10]
            ]
        }


# Singleton
_real_pattern_learner: RealPatternLearner | None = None


def get_real_pattern_learner(path: str | None = None) -> RealPatternLearner:
    """Ottieni il singleton Real Pattern Learner."""
    global _real_pattern_learner
    if _real_pattern_learner is None:
        # Usa il path delle formule reali dell'utente se non specificato
        if path is None:
            path = str(Path(cfg.CATALOGO_PATH).parent / "FormuleWinsarpInUso.txt")
        _real_pattern_learner = RealPatternLearner(real_formulas_path=path)
    return _real_pattern_learner
