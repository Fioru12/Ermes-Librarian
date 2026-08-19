"""
formula_patterns.py — Enciclopedia strutturata dei pattern formula WinSarp.

Ogni pattern formalizza la struttura di una tipologia di formula reale:
- Template IR (con slot parametrizzati)
- Codici workbook associati (campo `codes`)
- Campi letti/scritti
- K-register usati
- Condizioni di attivazione
- Posizione nella catena
- Pre/post condizioni

Consente la generazione deterministica di formule complete,
senza dipendere da LLM per la conoscenza sintattica.
"""

from __future__ import annotations
import re

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


# ============================================================
# Pattern IR Template
# ============================================================

@dataclass
class FormulaPattern:
    """Pattern di formula WinSarp con template IR e metadati."""
    id: str
    name: str
    description: str
    phase: str                                # IG / DG / FG / SUB
    chain_position: int                       # Ordine nella catena (basso = prima)
    chain_group: str                          # Gruppo di catena (standard, gugest_a, gugest_b, fg_b, dir_qua, chiamata, conad)
    template: List[str]                       # Step IR con {slot}
    parameters: Dict[str, dict]               # {nome_slot: {type, default, description}}
    calls: List[str]                          # Pattern ID chiamati
    called_by: List[str]                      # Pattern ID che ci chiamano
    fields_read: Set[int]                     # Campi letti
    fields_write: Set[int]                    # Campi scritti (reset o set)
    k_regs_read: Set[str]                     # K-register letti
    k_regs_write: Set[str]                    # K-register scritti (accumulo)
    causali_slots: Dict[int, str]             # {slot: causale_code}
    conditions: List[str]                     # Condizioni di attivazione (NL)
    prerequisites: List[str]                  # Cosa deve essere vero prima
    postconditions: List[str]                 # Cosa garantisce dopo
    codes: List[int] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)


# ============================================================
# PATTERN DEFINITIONS
# ============================================================

PATTERNS: Dict[str, FormulaPattern] = {}


def _p(pattern: FormulaPattern) -> FormulaPattern:
    """Registra e restituisce un pattern."""
    PATTERNS[pattern.id] = pattern
    return pattern


# ---------------------------------------------------------------------------
# IG — INIZIO GIORNATA
# ---------------------------------------------------------------------------

_p(FormulaPattern(
    id="ig_reset",
    codes=[],
    name="Azzeramento turno",
    description="Resetta il flag turno (campo 900) all'inizio della giornata. Sempre eseguito per primo.",
    phase="IG",
    chain_position=1,
    chain_group="standard",
    template=[
        "RESET 900  # azzera flag turno per nuova giornata"
    ],
    parameters={},
    calls=[],
    called_by=[],
    fields_read=set(),
    fields_write={900},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["inizio giornata", "azzeramento", "reset", "nuova giornata"],
    prerequisites=["Nessuna — prima formula IG"],
    postconditions=["900 = Z (turno non ancora riconosciuto)"],
    tags={"ig", "reset", "fondamentale"},
))

_p(FormulaPattern(
    id="ig_turn_recognition",
    codes=[5],
    name="Riconoscimento turno da timbrature",
    description="Analizza le timbrature effettive per determinare il turno (MATT/POME/NOTT) e aggiorna l'orario previsionale.",
    phase="IG",
    chain_position=2,
    chain_group="standard",
    template=[
        "RESET 800  # azzera area di appoggio",
        "RESET 801",
        "RESET 802",
        "RESET 803",
        "RESET 804",
        "IF {801} > '04.00' AND {801} < '09.00' THEN",
        "  SET 58 = 'MATT'",
        "  SET 111 = '06'",
        "  SET 141 = '14'",
        "  RESET 112",
        "  RESET 142",
        "  SET 100 = 1",
        "  SET 900 = 1",
        "  VF",
        "ENDIF",
        "IF {801} > '12.00' AND {801} < '17.00' THEN",
        "  SET 58 = 'POME'",
        "  SET 111 = '14'",
        "  SET 141 = '22'",
        "  RESET 112",
        "  RESET 142",
        "  SET 100 = 1",
        "  SET 900 = 2",
        "  VF",
        "ENDIF",
        "IF {801} > '20.00' AND {801} < '23.59' THEN",
        "  SET 58 = 'NOTT'",
        "  SET 111 = '22'",
        "  SET 141 = '06'",
        "  RESET 112",
        "  RESET 142",
        "  SET 100 = 1",
        "  SET 900 = 3",
        "  VF",
        "ENDIF",
    ],
    parameters={
        "mattino_window_start": {"type": "time", "default": "04.00", "description": "Inizio finestra turno mattino"},
        "mattino_window_end": {"type": "time", "default": "09.00", "description": "Fine finestra turno mattino"},
        "pomeriggio_window_start": {"type": "time", "default": "12.00", "description": "Inizio finestra turno pomeriggio"},
        "pomeriggio_window_end": {"type": "time", "default": "17.00", "description": "Fine finestra turno pomeriggio"},
        "notte_window_start": {"type": "time", "default": "20.00", "description": "Inizio finestra turno notte"},
        "notte_window_end": {"type": "time", "default": "23.59", "description": "Fine finestra turno notte"},
        "mattino_label": {"type": "string", "default": "MATT", "description": "Etichetta turno mattino"},
        "pomeriggio_label": {"type": "string", "default": "POME", "description": "Etichetta turno pomeriggio"},
        "notte_label": {"type": "string", "default": "NOTT", "description": "Etichetta turno notte"},
    },
    calls=[],
    called_by=["ig_reset"],
    fields_read={200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 220, 58, 801, 802},
    fields_write={58, 111, 112, 141, 142, 100, 900, 800, 801, 802, 803, 804},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["riconoscimento turno", "classificazione turno", "turno mattino", "turno pomeriggio",
                 "turno notte", "determinazione turno", "turnista"],
    prerequisites=["900 = Z (ig_reset eseguito)"],
    postconditions=["900 determinato (1/2/3)", "58 impostato (MATT/POME/NOTT)", "111/141 aggiornati"],
    tags={"ig", "turno", "riconoscimento", "turnista"},
))

_p(FormulaPattern(
    id="ig_copy_planned",
    codes=[1000, 1010],
    name="Copia previsionale in calcolato (Dirigenti/Quadri)",
    description="Per dipendenti che non timbrano (dirigenti) o timbrano solo opzionalmente (quadri): copia l'orario previsionale nei campi calcolati.",
    phase="IG",
    chain_position=2,
    chain_group="standard",
    template=[
        "IF 390 != Z THEN",
        "  VF",
        "ENDIF",
        "SET 251 = 111",
        "SET 271 = 141",
        "IF 112 > Z THEN",
        "  SET 252 = 112",
        "  SET 272 = 142",
        "ENDIF",
        "IF 113 > Z THEN",
        "  SET 253 = 113",
        "  SET 273 = 143",
        "ENDIF",
        "IF 114 > Z THEN",
        "  SET 254 = 114",
        "  SET 274 = 144",
        "ENDIF",
    ],
    parameters={
        "respect_punches": {"type": "bool", "default": "False", "description": "Se True, non sovrascrive se ci sono timbrature reali (quadri)"},
    },
    calls=[],
    called_by=["ig_reset"],
    fields_read={111, 112, 113, 114, 141, 142, 143, 144, 390, 201, 221},
    fields_write={251, 252, 253, 254, 271, 272, 273, 274},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["dirigente", "dirigenti", "quadro", "quadri", "non timbra", "non timbrano", "copia previsionale"],
    prerequisites=["390 controllato (giornata normale)"],
    postconditions=["251/271 = 111/141 (calcolato = previsionale)"],
    tags={"ig", "dirigenti", "quadri", "copia"},
))

_p(FormulaPattern(
    id="ig_single_punch",
    codes=[1020],
    name="Classificazione timbratura singola",
    description="Per dipendenti che timbrano una volta per intervallo: classifica ogni timbratura come entrata o uscita in base all'orario previsionale.",
    phase="IG",
    chain_position=2,
    chain_group="standard",
    template=[
        "IF 390 != Z THEN",
        "  VF",
        "ENDIF",
        "IF 100 = Z THEN",
        "  RESET 251",
        "  RESET 271",
        "  RESET 252",
        "  RESET 272",
        "  VF",
        "ENDIF",
        "RESET 800",
        "RESET 801",
        "RESET 802",
        "RESET 803",
        "RESET 804",
        "SET 802 = 200",
        "SET 803 = 220",
        "# Loop sulle timbrature usando puntatori",
    ],
    parameters={},
    calls=[],
    called_by=["ig_reset"],
    fields_read={100, 111, 112, 141, 142, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 220, 390, 800, 801, 802, 803, 804},
    fields_write={251, 252, 271, 272, 800, 801, 802, 803, 804},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["timbratura singola", "timbrano una volta", "single punch"],
    prerequisites=["100 determinato (intervalli previsionali esistenti)"],
    postconditions=["251/271 aggiornati in base alla singola timbratura"],
    tags={"ig", "timbratura", "singola"},
))

# ---------------------------------------------------------------------------
# FG — FINE GIORNATA (STANDARD)
# ---------------------------------------------------------------------------

_p(FormulaPattern(
    id="fg_azzeramenti",
    codes=[100],
    name="Prima formula FG — Azzeramenti",
    description="Imposta la modalità di calcolo DURATA, azzera le causali automatiche (561-570) e salta alla formula 110.",
    phase="FG",
    chain_position=1,
    chain_group="standard",
    template=[
        "SET 500 = 'DURATA'  # modalità calcolo durata",
        "RESET 561  # azzera slot causali automatiche",
        "RESET 562",
        "RESET 563",
        "RESET 564",
        "RESET 565",
        "RESET 566",
        "RESET 567",
        "RESET 568",
        "RESET 569",
        "RESET 570",
        "R 110  # salta a riproporzionamento",
    ],
    parameters={},
    calls=["fg_riproporzionamento"],
    called_by=[],
    fields_read=set(),
    fields_write={500, 561, 562, 563, 564, 565, 566, 567, 568, 569, 570},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={561: "", 562: "", 563: "", 564: "", 565: "", 566: "", 567: "", 568: "", 569: "", 570: ""},
    conditions=["fine giornata", "prima formula", "azzeramento causali", "fg iniziale"],
    prerequisites=["Campo 1-5 calcolati dalle timbrature"],
    postconditions=["500 = DURATA", "561-570 = Z (causali pulite)"],
    tags={"fg", "azzeramento", "fondamentale"},
))

