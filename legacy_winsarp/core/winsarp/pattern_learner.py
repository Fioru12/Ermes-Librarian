"""
Pattern Learner - Estrazione automatica pattern dal catalogo WinSarp.

Analizza le formule esistenti per identificare:
- Pattern strutturali comuni (IF, K, RESET, etc.)
- Cluster di formule simili per categoria
- Template parametrizzabili per generazione
"""

import logging
import re
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Any

from legacy_winsarp.core.winsarp.catalog import load_catalog
from legacy_winsarp.core.winsarp.patterns import FormulaPatternLibrary

_logger = logging.getLogger(__name__)


@dataclass
class StructuralPattern:
    """Pattern strutturale di una formula."""
    name: str
    structure: str  # Es. "IF_K_RESET_VF"
    components: List[str] = field(default_factory=list)
    field_patterns: List[int] = field(default_factory=list)
    frequency: int = 0


@dataclass
class FormulaCluster:
    """Cluster di formule simili."""
    cluster_id: str
    category: str
    formulas: List[int] = field(default_factory=list)
    common_fields: Set[int] = field(default_factory=set)
    common_structure: str = ""
    representative: int = 0


class PatternLearner:
    """Estrae pattern strutturali dal catalogo formule."""

    def __init__(self):
        self._catalog: List[Dict[str, Any]] = []
        self._pattern_library: FormulaPatternLibrary = FormulaPatternLibrary()
        self._structural_patterns: Dict[str, StructuralPattern] = {}
        self._clusters: Dict[str, FormulaCluster] = {}
        self._initialized = False

    def initialize(self) -> None:
        """Carica catalogo e calcola pattern."""
        if self._initialized:
            return

        _logger.info("Inizializzazione Pattern Learner...")

        try:
            self._catalog = load_catalog()
            _logger.info("Catalogo caricato: %d formule", len(self._catalog))
        except Exception as e:
            _logger.warning("Errore caricamento catalogo: %s", e)
            self._catalog = []

        self._extract_structural_patterns()
        self._cluster_formulas()
        self._initialized = True

        _logger.info(
            "Pattern Learner inizializzato: %d pattern strutturali, %d cluster",
            len(self._structural_patterns),
            len(self._clusters)
        )

    def _extract_structural_patterns(self) -> None:
        """Estrae pattern strutturali dalle formule."""
        pattern_counter = Counter()

        for formula in self._catalog:
            code = formula.get("code")
            formula_code = formula.get("code", "")

            # Estrai struttura
            structure = self._analyze_structure(formula_code)
            pattern_counter[structure] += 1

            # Estrai componenti
            components = self._extract_components(formula_code)

            # Crea pattern se non esiste
            if structure not in self._structural_patterns:
                self._structural_patterns[structure] = StructuralPattern(
                    name=structure,
                    structure=structure,
                    components=components,
                    field_patterns=self._extract_field_patterns(formula_code)
                )

            self._structural_patterns[structure].frequency += 1

        # Aggiorna frequenze
        for structure, pattern in self._structural_patterns.items():
            pattern.frequency = pattern_counter[structure]

        _logger.info("Estratti %d pattern strutturali", len(self._structural_patterns))

    def _analyze_structure(self, code: str) -> str:
        """Analizza la struttura di una formula."""
        if not code:
            return "EMPTY"

        structure_parts = []

        # Rileva costrutti principali
        if re.search(r'\([^)]*Z[^)]*\)', code):  # Condizione con Z
            structure_parts.append("IF_Z")
        elif re.search(r'\([^)]*[<>#=!][^)]*\)', code):  # Condizione generica
            structure_parts.append("IF")

        if re.search(r'K\d+[AS]', code):  # Accumulo K
            structure_parts.append("K")

        if re.search(r'!\d+', code):  # Reset
            structure_parts.append("RESET")

        if re.search(r'R\d+', code):  # Goto
            structure_parts.append("R")

        if re.search(r'P\d+', code):  # Perform
            structure_parts.append("P")

        if re.search(r'VF|VU', code):  # Return
            structure_parts.append("V")

        if re.search(r'70=', code):  # Campo70
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

    def _extract_field_patterns(self, code: str) -> List[int]:
        """Estrae campi usati nella formula."""
        fields = set()

        # Field references
        field_matches = re.findall(r'\b(\d{2,4})\b', code)
        for f in field_matches:
            f_int = int(f)
            # Filtra numeri che sono probabilmente valori, non campi
            if f_int >= 50 or f_int in [1, 2, 3, 4, 5]:
                fields.add(f_int)

        return sorted(fields)

    def _cluster_formulas(self) -> None:
        """Clusterizza formule simili per categoria."""
        category_formulas = defaultdict(list)

        # Raggruppa per categoria
        for formula in self._catalog:
            category = formula.get("categoria", "Altro")
            category_formulas[category].append(formula)

        # Crea cluster per categoria
        for category, formulas in category_formulas.items():
            cluster_id = f"cluster_{category.lower().replace(' ', '_')}"

            # Trova campi comuni
            all_fields = []
            for f in formulas:
                all_fields.extend(f.get("numeric_refs", []))

            field_counter = Counter(all_fields)
            common_fields = {f for f, c in field_counter.items() if c >= len(formulas) * 0.5}

            # Trova struttura comune
            structures = []
            for f in formulas:
                structure = self._analyze_structure(f.get("code", ""))
                structures.append(structure)

            structure_counter = Counter(structures)
            common_structure = structure_counter.most_common(1)[0][0] if structures else ""

            # Rappresentativo (formula più complessa)
            representative = max(formulas, key=lambda x: len(x.get("code", ""))).get("code", 0)

            self._clusters[cluster_id] = FormulaCluster(
                cluster_id=cluster_id,
                category=category,
                formulas=[f.get("code") for f in formulas],
                common_fields=common_fields,
                common_structure=common_structure,
                representative=representative
            )

        _logger.info("Creati %d cluster di formule", len(self._clusters))

    def get_similar_formulas(self, formula_code: int, top_k: int = 5) -> List[Tuple[int, float]]:
        """Trova formule simili per struttura e campi."""
        if not self._initialized:
            self.initialize()

        target_formula = next((f for f in self._catalog if f.get("code") == formula_code), None)
        if not target_formula:
            return []

        target_structure = self._analyze_structure(target_formula.get("code", ""))
        target_fields = set(target_formula.get("numeric_refs", []))

        similarities = []

        for formula in self._catalog:
            if formula.get("code") == formula_code:
                continue

            code = formula.get("code")
            structure = self._analyze_structure(formula.get("code", ""))
            fields = set(formula.get("numeric_refs", []))

            # Calcola similarità
            structure_match = 1.0 if structure == target_structure else 0.0
            field_overlap = len(target_fields & fields) / max(len(target_fields | fields), 1)

            similarity = 0.7 * structure_match + 0.3 * field_overlap
            similarities.append((code, similarity))

        # Ordina per similarità
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]

    def get_template_for_category(self, category: str) -> Dict[str, Any] | None:
        """Ottieni template parametrizzabile per una categoria."""
        if not self._initialized:
            self.initialize()

        cluster_id = f"cluster_{category.lower().replace(' ', '_')}"
        cluster = self._clusters.get(cluster_id)

        if not cluster:
            return None

        # Ottieni formula rappresentativa
        pattern = self._pattern_library.get_pattern(cluster.representative)

        if not pattern:
            return None

        return {
            "category": category,
            "template_code": cluster.representative,
            "template_compact": pattern.compact,
            "common_fields": sorted(cluster.common_fields),
            "common_structure": cluster.common_structure,
            "similar_formulas": cluster.formulas[:5],
            "description": pattern.description
        }

    def suggest_pattern_for_request(self, request_text: str) -> Dict[str, Any] | None:
        """Suggerisce pattern basato su richiesta testuale."""
        if not self._initialized:
            self.initialize()

        # Analizza richiesta per identificare categoria
        request_lower = request_text.lower()

        # Mapping keywords → categoria
        category_keywords = {
            "Straordinario": ["straordinario", "straord", "extra"],
            "Arrotondamento": ["arrotondamento", "arrotonda", "approssima"],
            "Festività": ["festività", "festivo", "domenica"],
            "Pausa Pranzo": ["pausa", "pranzo", "mensa"],
            "Turnisti": ["turno", "turnista", "maggiorazione"],
            "Causali": ["causale", "causali", "esplo"],
            "Alert": ["warning", "avviso", "allarme"],
            "Standard": ["standard", "normale", "base"],
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

    def get_pattern_statistics(self) -> Dict[str, Any]:
        """Statistiche sui pattern estratti."""
        if not self._initialized:
            self.initialize()

        return {
            "total_formulas": len(self._catalog),
            "total_structural_patterns": len(self._structural_patterns),
            "total_clusters": len(self._clusters),
            "most_common_patterns": [
                (p.name, p.frequency)
                for p in sorted(self._structural_patterns.values(), key=lambda x: x.frequency, reverse=True)[:10]
            ],
            "clusters_by_size": [
                (c.category, len(c.formulas))
                for c in sorted(self._clusters.values(), key=lambda x: len(x.formulas), reverse=True)
            ]
        }


# Singleton
_pattern_learner: PatternLearner | None = None


def get_pattern_learner() -> PatternLearner:
    """Ottieni il singleton Pattern Learner."""
    global _pattern_learner
    if _pattern_learner is None:
        _pattern_learner = PatternLearner()
    return _pattern_learner
