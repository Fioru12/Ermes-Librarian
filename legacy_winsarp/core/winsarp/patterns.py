"""
Formula Pattern Library — Repository di tutti i pattern reali di formule WinSarp.

Carica pattern da WinSarp_Formule.txt (se presente) o da dati hardcoded,
fornendo ai builder un catalogo completo di pattern di sintassi compatta
da usare come template per la generazione.

Ogni pattern include:
- Codice formula, nome, tipo (IG/FG/Sub), categoria
- Sintassi compatta reale
- Campi coinvolti
- Relazioni (chiamate P e salti R)
- Spiegazione step-by-step
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


# ============================================================
# Tipi formula
# ============================================================

FORMULA_TIPO_IG = "IG"   # Inizio Giornata
FORMULA_TIPO_FG = "FG"   # Fine Giornata
FORMULA_TIPO_SUB = "SUB" # Subroutine
FORMULA_TIPO_DG = "DG"   # Di Giornata


# ============================================================
# Modello pattern formula
# ============================================================


@dataclass
class FormulaPattern:
    code: int
    name: str
    tipo: str
    category: str = ""
    compact: str = ""
    steps: list[dict[str, str]] = field(default_factory=list)
    fields_involved: list[int] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)  # {type: "P"|"R", target: int}
    description: str = ""
    notes: str = ""
    is_template: bool = False  # True se e' un pattern generico (non formula reale)


# ============================================================
# Pattern Library
# ============================================================


class FormulaPatternLibrary:
    """Catalogo di tutti i pattern formula WinSarp reali."""

    PATTERNS: dict[int, FormulaPattern] = {}
    # Pattern raggruppati per tipo e categoria
    _by_tipo: dict[str, list[FormulaPattern]] = {}
    _by_category: dict[str, list[FormulaPattern]] = {}

    _instance: FormulaPatternLibrary | None = None

    def __new__(cls) -> FormulaPatternLibrary:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self._build_patterns()
        self._build_indexes()
        self._load_from_formule_file()

    def _build_patterns(self) -> None:
        """Costruisce database pattern dalle formule reali di WinSarp_Formule.txt."""
        patterns: dict[int, FormulaPattern] = {}

        # --- 1: Azzeramento inizio giornata ---
        patterns[1] = FormulaPattern(
            code=1, name="Azzeramenti di inizio giornata", tipo=FORMULA_TIPO_IG,
            category="Standard",
            compact="(!900)",
            description="Azzeramento minimo di inizio giornata. Resetta campo 900 (flag anti-loop).",
            fields_involved=[900],
            steps=[{"istruzione": "!900", "descrizione": "Azzera campo 900 (flag anti-loop / indicatore turno)"}],
        )

        # --- 5: Riconoscimento turno ---
        patterns[5] = FormulaPattern(
                code=5, name="Riconoscimento Turno e cambio del previsionale", tipo=FORMULA_TIPO_IG,
                category="Turnisti",
                compact='(!900)(!800!801!802!803!804)200UZO58U"RIPO"(VF(801=\'200\')(802=\'220\')([800[801[802)(803={802}S{801})803<Z((K803A\'24\')803<804((803=804)V11{801}>U\'04.00\'E{801}<U\'09.00\'((58="MATT")(111=\'06\')(141=\'14\')(!112!142)(100=I)(900=\'1\')V11{801}>U\'12.00\'E{801}<U\'17.00\'((58="POME")(111=\'14\')(141=\'22\')(!112!142)(100=I)(900=\'2\')V11{801}>U\'20.00\'E{801}<U\'23.59\'((58="NOTT")(111=\'22\')(141=\'06\')(!112!142)(100=I)(900=\'3\')V11800U200(VF(804=803)V04',
            description="Analizza timbrature effettive per determinare turno (MATT/POME/NOTT) e aggiorna orario previsionale.",
            fields_involved=[58, 100, 111, 112, 141, 142, 200, 220, 800, 801, 802, 803, 804, 900],
            steps=[
                {"istruzione": "!900, !800-804", "descrizione": "Azzera flag e variabili di lavoro"},
                {"istruzione": "200 U Z O 58='RIPO' ( VF", "descrizione": "Se nessuna timbratura o riposo → esci"},
                {"istruzione": "801=200, 802=220", "descrizione": "Inizializza puntatori range timbrature"},
                {"istruzione": "[800[801[802", "descrizione": "Incrementa puntatori per scorrere timbrature"},
                {"istruzione": "803 = {802} S {801}", "descrizione": "Calcola durata intervallo timbrato"},
                {"istruzione": "803 < Z → K803 A 24", "descrizione": "Se durata negativa (mezzanotte) → aggiunge 24h"},
                {"istruzione": "804 = max durata", "descrizione": "Tiene traccia della durata massima"},
                {"istruzione": "Entrata 04-09 → MATT 06-14", "descrizione": "Turno mattino, 900=1"},
                {"istruzione": "Entrata 12-17 → POME 14-22", "descrizione": "Turno pomeriggio, 900=2"},
                {"istruzione": "Entrata 20-24 → NOTT 22-06", "descrizione": "Turno notte, 900=3"},
            ],
            calls=[{"type": "V", "target": 4}],
        )

        # --- 10: Determinazione turno ---
        patterns[10] = FormulaPattern(
            code=10, name="Determinazione del turno e cambio del previsionale", tipo=FORMULA_TIPO_DG,
            category="Turnisti",
            compact='1UZO58U"RIPO"(VF(802=85)802<84((K802A\'24\')(801=802S84)801<\'7\'((58="OPE")(111=\'8\')(141=\'12\')(112=\'13\')(142=\'17\')(100=\'2\')VF84<\'7\'E84>\'5\'((900=I)(58="MATT")(111=\'6\')(141=\'14\')(!112!142)(100=I)VF84<\'15\'E84>U\'13\'((900=\'2\')(58="POME")(111=\'14\')(141=\'22\')(!112!142)(100=I)VF(900=\'3\')(58="NOTT")(111=\'22\')(141=\'6\')(!112!142)(100=I)',
            description="Variante formula 5 eseguita durante la giornata. Usa orario calcolato (campo 85) invece di timbrature grezze.",
            fields_involved=[58, 84, 85, 100, 111, 112, 141, 142, 800, 801, 802, 900],
            steps=[
                {"istruzione": "1 U Z O 58='RIPO' ( VF", "descrizione": "Se nessuna ora prevista o riposo → esci"},
                {"istruzione": "802=85, durata", "descrizione": "Usa uscita calcolata per durata turno"},
                {"istruzione": "801<7 → OPE 2 int.", "descrizione": "Turno breve → operaio spezzato 08-12/13-17"},
                {"istruzione": "84 tra 5-7 → MATT", "descrizione": "Entrata 5-7 → turno mattino"},
                {"istruzione": "84 tra 13-15 → POME", "descrizione": "Entrata 13-15 → turno pomeriggio"},
                {"istruzione": "default → NOTT", "descrizione": "Altro orario → turno notte"},
            ],
        )

        # --- 100: Prima formula azzeramenti FG ---
        patterns[100] = FormulaPattern(
            code=100, name="PRIMA FORMULA – Azzeramenti", tipo=FORMULA_TIPO_FG,
            category="Standard",
            compact='(500="DURATA")(!561!562!563!564!565!566!567!568!569!570)R110',
            description="Prima operazione Fine Giornata. Imposta calcolo totali su DURATA e azzera causali automatiche 561-570.",
            fields_involved=[500, 561, 562, 563, 564, 565, 566, 567, 568, 569, 570],
            steps=[
                {"istruzione": "500='DURATA'", "descrizione": "Modalita calcolo totali = DURATA"},
                {"istruzione": "!561-!570", "descrizione": "Azzera campi causali automatiche"},
                {"istruzione": "R110", "descrizione": "Salta a formula 110"},
            ],
            calls=[{"type": "R", "target": 110}],
        )

        # --- 110: Riproporziono 3, 4, 5 ---
        patterns[110] = FormulaPattern(
            code=110, name="Riproporziono 3, 4 e 5 in base alle assenze", tipo=FORMULA_TIPO_FG,
            category="Standard",
            compact="(800=3A4)1UZ((!3!5)(4=800)VU(K800A608A609)800>1((4=800S1)(3=1S608S609)(!5)VU(3=800S608S609)(!4)(5=1S800)R120",
            description="Ridistribuisce ore ordinarie, straordinario e assenze per far quadrare i conti.",
            fields_involved=[1, 3, 4, 5, 608, 609, 800],
            steps=[
                {"istruzione": "800=3A4", "descrizione": "Totale lavorato = ordinario + straordinario"},
                {"istruzione": "1 U Z", "descrizione": "Se nessuna ora prevista → azzera, esci"},
                {"istruzione": "K800 A 608 A 609", "descrizione": "Aggiunge assenze retribuite e non"},
                {"istruzione": "800 > 1", "descrizione": "Se supera previsionale → straordinario netto"},
                {"istruzione": "default", "descrizione": "Altrimenti ordinario - assenze = assenza residua"},
            ],
            calls=[{"type": "R", "target": 120}],
        )

        # --- 120: Principale ---
        patterns[120] = FormulaPattern(
            code=120, name="Principale (smistatore FG)", tipo=FORMULA_TIPO_FG,
            category="Standard",
            compact='4UZ(VU1121U"N"((!4)VU55UIO50UI(R130R140R200',
            description="Smistatore centrale Fine Giornata. Instrada verso formule specifiche per straordinario.",
            fields_involved=[4, 50, 55, 1121],
            steps=[
                {"istruzione": "4 U Z ( VU", "descrizione": "Se nessuno straordinario → esci"},
                {"istruzione": "1121='N'", "descrizione": "Se straordinario non ammesso → azzera 4, esci"},
                {"istruzione": "55=I O 50=I → R130", "descrizione": "Festivo o domenica → Straord. Festivo"},
                {"istruzione": "R140", "descrizione": "Giorno ordinario → Straord. Diurno/Notturno"},
            ],
            calls=[{"type": "R", "target": 130}, {"type": "R", "target": 140}, {"type": "R", "target": 200}],
        )

        # --- 130: Straordinario Festivo ---
        patterns[130] = FormulaPattern(
            code=130, name="Straordinario Festivo e Festivo Notturno", tipo=FORMULA_TIPO_FG,
            category="Straordinario",
            compact='21UZ(V04(504="SFN")21>4((564=4)(K21S4)(!4)V05(564=21)(K4S21)(!21)(503="SF")(563=4)(!4)(K601A563A564)(K604A563A564)(K615A563)(K616A564)R200',
            description="Separa notturno da diurno nei festivi. Assegna causali SFN e SF.",
            fields_involved=[4, 21, 503, 504, 563, 564, 601, 604, 615, 616],
            steps=[
                {"istruzione": "21 U Z ( V04", "descrizione": "Se nessun notturno → salta a SF puro"},
                {"istruzione": '504="SFN"', "descrizione": "Assegna causale Straord. Festivo Notturno"},
                {"istruzione": "21 > 4", "descrizione": "Se notturno > straord. totale"},
                {"istruzione": '503="SF", 563=4', "descrizione": "Ore residue → SF (Straord. Festivo Diurno)"},
                {"istruzione": "K601 A 563 A 564", "descrizione": "Aggiorna progressivi"},
            ],
            calls=[{"type": "R", "target": 200}],
        )

        # --- 140: Straordinario Diurno/Notturno ---
        patterns[140] = FormulaPattern(
            code=140, name="Straordinario Diurno e Notturno", tipo=FORMULA_TIPO_FG,
            category="Straordinario",
            compact='21UZO900U\'3\'(V04(502="SN")21>4((562=4)(K21S4)(!4)V05(562=21)(K4S21)(!21)(501="S")(561=4)(!4)(K601A561A562)(K604A561A562)(K611A561)(K614A562)R200',
            description="Separa notturno da diurno in giorni ordinari. Assegna causali SN e S.",
            fields_involved=[4, 21, 501, 502, 561, 562, 601, 604, 611, 614, 900],
            steps=[
                {"istruzione": "21 U Z O 900='3'", "descrizione": "Se nessun notturno o turno notte → salta"},
                {"istruzione": "502='SN'", "descrizione": "Assegna causale Straord. Notturno"},
                {"istruzione": "Split 21/4", "descrizione": "Divide notturno/diurno"},
                {"istruzione": "501='S', 561=4", "descrizione": "Ore diurne → S (Straordinario Diurno)"},
                {"istruzione": "K611 A 561, K614 A 562", "descrizione": "Aggiorna progressivi straordinario"},
            ],
            calls=[{"type": "R", "target": 200}],
        )

        # --- 200: Formula Finale ---
        patterns[200] = FormulaPattern(
            code=200, name="Formula Finale", tipo=FORMULA_TIPO_FG,
            category="Standard",
            compact="(K601A3)(K602A3)900>Z(P210",
            description="Accumula ore ordinarie nei progressivi e chiama maggiorazioni turnisti.",
            fields_involved=[3, 601, 602, 900],
            steps=[
                {"istruzione": "K601 A 3, K602 A 3", "descrizione": "Accumula ore ordinarie nei progressivi"},
                {"istruzione": "900 > Z ( P210", "descrizione": "Se turno attivo → chiama maggiorazioni (210)"},
            ],
            calls=[{"type": "P", "target": 210}],
        )

        # --- 210: Maggiorazioni Turnisti ---
        patterns[210] = FormulaPattern(
            code=210, name="Maggiorazioni per Turnisti", tipo=FORMULA_TIPO_FG,
            category="Turnisti",
            compact='21>Z((505="N")(565=21)(890=3S21)890>Z((506="T")(566=890)(K626A565)(K625A566)',
            description="Calcola maggiorazioni turnisti: notturno (N) e diurno (T). Aggiorna K626 e K625.",
            fields_involved=[3, 21, 505, 506, 565, 566, 625, 626, 890],
            steps=[
                {"istruzione": "21 > Z", "descrizione": "Se ore notturne → causale N, slot 565=21"},
                {"istruzione": "890 = 3 S 21", "descrizione": "Ore diurne = ordinarie - notturne"},
                {"istruzione": "890 > Z", "descrizione": "Se ore diurne positive → causale T, slot 566=890"},
                {"istruzione": "K626 A 565, K625 A 566", "descrizione": "Accumula progressivi maggiorazioni"},
            ],
        )

        # --- 1000: Dirigenti ---
        patterns[1000] = FormulaPattern(
            code=1000, name="Dirigenti (non timbratori)", tipo=FORMULA_TIPO_IG,
            category="Dirigenti",
            compact="390#Z(VF(251=111)(271=141)112>Z((252=112)(272=142)113>Z((253=113)(273=143)114>Z((254=114)(274=144)",
            description="Imposta timbrature calcolate uguali all'orario previsionale per dirigenti (non timbratori).",
            fields_involved=[111, 112, 113, 114, 141, 142, 143, 144, 251, 252, 253, 254, 271, 272, 273, 274, 390],
        )

        # --- 1010: Quadri ---
        patterns[1010] = FormulaPattern(
            code=1010, name="Quadri", tipo=FORMULA_TIPO_IG,
            category="Dirigenti/Quadri",
            compact="390#Z(VF201UZE221UZ(VF(251=111)(271=141)112>Z((252=112)(272=142)113>Z((253=113)(273=143)114>Z((254=114)(274=144)",
            description="Come 1000 ma con controllo timbrature effettive: se ha gia timbrato, non sovrascrive.",
            fields_involved=[111, 112, 113, 114, 141, 142, 143, 144, 201, 221, 251, 252, 253, 254, 271, 272, 273, 274, 390],
        )

        # --- 1020: Timbratura singola ---
        patterns[1020] = FormulaPattern(
            code=1020, name="Dipendenti che timbrano una volta per intervallo", tipo=FORMULA_TIPO_IG,
            category="Speciale",
            compact="390#Z(VF100UZ((!251!271!252!272)VF(!800!801)(!802!803!804)(802='200')(803='220')([802[803[804){802}UZE{803}UZ(V12{802}#ZE{802}<U141((800=141S111){802}#ZE{802}>141((801=142S112){803}#ZE{803}<U141((800=141S111){803}#ZE{803}>141((801=142S112)804#200(V05800>Z((251=111)(271=141)(!252!272)801>Z((252=112)(272=142)800UZE801#Z((251=112)(271=142)(!252!272)",
            description="Gestisce dipendenti con singola timbratura per intervallo. Classifica come entrata o uscita in base a orario previsionale.",
            fields_involved=[100, 111, 112, 141, 142, 200, 220, 251, 252, 271, 272, 390, 800, 801, 802, 803, 804],
        )

        # --- 1100: FG Dirigenti ---
        patterns[1100] = FormulaPattern(
            code=1100, name="PRIMA FORMULA per Dirigenti e Quadri", tipo=FORMULA_TIPO_FG,
            category="Dirigenti",
            compact="(800=608A609)1UZO800UZ(VU800>U1((!251!271!252!272!3)VF(801=142S112)(K3S800)800<801((K272S800)VU800U801((!252!272)VU800>801((271=251A3)(!252!272)VU(K601A3)(K602A3)",
            description="Prima formula FG per dirigenti/quadri. Gestisce assenze che superano il previsionale.",
            fields_involved=[1, 3, 112, 142, 251, 252, 271, 272, 601, 602, 608, 609, 800, 801],
        )

        # --- 1120: FG Timbratura singola ---
        patterns[1120] = FormulaPattern(
            code=1120, name="PRIMA FORMULA per dip. che timbrano una volta", tipo=FORMULA_TIPO_FG,
            category="Speciale",
            compact="(800=800)(801=801)(805=608A609)(806=1S3)1UZO805UZ(VF805>U1((!251!271!252!272!3!4!5)VF(807=805S806)800>ZE801>ZE805>ZE801>805((K272S805)VU800>ZE801UZE805>ZE800<U805((K271S807)VU800UZE801>ZE805>ZE801<U805((K251A807)VU(3=1S805)(5=1S3S805)",
            description="Come 1100 per timbratura singola. Gestisce assenze parziali tra mattino e pomeriggio.",
            fields_involved=[1, 3, 4, 5, 251, 252, 271, 272, 601, 602, 608, 609, 800, 801, 805, 806, 807],
        )

        # --- 2000: Dip. a chiamata ---
        patterns[2000] = FormulaPattern(
            code=2000, name="PRIMA FORMULA per dipendenti a chiamata", tipo=FORMULA_TIPO_FG,
            category="A Chiamata",
            compact='300>305(VF200UZ((!111!112!113!141!142!143)(58="RIPO")VU(111=251)(141=271)(112=252)(142=272)(113=253)(143=273)(114=254)(144=274)58U"CHIA"((58="CHI")VU(58="CHIA")(K3A4)(!4!5)(100=250)(1=3)(K601A3)(K602A3)',
            description="Gestisce dipendenti a chiamata (CHIA): se non ha timbrato -> riposo, altrimenti copia calcolate in previsionali.",
            fields_involved=[1, 3, 4, 5, 58, 100, 111, 112, 113, 114, 141, 142, 143, 144, 200, 250, 251, 252, 253, 254, 271, 272, 273, 274, 300, 305, 601, 602],
        )

        # --- 2050: Conad arrotondamento entrate ---
        patterns[2050] = FormulaPattern(
            code=2050, name="Conad Gubbio – Arrotondamento entrate", tipo=FORMULA_TIPO_IG,
            category="Personalizzato",
            compact="300>U'20230601'(R2060201UZ(VU(71=201)(70='3')(251=72)73<U'30.00'E73>Z((K251A'0.30')V0673<U'59.00'E73>Z((K251A'1.00')R2051",
            description="Arrotonda timbratura entrata effettiva alla mezz'ora o ora successiva. Dal 01/06/2023 delega a 2060.",
            fields_involved=[70, 71, 72, 73, 201, 251, 300],
            calls=[{"type": "R", "target": 2060}, {"type": "R", "target": 2051}],
        )

        # --- 2051: Conad arrotondamento uscite ---
        patterns[2051] = FormulaPattern(
            code=2051, name="Conad Gubbio – Arrotondamento uscite", tipo=FORMULA_TIPO_IG,
            category="Personalizzato",
            compact="200U'2'E222>Z(V02V05(71=222)(70='3')(272=72)73>U'30.00'E73>Z((K272A'0.30')V05200U'1'E221>Z(V07V10(71=221)(70='3')(271=72)73>U'30.00'E73>Z((K271A'0.30')V10",
            description="Arrotonda uscite effettive alla mezz'ora successiva, 2° e 1° intervallo.",
            fields_involved=[70, 71, 72, 73, 200, 221, 222, 271, 272],
        )

        # --- 2060: Cap uscite 20:05 ---
        patterns[2060] = FormulaPattern(
            code=2060, name="Cap uscite 20:05 (dal 01/06/2023)", tipo=FORMULA_TIPO_IG,
            category="Personalizzato",
            compact="VF221>'20.05'((271='20.05')222>'20.05'((272='20.05')223>'20.05'((273='20.05')224>'20.05'((274='20.05')225>'20.05'((275='20.05')226>'20.05'((276='20.05')227>'20.05'((277='20.05')",
            description="Vincolo fisso: nessuna uscita calcolata oltre 20:05 per tutti i 7 intervalli.",
            fields_involved=[221, 222, 223, 224, 225, 226, 227, 271, 272, 273, 274, 275, 276, 277],
        )

        # --- 2100: GUGEST 1 (A) ---
        patterns[2100] = FormulaPattern(
            compact="900>Z((!1801)R2101300U301((!791)(!792)(!890)(!891)(!892)(!899)(!900)50U'2'((!770)(!771)(!772)(!773)(!774)(!782)(!887)(!889)300U301((!770)(K770+I)55UI(P2109(K771A3A4)(K772A608A609)(773=771A772)(887='40.00'S772)1391>ZE1391<'40.00'((889='40.00'S772)(887=1391S772)887<Z((!887)889<Z((!889)300U302O300U311O50UI(V13VF(900='1')(K770-I)(1801=-770)770<UZ((1801='500')",
            code=2100, name="GUGEST 1 – Calcolo settimanale (variante A)", tipo=FORMULA_TIPO_FG,
            category="Gestione Personalizzata",
            description="Primo giro settimanale GUGEST: inizializza contatori, cumula ore settimanali, calcola soglia straordinario.",
            fields_involved=[50, 300, 301, 887, 889, 900, 1391, 1801, 771, 772, 770],
            calls=[{"type": "P", "target": 2109}, {"type": "chain", "target": 2101}],
        )

        # --- 2101: GUGEST 2 (A) ---
        patterns[2101] = FormulaPattern(
            compact="51UIE52UI((!783)50U'2'((!771)(!772)(!773)(!774)(!782)(!918)(!919)(71=\"SECONDO GIRO\")(72=300)?(70='99')(K3A4)(!4)(!5)55UI(P2109(K781A1)(K782A608A609)(K772A608A609)?(K771A3A4)(773=771A772)251>ZE271>Z((811=251)(812=271)P2122252>ZE272>Z((811=252)(812=272)P2122253>ZE273>Z((811=253)(812=273)P2122254>ZE274>Z((811=254)(812=274)P2122255>ZE275>Z((811=255)(812=275)P2122256>ZE276>Z((811=256)(812=276)P2122257>ZE277>Z((811=257)(812=277)P2122P2123P2124P2125(3=902A903A904A905A908)(4=906A907A909A910A914A915)(K771A3A4)(773=771A772)(K774A907)(K783A4)(K783A4S906)(K784A906)P2114P2115(800=3A4A608A609S1)(801=887)782<801E50UI((5=801S782)300U311E50#IE785<781((5=781S785)(K601A3A4)(K602A3)(K626A902A903)(K627A904A908)(K612A906)(K611A907A915)(K615A914)(K614A909)(K616A910)(K610A612A611A615A614A616)(K604A904A908)(K603A902)(K605A903)P2130(!901)(!902)(!903)(!904)(!905)(!906)(!907)(!908)(!909)(!910)(!911)(!912)(!913)(!914)(!915)(!916)(!917)(!918)(!919)(!920)(!922)(!928)(!929)50UIO300U302O300U311((K900-I)",
            code=2101, name="GUGEST 2 – Calcolo giornaliero (variante A)", tipo=FORMULA_TIPO_FG,
            category="Gestione Personalizzata",
            description="Secondo passaggio GUGEST: calcola ore per tipo per ogni intervallo, arrotonda, esplode causali.",
            fields_involved=[3, 4, 251, 252, 253, 254, 255, 256, 257, 271, 272, 273, 274, 275, 276, 277, 901, 902, 903, 904, 905, 906, 907, 908, 909, 910, 914, 915, 929],
            calls=[
                {"type": "P", "target": 2122},
                {"type": "P", "target": 2123},
                {"type": "P", "target": 2124},
                {"type": "P", "target": 2125},
                {"type": "P", "target": 2114},
                {"type": "P", "target": 2115},
                {"type": "P", "target": 2130},
            ],
        )

        # --- 2105: GUGEST 1 (B) ---
        patterns[2105] = FormulaPattern(
            compact="900>Z((!1801)R2106300U301((!791)(!792)(!890)(!891)(!892)(!899)(!900)50U'2'((!770)(!771)(!772)(!773)(!774)(!782)(!887)(!889)300U301((!770)(K770+I)55UI(P2109251>ZE271>Z((811=251)(812=271)P2122252>ZE272>Z((811=252)(812=272)P2122253>ZE273>Z((811=253)(812=273)P2122254>ZE274>Z((811=254)(812=274)P2122255>ZE275>Z((811=255)(812=275)P2122256>ZE276>Z((811=256)(812=276)P2122257>ZE277>Z((811=257)(812=277)P2122P2123P2124P2125(3=902A903A904A905A908)(4=906A907A909A910A914A915)(K771A3A4)(K772A608A609)(773=771A772)(887='40.00'S772)(71=\"PRIMO GIRO\")(72=300)?(70='99')1391>ZE1391<'40.00'((889='40.00'S772)(887=1391S772)887<Z((!887)889<Z((!889)300U302O300U311O50UI(V24VF(900='1')(K770-I)(1801=-770)(71=\"CONTO\")(72=300)(73=\"ORE TOT\")(74=887)?(70='99')770<UZ((1801='500')",
            code=2105, name="GUGEST 1 – Calcolo settimanale (variante B)", tipo=FORMULA_TIPO_FG,
            category="Gestione Personalizzata",
            description="Variante B del primo giro GUGEST. Come 2100 ma con loop intervalli nel 1 giro e logging Campo70=99.",
            calls=[{"type": "P", "target": 2109}, {"type": "P", "target": 2122}, {"type": "chain", "target": 2106}],
        )

        # --- 2106: GUGEST 2 (B) ---
        patterns[2106] = FormulaPattern(
            compact="51UIE52UI((!783)50U'2'((!771)(!772)(!773)(!774)(!782)(!918)(!919)(71=\"SECONDO GIRO\")(72=300)?(70='99')(K3A4)(!4)(!5)55UI(P2109(K781A1)(K782A608A609)(K772A608A609)?(K771A3A4)(773=771A772)251>ZE271>Z((811=251)(812=271)P2122252>ZE272>Z((811=252)(812=272)P2122253>ZE273>Z((811=253)(812=273)P2122254>ZE274>Z((811=254)(812=274)P2122255>ZE275>Z((811=255)(812=275)P2122256>ZE276>Z((811=256)(812=276)P2122257>ZE277>Z((811=257)(812=277)P2122P2123P2124P2125(3=902A903A904A905A908)(4=906A907A909A910A914A915)(K771A3A4)(773=771A772)(K774A907)(K783A4)(K783A4S906)(K784A906)P2114P2115(800=3A4A608A609S1)(801=887)782<801E50UI((5=801S782)300U311E50#IE785<781((5=781S785)(K601A3A4)(K602A3)(K626A902A903)(K627A904A908)(K612A906)(K611A907A915)(K615A914)(K614A909)(K616A910)(K610A612A611A615A614A616)(K604A904A908)(K603A902)(K605A903)P2130(!901)(!902)(!903)(!904)(!905)(!906)(!907)(!908)(!909)(!910)(!911)(!912)(!913)(!914)(!915)(!916)(!917)(!918)(!919)(!920)(!922)(!928)(!929)50UIO300U302O300U311((K900-I)",
            code=2106, name="GUGEST 2 – Calcolo giornaliero (variante B)", tipo=FORMULA_TIPO_FG,
            category="Gestione Personalizzata",
            description="Variante B del secondo giro. Identica a 2101.",
            calls=[
                {"type": "P", "target": 2122},
                {"type": "P", "target": 2123},
                {"type": "P", "target": 2124},
                {"type": "P", "target": 2125},
                {"type": "P", "target": 2114},
                {"type": "P", "target": 2115},
                {"type": "P", "target": 2130},
            ],
        )

        # --- 2107: Conteggio ore con arrotondamento ---
        patterns[2107] = FormulaPattern(
            compact="(801=3A4)801UZ(V08(71=801)(70='3')(801=72)(!800)73<'15.00'(V0873<'30.00'((K800A'0.15')V0773<'45.00'((K800A'0.35')V0773<U'59.00'((K800A'0.45')V07(K801A800)(K782A801)(810)(905=801)(K782A)889>ZE782>887E782<U889((K906A810)VU782>887((K907A810)VU(K905A810)VU782<U887E811<U'06.00'((K903A810)VU782<U887E811>'22.00'E811<U'30.00'((K903A810)VU782>887E811<U'06.00'((K910A810)VU782>887E811>'22.00'E811<U'30.00'((K910A810)VU889>ZE782>887E782<U889((K906A810)VU782>887((K914A810)VU(K904A810)VU782<U887E811<U'06.00'((K903A810)VU782<U887E811>'22.00'E811<U'30.00'((K903A810)VU782>887E811<U'06.00'((K910A810)VU782>887E811>'22.00'E811<U'30.00'((K910A810)VU889>ZE782>887E782<U889((K906A810)VU782>887((K914A810)VU(K908A810)811<812(V03",
            code=2107, name="Conteggio ore con arrotondamento minuti", tipo=FORMULA_TIPO_SUB,
            category="Calcolo",
            description="Calcola durata intervallo, arrotonda ai quarti d'ora, classifica per tipo in base a ore settimanali.",
            fields_involved=[70, 71, 72, 73, 74, 78, 811, 812, 782, 887, 889, 902, 904, 905, 907, 908, 909, 910, 914, 915],
        )

        # --- 2109: Festività automatiche (A) ---
        patterns[2109] = FormulaPattern(
            compact="(919=I)(!918)(800=1)684>ZE684U1((800=Z)50U'7'E1UZ((!919)VF1>ZE3>ZE684UZ((919='2')(K629+I)VF50UIE1UZE684UZ((919='2')(K629+I)VF55UIE1UZE684UZ((919='2')(K629+I)VF800UZ(VF1051U51E1052U52((919='3')(918=800)(K631A800)(K608A800)VF(K918A800)(K630A800)(K608A800)",
            code=2109, name="Gestione festività automatiche (variante A)", tipo=FORMULA_TIPO_SUB,
            category="Festività",
            description="Riconosce e gestisce giorni festivi. Tipi: 1=normale, 2=non goduta, 3=patrono. Aggiorna K918, K630, K608, K629.",
            fields_involved=[608, 629, 630, 631, 918, 919],
        )

        # --- 2114: Ritocco SA/SB ---
        patterns[2114] = FormulaPattern(
            code=2114, name="Ritocco SA/SB (cap 8 ore straordinario)", tipo=FORMULA_TIPO_SUB,
            category="Straordinario",
            compact="774<U'08.00'(VF(800=774S907)774>'8.00'E800<'08.00'((915=907S'08.00')(K907S915)(915=907)(!907)",
            description="Verifica che straordinario diurno (907) non superi soglia massima. Scorpora eccedenza in 915 (SB).",
            fields_involved=[774, 800, 907, 915],
        )

        # --- 2115: Esplode causali automatiche (A) ---
        patterns[2115] = FormulaPattern(
            compact="918>ZE919U'1'((501=\"F\")(561=918)919U'2'((501=\"FNG\")(561=918)918>ZE919U'3'((501=\"FP\")(561=918)902>Z((502=\"N\")(562=902)903>Z((503=\"NF\")(563=903)904>ZO908>Z((504=\"LFS\")(564=904A908)906>Z((505=\"SP\")(565=906)907>Z((506=\"SA\")(566=907)914>Z((507=\"SF\")(567=914)909>Z((508=\"SN\")(568=909)910>Z((509=\"SNF\")(569=910)915>Z((510=\"SB\")(570=915)",
            code=2115, name="Esplode causali automatiche (variante A)", tipo=FORMULA_TIPO_SUB,
            category="Causali",
            description="Assegna causali automatiche 501-510 in base a ore calcolate 902-915.",
            fields_involved=[501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 902, 903, 904, 905, 906, 907, 908, 909, 910, 914, 915, 918, 919],
        )

        # --- 2122: Calcolo ore per intervallo ---
        patterns[2122] = FormulaPattern(
            compact="3UZ(VF(810='00.01')811>812((812=812A'24.00')(K811A810)(K782A810)(K785A810S810)50UI(V2255UI(V14782<U887E811<U'06.00'((K902A810)VU782<U887E811>'22.00'E811<U'30.00'((K902A810)VU782>887E811<U'06.00'((K909A810)VU782>887E811>'22.00'E811<U'30.00'((K909A810)VU889>ZE782>887E782<U889((K906A810)VU782>887((K907A810)VU(K905A810)VU782<U887E811<U'06.00'((K903A810)VU782<U887E811>'22.00'E811<U'30.00'((K903A810)VU782>887E811<U'06.00'((K910A810)VU782>887E811>'22.00'E811<U'30.00'((K910A810)VU889>ZE782>887E782<U889((K906A810)VU782>887((K914A810)VU(K904A810)VU782<U887E811<U'06.00'((K903A810)VU782<U887E811>'22.00'E811<U'30.00'((K903A810)VU782>887E811<U'06.00'((K910A810)VU782>887E811>'22.00'E811<U'30.00'((K910A810)VU889>ZE782>887E782<U889((K906A810)VU782>887((K914A810)VU(K908A810)811<812(V03",
            code=2122, name="Calcolo ore per singolo intervallo", tipo=FORMULA_TIPO_SUB,
            category="Calcolo",
            description="Calcola durata singolo intervallo. Scorre minuto per minuto e classifica in bucket 902-910.",
            fields_involved=[70, 71, 72, 73, 78, 810, 811, 812, 902, 903, 904, 905, 906, 907, 908, 909, 910],
        )

        # --- 2123: Arrotondamento quarti ordinario ---
        patterns[2123] = FormulaPattern(
            code=2123, name="Arrotondamento minuti ore ordinarie/festive", tipo=FORMULA_TIPO_SUB,
            category="Arrotondamento",
            compact="902UZ(V08(71=902)(70='3')(902=72)(!800)73<'15.00'(V0873<'30.00'((K800A'0.15')V0773<'45.00'((K800A'0.35')V0773<U'59.00'((K800A'0.45')V07(K902A800)903UZ(V16(71=903)(70='3')(903=72)(!800)73<'15.00'(V1673<'30.00'((K800A'0.15')V1573<'45.00'((K800A'0.35')V1573<U'59.00'((K800A'0.45')V15(K903A800)904UZ(V24(71=904)(70='3')(904=72)(!800)73<'15.00'(V2473<'30.00'((K800A'0.15')V2573<'45.00'((K800A'0.35')V2573<U'59.00'((K800A'0.45')V25(K904A800)905UZ(V32(71=905)(70='3')(905=72)(!800)73<'15.00'(V3273<'30.00'((K800A'0.15')V3173<'45.00'((K800A'0.35')V3173<U'59.00'((K800A'0.45')V31(K905A800)908UZ(V40(71=908)(70='3')(908=72)(!800)73<'15.00'(V4073<'30.00'((K800A'0.15')V3973<'45.00'((K800A'0.35')V3973<U'59.00'((K800A'0.45')V39(K908A800)VF",
            description="Arrotonda ai quarti d'ora per ore ordinarie/festive (902-905, 908). <15 scarta, <30 +0.15, <45 +0.35, <59 +0.45.",
            fields_involved=[70, 71, 72, 73, 800, 902, 903, 904, 905, 908],
            steps=[
                {"istruzione": "902 U Z ( V08", "descrizione": "Se campo zero → salta tutto"},
                {"istruzione": "!800, 71=902, 70=3", "descrizione": "Azzeramento, separa ore/minuti"},
                {"istruzione": "73 < 15 → V08", "descrizione": "Meno di 15 min → scarta"},
                {"istruzione": "73 < 30 → +0.15", "descrizione": "15-29 min → aggiungi 0.15"},
                {"istruzione": "73 < 45 → +0.35", "descrizione": "30-44 min → aggiungi 0.35"},
                {"istruzione": "73 <= 59 → +0.45", "descrizione": "45-59 min → aggiungi 0.45"},
                {"istruzione": "K902 A 800", "descrizione": "Accumula arrotondamento"},
            ],
        )

        # --- 2124: Arrotondamento quarti straordinario ---
        patterns[2124] = FormulaPattern(
            compact="906UZ(V08(71=906)(70='3')(906=72)(!800)73<'15.00'(V0873<'30.00'((K800A'0.15')V0773<'45.00'((K800A'0.35')V0773<U'59.00'((K800A'0.45')V07(K906A800)907UZ(V16(71=907)(70='3')(907=72)(!800)73<'15.00'(V1673<'30.00'((K800A'0.15')V1573<'45.00'((K800A'0.35')V1573<U'59.00'((K800A'0.45')V15(K907A800)909UZ(V24(71=909)(70='3')(909=72)(!800)73<'15.00'(V2473<'30.00'((K800A'0.15')V2573<'45.00'((K800A'0.35')V2573<U'59.00'((K800A'0.45')V25(K909A800)910UZ(V32(71=910)(70='3')(910=72)(!800)73<'15.00'(V3273<'30.00'((K800A'0.15')V3173<'45.00'((K800A'0.35')V3173<U'59.00'((K800A'0.45')V31(K910A800)914UZ(V40(71=914)(70='3')(914=72)(!800)73<'15.00'(V4073<'30.00'((K800A'0.15')V3973<'45.00'((K800A'0.35')V3973<U'59.00'((K800A'0.45')V39(K914A800)VF",
            code=2124, name="Arrotondamento minuti ore straordinarie", tipo=FORMULA_TIPO_SUB,
            category="Arrotondamento",
            description="Come 2123 ma applicato a ore straordinarie (906, 907, 909, 910, 914).",
            fields_involved=[70, 71, 72, 73, 800, 906, 907, 909, 910, 914],
        )

        # --- 2125: Placeholder ---
        patterns[2125] = FormulaPattern(
            code=2125, name="GUGEST 22 – placeholder vuoto", tipo=FORMULA_TIPO_SUB,
            category="—",
            description="Placeholder riservato. Nessun contenuto.",
        )

        # --- 2130: Warning ore carenti ---
        patterns[2130] = FormulaPattern(
            code=2130, name="Warning ore carenti / soglia 250h annuali (A)", tipo=FORMULA_TIPO_SUB,
            category="Alert",
            compact='5>Z(V02V06(71="ATTENZIONE SETTIMANA CON ORE CARENTI")(72="Cod.Azienda e Cod.dipendente")(73=1000)(74=1100)(75="Giorno e Ore carenti")(76=300)(77=5)(!78)(70=\'99\')783>U\'220.00\'E783<U\'250.00\'(V08V12(71="ATTENZIONE Potenziale avvicinamento alle 250 ore annuali")(72="Cod.Azienda e Cod.dipendente")(73=1000)(74=1100)(75="Ore raggiunte annuali")(76=783)(77="al giorno")(78=300)(70=\'99\')',
            description="Genera avvisi via Campo70=99: settimana ore carenti (5>0) e avvicinamento soglia 250h (783 tra 220 e 250).",
            fields_involved=[5, 70, 71, 72, 73, 74, 75, 76, 77, 78, 783, 1000, 1100, 300],
        )

        # --- 2140: Arrotondamento base ---
        patterns[2140] = FormulaPattern(
            code=2140, name="Arrotondamento base", tipo=FORMULA_TIPO_SUB,
            category="Arrotondamento",
            compact="(71=3A4)",
            description="Minimalista: somma ordinario + straordinario in campo 71.",
            fields_involved=[3, 4, 71],
        )

        # --- 3000: FG 1 ---
        patterns[3000] = FormulaPattern(
            compact="900>Z((!1801)R3001300U301((!770)50U'2'((!772)(!788)(!790)(!774)(!775)55UI(P3009(K770+I)(K772A608A609)(K775A3A4A608A609)(K3A4)(!4)(!5)(!918)(!919)300<'20230601'(P3002300>U'20230601'(P3003P3017(887='40.00'S772)(71=\"PRIMO GIRO\")(72=300)?(70='99')1391>ZE1391<'40.00'((889='40.00'S1391)(887=1391S772)887<Z((!887)889<Z((!889)300U302O300U311O50UI(V15VF(900='1')(K770-I)(1801=-770)(71=\"CONTO\")(72=300)(73=\"ORE TOT\")(74=887)?(70='99')770<UZ((1801='500')",
            code=3000, name="FG 1 – Formula gestione principale", tipo=FORMULA_TIPO_FG,
            category="Gestione Personalizzata",
            description="Versione aggiornata GUGEST. Gestisce 1 giro settimanale con split al 01/06/2023.",
            calls=[
                {"type": "P", "target": 3009},
                {"type": "P", "target": 3002},
                {"type": "P", "target": 3003},
                {"type": "P", "target": 3017},
                {"type": "chain", "target": 3001},
            ],
        )

        # --- 3001: FG NEW ---
        patterns[3001] = FormulaPattern(
            compact="50U'2'((!788)(!790)(!774)(!775)(!776)51UIE52UI((!783)55UI(P3009(K3A4)(!4)(!5)(K775A3A4A608A609)300<'20230601'(P3002300>U'20230601'(P3003P3017(K788A608A609S608S609A3)P3005P3014P3004P3015(K776A3A902A903A608A609)50UIE776<'40.00'E1391UZ((5='40.00'S776)50UIE776<1391E1391>Z((5=1391S776)(K602A3)(K626A902A903)(K627A904A908)(K612A906)(K611A907A915)(K615A914)(K614A909)(K616A910)(K604A612A611A615A614A616)(K783A610)",
            code=3001, name="FG NEW – Formula gestione aggiornata", tipo=FORMULA_TIPO_FG,
            category="Gestione Personalizzata",
            description="Secondo giro FG aggiornato. Calcolo straordinario P3005, esplode causali P3015.",
            calls=[
                {"type": "P", "target": 3009},
                {"type": "P", "target": 2122},
                {"type": "P", "target": 2123},
                {"type": "P", "target": 2124},
                {"type": "P", "target": 3005},
                {"type": "P", "target": 3014},
                {"type": "P", "target": 3015},
                {"type": "P", "target": 3030},
            ],
        )

        # --- 3002: Arrotondamento ante 01/06/2023 ---
        patterns[3002] = FormulaPattern(
            compact="(800='40.00')1391>Z((800=1391)775>800(V11(71=3)(!800)(70='3')(3=72)73<'15.00'(V1073<'30.00'((K800A'0.15')V0973<'45.00'((K800A'0.30')V0973<U'59.00'((K800A'0.45')V09(K3A800)VF(71=3)(!800)(70='3')(3=72)73<'30.00'(VF73<U'59.00'((K3A'0.30')",
            code=3002, name="FG 2 – Arrotondamento ore (ante 01/06/2023)", tipo=FORMULA_TIPO_SUB,
            category="Arrotondamento",
            description="Arrotondamento ore ordinarie (3) al quarto d'ora. Logica ante 01/06/2023 con due livelli.",
            fields_involved=[3, 70, 71, 72, 73, 74, 78, 775, 800],
        )

        # --- 3003: Arrotondamento dal 01/06/2023 ---
        patterns[3003] = FormulaPattern(
            code=3003, name="FG 2 NEW – Arrotondamento ore (dal 01/06/2023)", tipo=FORMULA_TIPO_SUB,
            category="Arrotondamento",
            compact="(71=3)(!800)(70='3')(3=72)73<'30.00'(VF73<U'59.00'((K800A'0.30')VU(K3A800)",
            description="Arrotondamento semplificato: arrotonda ore ordinarie (3) alla mezz'ora.",
            fields_involved=[3, 70, 71, 72, 73, 800],
            steps=[
                {"istruzione": "71=3, !800, 70=3", "descrizione": "Separa ore/minuti del campo 3"},
                {"istruzione": "3=72", "descrizione": "Reimposta 3 con solo ore intere"},
                {"istruzione": "73 < 30 → VF", "descrizione": "Meno di 30 min → esci"},
                {"istruzione": "73 <= 59 → +0.30", "descrizione": "30-59 min → aggiungi 30 min"},
            ],
        )

        # --- 3004: Straordinario Festivo (sub) ---
        patterns[3004] = FormulaPattern(
            code=3004, name="Straordinario Festivo", tipo=FORMULA_TIPO_SUB,
            category="Straordinario",
            compact="50UIO55UI(V02VF907>Z((914=907)(!907)915>Z((K914A915)(!915)3>Z((904=3)",
            description="Riclassifica straordinario diurno (907) in festivo (914) nei giorni festivi/domenicali.",
            fields_involved=[3, 50, 55, 904, 907, 914, 915],
        )

        # --- 3005: Calcolo straordinario settimanale ---
        patterns[3005] = FormulaPattern(
            compact="(810=788)(811=788S3)(71=300)(72=\"limite sett\")(73=887)(74=\"tot sett\")(75=788)?(70='99')810<U887((3=3)VF810>887E811<887((4=788S887)(K3S4)V04(4=3)(K3S4)3<Z((!3)820>ZE821>Z((907=821)V08820UZ(V08(K907A4)889>Z(V10VU(906=907)(!907)(K790A906)(812=790)(813=790S906)812<U889E813<U889((906=906)VU812>889E813<889((907=790S889)(K906S907)VU(907=906)(!906)(K774A907)",
            code=3005, name="Calcolo straordinario settimanale", tipo=FORMULA_TIPO_SUB,
            category="Straordinario",
            description="Determina se ore giorno generano straordinario confrontando totale sett. con soglia. Gestisce supplementare.",
            fields_involved=[788, 810, 811, 887, 889, 906, 907],
        )

        # --- 3009: Festività automatiche (B) ---
        patterns[3009] = FormulaPattern(
            compact="(919=I)(!918)(800=1)684>ZE684U1((800=Z)1>ZE3>ZE684UZ((800=Z)50U'7'E1UZ((!919)VF1>ZE3>ZE684UZ((919='4')(K918A800)(K605A800)(K608A800)VF((919='2')(K629+I)VF50UIE1UZE684UZ((919='2')(K629+I)VF55UIE1UZE684UZ((919='2')(K629+I)VF800UZ(VF1051U51E1052U52((919='3')(918=800)(K605A800)(K608A800)VF(K918A800)(K605A800)(K608A800)774<U'08.00'(VF(800=774S907)774>'8.00'E800<'08.00'((915=907)(907='08.00'S800)(K915S907)VF(915=907)(!907)",
            code=3009, name="Gestione festività automatiche (variante B)", tipo=FORMULA_TIPO_SUB,
            category="Festività",
            description="Come 2109 con tipo 919=4 (FX, festività in stipendio). Usa K605 invece di K630.",
            fields_involved=[605, 608, 629, 631, 918, 919],
        )

        # --- 3014: Ritocco SA/SB (B) ---
        patterns[3014] = FormulaPattern(
            compact="774<U'08.00'(VF(800=774S907)774>'8.00'E800<'08.00'((915=907)(907='08.00'S800)(K915S907)VF(915=907)(!907)",
            code=3014, name="Ritocco SA/SB (variante B)", tipo=FORMULA_TIPO_SUB,
            category="Straordinario",
            description="Variante B del ritocco SA/SB con logica diversa nello scorporo.",
            fields_involved=[774, 800, 907, 915],
        )

        # --- 3015: Esplode causali (B) ---
        patterns[3015] = FormulaPattern(
            compact="918>ZE919U'1'((501=\"F\")(561=918)919U'2'((501=\"FNG\")(561=918)918>ZE919U'3'((501=\"FP\")(561=918)918>ZE919U'4'((501=\"FX\")(561=918)902>Z((502=\"N\")(562=902)903>Z((503=\"NF\")(563=903)904>ZO908>Z((504=\"LFS\")(564=904A908)906>Z((505=\"SP\")(565=906)907>Z((506=\"SA\")(566=907)914>Z((507=\"SF\")(567=914)909>Z((508=\"SN\")(568=909)910>Z((509=\"SNF\")(569=910)915>Z((510=\"SB\")(570=915)",
            code=3015, name="Esplode causali automatiche (variante B)", tipo=FORMULA_TIPO_SUB,
            category="Causali",
            description="Come 2115 con tipo 919=4 → 501='FX' (Festività in stipendio).",
            fields_involved=[501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 902, 903, 904, 905, 906, 907, 908, 909, 910, 914, 915, 918, 919],
        )

        # --- 3017: Gestione AUTS ---
        patterns[3017] = FormulaPattern(
            code=3017, name="Gestione autorizzazioni straordinario (AUTS)", tipo=FORMULA_TIPO_SUB,
            category="Straordinario",
            compact='(!820)(!821)401U"AUTS"((820=\'1\')(821=431)402U"AUTS"((820=\'2\')(821=432)403U"AUTS"((820=\'3\')(821=433)404U"AUTS"((820=\'4\')(821=434)',
            description="Legge causali manuali 401-404. Se 'AUTS', salva valore autorizzato in 820/821.",
            fields_involved=[401, 402, 403, 404, 431, 432, 433, 434, 820, 821],
        )

        # --- 3020: Pausa pranzo ---
        patterns[3020] = FormulaPattern(
            code=3020, name="Pausa pranzo – ricalcolo e forzatura 30 min", tipo=FORMULA_TIPO_SUB,
            category="Pausa Pranzo",
            description="Ricalcolo e forzatura pausa pranzo a 30 min.",
        )

        # --- 3030: Warning ore carenti (B) ---
        patterns[3030] = FormulaPattern(
            compact="5>Z(V02V06(71=\"ATTENZIONE SETTIMANA CON ORE CARENTI\")(72=\"Cod.Azienda  e Cod.dipendente\")(73=1000)(74=1100)(75=\"Giorno e Ore carenti\")(76=300)(77=5)(!78)(70='99')783>U'220.00'E783<U'250.00'(V08V12(71=\"ATTENZIONE Potenziale avvicinamento alle 250 ore annuali (range 220/250 ore )\")(72=\"Cod.Azienda  e Cod.dipendente\")(73=1000)(74=1100)(75=\"Ore raggiunte annuali\")(76=783)(77=\"al giorno\")(78=300)(70='99')",
            code=3030, name="Warning ore carenti / soglia 250h annuali (B)", tipo=FORMULA_TIPO_SUB,
            category="Alert",
            description="Identica a 2130. Usata dal sistema FG (3000/3001).",
            fields_involved=[5, 70, 71, 72, 73, 74, 75, 76, 77, 78, 783, 1000, 1100, 300],
        )

        # --- 9001: Arrotondamento Impiegati I ---
        patterns[9001] = FormulaPattern(
            code=9001, name="Arrotondamento Impiegati (I)", tipo=FORMULA_TIPO_IG,
            category="Arrotondamento",
            compact="(800='250')(801='270')(!802)200UZ(VF([800[801)(K802A{801}S{800}){801}<{800}((K802A'24'){800}UZE{801}UZ(V07800<'257'(V02(71=802)(72='15')(!73!74)(70='21')(800='250')(801='270')(802=71)(!803!804)([800[801[803)803U200(R9002(71={800})(72='15')(!73!74)(70='20')({800}=71)(71={801})(72='15')(!73!74)(70='21')({801}=71)(K804A{801}S{800}){801}<{800}((K804A'24')803<U200(V09",
            description="Arrotonda totale ore calcolate al quarto d'ora. Riproporziona tutte le timbrature tranne l'ultima.",
            fields_involved=[70, 71, 72, 73, 74, 200, 250, 257, 270, 800, 801, 802, 803, 804],
            calls=[{"type": "R", "target": 9002}],
        )

        # --- 9002: Arrotondamento Impiegati II ---
        patterns[9002] = FormulaPattern(
            code=9002, name="Arrotondamento Impiegati (II)", tipo=FORMULA_TIPO_IG,
            category="Arrotondamento",
            compact="(71={800})(72='15')(!73!74)(70='20')({800}=71)({801}={800}A802S804)(!800!801!802!803!804)",
            description="Aggiusta ultimo intervallo per far coincidere totale con arrotondato.",
            fields_involved=[70, 71, 72, 73, 74, 800, 801, 802, 804],
        )

        self.PATTERNS = patterns

    def _build_indexes(self) -> None:
        self._by_tipo = {}
        self._by_category = {}
        for p in self.PATTERNS.values():
            self._by_tipo.setdefault(p.tipo, []).append(p)
            self._by_category.setdefault(p.category, []).append(p)

    def _load_from_formule_file(self) -> None:
        """Carica e arricchisce pattern dal file WinSarp_Formule.txt."""
        path = Path(__file__).parent.parent.parent / "documenti" / "WinSarp" / "WinSarp_Formule.txt"
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                enriched = self._extract_compact_from_text(text, self.PATTERNS)
                _logger.info("Formula patterns enriched from %s (%d compact trovati)", path.name, enriched)
            except Exception as e:
                _logger.warning("Errore caricamento patterns: %s", e)

    @staticmethod
    def _extract_compact_from_text(text: str, patterns_dict: dict) -> int:
        """Estrae sintassi compatta dal file WinSarp_Formule.txt e
        aggiorna i pattern che ne sono sprovvisti.
        """
        count = 0
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
                    # Remove orphaned comment words (non-code uppercase text after VF or ))
                    compact = re.sub(r"VF[A-Z]{4,}", "VF", compact)
                    compact = re.sub(r"\)[A-Z]{4,}", ")", compact)
                    p = patterns_dict.get(current_code)
                    if p and not p.compact:
                        p.compact = compact
                        count += 1
                current_code = 0
                compact_lines = []
                continue

            if in_compact_block:
                stripped = re.sub(r"\?(?![(])[^(]*", "", stripped)
                compact_lines.append(stripped)

        return count

    # ============================================================
    # API di interrogazione
    # ============================================================

    def get_pattern(self, code: int) -> FormulaPattern | None:
        return self.PATTERNS.get(code)

    def get_patterns_by_tipo(self, tipo: str) -> list[FormulaPattern]:
        return self._by_tipo.get(tipo, [])

    def get_patterns_by_category(self, category: str) -> list[FormulaPattern]:
        return self._by_category.get(category, [])

    def search_patterns(self, query: str) -> list[FormulaPattern]:
        q = query.lower()
        results = []
        for p in self.PATTERNS.values():
            if str(p.code) == query:
                results.insert(0, p)
            elif q in p.name.lower() or q in p.category.lower() or q in p.description.lower():
                results.append(p)
            elif p.tipo.lower() == q:
                results.append(p)
        return results[:30]

    def get_compact(self, code: int) -> str:
        p = self.PATTERNS.get(code)
        return p.compact if p else ""

    def get_template(self, code: int) -> str | None:
        """Restituisce un pattern formula come template generico (placeholder)."""
        p = self.PATTERNS.get(code)
        if not p or not p.compact:
            return None
        return p.compact

    def find_by_field(self, field: int) -> list[FormulaPattern]:
        """Trova tutte le formule che coinvolgono un dato campo."""
        return [p for p in self.PATTERNS.values() if field in p.fields_involved]

    def get_all_codes(self) -> list[int]:
        return sorted(self.PATTERNS.keys())

    def get_patterns_that_call(self, target: int) -> list[FormulaPattern]:
        return [p for p in self.PATTERNS.values() if any(c["target"] == target for c in p.calls)]

    def get_patterns_called_by(self, code: int) -> list[FormulaPattern]:
        p = self.PATTERNS.get(code)
        if not p:
            return []
        return [self.PATTERNS[c["target"]] for c in p.calls if c["target"] in self.PATTERNS]

    def stats(self) -> dict[str, Any]:
        return {
            "total_patterns": len(self.PATTERNS),
            "by_tipo": {t: len(ps) for t, ps in self._by_tipo.items()},
            "by_category": {c: len(ps) for c, ps in self._by_category.items()},
            "with_compact": sum(1 for p in self.PATTERNS.values() if p.compact),
            "with_calls": sum(1 for p in self.PATTERNS.values() if p.calls),
        }


# Singleton
patterns: FormulaPatternLibrary = FormulaPatternLibrary()