_p(FormulaPattern(
    id="fg_riproporzionamento",
    codes=[110],
    name="Riproporzionamento ore ordinarie/straordinario/assenze",
    description="Bilancia ore ordinarie (3), straordinario (4) e assenze (5) in base al totale lavorato e alle ore previsionali (1).",
    phase="FG",
    chain_position=2,
    chain_group="standard",
    template=[
        "SET 800 = 3 + 4  # totale ore lavorate",
        "IF 1 = Z THEN",
        "  RESET 3  # nessun previsionale -> azzera ordinario",
        "  RESET 5",
        "  SET 4 = 800  # tutto è straordinario",
        "  VU",
        "ENDIF",
        "K 800 A 608 A 609  # somma assenze al totale",
        "IF 800 > 1 THEN",
        "  SET 4 = 800 - 1  # eccedenza = straordinario",
        "  SET 3 = 1 - 608 - 609  # ordinario = previsionale - assenze",
        "  RESET 5  # nessuna assenza residua",
        "  VU",
        "ENDIF",
        "SET 3 = 800 - 608 - 609  # ordinario = totale - assenze",
        "RESET 4  # nessuno straordinario",
        "SET 5 = 1 - 800  # differenza = assenza",
        "R 120  # salta a dispatcher",
    ],
    parameters={},
    calls=["fg_dispatcher"],
    called_by=["fg_azzeramenti"],
    fields_read={1, 3, 4, 5, 608, 609},
    fields_write={3, 4, 5, 800},
    k_regs_read={"K800"},
    k_regs_write={"K800"},
    causali_slots={},
    conditions=["riproporzionamento", "bilanciamento ore", "3 4 5", "ordinario straordinario assenze"],
    prerequisites=["3, 4, 5 calcolati", "1 = ore previsionali"],
    postconditions=["3 + 4 + 5 = 1 (matematicamente consistente)", "Se 800 > 1 -> 4 = eccedenza"],
    tags={"fg", "riproporzionamento", "fondamentale"},
))

_p(FormulaPattern(
    id="fg_dispatcher",
    codes=[120],
    name="Smistatore centrale — instradamento straordinario",
    description="Se c'è straordinario (4 > 0), controlla se il giorno è festivo/domenica e instrada a 130 (festivo) o 140 (ordinario).",
    phase="FG",
    chain_position=3,
    chain_group="standard",
    template=[
        "IF 4 = Z THEN",
        "  VU  # nessuno straordinario -> esce",
        "ENDIF",
        "IF 1121 = 'N' THEN",
        "  RESET 4  # straordinario non ammesso",
        "  VU",
        "ENDIF",
        "IF 55 = 'I' OR 50 = 1 THEN",
        "  R 130  # festivo o domenica -> split festivo",
        "ENDIF",
        "R 140  # giorno ordinario -> split ordinario",
    ],
    parameters={},
    calls=["fg_split_festivo", "fg_split_ordinario"],
    called_by=["fg_riproporzionamento"],
    fields_read={4, 50, 55, 1121},
    fields_write={4},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["smistatore", "dispatcher", "instradamento", "principale"],
    prerequisites=["4 determinato (fg_riproporzionamento)"],
    postconditions=["Instrada a 130 (festivo) o 140 (ordinario) o 200 (nessun straordinario)"],
    tags={"fg", "smistatore", "fondamentale"},
))

_p(FormulaPattern(
    id="fg_split_festivo",
    codes=[130],
    name="Straordinario festivo — split SF/SFN",
    description="Nei giorni festivi/domenica, separa lo straordinario in festivo diurno (SF, K615) e festivo notturno (SFN, K616).",
    phase="FG",
    chain_position=4,
    chain_group="standard",
    template=[
        "IF 21 = Z THEN",
        "  V04  # niente ore notturne -> salta blocco SFN",
        "ENDIF",
        "SET 504 = 'SFN'  # causale straordinario festivo notturno",
        "IF 21 > 4 THEN",
        "  SET 564 = 4  # notturne > totale -> cap a 4",
        "  K 21 S 4  # sottrae 4 da notturne",
        "  RESET 4",
        "  V05",
        "ENDIF",
        "SET 564 = 21  # ore SFN = ore notturne",
        "K 4 S 21  # sottrae notturne da straordinario",
        "RESET 21  # notturne consumate",
        "SET 503 = 'SF'  # causale straordinario festivo diurno",
        "SET 563 = 4  # ore SF = straordinario residuo",
        "RESET 4",
        "K 601 A 563  # ore lavorate += SF",
        "K 601 A 564  # ore lavorate += SFN",
        "K 604 A 563  # straordinario totale += SF",
        "K 604 A 564  # straordinario totale += SFN",
        "K 615 A 563  # progressivo festivo diurno",
        "K 616 A 564  # progressivo festivo notturno",
        "R 200  # salta a formula finale",
    ],
    parameters={},
    calls=["fg_finale"],
    called_by=["fg_dispatcher"],
    fields_read={4, 21, 503, 504},
    fields_write={4, 21, 503, 504, 563, 564},
    k_regs_read={"K601", "K604", "K615", "K616"},
    k_regs_write={"K601", "K604", "K615", "K616", "K4", "K21"},
    causali_slots={503: "SF", 504: "SFN", 563: "SF", 564: "SFN"},
    conditions=["straordinario festivo", "festivo notturno", "festivo diurno", "sfn"],
    prerequisites=["4 > 0 (straordinario presente)", "55 = I o 50 = 1 (festivo/domenica)"],
    postconditions=["4 consumato", "SFN in 564/K616", "SF in 563/K615"],
    tags={"fg", "festivo", "straordinario", "split"},
))

_p(FormulaPattern(
    id="fg_split_ordinario",
    codes=[140],
    name="Straordinario ordinario — split S/SN",
    description="Nei giorni ordinari, separa lo straordinario in diurno (S, K611) e notturno (SN, K614).",
    phase="FG",
    chain_position=4,
    chain_group="standard",
    template=[
        "IF 21 = Z OR 900 = 3 THEN",
        "  V04  # niente notturne o turno notte intero -> salta SN",
        "ENDIF",
        "SET 502 = 'SN'  # causale straordinario notturno",
        "IF 21 > 4 THEN",
        "  SET 562 = 4  # notturne > totale -> cap a 4",
        "  K 21 S 4",
        "  RESET 4",
        "  V05",
        "ENDIF",
        "SET 562 = 21  # ore SN = ore notturne",
        "K 4 S 21  # sottrae notturne da straordinario",
        "RESET 21",
        "SET 501 = 'S'  # causale straordinario diurno",
        "SET 561 = 4  # ore S = straordinario residuo",
        "RESET 4",
        "K 601 A 561  # ore lavorate",
        "K 601 A 562",
        "K 604 A 561  # straordinario totale",
        "K 604 A 562",
        "K 611 A 561  # progressivo straordinario diurno",
        "K 614 A 562  # progressivo straordinario notturno",
        "R 200",
    ],
    parameters={},
    calls=["fg_finale"],
    called_by=["fg_dispatcher"],
    fields_read={4, 21, 501, 502, 900},
    fields_write={4, 21, 501, 502, 561, 562},
    k_regs_read={"K601", "K604", "K611", "K614"},
    k_regs_write={"K601", "K604", "K611", "K614", "K4", "K21"},
    causali_slots={501: "S", 502: "SN", 561: "S", 562: "SN"},
    conditions=["straordinario ordinario", "straordinario diurno", "straordinario notturno"],
    prerequisites=["4 > 0 (straordinario presente)", "55 != I e 50 != 1 (giorno ordinario)"],
    postconditions=["4 consumato", "SN in 562/K614", "S in 561/K611"],
    tags={"fg", "ordinario", "straordinario", "split"},
))

_p(FormulaPattern(
    id="fg_finale",
    codes=[200],
    name="Formula finale — accumulo ore ordinarie",
    description="Accumula le ore ordinarie (3) nei progressivi K601 e K602. Se turno attivo (900 > 0), chiama il calcolo maggiorazioni turnisti (P210).",
    phase="FG",
    chain_position=5,
    chain_group="standard",
    template=[
        "K 601 A 3  # ore lavorate += ordinarie",
        "K 602 A 3  # ore ordinarie progressivo",
        "IF 900 > Z THEN",
        "  P 210  # calcola maggiorazioni turnisti",
        "ENDIF",
    ],
    parameters={},
    calls=["fg_maggiorazioni"],
    called_by=["fg_split_festivo", "fg_split_ordinario"],
    fields_read={3, 900},
    fields_write=set(),
    k_regs_read={"K601", "K602"},
    k_regs_write={"K601", "K602"},
    causali_slots={},
    conditions=["finale", "accumulo", "ore lavorate", "chiusura giornata"],
    prerequisites=["3 determinato", "4 consumato da 130 o 140"],
    postconditions=["K601 += 3", "K602 += 3"],
    tags={"fg", "finale", "accumulo", "fondamentale"},
))

_p(FormulaPattern(
    id="fg_maggiorazioni",
    codes=[210],
    name="Maggiorazioni turnisti — N/T",
    description="Calcola le maggiorazioni per turnisti: ore notturne maggiorate (N, K626) e ore diurne residue (T, K625).",
    phase="FG",
    chain_position=6,
    chain_group="standard",
    template=[
        "IF 21 > Z THEN",
        "  SET 505 = 'N'  # causale maggiorazione notturna",
        "  SET 565 = 21  # ore maggiorazione notturna",
        "ENDIF",
        "SET 890 = 3 - 21  # ore diurne = ordinarie - notturne",
        "IF 890 > Z THEN",
        "  SET 506 = 'T'  # causale maggiorazione diurna",
        "  SET 566 = 890  # ore maggiorazione diurna",
        "ENDIF",
        "K 626 A 565  # progressivo maggiorazione notturna",
        "K 625 A 566  # progressivo maggiorazione diurna",
    ],
    parameters={},
    calls=[],
    called_by=["fg_finale"],
    fields_read={3, 21, 505, 506, 890},
    fields_write={505, 506, 565, 566, 890},
    k_regs_read={"K625", "K626"},
    k_regs_write={"K625", "K626"},
    causali_slots={505: "N", 506: "T", 565: "N", 566: "T"},
    conditions=["maggiorazioni", "turnisti", "premi turno", "indennità turno", "notturna", "diurna"],
    prerequisites=["900 > 0 (turno attivo)", "3 e 21 determinati"],
    postconditions=["K626 += 565 (notturna)", "K625 += 566 (diurna)"],
    tags={"fg", "maggiorazioni", "turnisti"},
))

# ---------------------------------------------------------------------------
# FG — DIRIGENTI / QUADRI / CHIAMATA
# ---------------------------------------------------------------------------

