"""
Table Registry — Conoscenza strutturata di causali, contratti e relazioni tra formule.

Fornisce un modello di dominio per:
- Causali (manuali e automatiche): codici, slot, descrizioni, flag tipo
- Relazioni tra formule: chi chiama chi
- Dettagli contrattuali estesi
- Mappatura slot -> causale (da formule 2115/3015)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


# ============================================================
# Tipi causale
# ============================================================

CAUSALE_TIPO_ASSENZA = "A"
CAUSALE_TIPO_PRESENZA = "P"
CAUSALE_TIPO_TURNO = "T"

CAUSALE_ORIGINE_MANUALE = "manuale"
CAUSALE_ORIGINE_AUTOMATICA = "automatica"
CAUSALE_ORIGINE_TURNO = "turno"


# ============================================================
# Modelli dati
# ============================================================


@dataclass
class CausaleInfo:
    """Definizione di un codice causale WinSarp."""

    code: str
    name: str
    description: str
    origin: str = CAUSALE_ORIGINE_AUTOMATICA
    tipo: str | None = None  # A=Assenza, P=Presenza
    category: str = ""  # straordinario, festivita, maggiorazione, supplementare, turno


@dataclass
class CausaleSlotMapping:
    """Mappatura slot causale automatica -> codice causale (da formule 2115/3015)."""

    slot: int  # 501-510
    code: str
    description: str
    source_fields: list[int] = field(default_factory=list)  # campi ore che generano questa causale
    formula_ref: str = ""


@dataclass
class FormulaRelation:
    """Relazione tra formule (chiamate P o salti R)."""

    from_code: int
    to_code: int
    relation_type: str  # "P" = perform, "R" = jump, "chain" = flusso
    description: str = ""


@dataclass
class ContractDetail:
    """Dettaglio esteso contratto WinSarp."""

    number: int
    name: str
    description: str
    timbra: bool = True
    max_entry_offset: str | None = None
    fascia_notturna_start: str = "22:00"
    fascia_notturna_end: str = "06:00"
    formulas_ig: list[int] = field(default_factory=list)  # Inizio Giornata formulas
    formulas_fg: list[int] = field(default_factory=list)  # Fine Giornata formulas


# ============================================================
# Registry completo delle tabelle
# ============================================================


class TableRegistry:
    """Registro di tutte le tabelle WinSarp: causali, contratti, relazioni."""

    # Causali note (codice -> info)
    CAUSALI: dict[str, CausaleInfo] = {}
    # Mappatura slot automatici (slot -> mappa slot->codice)
    SLOT_MAPPINGS: dict[int, CausaleSlotMapping] = {}
    # Relazioni tra formule
    FORMULA_RELATIONS: list[FormulaRelation] = []
    # Dettaglio contratti
    CONTRACTS: dict[int, ContractDetail] = {}
    # Flussi formula per tipo
    FORMULA_FLOWS: dict[str, list[int]] = {}

    _instance: TableRegistry | None = None

    def __new__(cls) -> TableRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self._build_causali()
        self._build_slot_mappings()
        self._build_contracts()
        self._build_formula_relations()
        self._build_formula_flows()
        self._load_from_grammar()

    def _build_causali(self) -> None:
        """Costruisce database completo codici causale."""
        self.CAUSALI = {
            # --- Straordinario ---
            "SA": CausaleInfo("SA", "Straordinario Diurno (1a fascia)",
                              "Straordinario diurno prima fascia (slot 506/507)",
                              category="straordinario"),
            "SB": CausaleInfo("SB", "Straordinario Diurno (2a fascia)",
                              "Straordinario diurno seconda fascia (slot 510)",
                              category="straordinario"),
            "SN": CausaleInfo("SN", "Straordinario Notturno",
                              "Straordinario notturno (slot 502/508)",
                              category="straordinario"),
            "SF": CausaleInfo("SF", "Straordinario Festivo Diurno",
                              "Straordinario festivo diurno (slot 503/507)",
                              category="straordinario"),
            "SFN": CausaleInfo("SFN", "Straordinario Festivo Notturno",
                               "Straordinario festivo notturno (slot 504/509)",
                               category="straordinario"),
            "SNF": CausaleInfo("SNF", "Straordinario Notturno Festivo",
                               "Straordinario notturno festivo (slot 509)",
                               category="straordinario"),
            # --- Supplementare ---
            "SP": CausaleInfo("SP", "Supplementare",
                              "Ore supplementari (slot 505)",
                              category="supplementare"),
            # --- Maggiorazioni ---
            "N": CausaleInfo("N", "Maggiorazione Notturna",
                             "Maggiorazione turno notturno (slot 502/505, 565)",
                             category="maggiorazione"),
            "NF": CausaleInfo("NF", "Maggiorazione Notturna Festiva",
                              "Maggiorazione notturna festiva (slot 503)",
                              category="maggiorazione"),
            "T": CausaleInfo("T", "Maggiorazione Turno Diurno",
                             "Maggiorazione turno diurno (slot 506, 566)",
                             category="maggiorazione"),
            "LFS": CausaleInfo("LFS", "Lavoro Festivo Straordinario",
                               "Maggiorazione lavoro festivo (slot 504)",
                               category="maggiorazione"),
            # --- Festività ---
            "F": CausaleInfo("F", "Festività Normale",
                             "Festività normale (slot 501, 918+919=1)",
                             category="festivita"),
            "FNG": CausaleInfo("FNG", "Festività Non Goduta",
                               "Festività non goduta (slot 501, 919=2)",
                               category="festivita"),
            "FP": CausaleInfo("FP", "Festività Patrono",
                              "Festività patrono (slot 501, 919=3)",
                              category="festivita"),
            "FX": CausaleInfo("FX", "Festività in Stipendio",
                              "Festività in stipendio (slot 501, 919=4, variante B)",
                              category="festivita"),
            # --- Tipi orario / Turno (campo 58) ---
            "MATT": CausaleInfo("MATT", "Turno Mattino",
                                "Tipo orario: turno mattino (06-14)",
                                origin=CAUSALE_ORIGINE_TURNO, category="turno"),
            "POME": CausaleInfo("POME", "Turno Pomeriggio",
                                "Tipo orario: turno pomeriggio (14-22)",
                                origin=CAUSALE_ORIGINE_TURNO, category="turno"),
            "NOTT": CausaleInfo("NOTT", "Turno Notte",
                                "Tipo orario: turno notte (22-06)",
                                origin=CAUSALE_ORIGINE_TURNO, category="turno"),
            "RIPO": CausaleInfo("RIPO", "Riposo",
                                "Tipo orario: giorno di riposo",
                                origin=CAUSALE_ORIGINE_TURNO, category="turno"),
            "OPE": CausaleInfo("OPE", "Operaio Spezzato",
                               "Tipo orario: operaio con spezzatura (2 intervalli 08-12/13-17)",
                               origin=CAUSALE_ORIGINE_TURNO, category="turno"),
            "CHIA": CausaleInfo("CHIA", "Chiamata",
                                "Tipo orario: dipendente a chiamata",
                                origin=CAUSALE_ORIGINE_TURNO, category="turno"),
            "CHI": CausaleInfo("CHI", "Chiamata (effettuata)",
                               "Tipo orario: chiamata effettuata",
                               origin=CAUSALE_ORIGINE_TURNO, category="turno"),
            # --- Autorizzazioni ---
            "AUTS": CausaleInfo("AUTS", "Autorizzazione Straordinario",
                                "Autorizzazione straordinario (causale manuale 401-404)",
                                origin=CAUSALE_ORIGINE_MANUALE, category="autorizzazione"),
            # --- Flag tipo causale manuale (441-450) ---
            "ASSENZA": CausaleInfo("A", "Assenza",
                                   "Flag tipo causale manuale: ASSENZA",
                                   origin=CAUSALE_ORIGINE_MANUALE, tipo=CAUSALE_TIPO_ASSENZA),
            "PRESENZA": CausaleInfo("P", "Presenza",
                                    "Flag tipo causale manuale: PRESENZA",
                                    origin=CAUSALE_ORIGINE_MANUALE, tipo=CAUSALE_TIPO_PRESENZA),
        }

    def _build_slot_mappings(self) -> None:
        """Mappatura slot causali automatiche 501-510 (da formule 2115/3015)."""
        self.SLOT_MAPPINGS = {
            501: CausaleSlotMapping(501, "F/FNG/FP/FX", "Festività (normale/non goduta/patrono/FX)",
                                    source_fields=[918], formula_ref="2115/3015"),
            502: CausaleSlotMapping(502, "N/NF", "Maggiorazione notturna / notturna festiva",
                                    source_fields=[902, 903], formula_ref="2115/3015"),
            503: CausaleSlotMapping(503, "NF/LFS", "Maggiorazione notturna festiva / lavoro festivo",
                                    source_fields=[903, 904, 908], formula_ref="2115/3015"),
            504: CausaleSlotMapping(504, "LFS/SF", "Maggiorazione lavoro festivo / straord. festivo",
                                    source_fields=[904, 908, 914], formula_ref="2115/3015"),
            505: CausaleSlotMapping(505, "SP/N", "Supplementare / maggiorazione notturna",
                                    source_fields=[906], formula_ref="2115/3015"),
            506: CausaleSlotMapping(506, "SA/T", "Straordinario diurno / maggiorazione diurna",
                                    source_fields=[907], formula_ref="2115/3015"),
            507: CausaleSlotMapping(507, "SF/SA", "Straordinario festivo / straord. diurno",
                                    source_fields=[914], formula_ref="2115/3015"),
            508: CausaleSlotMapping(508, "SN", "Straordinario notturno",
                                    source_fields=[909], formula_ref="2115/3015"),
            509: CausaleSlotMapping(509, "SNF/SN", "Straordinario notturno festivo / notturno",
                                    source_fields=[910], formula_ref="2115/3015"),
            510: CausaleSlotMapping(510, "SB", "Straordinario seconda fascia",
                                    source_fields=[915], formula_ref="2114/3014"),
        }

    def _build_contracts(self) -> None:
        """Dettaglio contratti con formule associate."""
        self.CONTRACTS = {
            1: ContractDetail(
                number=1, name="Standard", description="Contratto Standard — timbrature normali",
                formulas_ig=[1, 5, 10, 2050, 2051, 2060, 9001, 9002],
                formulas_fg=[100, 110, 120, 130, 140, 200, 210],
            ),
            2: ContractDetail(
                number=2, name="Dirigenti/Quadri", description="Dipendenti che NON timbrano",
                timbra=False,
                formulas_ig=[1000, 1010],
                formulas_fg=[1100],
            ),
            3: ContractDetail(
                number=3, name="Turnisti", description="Dipendenti Turnisti — con max entrata posticipata",
                max_entry_offset="posticipata",
                formulas_ig=[1, 5, 10],
                formulas_fg=[100, 110, 120, 130, 140, 200, 210],
            ),
        }

    def _build_formula_relations(self) -> None:
        """Relazioni note tra formule (chiamate P e salti R)."""
        self.FORMULA_RELATIONS = [
            # Flusso Fine Giornata standard
            FormulaRelation(100, 110, "R", "FineGiornata: 100 -> 110 (R110)"),
            FormulaRelation(110, 120, "R", "FineGiornata: 110 -> 120 (R120)"),
            FormulaRelation(120, 130, "R", "FineGiornata: 120 -> 130 se festivo (R130)"),
            FormulaRelation(120, 140, "R", "FineGiornata: 120 -> 140 se ordinario (R140)"),
            FormulaRelation(120, 200, "R", "FineGiornata: 120 -> 200 default (R200)"),
            FormulaRelation(130, 200, "R", "FineGiornata: 130 -> 200 (R200)"),
            FormulaRelation(140, 200, "R", "FineGiornata: 140 -> 200 (R200)"),
            FormulaRelation(200, 210, "P", "FineGiornata: 200 chiama 210 se turno attivo (P210)"),
            # Flusso GUGEST variante A
            FormulaRelation(2100, 2101, "chain", "GUGEST A: 2100 -> 2101 (anti-loop 900)"),
            FormulaRelation(2101, 2109, "P", "GUGEST A: 2101 chiama festività (P2109)"),
            FormulaRelation(2101, 2122, "P", "GUGEST A: 2101 chiama calcolo intervallo (P2122)"),
            FormulaRelation(2101, 2123, "P", "GUGEST A: 2101 chiama arrot. ordinario (P2123)"),
            FormulaRelation(2101, 2124, "P", "GUGEST A: 2101 chiama arrot. straord. (P2124)"),
            FormulaRelation(2101, 2125, "P", "GUGEST A: 2101 chiama placeholder (P2125)"),
            FormulaRelation(2101, 2114, "P", "GUGEST A: 2101 chiama ritocco SA/SB (P2114)"),
            FormulaRelation(2101, 2115, "P", "GUGEST A: 2101 chiama esplode causali (P2115)"),
            FormulaRelation(2101, 2130, "P", "GUGEST A: 2101 chiama warning (P2130)"),
            # Flusso FG variante B
            FormulaRelation(3000, 3001, "chain", "FG B: 3000 -> 3001 (anti-loop 900)"),
            FormulaRelation(3000, 3009, "P", "FG B: 3000 chiama festività (P3009)"),
            FormulaRelation(3000, 3002, "P", "FG B: 3000 chiama arrot. vecchio (P3002) ante 01/06/2023"),
            FormulaRelation(3000, 3003, "P", "FG B: 3000 chiama arrot. nuovo (P3003) dal 01/06/2023"),
            FormulaRelation(3001, 3009, "P", "FG B: 3001 chiama festività (P3009)"),
            FormulaRelation(3001, 2122, "P", "FG B: 3001 chiama calcolo intervallo (P2122)"),
            FormulaRelation(3001, 2123, "P", "FG B: 3001 chiama arrot. ordinario (P2123)"),
            FormulaRelation(3001, 2124, "P", "FG B: 3001 chiama arrot. straord. (P2124)"),
            FormulaRelation(3001, 3005, "P", "FG B: 3001 chiama calcolo straord. (P3005)"),
            FormulaRelation(3001, 3014, "P", "FG B: 3001 chiama ritocco SA/SB (P3014)"),
            FormulaRelation(3001, 3015, "P", "FG B: 3001 chiama esplode causali (P3015)"),
            FormulaRelation(3001, 3030, "P", "FG B: 3001 chiama warning (P3030)"),
            # Subroutine chiamate da piu flussi
            FormulaRelation(2050, 2051, "R", "Arrot. entrate chiama arrot. uscite (R2051)"),
            FormulaRelation(2050, 2060, "R", "Arrot. entrate chiama cap uscite (R2060, dal 01/06/2023)"),
            FormulaRelation(9001, 9002, "R", "Arrot. impiegati I chiama II (R9002)"),
        ]

    def _build_formula_flows(self) -> None:
        """Flussi formula principali per tipo."""
        self.FORMULA_FLOWS = {
            "fine_giornata_standard": [100, 110, 120, 130, 140, 200, 210],
            "fine_giornata_dirigenti": [1100],
            "fine_giornata_timbratura_singola": [1120],
            "fine_giornata_chiamata": [2000],
            "fine_giornata_gugest_a": [2100, 2101],
            "fine_giornata_gugest_b": [2105, 2106],
            "fine_giornata_fg_b": [3000, 3001],
            "inizio_giornata_standard": [1, 5, 10],
            "inizio_giornata_dirigenti": [1000, 1010],
            "inizio_giornata_quadri": [1010],
            "inizio_giornata_timbratura_singola": [1020],
            "inizio_giornata_conad": [2050, 2051, 2060],
            "inizio_giornata_arrotondamento_impiegati": [9001, 9002],
        }

    def _load_from_grammar(self) -> None:
        """Carica conoscenza aggiuntiva da file grammatica."""
        path = Path(__file__).parent.parent.parent / "documenti" / "WinSarp" / "WinsarpGrammatica.txt"
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                self._parse_causali_from_grammar(text)
            except Exception as e:
                _logger.warning("Errore caricamento causali da grammar: %s", e)

    def _parse_causali_from_grammar(self, text: str) -> None:
        """Arricchisce causali esistenti con dettagli dal file grammatica."""
        for m in re.finditer(r'(\d+)\s*=\s*(.+)', text):
            num = int(m.group(1))
            desc = m.group(2).strip().strip(",")
            # Rileva causali automatiche nel range 501-510 o 561-570
            if 501 <= num <= 510:
                slot = self.SLOT_MAPPINGS.get(num)
                if slot:
                    slot.description = desc
            elif 561 <= num <= 570:
                pass  # ore causali per tipo - info gia presente
        _logger.info("Grammar file loaded for causali enrichment")

    # ============================================================
    # API di interrogazione — Causali
    # ============================================================

    def get_causale(self, code: str) -> CausaleInfo | None:
        return self.CAUSALI.get(code.upper()) if code else None

    def get_causali_by_category(self, category: str) -> list[CausaleInfo]:
        return [c for c in self.CAUSALI.values() if c.category == category]

    def get_causali_by_origin(self, origin: str) -> list[CausaleInfo]:
        return [c for c in self.CAUSALI.values() if c.origin == origin]

    def get_slot_mapping(self, slot: int) -> CausaleSlotMapping | None:
        return self.SLOT_MAPPINGS.get(slot)

    def get_slot_for_causale(self, code: str) -> list[int]:
        code_upper = code.upper()
        return [s for s, m in self.SLOT_MAPPINGS.items() if code_upper in m.code]

    def search_causali(self, query: str) -> list[CausaleInfo]:
        q = query.lower()
        return [c for c in self.CAUSALI.values()
                if q in c.code.lower() or q in c.name.lower() or q in c.description.lower()]

    # ============================================================
    # API — Contratti
    # ============================================================

    def get_contract(self, number: int) -> ContractDetail | None:
        return self.CONTRACTS.get(number)

    def get_contract_formulas(self, number: int, flusso: str = "") -> list[int]:
        c = self.CONTRACTS.get(number)
        if not c:
            return []
        if flusso == "ig":
            return c.formulas_ig
        if flusso == "fg":
            return c.formulas_fg
        return c.formulas_ig + c.formulas_fg

    # ============================================================
    # API — Relazioni tra formule
    # ============================================================

    def get_relations_from(self, code: int) -> list[FormulaRelation]:
        return [r for r in self.FORMULA_RELATIONS if r.from_code == code]

    def get_relations_to(self, code: int) -> list[FormulaRelation]:
        return [r for r in self.FORMULA_RELATIONS if r.to_code == code]

    def get_formula_flow(self, name: str) -> list[int]:
        return self.FORMULA_FLOWS.get(name, [])

    def get_all_flow_names(self) -> list[str]:
        return list(self.FORMULA_FLOWS.keys())

    # ============================================================
    # API — Utility
    # ============================================================

    def get_causale_slot_info(self) -> dict[int, dict[str, Any]]:
        info = {}
        for slot, mapping in self.SLOT_MAPPINGS.items():
            info[slot] = {
                "slot": slot,
                "code": mapping.code,
                "description": mapping.description,
                "source_fields": mapping.source_fields,
            }
        return info

    def get_causali_summary(self) -> dict[str, Any]:
        return {
            "total_causali": len(self.CAUSALI),
            "by_origin": {
                "automatiche": len(self.get_causali_by_origin(CAUSALE_ORIGINE_AUTOMATICA)),
                "manuali": len(self.get_causali_by_origin(CAUSALE_ORIGINE_MANUALE)),
                "turno": len(self.get_causali_by_origin(CAUSALE_ORIGINE_TURNO)),
            },
            "by_category": {
                cat: len(self.get_causali_by_category(cat))
                for cat in {c.category for c in self.CAUSALI.values()}
            },
            "slot_mappings": len(self.SLOT_MAPPINGS),
            "formula_relations": len(self.FORMULA_RELATIONS),
            "formula_flows": len(self.FORMULA_FLOWS),
            "contracts": len(self.CONTRACTS),
        }

    def stats(self) -> dict[str, Any]:
        return self.get_causali_summary()


# Singleton
table_registry: TableRegistry = TableRegistry()