_p(FormulaPattern(
    id="fg_dirigenti_assenze",
    codes=[1100],
    name="Gestione assenze Dirigenti/Quadri",
    description="Per dirigenti e quadri: riduce le ore calcolate in base alle assenze. Se assenze >= previsionale, azzera tutto.",
    phase="FG",
    chain_position=1,
    chain_group="dir_qua",
    template=[
        "SET 800 = 608 + 609  # totale assenze",
        "IF 1 = Z OR 800 = Z THEN",
        "  VU  # niente da fare",
        "ENDIF",
        "IF 800 > 1 THEN",
        "  RESET 251  # assenze >= previsionale -> azzera tutto",
        "  RESET 271",
        "  RESET 252",
        "  RESET 272",
        "  RESET 3",
        "  VF",
        "ENDIF",
        "SET 801 = 142 - 112  # durata secondo intervallo",
        "K 3 S 800  # ordinario = ordinario - assenze",
        "IF 800 < 801 THEN",
        "  K 272 S 800  # assenze parziali -> riduci uscita 2",
        "  VU",
        "ENDIF",
        "IF 800 = 801 THEN",
        "  RESET 252  # assenze = secondo intervallo -> azzera",
        "  RESET 272",
        "  VU",
        "ENDIF",
        "IF 800 > 801 THEN",
        "  SET 271 = 251 + 3  # assenze > secondo -> riduci primo",
        "  RESET 252",
        "  RESET 272",
        "  VU",
        "ENDIF",
        "K 601 A 3  # accumula ore ordinarie",
        "K 602 A 3",
    ],
    parameters={},
    calls=[],
    called_by=[],
    fields_read={1, 3, 4, 5, 111, 112, 141, 142, 251, 252, 271, 272, 608, 609},
    fields_write={3, 251, 252, 271, 272, 800, 801},
    k_regs_read={"K601", "K602"},
    k_regs_write={"K601", "K602", "K3", "K272", "K271"},
    causali_slots={},
    conditions=["assenze dirigenti", "assenze quadri", "fg dirigenti", "fg quadri"],
    prerequisites=["608/609 = assenze totali", "251-272 = calcolati"],
    postconditions=["3 = 1 - 800 (ordinario = previsionale - assenze)", "251/271/252/272 aggiustati"],
    tags={"fg", "dirigenti", "quadri", "assenze"},
))

_p(FormulaPattern(
    id="fg_chiamata",
    codes=[2000],
    name="Formula chiamata — auto-contenuta",
    description="Per dipendenti a chiamata: se non timbrato -> RIPO; se timbrato -> copia calcolato in previsionale e accumula.",
    phase="FG",
    chain_position=1,
    chain_group="chiamata",
    template=[
        "IF 300 > 305 THEN",
        "  VF  # fuori data -> esci",
        "ENDIF",
        "IF 200 = Z THEN",
        "  RESET 111  # non timbrato -> RIPO",
        "  RESET 112",
        "  RESET 113",
        "  RESET 141",
        "  RESET 142",
        "  RESET 143",
        "  SET 58 = 'RIPO'",
        "  VU",
        "ENDIF",
        "SET 111 = 251  # copia calcolato in previsionale",
        "SET 141 = 271",
        "SET 112 = 252",
        "SET 142 = 272",
        "SET 113 = 253",
        "SET 143 = 273",
        "SET 114 = 254",
        "SET 144 = 274",
        "IF 58 = 'CHIA' THEN",
        "  SET 58 = 'CHI'  # chiamata effettuata",
        "  VU",
        "ENDIF",
        "SET 58 = 'CHIA'  # chiamata attiva",
        "K 601 A 3",
        "K 602 A 3",
        "SET 100 = 250  # intervalli",
        "SET 1 = 3  # previsionale = ordinario",
    ],
    parameters={},
    calls=[],
    called_by=[],
    fields_read={58, 200, 251, 252, 253, 254, 271, 272, 273, 274, 300, 305},
    fields_write={58, 100, 111, 112, 113, 114, 141, 142, 143, 144, 1, 3, 4, 5},
    k_regs_read={"K601", "K602"},
    k_regs_write={"K601", "K602"},
    causali_slots={},
    conditions=["chiamata", "a chiamata", "on call", "CHIA"],
    prerequisites=["300/305 controllati (data validità)", "251-274 calcolati"],
    postconditions=["58 = CHI/CHIA/RIPO", "Previsionale = calcolato"],
    tags={"fg", "chiamata", "speciale"},
))

_p(FormulaPattern(
    id="fg_single_punch_assenze",
    codes=[1120],
    name="Gestione assenze timbratura singola",
    description="Per dipendenti con timbratura singola: distribuisce le assenze tra mattino e pomeriggio.",
    phase="FG",
    chain_position=1,
    chain_group="single_punch",
    template=[
        "SET 805 = 608 + 609  # totale assenze",
        "SET 806 = 1 - 3  # gap previsionale - ordinario",
        "IF 1 = Z OR 805 = Z THEN",
        "  VF",
        "ENDIF",
        "IF 805 > 1 THEN",
        "  RESET 251  # assenze totali -> azzera tutto",
        "  RESET 271",
        "  RESET 252",
        "  RESET 272",
        "  RESET 3",
        "  RESET 4",
        "  RESET 5",
        "  VF",
        "ENDIF",
        "SET 807 = 805 - 806  # assenze residue",
        "# Riduzione proporzionale sugli intervalli",
        "K 601 A 3",
        "K 602 A 3",
        "SET 3 = 1 - 805",
        "SET 5 = 1 - 3 - 805",
    ],
    parameters={},
    calls=[],
    called_by=[],
    fields_read={1, 3, 251, 271, 252, 272, 608, 609, 800, 801},
    fields_write={3, 4, 5, 251, 271, 252, 272, 805, 806, 807},
    k_regs_read={"K601", "K602"},
    k_regs_write={"K601", "K602", "K251", "K271", "K272"},
    causali_slots={},
    conditions=["timbratura singola assenze", "assenze singola timbratura"],
    prerequisites=["1, 3, 800, 801 determinati"],
    postconditions=["3 = 1 - 805", "Intervalli aggiustati per assenze"],
    tags={"fg", "timbratura", "singola", "assenze"},
))

# ---------------------------------------------------------------------------
# SUB — SUBROUTINE STANDARD
# ---------------------------------------------------------------------------

_p(FormulaPattern(
    id="sub_calcolo_intervallo",
    codes=[2122],
    name="Calcolo ore per intervallo (minuto per minuto)",
    description="Prende un intervallo (811=entrata, 812=uscita) e classifica ogni minuto nel bucket corretto. Loop: avanza di 1 minuto, controlla giorno (50/55), confronta cumulato (782) con soglie (887/889), assegna al bucket corretto (902-914).",
    phase="SUB",
    chain_position=1,
    chain_group="gugest_a",
    template=[
        "IF 3 = Z THEN VF ENDIF",
        "SET 810 = '00.01'",
        "IF 811 > 812 THEN SET 812 = 812 + '24.00' ENDIF",
        "K811 A 810  # avanza entrata di 1 minuto",
        "K782 A 810  # cumula settimanale",
        "K785 A 810 S 810  # cumula senza sottrarre",
        "# Branch giorno (50=I festivo, 55=I festivo)",
        "# Se 50=I -> V22 (branch festivo)",
        "# Se 55=I -> V14 (branch festivo)",
        "# BRANCH ORDINARIO (50!=I E 55!=I):",
        "#   782 <U 887 E 811 <U '06.00' -> K902 A 810 (notturno ordinario)",
        "#   782 <U 887 E 811 > '22.00' -> K902 A 810 (notturno ordinario)",
        "#   782 > 887 E 811 <U '06.00' -> K909 A 810 (notturno straordinario)",
        "#   782 > 887 E 811 > '22.00' -> K909 A 810 (notturno straordinario)",
        "#   889 > Z E 782 > 887 E 782 <U 889 -> K906 A 810 (supplementare)",
        "#   782 > 887 -> K907 A 810 (straordinario diurno)",
        "#   default -> K905 A 810 (ordinario diurno)",
        "# BRANCH FESTIVO (50=I):",
        "#   782 <U 887 E 811 <U '06.00' -> K903 A 810 (notturno festivo)",
        "#   782 <U 887 E 811 > '22.00' -> K903 A 810 (notturno festivo)",
        "#   782 > 887 E 811 <U '06.00' -> K910 A 810 (notturno straord. festivo)",
        "#   782 > 887 E 811 > '22.00' -> K910 A 810 (notturno straord. festivo)",
        "#   889 > Z E 782 > 887 E 782 <U 889 -> K906 A 810 (supplementare)",
        "#   782 > 887 -> K914 A 810 (straordinario diurno festivo)",
        "#   default -> K904 A 810 (lavoro festivo straordinario)",
        "# BRANCH DOMENICA (55=I):",
        "#   stessa logica festivo con K903/K910/K906/K914/K908",
        "# Loop: 811 < 812 -> ripeti (V03)",
    ],
    parameters={
        "night_start": {"type": "time", "default": "22.00", "description": "Inizio fascia notturna"},
        "night_end": {"type": "time", "default": "06.00", "description": "Fine fascia notturna"},
    },
    calls=[],
    called_by=["gugest_2a", "gugest_2a"],
    fields_read={3, 50, 55, 782, 811, 812, 887, 889},
    fields_write={810, 782, 785},
    k_regs_read={"K782", "K785", "K811"},
    k_regs_write={"K782", "K785", "K811", "K902", "K903", "K904", "K905", "K906", "K907", "K908", "K909", "K910", "K914"},
    causali_slots={},
    conditions=["calcolo ore intervallo", "conteggio minuti", "classificazione ore",
                 "calcolo ore per intervallo"],
    prerequisites=["811/812 = intervallo da calcolare", "782 = cumulato settimanale", "887 = soglia straordinario"],
    postconditions=["Ore classificate in K902-K914"],
    tags={"sub", "calcolo", "intervallo", "classificazione"},
))

_p(FormulaPattern(
    id="sub_festivita",
    codes=[2109, 3009],
    name="Gestione festività automatiche",
    description="Riconosce e classifica il tipo di festività (normale, non goduta, patrono) e accumula ore nei progressivi corretti. Controlla: sabato per 5gg (50=7), non goduta su lavorato (684), patrono (1051/1052).",
    phase="SUB",
    chain_position=2,
    chain_group="gugest_a",
    template=[
        "( 919 = I )( !918 )  # nasce normale, reset 918",
        "( 800 = 1 )  # ore festività = 1",
        "# Se 684 > 0 e = 1 -> festività non goduta (zero ore)",
        "684 > Z E 684 U 1 (( 800 = Z )",
        "# Se 50=7 (sabato) e 1=Z (nessun previsionale) -> skip",
        "50 U '7' E 1 U Z (( !919 ) VF",
        "# Se 1>0 e 3>0 e 684=Z -> non goduta su ordinario lavorato",
        "1 > Z E 3 > Z E 684 U Z (( 919 = '2' )( K629 + I ) VF",
        "# Se 50=I (domenica) e 1>0 e 684=Z -> non goduta",
        "50 U I E 1 U Z E 684 U Z (( 919 = '2' )( K629 + I ) VF",
        "# Se 55=I (festivo) e 1>0 e 684=Z -> non goduta",
        "55 U I E 1 U Z E 684 U Z (( 919 = '2' )( K629 + I ) VF",
        "# Se festività attiva (800>0) -> classifica tipo",
        "800 U Z ( VF",
        "# Patrono: 1051=51 E 1052=52",
        "1051 U 51 E 1052 U 52 (( 919 = '3' )( 918 = 800 )( K631 A 800 )( K608 A 800 ) VF",
        "# Normale: accumula in K918, K630, K608",
        "( K918 A 800 )( K630 A 800 )( K608 A 800 )",
    ],
    parameters={},
    calls=[],
    called_by=["gugest_1a", "gugest_2a", "gugest_1a", "gugest_2a", "fg_b_1"],
    fields_read={1, 3, 50, 55, 684, 1051, 1052, 51, 52, 800},
    fields_write={918, 919, 800},
    k_regs_read={"K608", "K918", "K629", "K630", "K631"},
    k_regs_write={"K608", "K918", "K629", "K630", "K631"},
    causali_slots={},
    conditions=["festività", "festivo automatico", "riconoscimento festivo",
                 "non goduta", "patrono", "feste"],
    prerequisites=["55 = I (giorno festivo)", "1 = ore previsionali"],
    postconditions=["919 = tipo festività (1/2/3)", "K608/K630/K631 aggiornati"],
    tags={"sub", "festività", "fondamentale"},
))

_p(FormulaPattern(
    id="sub_arrotondamento_ordinari",
    codes=[2123],
    name="Arrotondamento quarti ore ordinarie/festive",
    description="Arrotonda ai quarti d'ora le ore ordinarie (902-905, 908). Per ogni bucket: legge CAMPO70=3 per separare ore/minuti, poi applica tabella: <15min=scarta, 15-29=+0.15, 30-44=+0.35, 45-59=+0.45.",
    phase="SUB",
    chain_position=3,
    chain_group="gugest_a",
    template=[
        "# Per ogni bucket ordinario (902, 903, 904, 905, 908):",
        "# Se il bucket > 0:",
        "#   ( 71 = 902 )( 70 = '3' )  # CAMPO70=3 separa 902 in 72=ore 73=min",
        "#   ( 902 = 72 )( !800 )      # 902 = ore intere, reset 800",
        "#   73 < '15.00' ( V08        # <15 min -> scarta (salta)",
        "#   73 < '30.00' (( K800 A '0.15' ) V07  # 15-29 min -> +0.15",
        "#   73 < '45.00' (( K800 A '0.35' ) V07  # 30-44 min -> +0.35",
        "#   73 <U '59.00' (( K800 A '0.45' ) V07 # 45-59 min -> +0.45",
        "#   ( K902 A 800 )            # accumula arrotondamento",
        "# Stessa logica per 903, 904, 905, 908 con jump diversi",
    ],
    parameters={},
    calls=[],
    called_by=["gugest_2a", "gugest_2a"],
    fields_read={902, 903, 904, 905, 908},
    fields_write={902, 903, 904, 905, 908, 800},
    k_regs_read={"K902", "K903", "K904", "K905", "K908"},
    k_regs_write={"K902", "K903", "K904", "K905", "K908"},
    causali_slots={},
    conditions=["arrotondamento ordinari", "arrotondamento festivi", "quarti d'ora"],
    prerequisites=["K902-K905, K908 = ore grezze"],
    postconditions=["Ore arrotondate ai quarti"],
    tags={"sub", "arrotondamento"},
))

_p(FormulaPattern(
    id="sub_arrotondamento_straordinari",
    codes=[2124],
    name="Arrotondamento quarti ore straordinarie",
    description="Arrotonda ai quarti d'ora le ore straordinarie (906, 907, 909, 910, 914) con la stessa tabella di 2123: <15min=scarta, 15-29=+0.15, 30-44=+0.35, 45-59=+0.45.",
    phase="SUB",
    chain_position=4,
    chain_group="gugest_a",
    template=[
        "# Per ogni bucket straordinario (906, 907, 909, 910, 914):",
        "# Se il bucket > 0:",
        "#   ( 71 = 906 )( 70 = '3' )  # CAMPO70=3 separa in 72=ore 73=min",
        "#   ( 906 = 72 )( !800 )      # 906 = ore intere, reset 800",
        "#   73 < '15.00' ( V08        # <15 min -> scarta",
        "#   73 < '30.00' (( K800 A '0.15' ) V07  # 15-29 min -> +0.15",
        "#   73 < '45.00' (( K800 A '0.35' ) V07  # 30-44 min -> +0.35",
        "#   73 <U '59.00' (( K800 A '0.45' ) V07 # 45-59 min -> +0.45",
        "#   ( K906 A 800 )            # accumula arrotondamento",
        "# Stessa logica per 907, 909, 910, 914 con jump diversi",
    ],
    parameters={},
    calls=[],
    called_by=["gugest_2a", "gugest_2a"],
    fields_read={906, 907, 909, 910, 914},
    fields_write={906, 907, 909, 910, 914, 800},
    k_regs_read={"K906", "K907", "K909", "K910", "K914"},
    k_regs_write={"K906", "K907", "K909", "K910", "K914"},
    causali_slots={},
    conditions=["arrotondamento straordinari", "quarti straordinario"],
    prerequisites=["K906-K914 = ore grezze straordinarie"],
    postconditions=["Ore straordinarie arrotondate ai quarti"],
    tags={"sub", "arrotondamento"},
))

_p(FormulaPattern(
    id="sub_ritocco_sa_sb",
    codes=[2114, 3014],
    name="Ritocco SA/SB (cap 8 ore)",
    description="Verifica che lo straordinario diurno (907) non superi 8 ore. L'eccedenza viene riclassificata come SB (915). Formula 3014 è la variante FG B.",
    phase="SUB",
    chain_position=5,
    chain_group="gugest_a",
    template=[
        "IF 774 < '08.00' THEN",
        "  VF  # sotto le 8h -> niente da fare",
        "ENDIF",
        "SET 800 = 774 - 907  # capacità residua",
        "IF 774 > '08.00' AND 800 < '08.00' THEN",
        "  SET 915 = 907 - '08.00'  # eccedenza -> SB",
        "  K 907 S 915  # riduce SA di SB",
        "  VF",
        "ENDIF",
        "SET 915 = 907  # tutto va in SB",
        "RESET 907  # SA azzerato",
    ],
    parameters={},
    calls=[],
    called_by=["gugest_2a", "gugest_2a"],
    fields_read={774, 800, 907},
    fields_write={800, 907, 915},
    k_regs_read={"K907"},
    k_regs_write={"K907", "K915"},
    causali_slots={},
    conditions=["ritocco SA SB", "cap 8 ore", "eccedenza straordinario", "seconda fascia"],
    prerequisites=["907 = straordinario diurno grezzo", "774 = straordinario settimanale"],
    postconditions=["907 <= 8:00", "915 = eccedenza SB"],
    tags={"sub", "ritocco", "sa", "sb"},
))

_p(FormulaPattern(
    id="sub_esplodi_causali",
    codes=[2115, 3015],
    name="Esplosione causali automatiche",
    description="Mappa i bucket ore (902-915) nei codici causale (501-510) e ore (561-570).",
    phase="SUB",
    chain_position=6,
    chain_group="gugest_a",
    template=[
        "IF 918 > Z AND 919 = 1 THEN",
        "  SET 501 = 'F'  # festività normale",
        "  SET 561 = 918",
        "ENDIF",
        "IF 919 = 2 THEN",
        "  SET 501 = 'FNG'  # festività non goduta",
        "  SET 561 = 918",
        "ENDIF",
        "IF 918 > Z AND 919 = 3 THEN",
        "  SET 501 = 'FP'  # festività patrono",
        "  SET 561 = 918",
        "ENDIF",
        "IF 902 > Z THEN",
        "  SET 502 = 'N'  # maggiorazione notturna",
        "  SET 562 = 902",
        "ENDIF",
        "IF 903 > Z THEN",
        "  SET 503 = 'NF'  # maggiorazione notturna festiva",
        "  SET 563 = 903",
        "ENDIF",
        "IF 904 > Z OR 908 > Z THEN",
        "  SET 504 = 'LFS'  # lavoro festivo straordinario",
        "  SET 564 = 904 + 908",
        "ENDIF",
        "IF 906 > Z THEN",
        "  SET 505 = 'SP'  # supplementare",
        "  SET 565 = 906",
        "ENDIF",
        "IF 907 > Z THEN",
        "  SET 506 = 'SA'  # straordinario diurno 1a fascia",
        "  SET 566 = 907",
        "ENDIF",
        "IF 914 > Z THEN",
        "  SET 507 = 'SF'  # straordinario festivo diurno",
        "  SET 567 = 914",
        "ENDIF",
        "IF 909 > Z THEN",
        "  SET 508 = 'SN'  # straordinario notturno",
        "  SET 568 = 909",
        "ENDIF",
        "IF 910 > Z THEN",
        "  SET 509 = 'SNF'  # straordinario notturno festivo",
        "  SET 569 = 910",
        "ENDIF",
        "IF 915 > Z THEN",
        "  SET 510 = 'SB'  # straordinario diurno 2a fascia",
        "  SET 570 = 915",
        "ENDIF",
    ],
    parameters={},
    calls=[],
    called_by=["gugest_2a", "gugest_2a"],
    fields_read={902, 903, 904, 905, 906, 907, 908, 909, 910, 914, 915, 918, 919},
    fields_write={501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 561, 562, 563, 564, 565, 566, 567, 568, 569, 570},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={
        501: "F/FNG/FP", 502: "N", 503: "NF", 504: "LFS",
        505: "SP", 506: "SA", 507: "SF", 508: "SN", 509: "SNF", 510: "SB",
    },
    conditions=["esplodi causali", "esplosione causali", "causali automatiche", "assegnazione causali"],
    prerequisites=["K902-K915 = ore classificate", "918/919 = ore festività/tipo"],
    postconditions=["501-510 = codici causale", "561-570 = ore corrispondenti"],
    tags={"sub", "causali", "esplosione", "fondamentale"},
))

_p(FormulaPattern(
    id="sub_warning",
    codes=[2130, 3030],
    name="Warning ore carenti e limite annuale",
    description="Genera alert se ci sono ore assenza (5 > 0) o se lo straordinario annuale (783) si avvicina al limite di 250 ore.",
    phase="SUB",
    chain_position=7,
    chain_group="gugest_a",
    template=[
        "IF 5 > Z THEN",
        "  # ATTENZIONE: SETTIMANA CON ORE CARENTI",
        "  CAMPO70 99  # genera alert",
        "ENDIF",
        "IF 783 > '220.00' AND 783 < '250.00' THEN",
        "  # ATTENZIONE: POTENZIALE AVVICINAMENTO 250H",
        "  CAMPO70 99",
        "ENDIF",
    ],
    parameters={
        "warning_threshold": {"type": "hours", "default": "220.00", "description": "Soglia di warning annuale"},
        "hard_limit": {"type": "hours", "default": "250.00", "description": "Limite annuale massimo"},
    },
    calls=[],
    called_by=["gugest_2a", "gugest_2a"],
    fields_read={5, 783, 1000, 1100, 300},
    fields_write={70, 71, 72, 73, 74, 75, 76, 77, 78},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["warning", "alert", "ore carenti", "limite 250 ore"],
    prerequisites=["5 = assenze", "783 = straordinario annuale"],
    postconditions=["Alert generati via CAMPO70"],
    tags={"sub", "warning", "alert"},
))

# ---------------------------------------------------------------------------
# GUGEST
# ---------------------------------------------------------------------------

_p(FormulaPattern(
    id="gugest_1a",
    codes=[2100, 2105],
    name="GUGEST 1 — Primo giro settimanale",
    description="Primo passo del calcolo settimanale GUGEST: inizializza contatori, chiama gestione festività, accumula totali settimanali, calcola soglia straordinario (887). Variante B (2105) include P2125 e intervalli extra 255-257.",
    phase="FG",
    chain_position=1,
    chain_group="gugest_a",
    template=[
        "IF 900 > Z THEN",
        "  RESET 1801",
        "  R 2101  # già passato -> secondo giro",
        "ENDIF",
        "IF 300 = 301 THEN",
        "  # Primo giorno della settimana -> azzera tutto",
        "  RESET 770",
        "  RESET 771",
        "  RESET 772",
        "  RESET 773",
        "  RESET 774",
        "  RESET 782",
        "  RESET 887",
        "  RESET 889",
        "ENDIF",
        "IF 50 = 2 THEN",
        "  # Domenica? -> azzera contatori settimanali",
        "  RESET 770",
        "  RESET 771",
        "  RESET 772",
        "  RESET 773",
        "  RESET 774",
        "  RESET 782",
        "  RESET 887",
        "  RESET 889",
        "ENDIF",
        "IF 300 = 301 THEN",
        "  RESET 770",
        "ENDIF",
        "K 770 + 1  # incrementa contatore settimana",
        "IF 55 = 'I' THEN",
        "  P 2109  # gestione festività",
        "ENDIF",
        "K 771 A 3 A 4  # ore lavorate settimanali",
        "K 772 A 608 A 609  # assenze settimanali",
        "SET 773 = 771 + 772  # totale settimanale",
        "SET 887 = '40.00' - 772  # soglia straordinario = 40h - assenze",
        "IF 1391 > Z AND 1391 < '40.00' THEN",
        "  SET 889 = '40.00' - 772  # soglia part-time",
        "  SET 887 = 1391 - 772  # soglia ridotta",
        "ENDIF",
        "IF 887 < Z THEN RESET 887 ENDIF",
        "IF 889 < Z THEN RESET 889 ENDIF",
        "IF fine_settimana THEN",
        "  # Ultimo giorno -> contabilità finale",
        "  SET 900 = 1",
        "  K 770 - 1",
        "  SET 1801 = -770",
        "ENDIF",
    ],
    parameters={
        "weekly_hours_threshold": {"type": "hours", "default": "40.00", "description": "Soglia ore settimanali"},
    },
    calls=["sub_festivita", "gugest_2a"],
    called_by=[],
    fields_read={3, 4, 50, 55, 1391, 300, 301, 302, 311, 608, 609, 770, 771, 772, 773, 774, 782, 887, 889, 900, 1801},
    fields_write={770, 771, 772, 773, 774, 782, 887, 889, 900, 1801},
    k_regs_read={"K770", "K771", "K772", "K887", "K889"},
    k_regs_write={"K770", "K771", "K772", "K887", "K889"},
    causali_slots={},
    conditions=["gugest 1", "gugest primo giro", "calcolo settimanale", "primo giro"],
    prerequisites=["900 controllato (anti-loop)", "300/50 = data/giorno corretti"],
    postconditions=["770 incrementato", "771-774 = totali settimanali", "887 = soglia calcolata"],
    tags={"gugest", "settimanale", "giro1", "fondamentale"},
))

_p(FormulaPattern(
    id="gugest_2a",
    codes=[2101, 2106],
    name="GUGEST 2 — Calcolo giornaliero dettagliato",
    description="Secondo passo GUGEST: per ogni intervallo calcolato chiama P2122, poi arrotonda (P2125 in variante B), ritocca SA/SB, esplode causali e aggiorna tutti i progressivi.",
    phase="FG",
    chain_position=2,
    chain_group="gugest_a",
    template=[
        "# Reset annuale a gennaio",
        "IF 51 = 1 AND 52 = 1 THEN",
        "  RESET 783  # azzera contatore annuale",
        "ENDIF",
        "# Reset settimanale alla domenica",
        "IF 50 = 2 THEN",
        "  RESET 771",
        "  RESET 772",
        "  RESET 773",
        "  RESET 774",
        "  RESET 782",
        "ENDIF",
        "RESET 918",
        "RESET 919",
        "K 3 A 4  # totale ordinario + straordinario",
        "RESET 4",
        "RESET 5",
        "IF 55 = 'I' THEN",
        "  P 2109  # gestione festività",
        "ENDIF",
        "K 781 A 1  # progressivo previsionale settimanale",
        "K 782 A 608 A 609  # progressivo assenze",
        "K 772 A 608 A 609  # assenze settimanali",
        "K 771 A 3 A 4  # lavorato settimanale",
        "SET 773 = 771 + 772",
        "# Loop su ogni intervallo calcolato (251-277)",
        "IF 251 > Z AND 271 > Z THEN",
        "  SET 811 = 251",
        "  SET 812 = 271",
        "  P 2122  # calcola ore intervallo",
        "ENDIF",
        "IF 252 > Z AND 272 > Z THEN",
        "  SET 811 = 252",
        "  SET 812 = 272",
        "  P 2122",
        "ENDIF",
        "IF 253 > Z AND 273 > Z THEN",
        "  SET 811 = 253",
        "  SET 812 = 273",
        "  P 2122",
        "ENDIF",
        "P 2123  # arrotondamento ore ordinarie",
        "P 2124  # arrotondamento ore straordinarie",
        "SET 3 = 902 + 903 + 904 + 905 + 908  # ri-calcola ordinarie",
        "SET 4 = 906 + 907 + 909 + 910 + 914 + 915  # ri-calcola straordinarie",
        "K 771 A 3 A 4  # aggiorna settimanale",
        "SET 773 = 771 + 772",
        "K 774 A 907  # straordinario settimanale cumulato",
        "K 783 A 4  # straordinario annuale",
        "K 784 A 906  # supplementare settimanale",
        "P 2114  # ritocco SA/SB",
        "P 2115  # esplodi causali",
        "# Calcolo assenze residue",
        "SET 800 = 3 + 4 + 608 + 609 - 1",
        "SET 801 = 887",
        "IF 782 < 801 AND 50 = 1 THEN",
        "  SET 5 = 801 - 782  # assenze residue domenica",
        "ENDIF",
        "IF fine_settimana AND non_domenica AND 785 < 781 THEN",
        "  SET 5 = 781 - 785",
        "ENDIF",
        "# Accumulo finale progressivi",
        "K 601 A 3 A 4",
        "K 602 A 3",
        "K 626 A 902 A 903",
        "K 627 A 904 A 908",
        "K 612 A 906",
        "K 611 A 907 A 915",
        "K 615 A 914",
        "K 614 A 909",
        "K 616 A 910",
        "K 604 A 904 A 908",
        "K 603 A 902",
        "K 605 A 903",
        "P 2130  # warning",
        "# Reset campi di appoggio",
        "RESET 901",
        "RESET 902",
        "RESET 903",
        "RESET 904",
        "RESET 905",
        "RESET 906",
        "RESET 907",
        "RESET 908",
        "RESET 909",
        "RESET 910",
        "RESET 914",
        "RESET 915",
        "RESET 916",
        "RESET 917",
        "RESET 918",
        "RESET 919",
        "RESET 920",
    ],
    parameters={},
    calls=["sub_calcolo_intervallo", "sub_festivita", "sub_arrotondamento_ordinari",
           "sub_arrotondamento_straordinari", "sub_ritocco_sa_sb", "sub_esplodi_causali", "sub_warning"],
    called_by=["gugest_1a"],
    fields_read={
        1, 3, 4, 5, 50, 51, 52, 55, 251, 252, 253, 254, 255, 256, 257,
        271, 272, 273, 274, 275, 276, 277, 300, 301, 302, 311,
        608, 609, 770, 771, 772, 773, 774, 781, 782, 783, 784, 785,
        800, 801, 887, 889, 900, 902, 903, 904, 905, 906, 907, 908, 909,
        910, 914, 915, 918, 919,
    },
    fields_write={
        3, 4, 5, 773, 800, 801, 902, 903, 904, 905, 906, 907, 908, 909,
        910, 914, 915, 918, 919,
    },
    k_regs_read={
        "K601", "K602", "K603", "K604", "K605", "K611", "K612", "K614",
        "K615", "K616", "K626", "K627", "K771", "K772", "K774", "K781",
        "K782", "K783", "K784", "K900",
    },
    k_regs_write={
        "K3", "K4", "K601", "K602", "K603", "K604", "K605", "K611", "K612",
        "K614", "K615", "K616", "K626", "K627", "K771", "K772", "K774",
        "K781", "K782", "K783", "K784", "K900",
    },
    causali_slots={},
    conditions=["gugest 2", "gugest secondo giro", "calcolo giornaliero", "secondo giro"],
    prerequisites=["770 incrementato (gugest_1a eseguito)", "771-774 calcolati"],
    postconditions=["Tutti i progressivi K6xx aggiornati", "Causali esplose in 501-510/561-570"],
    tags={"gugest", "giornaliero", "giro2", "fondamentale"},
))

# ---------------------------------------------------------------------------
# FG VARIANTE B (3xxx)
# ---------------------------------------------------------------------------

_p(FormulaPattern(
    id="fg_b_1",
    codes=[3000],
    name="FG B — Primo giro (con split data 01/06/2023)",
    description="Versione aggiornata del primo giro GUGEST con split logica arrotondamento al 01/06/2023 e gestione AUTS.",
    phase="FG",
    chain_position=1,
    chain_group="fg_b",
    template=[
        "IF 900 > Z THEN",
        "  RESET 1801",
        "  R 3001",
        "ENDIF",
        "IF 300 = 301 THEN",
        "  RESET 770",
        "ENDIF",
        "IF 50 = 2 THEN",
        "  RESET 772",
        "  RESET 788",
        "  RESET 790",
        "  RESET 774",
        "  RESET 775",
        "ENDIF",
        "IF 55 = 'I' THEN P 3009 ENDIF  # festività B",
        "K 770 + 1",
        "K 772 A 608 A 609",
        "K 775 A 3 A 4 A 608 A 609",
        "K 3 A 4",
        "RESET 4",
        "RESET 5",
        "RESET 918",
        "RESET 919",
        "# Split arrotondamento: ante vs post 01/06/2023",
        "IF 300 < '20230601' THEN",
        "  P 3002  # arrotondamento vecchio (quarti doppi)",
        "ENDIF",
        "IF 300 >= '20230601' THEN",
        "  P 3003  # arrotondamento nuovo (mezz'ora)",
        "ENDIF",
        "P 3017  # AUTS",
        "SET 887 = '40.00' - 772",
        "IF 1391 > Z AND 1391 < '40.00' THEN",
        "  SET 889 = '40.00' - 1391",
        "  SET 887 = 1391 - 772",
        "ENDIF",
        "IF 887 < Z THEN RESET 887 ENDIF",
        "IF 889 < Z THEN RESET 889 ENDIF",
        "IF fine_settimana THEN",
        "  SET 900 = 1",
        "  K 770 - 1",
        "  SET 1801 = -770",
        "ENDIF",
    ],
    parameters={},
    calls=["fg_b_2", "sub_festivita"],
    called_by=[],
    fields_read={3, 4, 50, 55, 300, 301, 302, 311, 608, 609, 770, 772, 775, 788, 790, 887, 889, 900, 1391, 1801},
    fields_write={770, 772, 775, 788, 790, 887, 889, 900, 1801, 918, 919},
    k_regs_read={"K770", "K772", "K775", "K887", "K889"},
    k_regs_write={"K770", "K772", "K775", "K3", "K4", "K887", "K889"},
    causali_slots={},
    conditions=["fg b primo giro", "fg 1", "variante b", "split 2023", "01/06/2023"],
    prerequisites=["900 controllato", "Data giornata in 300"],
    postconditions=["887, 889 calcolati", "AUTS processato"],
    tags={"fg", "gugest", "variante_b", "giro1"},
))

_p(FormulaPattern(
    id="fg_b_2",
    codes=[3001],
    name="FG B — Secondo giro (calcolo completo)",
    description="Versione aggiornata del secondo giro GUGEST. Include calcolo straordinario settimanale (P3005), gestione assenze domenica, progressivo K711.",
    phase="FG",
    chain_position=2,
    chain_group="fg_b",
    template=[
        "# Reset annuale a gennaio",
        "IF 51 = 1 AND 52 = 1 THEN RESET 783 ENDIF",
        "# Per ogni intervallo come in gugest_2a",
        "P 3005  # straordinario settimanale",
        "P 3014  # ritocco SA/SB B",
        "P 3015  # esplodi causali B (con FX)",
        "P 3030  # warning B",
        "K 711 A 601 A 608  # totale ore settimanali",
        "IF fine_settimana THEN",
        "  # Calcolo assenze domenica",
        "  SET 776 = 3 + 21  # lavorato + ordinario notturno",
        "  IF 1391 > Z THEN",
        "    SET 5 = 1391 - 776  # part-time",
        "  ELSE",
        "    SET 5 = '40.00' - 776  # full-time",
        "  ENDIF",
        "ENDIF",
    ],
    parameters={},
    calls=[],
    called_by=["fg_b_1"],
    fields_read={50, 51, 52, 300, 301, 302, 311, 601, 608, 771, 772, 773, 774, 775, 776, 781, 782, 783, 784, 785, 887, 889, 900, 1391, 1801},
    fields_write={5, 776, 783, 784, 785},
    k_regs_read={"K601", "K602", "K603", "K604", "K605", "K611", "K612", "K614", "K615", "K616", "K626", "K627", "K711", "K771", "K772", "K774", "K781", "K782", "K783", "K784"},
    k_regs_write={"K3", "K4", "K601", "K602", "K603", "K604", "K605", "K611", "K612", "K614", "K615", "K616", "K626", "K627", "K711", "K771", "K772", "K774", "K781", "K782", "K783", "K784", "K900"},
    causali_slots={},
    conditions=["fg b secondo giro", "fg new", "gestione aggiornata", "variante b secondo"],
    prerequisites=["fg_b_1 eseguito", "Intervalli calcolati"],
    postconditions=["Tutti i progressivi aggiornati", "Causali esplose"],
    tags={"fg", "gugest", "variante_b", "giro2"},
))

# ---------------------------------------------------------------------------
# SUB SPECIALI
# ---------------------------------------------------------------------------


_p(FormulaPattern(
    id="sub_auts",
    codes=[3017],
    name="Gestione autorizzazioni straordinario (AUTS)",
    description="Legge le autorizzazioni straordinario dalle causali manuali (401-404) e prepara i campi 820/821 per il limite.",
    phase="SUB",
    chain_position=1,
    chain_group="sub_speciali",
    template=[
        "# Legge AUTS dalle causali manuali",
        "# Se causale manuale = AUTS -> set 820 = slot, 821 = ore autorizzate",
        "IF 401 = 'AUTS' THEN",
        "  SET 820 = 411  # ora inizio autorizzazione",
        "  SET 821 = 431  # ore autorizzate",
        "ENDIF",
        "IF 402 = 'AUTS' THEN",
        "  SET 820 = 412",
        "  SET 821 = 432",
        "ENDIF",
        "IF 403 = 'AUTS' THEN",
        "  SET 820 = 413",
        "  SET 821 = 433",
        "ENDIF",
        "IF 404 = 'AUTS' THEN",
        "  SET 820 = 414",
        "  SET 821 = 434",
        "ENDIF",
    ],
    parameters={},
    calls=[],
    called_by=[],
    fields_read={401, 402, 403, 404, 411, 412, 413, 414, 431, 432, 433, 434},
    fields_write={820, 821},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["auts", "autorizzazione straordinario", "autorizzazione"],
    prerequisites=["401-404 = causali manuali"],
    postconditions=["820/821 = slot/ore autorizzati"],
    tags={"sub", "auts", "autorizzazione"},
))

_p(FormulaPattern(
    id="sub_conad_arrotondamento_entrate",
    codes=[2050],
    name="Arrotondamento entrate Conad",
    description="Arrotonda le timbrature di entrata alla mezz'ora o all'ora per dipendenti Conad Gubbio.",
    phase="IG",
    chain_position=2,
    chain_group="conad",
    template=[
        "# Arrotondamento entrate Conad",
        "IF 201 > Z THEN",
        "  CAMPO70 3  # separa ore e minuti di 201",
        "  IF 73 >= '30' THEN",
        "    SET 201 = 72 + '01.00'  # arrotonda all'ora successiva",
        "  ELSE",
        "    SET 201 = 72  # arrotonda all'ora esatta",
        "  ENDIF",
        "ENDIF",
    ],
    parameters={
        "rounding_minutes": {"type": "int", "default": "30", "description": "Minuti di arrotondamento"},
    },
    calls=[],
    called_by=[],
    fields_read={201, 72, 73},
    fields_write={201},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["conad arrotondamento", "arrotondamento entrate", "conad gubbio"],
    prerequisites=["201 = entrata effettiva"],
    postconditions=["201 arrotondato"],
    tags={"sub", "arrotondamento", "conad"},
))

_p(FormulaPattern(
    id="sub_conad_arrotondamento_uscite",
    codes=[2051],
    name="Arrotondamento uscite Conad",
    description="Arrotonda le timbrature di uscita alla mezz'ora.",
    phase="IG",
    chain_position=3,
    chain_group="conad",
    template=[
        "# Arrotondamento uscite Conad",
        "IF 221 > Z THEN",
        "  CAMPO70 3  # separa ore e minuti di 221",
        "  IF 73 >= '30' THEN",
        "    SET 221 = 72 + '01.00'",
        "  ELSE",
        "    SET 221 = 72",
        "  ENDIF",
        "ENDIF",
    ],
    parameters={},
    calls=[],
    called_by=[],
    fields_read={221, 72, 73},
    fields_write={221},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["conad arrotondamento uscite", "arrotondamento uscite"],
    prerequisites=["221 = uscita effettiva"],
    postconditions=["221 arrotondato"],
    tags={"sub", "arrotondamento", "conad"},
))

_p(FormulaPattern(
    id="sub_conad_cap_uscite",
    codes=[2060],
    name="Cap uscite Conad a 20:05",
    description="Limita l'orario di uscita massimo a 20:05 per i dipendenti Conad Gubbio.",
    phase="IG",
    chain_position=4,
    chain_group="conad",
    template=[
        "# Cap uscite a 20:05",
        "IF 271 > '20.05' THEN",
        "  SET 271 = '20.05'",
        "ENDIF",
        "IF 272 > '20.05' THEN",
        "  SET 272 = '20.05'",
        "ENDIF",
    ],
    parameters={
        "cap_time": {"type": "time", "default": "20.05", "description": "Orario massimo uscita"},
    },
    calls=[],
    called_by=[],
    fields_read={271, 272},
    fields_write={271, 272},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["conad cap uscite", "cap 20:05", "limite uscita"],
    prerequisites=["271/272 = uscite calcolate"],
    postconditions=["271/272 <= 20:05"],
    tags={"sub", "conad", "cap", "uscita"},
))

_p(FormulaPattern(
    id="sub_arrotondamento_impiegati_1",
    codes=[9001],
    name="Arrotondamento impiegati I — tutti tranne ultimo",
    description="Arrotonda ai quarti d'ora tutti gli intervalli tranne l'ultimo per impiegati.",
    phase="IG",
    chain_position=2,
    chain_group="impiegati",
    template=[
        "# Arrotondamento ai quarti per intervalli 1..N-1",
    ],
    parameters={},
    calls=[],
    called_by=[],
    fields_read={250, 251, 252, 253, 254, 255, 256, 257, 271, 272, 273, 274, 275, 276, 277},
    fields_write={251, 252, 253, 254, 255, 256, 257, 271, 272, 273, 274, 275, 276, 277, 800, 801, 802, 803, 804},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["arrotondamento impiegati", "impiegati quarti"],
    prerequisites=["250 = numero intervalli calcolati"],
    postconditions=["Intervalli 1..N-1 arrotondati ai quarti"],
    tags={"sub", "arrotondamento", "impiegati"},
))

_p(FormulaPattern(
    id="sub_arrotondamento_impiegati_2",
    codes=[9002],
    name="Arrotondamento impiegati II — ultimo intervallo",
    description="Sistema l'ultimo intervallo per far quadrare il totale dopo arrotondamento dei precedenti.",
    phase="IG",
    chain_position=3,
    chain_group="impiegati",
    template=[
        "# Sistema l'ultimo intervallo per quadratura",
    ],
    parameters={},
    calls=[],
    called_by=[],
    fields_read={250, 251, 252, 253, 254, 255, 256, 257, 271, 272, 273, 274, 275, 276, 277, 800, 801, 802, 803, 804},
    fields_write={251, 252, 253, 254, 255, 256, 257, 271, 272, 273, 274, 275, 276, 277},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["arrotondamento impiegati ultimo", "quadratura arrotondamento"],
    prerequisites=["sub_arrotondamento_impiegati_1 eseguito"],
    postconditions=["Ultimo intervallo aggiustato per quadratura"],
    tags={"sub", "arrotondamento", "impiegati"},
))



# ---------------------------------------------------------------------------
# IG supplementari
# ---------------------------------------------------------------------------

_p(FormulaPattern(
    id="ig_turn_calendar",
    codes=[10],
    name="Riconoscimento turno su calendario",
    description="Determina il turno (MATT/POME/NOTT/RIPO/OPE) usando le ore del calendario (84/85) e campo 802. Alternativa alla formula 5.",
    phase="IG",
    chain_position=2,
    chain_group="standard",
    template=[
        "IF 1 = Z OR 58 = 'RIPO' THEN VF ENDIF",
        "SET 802 = 85",
        "IF 802 < 84 THEN K802 A '24' ENDIF",
        "SET 801 = 802 - 84",
        "IF 801 < '7' THEN",
        "  SET 58 = 'OPE'",
        "  SET 111 = '8'",
        "  SET 141 = '12'",
        "  SET 112 = '13'",
        "  SET 142 = '17'",
        "  SET 100 = 2",
        "  VF",
        "ENDIF",
        "IF 84 < '7' AND 84 > '5' THEN",
        "  SET 900 = 1",
        "  SET 58 = 'MATT'",
        "  SET 111 = '6'",
        "  SET 141 = '14'",
        "  RESET 112",
        "  RESET 142",
        "  SET 100 = 1",
        "  VF",
        "ENDIF",
        "IF 84 < '15' AND 84 > '13' THEN",
        "  SET 900 = 2",
        "  SET 58 = 'POME'",
        "  SET 111 = '14'",
        "  SET 141 = '22'",
        "  RESET 112",
        "  RESET 142",
        "  SET 100 = 1",
        "  VF",
        "ENDIF",
        "SET 900 = 3",
        "SET 58 = 'NOTT'",
        "SET 111 = '22'",
        "SET 141 = '6'",
        "RESET 112",
        "RESET 142",
        "SET 100 = 1",
    ],
    parameters={
        "finestra_mattino_start": {"type": "time", "default": "5.00", "description": "Inizio finestra turno mattino (campo 84)"},
        "finestra_mattino_end": {"type": "time", "default": "7.00", "description": "Fine finestra turno mattino (campo 84)"},
        "finestra_pomeriggio_start": {"type": "time", "default": "13.00", "description": "Inizio finestra turno pomeriggio (campo 84)"},
        "finestra_pomeriggio_end": {"type": "time", "default": "15.00", "description": "Fine finestra turno pomeriggio (campo 84)"},
    },
    calls=[],
    called_by=["ig_reset"],
    fields_read={1, 58, 84, 85, 802},
    fields_write={58, 100, 111, 112, 141, 142, 801, 802, 900},
    k_regs_read={"K802"},
    k_regs_write={"K802"},
    causali_slots={},
    conditions=["riconoscimento turno calendario", "determinazione turno da ore", "calendario ore",
                 "turno ope", "operaio", "orario continuato"],
    prerequisites=["1 e 84/85 caricati dal calendario"],
    postconditions=["900 determinato (1/2/3)", "58 = MATT/POME/NOTT/OPE"],
    tags={"ig", "turno", "calendario", "ope"},
))

# ---------------------------------------------------------------------------
# SUB — GUGEST B chiamate interne
# ---------------------------------------------------------------------------

_p(FormulaPattern(
    id="sub_maggiorazioni_dettaglio",
    codes=[2107],
    name="Maggiorazioni GUGEST B — calcolo dettagliato",
    description="Chiamato da formula 2106: classifica ogni minuto dell'intervallo nei bucket maggiorazioni (notte, festivo, supplementare, straordinario).",
    phase="SUB",
    chain_position=1,
    chain_group="gugest_b",
    template=[
        "SET 801 = 3 + 4",
        "IF 801 = Z THEN VF ENDIF",
        "CAMPO70 3  # separa 801 in 72=ore 73=minuti",
        "IF 73 < '15' THEN V08 ENDIF",
        "IF 73 < '30' THEN K800 A '0.15' V07 ENDIF",
        "IF 73 < '45' THEN K800 A '0.35' V07 ENDIF",
        "K800 A '0.45'  # 45-59 min",
        "V07  # etichetta accumulo",
        "K801 A 800",
        "K782 A 801",
        "CAMPO70 20  # round entrata in 810",
        "SET 905 = 801",
        "K782 A Z  # ???",
        "# Classificazione per fasce orarie e soglie",
        "IF 889 > Z AND 782 > 887 AND 782 < 889 THEN",
        "  K906 A 810  # supplementare entro part-time",
        "  VU",
        "ENDIF",
        "IF 782 > 887 THEN",
        "  K907 A 810  # straordinario diurno",
        "  VU",
        "ENDIF",
        "K905 A 810  # ordinario oltre notte",
    ],
    parameters={},
    calls=[],
    called_by=["gugest_2a"],
    fields_read={3, 4, 782, 800, 801, 810, 811, 812, 887, 889},
    fields_write={800, 801, 905},
    k_regs_read={"K782", "K800", "K801", "K887", "K889"},
    k_regs_write={"K782", "K800", "K801", "K905", "K906", "K907", "K910", "K914", "K903", "K904", "K908"},
    causali_slots={},
    conditions=["maggiorazioni dettaglio", "classificazione minuti", "2107"],
    prerequisites=["811/812 = intervallo da calcolare", "887/889 = soglie"],
    postconditions=["Ore classificate in K902-K915"],
    tags={"sub", "gugest", "maggiorazioni", "dettaglio"},
))

_p(FormulaPattern(
    id="sub_arrotondamento_base",
    codes=[2140],
    name="Arrotondamento base — durata ore",
    description="Calcola la durata totale (ore + minuti) tra entrata e uscita. Chiamato come utilità base.",
    phase="SUB",
    chain_position=1,
    chain_group="sub_speciali",
    template=[
        "SET 71 = 3 + 4  # ore totali in 71",
        "CAMPO70 3  # separa in 72=ore 73=minuti",
    ],
    parameters={},
    calls=[],
    called_by=[],
    fields_read={3, 4},
    fields_write={71, 72, 73},
    k_regs_read=set(),
    k_regs_write=set(),
    causali_slots={},
    conditions=["arrotondamento base", "durata ore", "calcolo durata"],
    prerequisites=["3 = ore ordinarie, 4 = straordinario"],
    postconditions=["71 = 3+4, 72/73 = ore/minuti separati"],
    tags={"sub", "arrotondamento", "base"},
))

# ---------------------------------------------------------------------------
# SUB FG VARIANTE B (3xxx)
# ---------------------------------------------------------------------------

_p(FormulaPattern(
    id="sub_arrotondamento_ante_2023",
    codes=[3002],
    name="Arrotondamento ante 01/06/2023 (quarti doppi)",
    description="Arrotondamento ore ordinarie per FG B prima del 01/06/2023: usa regola quarti doppi con soglia 40h o part-time.",
    phase="SUB",
    chain_position=1,
    chain_group="fg_b",
    template=[
        "SET 800 = '40.00'  # soglia default",
        "IF 1391 > Z THEN SET 800 = 1391 ENDIF  # part-time",
        "IF 775 > 800 THEN V11 ENDIF  # oltre soglia -> salta",
        "CAMPO70 3  # separa 3 in 72=ore 73=minuti",
        "SET 3 = 72",
        "IF 73 < '15' THEN V10 ENDIF  # scarta",
        "IF 73 < '30' THEN K800 A '0.15' V09 ENDIF  # +0.15",
        "IF 73 < '45' THEN K800 A '0.30' V09 ENDIF  # +0.30",
        "K800 A '0.45'  # +0.45",
        "V09: K3 A 800  # accumula arrotondamento",
        "VF",
        "V10: CAMPO70 3",
        "IF 73 < '30' THEN VF ENDIF  # scarta sotto 30",
        "K800 A '0.30'",
        "K3 A 800",
    ],
    parameters={
        "threshold_weekly": {"type": "hours", "default": "40.00", "description": "Soglia ore settimanali"},
    },
    calls=[],
    called_by=["fg_b_1"],
    fields_read={3, 775, 1391},
    fields_write={3, 71, 72, 73, 800},
    k_regs_read={"K3", "K800"},
    k_regs_write={"K3", "K800"},
    causali_slots={},
    conditions=["arrotondamento ante 2023", "arrotondamento vecchio", "quarti doppi", "prima 01/06/2023"],
    prerequisites=["3 = ore ordinarie pre-arrotondamento"],
    postconditions=["3 = ore arrotondate con regola vecchia"],
    tags={"sub", "arrotondamento", "fg_b", "ante_2023"},
))

_p(FormulaPattern(
    id="sub_arrotondamento_post_2023",
    codes=[3003],
    name="Arrotondamento post 01/06/2023 (mezz'ora)",
    description="Arrotondamento ore ordinarie per FG B dopo il 01/06/2023: regola mezz'ora (30min = 0.30, scarta sotto).",
    phase="SUB",
    chain_position=2,
    chain_group="fg_b",
    template=[
        "CAMPO70 3  # separa 3 in 72=ore 73=minuti",
        "SET 3 = 72  # ore intere",
        "IF 73 < '30' THEN VF ENDIF  # scarta sotto 30",
        "K800 A '0.30'  # +0.30 se >= 30 min",
        "K3 A 800",
    ],
    parameters={},
    calls=[],
    called_by=["fg_b_1"],
    fields_read={3},
    fields_write={3, 71, 72, 73, 800},
    k_regs_read={"K3", "K800"},
    k_regs_write={"K3", "K800"},
    causali_slots={},
    conditions=["arrotondamento post 2023", "arrotondamento nuovo", "mezz'ora", "dopo 01/06/2023"],
    prerequisites=["3 = ore ordinarie pre-arrotondamento"],
    postconditions=["3 = ore arrotondate con regola nuova"],
    tags={"sub", "arrotondamento", "fg_b", "post_2023"},
))

_p(FormulaPattern(
    id="sub_maggiorazioni_turnisti_b",
    codes=[3004],
    name="Maggiorazioni turnisti FG B — N/T",
    description="Per FG B: riclassifica ore. Straordinario diurno (907) diventa festivo (914). Ore ordinarie (3) vanno in LFS (904).",
    phase="SUB",
    chain_position=3,
    chain_group="fg_b",
    template=[
        "IF 50 = I OR 55 = I THEN V02 ENDIF  # non festivo/domenica",
        "VF",
        "IF 907 > Z THEN",
        "  SET 914 = 907  # straordinario -> festivo",
        "  RESET 907",
        "ENDIF",
        "IF 915 > Z THEN",
        "  K914 A 915  # SB -> festivo",
        "  RESET 915",
        "ENDIF",
        "IF 3 > Z THEN",
        "  SET 904 = 3  # ordinario -> LFS",
        "ENDIF",
    ],
    parameters={},
    calls=[],
    called_by=["fg_b_1"],
    fields_read={3, 50, 55, 907, 915},
    fields_write={904, 907, 914, 915},
    k_regs_read={"K914"},
    k_regs_write={"K914"},
    causali_slots={},
    conditions=["maggiorazioni turnisti b", "maggiorazioni fg b", "riclassificazione festivo"],
    prerequisites=["50/55 = giorno festivo/domenica"],
    postconditions=["907/915 -> 914 (festivo)", "3 -> 904 (LFS)"],
    tags={"sub", "maggiorazioni", "fg_b"},
))

_p(FormulaPattern(
    id="sub_straordinario_settimanale",
    codes=[3005],
    name="Straordinario settimanale FG B",
    description="Calcola lo straordinario settimanale per FG B: confronta totale settimana (788) con soglia (887), eccedenza va in 907. Gestisce anche AUTS (820/821).",
    phase="SUB",
    chain_position=4,
    chain_group="fg_b",
    template=[
        "SET 810 = 788  # ore lavorate settimana",
        "SET 811 = 788 - 3  # ore senza oggi",
        "IF 810 < 887 THEN VF ENDIF  # sotto soglia -> niente",
        "IF 810 > 887 AND 811 < 887 THEN",
        "  SET 4 = 788 - 887  # eccedenza parziale",
        "  K3 S 4  # toglie da ordinarie",
        "  V04",
        "ENDIF",
        "SET 4 = 3  # tutto straordinario",
        "K3 S 4",
        "IF 3 < Z THEN RESET 3 ENDIF",
        "IF 820 > Z AND 821 > Z THEN",
        "  SET 907 = 821  # da AUTS",
        "  V08",
        "ENDIF",
        "K907 A 4  # accumula in straordinario diurno",
        "IF 889 > Z THEN V10 ENDIF  # soglia part-time",
        "VU",
        "SET 906 = 907  # supplementare",
        "RESET 907",
        "K790 A 906",
        "SET 812 = 790",
        "SET 813 = 790 - 906",
        "IF 812 < 889 AND 813 < 889 THEN VU ENDIF",
        "IF 812 > 889 AND 813 < 889 THEN",
        "  SET 907 = 790 - 889",
        "  K906 S 907",
        "  VU",
        "ENDIF",
        "SET 907 = 906",
        "RESET 906",
        "K774 A 907",
    ],
    parameters={
        "weekly_threshold": {"type": "hours", "default": "40.00", "description": "Soglia ore settimanali"},
    },
    calls=[],
    called_by=["fg_b_2"],
    fields_read={3, 4, 5, 770, 774, 788, 790, 820, 821, 887, 889},
    fields_write={3, 4, 5, 788, 790, 906, 907, 810, 811, 812, 813},
    k_regs_read={"K3", "K4", "K774", "K788", "K790", "K887", "K889", "K906", "K907"},
    k_regs_write={"K3", "K4", "K774", "K788", "K790", "K906", "K907"},
    causali_slots={},
    conditions=["straordinario settimanale", "eccedenza settimanale", "fg b straordinario"],
    prerequisites=["788 = ore settimana", "887 = soglia"],
    postconditions=["4 = eccedenza settimanale classificata"],
    tags={"sub", "straordinario", "settimanale", "fg_b"},
))

# ============================================================
# CHAIN DEFINITIONS
# ============================================================

@dataclass
class ChainDef:
    """Definizione di una catena di formule."""
    id: str
    name: str
    description: str
    patterns: List[str]           # Pattern ID in ordine
    contract_types: List[int]     # Contratti applicabili (1=standard, 2=dirigenti, 3=turnisti)


CHAINS: Dict[str, ChainDef] = {
    "standard_ig": ChainDef(
        id="standard_ig",
        name="IG Standard",
        description="Standard IG chain for all employees",
        patterns=["ig_reset", "ig_turn_recognition"],
        contract_types=[3],
    ),
    "standard_fg": ChainDef(
        id="standard_fg",
        name="FG Standard",
        description="Standard FG chain with overtime classification",
        patterns=[
            "fg_azzeramenti",
            "fg_riproporzionamento",
            "fg_dispatcher",
            "fg_split_festivo",   # if holiday
            "fg_split_ordinario", # if ordinary
            "fg_finale",
            "fg_maggiorazioni",
        ],
        contract_types=[3],
    ),
    "dirigenti_ig": ChainDef(
        id="dirigenti_ig",
        name="IG Dirigenti",
        description="IG for directors (no punches)",
        patterns=["ig_reset", "ig_copy_planned"],
        contract_types=[2],
    ),
    "dirigenti_fg": ChainDef(
        id="dirigenti_fg",
        name="FG Dirigenti",
        description="FG for directors/quads",
        patterns=["fg_dirigenti_assenze"],
        contract_types=[2],
    ),
    "chiamata_fg": ChainDef(
        id="chiamata_fg",
        name="FG Chiamata",
        description="FG for on-call employees",
        patterns=["fg_chiamata"],
        contract_types=[1],
    ),
    "single_punch_ig": ChainDef(
        id="single_punch_ig",
        name="IG Timbratura Singola",
        description="IG for single-punch employees",
        patterns=["ig_reset", "ig_single_punch"],
        contract_types=[1],
    ),
    "single_punch_fg": ChainDef(
        id="single_punch_fg",
        name="FG Timbratura Singola",
        description="FG for single-punch employees",
        patterns=["fg_single_punch_assenze"],
        contract_types=[1],
    ),
    "gugest_a": ChainDef(
        id="gugest_a",
        name="GUGEST A",
        description="GUGEST two-pass system variant A",
        patterns=["gugest_1a", "gugest_2a"],
        contract_types=[3],
    ),
    "gugest_b": ChainDef(
        id="gugest_b",
        name="GUGEST B (orario continuato)",
        description="GUGEST variant B (2105/2106) with P2125 rounding for split-shift employees",
        patterns=["gugest_1a", "gugest_2a"],
        contract_types=[3],
    ),
    "fg_b": ChainDef(
        id="fg_b",
        name="FG B (post-2023)",
        description="Updated FG with 01/06/2023 split",
        patterns=["fg_b_1", "fg_b_2"],
        contract_types=[3],
    ),
    "conad_ig": ChainDef(
        id="conad_ig",
        name="IG Conad Gubbio",
        description="Conad Gubbio rounding chain",
        patterns=[
            "ig_reset",
            "sub_conad_arrotondamento_entrate",
            "sub_conad_arrotondamento_uscite",
            "sub_conad_cap_uscite",
        ],
        contract_types=[1],
    ),
    "impiegati_ig": ChainDef(
        id="impiegati_ig",
        name="IG Impiegati arrotondamento",
        description="Employee quarter-rounding chain",
        patterns=["ig_reset", "sub_arrotondamento_impiegati_1", "sub_arrotondamento_impiegati_2"],
        contract_types=[1],
    ),
}


# ============================================================
# CLASSIFIER — Match user request to patterns
# ============================================================

def match_patterns(user_request: str, top_k: int = 3, min_score: float = 2.0) -> List[FormulaPattern]:
    """Matcha una richiesta utente con i pattern formula più pertinenti.

    Usa keyword matching sul nome, descrizione, condizioni e tag di ogni pattern.
    Solo parole con lunghezza >= 3 sono considerate per nome/descrizione.
    Restituisce i pattern ordinati per punteggio decrescente, solo se score >= min_score.
    """
    low = user_request.lower()
    scored = []

    for pid, pat in PATTERNS.items():
        score = 0.0
        # Match sul nome (solo parole >= 3 char per evitare falsi positivi su a/e/i/di/da)
        for word in pat.name.lower().split():
            if len(word) >= 3 and word in low:
                score += 3.0
        # Match sulla descrizione
        for word in pat.description.lower().split():
            if len(word) >= 3 and word in low:
                score += 1.5
        # Match sulle condizioni (le condizioni complete sono più specifiche)
        for cond in pat.conditions:
            if cond.lower() in low:
                score += 5.0
        # Match sui tag (anche tag brevi solo se sono substring esatta)
        for tag in pat.tags:
            if len(tag) >= 3 and tag in low:
                score += 2.0
        # Match sui codici numerici workbook (word boundary)
        for code in pat.codes:
            if re.search(rf'\b{code}\b', low):
                score += 10.0
        if score >= min_score:
            scored.append((score, pat))

    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:top_k]]


def match_chain(user_request: str, min_score: int = 2) -> List[ChainDef]:
    """Matcha una richiesta utente con le catene di formule."""
    low = user_request.lower()
    matched = []
    for cid, chain in CHAINS.items():
        score = 0
        for word in chain.name.lower().split():
            if len(word) >= 3 and word in low:
                score += 2
        for pid in chain.patterns:
            if pid in PATTERNS:
                pat = PATTERNS[pid]
                for cond in pat.conditions:
                    if len(cond) >= 3 and cond.lower() in low:
                        score += 3
        if score >= min_score:
            matched.append((score, chain))
    matched.sort(key=lambda x: -x[0])
    return [c for _, c in matched]


class FormulaPatternLibrary:
    """Wrapper class providing object-oriented access to pattern functions."""

    def get_pattern(self, pattern_id: str) -> Optional[FormulaPattern]:
        return get_pattern(pattern_id)

    def match_patterns(self, text: str, min_score: float = 0.5) -> list:
        return match_patterns(text, min_score)

    def get_patterns_by_phase(self, phase: str) -> list:
        return get_patterns_by_phase(phase)

    def get_patterns_by_tag(self, tag: str) -> list:
        return get_patterns_by_tag(tag)


def get_pattern(pattern_id: str) -> Optional[FormulaPattern]:
    """Restituisce un pattern per ID."""
    return PATTERNS.get(pattern_id)


def get_chain(chain_id: str) -> Optional[ChainDef]:
    """Restituisce una catena per ID."""
    return CHAINS.get(chain_id)


def fill_template(pattern: FormulaPattern, params: Dict[str, str], strip_comments: bool = True) -> List[str]:
    """Riempie un template IR con parametri specifici.

    I parametri sono sostituiti nei placeholder {nome_slot}.
    Se un parametro non è fornito, usa il default.
    Se strip_comments=True, rimuove i commenti inline ( # ...).
    """
    replacements = {}
    for slot, meta in pattern.parameters.items():
        if slot in params:
            replacements[f"{{{slot}}}"] = params[slot]
        else:
            replacements[f"{{{slot}}}"] = meta["default"]

    filled = []
    for step in pattern.template:
        line = step
        for placeholder, value in replacements.items():
            line = line.replace(placeholder, value)
        if strip_comments and " # " in line:
            line = line.split(" # ", 1)[0].rstrip()
        filled.append(line)

    return filled


def get_patterns_by_phase(phase: str) -> List[FormulaPattern]:
    """Restituisce tutti i pattern per una fase (IG/DG/FG/SUB)."""
    return [p for p in PATTERNS.values() if p.phase == phase]


def get_patterns_by_tag(tag: str) -> List[FormulaPattern]:
    """Restituisce tutti i pattern con un dato tag."""
    return [p for p in PATTERNS.values() if tag in p.tags]
