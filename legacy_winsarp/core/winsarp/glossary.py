"""
business_glossary.py
Glossario semantico del dominio WinSarp.

Mapping da concetti di business (come parlano gli utenti) a entità tecniche
WinSarp (campi, formule, K, causali, pattern).

Permette di espandere una query NL con sinonimi, concetti correlati,
e riferimenti a formule/campi prima di passarla al classificatore LLM.
"""

from __future__ import annotations

import logging
from typing import Dict, List

_logger = logging.getLogger(__name__)

# ============================================================
# 1. CONCEPT → FIELD MAPPING
# Ogni concetto di business mappa a uno o più campi WinSarp
# ============================================================

CONCEPT_TO_FIELD: Dict[str, Dict] = {
    # Ore e presenze
    "ore previste": {"fields": [1], "description": "Ore previsionali (da contratto/piano orario)"},
    "ore previsionali": {"fields": [1], "description": "Ore previsionali (da contratto/piano orario)"},
    "ore effettive": {"fields": [2], "description": "Ore effettive (da timbrature)"},
    "ore timbrate": {"fields": [2], "description": "Ore effettive (da timbrature)"},
    "ore ordinarie": {"fields": [3, 905, 'K602'], "description": "Ore ordinarie calcolate"},
    "ore normali": {"fields": [3, 905, 'K602'], "description": "Ore ordinarie calcolate"},
    "ore base": {"fields": [3, 905, 'K602'], "description": "Ore ordinarie calcolate"},
    "ore lavorate": {"fields": [3, 4, 'K601'], "description": "Totale ore lavorate (ordinarie + straordinario)"},
    "ore presenza": {"fields": [3, 'K601'], "description": "Ore di presenza al lavoro"},
    "ore straordinarie": {"fields": [4, 'K604'], "description": "Ore straordinarie totali"},
    "straordinario": {"fields": [4, 'K604'], "description": "Straordinario totale (diurno+notturno+festivo)"},
    "ore assenza": {"fields": [5, 'K608', 'K609'], "description": "Ore di assenza"},
    "assenze": {"fields": [5, 'K608', 'K609'], "description": "Ore di assenza retribuite e non"},
    "ore carenti": {"fields": [5], "description": "Ore mancanti rispetto al previsionale"},

    # Fasce orarie e turni
    "fascia notturna": {"fields": [21, 22], "description": "Ore in fascia notturna (22:00-06:00)"},
    "ore notturne": {"fields": [21, 902, 909, 'K902', 'K909'], "description": "Ore lavorate in fascia notturna"},
    "notturno": {"fields": [21, 902, 909, 'K902', 'K909', 'K626'], "description": "Lavoro notturno"},
    "fascia diurna": {"fields": [20, 22], "description": "Ore in fascia diurna"},
    "ore diurne": {"fields": [3, 905, 907], "description": "Ore lavorate in fascia diurna"},
    "diurno": {"fields": [3, 905, 907, 'K611'], "description": "Lavoro diurno"},

    # Turni specifici
    "turno mattino": {"fields": [58, 900, 111, 141], "description": "Turno mattino (58=MATT, 900=1, prev. 06-14)"},
    "mattino": {"fields": [58, 900, 111, 141], "description": "Turno mattino"},
    "mattina": {"fields": [58, 900, 111, 141], "description": "Turno mattino"},
    "turno pomeriggio": {"fields": [58, 900, 112, 142], "description": "Turno pomeriggio (58=POME, 900=2, prev. 14-22)"},
    "pomeriggio": {"fields": [58, 900, 112, 142], "description": "Turno pomeriggio"},
    "turno notte": {"fields": [58, 900, 111, 141], "description": "Turno notte (58=NOTT, 900=3, prev. 22-06)"},
    "turno notturno": {"fields": [58, 900, 111, 141], "description": "Turno notte"},
    "notte": {"fields": [58, 900, 111, 141], "description": "Turno notte"},
    "riposo": {"fields": [58], "description": "Giorno di riposo (58=RIPO)"},
    "operaio spezzato": {"fields": [58, 100, 111, 112, 141, 142], "description": "Operaio con 2 intervalli (58=OPE, 08-12/13-17)"},

    # Festività
    "festivo": {"fields": [55, 684, 'K603', 'K605', 'K627', 'K629', 'K630'], "description": "Giorno festivo (55=I)"},
    "giorno festivo": {"fields": [55, 684, 'K603', 'K605', 'K627', 'K629', 'K630'], "description": "Giorno festivo"},
    "domenica": {"fields": [50, 55], "description": "Domenica (50=7, 55=I)"},
    "sabato": {"fields": [50], "description": "Sabato (50=6)"},
    "festività normale": {"fields": [919, 918, 'K630', 'K605'], "description": "Festività normale (919=1)"},
    "festività non goduta": {"fields": [684, 919, 'K629'], "description": "Festività non goduta (919=2)"},
    "festività patrono": {"fields": [919, 'K631'], "description": "Festività patrono (919=3, 1051=51, 1052=52)"},
    "festività in stipendio": {"fields": [919, 'K605'], "description": "Festività in stipendio FX (919=4)"},
    "non goduta": {"fields": [684, 919, 'K629'], "description": "Festività non goduta"},

    # Straordinario per tipo
    "straordinario diurno": {"fields": [4, 907, 'K611', 'K907'], "description": "Straordinario in fascia diurna (causale SA)"},
    "straordinario notturno": {"fields": [4, 21, 909, 'K614', 'K909'], "description": "Straordinario in fascia notturna (causale SN)"},
    "straordinario festivo": {"fields": [4, 54, 55, 914, 'K615', 'K914'], "description": "Straordinario in giorno festivo (causale SF)"},
    "straordinario festivo notturno": {"fields": [4, 21, 55, 910, 'K616', 'K910'], "description": "Straordinario festivo in fascia notturna (causale SNF)"},
    "straordinario seconda fascia": {"fields": [915, 'K915'], "description": "Straordinario diurno 2a fascia (causale SB, oltre 8h)"},
    "supplementare": {"fields": [906, 'K612', 'K906'], "description": "Ore supplementari part-time (causale SP)"},
    "supplementari": {"fields": [906, 'K612', 'K906'], "description": "Ore supplementari part-time"},

    # Maggiorazioni
    "maggiorazione": {"fields": ['K625', 'K626', 'K627'], "description": "Maggiorazioni turno"},
    "maggiorazione notturna": {"fields": [21, 565, 902, 'K626'], "description": "Maggiorazione per lavoro notturno (causale N)"},
    "maggiorazione turno diurno": {"fields": [890, 566, 'K625'], "description": "Maggiorazione per lavoro diurno (causale T)"},
    "maggiorazione festiva": {"fields": [904, 908, 564, 'K627'], "description": "Maggiorazione per lavoro festivo (causale LFS)"},
    "premio turno": {"fields": ['K625', 'K626', 'K627'], "description": "Premi/incentivi per lavoro turnista"},
    "indennità turno": {"fields": ['K625', 'K626', 'K627'], "description": "Indennità per lavoro a turni"},

    # Giornata e date
    "inizio giornata": {"fields": [390, 391, 100], "description": "Formula di inizio giornata (IG)"},
    "fine giornata": {"fields": [300, 500], "description": "Formula di fine giornata (FG)"},
    "data giornata": {"fields": [300], "description": "Data del giorno in elaborazione (AAAAMMGG)"},
    "data oggi": {"fields": [301], "description": "Data odierna per confronti"},
    "giorno settimana": {"fields": [50], "description": "Giorno della settimana (1=Dom…7=Sab)"},

    # Timbrature
    "timbratura": {"fields": [200, 201, 202], "description": "Timbrature effettive (entrate pari, uscite dispari)"},
    "entrata": {"fields": [111, 251, 201], "description": "Orario di entrata"},
    "uscita": {"fields": [141, 271, 221], "description": "Orario di uscita"},
    "orario previsionale": {"fields": [111, 112, 141, 142, 100], "description": "Orario previsionale (pianificato)"},
    "orario calcolato": {"fields": [251, 252, 271, 272, 250], "description": "Orario calcolato (dopo elaborazione)"},
    "orario effettivo": {"fields": [201, 202, 221, 222, 200], "description": "Orario effettivo (da timbrature)"},

    # Arrotondamento
    "arrotondamento": {"fields": [86, 87, 88, 89], "description": "Arrotondamento entrate/uscite"},
    "arrotondamento entrata": {"fields": [86, 87, 251], "description": "Arrotondamento orario di entrata"},
    "arrotondamento uscita": {"fields": [88, 89, 271], "description": "Arrotondamento orario di uscita"},
    "arrotondamento quarti": {"fields": [73, 800], "description": "Arrotondamento ai quarti d'ora"},
    "bonus arrotondamento": {"fields": [86, 88], "description": "Bonus/minuti di arrotondamento"},
    "frazione arrotondamento": {"fields": [87, 89], "description": "Frazione di arrotondamento in minuti"},

    # Causali
    "causale": {"fields": [400, 401, 411, 421, 431, 441, 501, 511], "description": "Causali orario"},
    "causali automatiche": {"fields": [500, 501, 502, 503, 504, 505, 506, 507, 508, 509, 510],
                           "description": "Slot causali automatiche (501-510)"},
    "causali manuali": {"fields": [400, 401, 402, 403, 404, 411, 421, 431, 441],
                       "description": "Causali inserite manualmente"},
    "autorizzazione straordinario": {"fields": [820, 821, 401, 402, 403, 404],
                                    "description": "Autorizzazione allo straordinario (AUTS)"},
    "auts": {"fields": [820, 821, 401, 402, 403, 404],
             "description": "Autorizzazione straordinario (AUTS)"},

    # Pause
    "pausa pranzo": {"fields": [811, 812, 3020], "description": "Pausa pranzo di 30 minuti"},
    "pausa": {"fields": [811, 812], "description": "Pausa/intervallo"},

    # Flag e stato
    "flag turno": {"fields": [900], "description": "Flag riconoscimento turno (0=nessuno, 1=MATT, 2=POME, 3=NOTT)"},
    "flag festivo": {"fields": [55], "description": "Flag giorno festivo (I=si, Z=no)"},
    "tipo turno": {"fields": [58], "description": "Tipo turno (MATT/POME/NOTT/RIPO/OPE/CHIA)"},
    "tipo calcolo": {"fields": [390], "description": "Tipo di calcolo (0=normale, <>0=speciale)"},

    # Totali progressivi
    "totale ore settimanali": {"fields": ['K711'], "description": "Totale ore settimanali progressivo"},
    "ore settimanali": {"fields": ['K711', 'K771', 'K774'], "description": "Ore cumulate nella settimana"},
    "straordinario settimanale": {"fields": ['K774', 'K784', 'K907'], "description": "Straordinario cumulato settimanale"},
    "flessibilità lavorata": {"fields": ['K621'], "description": "Banca ore positiva (flessibilità lavorata)"},
    "flessibilità goduta": {"fields": ['K622'], "description": "Banca ore negativa (flessibilità goduta)"},
    "banca ore": {"fields": ['K621', 'K622'], "description": "Banca ore (flessibilità)"},
    "malattia": {"fields": ['K651'], "description": "Ore di malattia"},
    "ferie": {"fields": ['K631'], "description": "Ore di ferie godute"},
    "rol": {"fields": ['K635'], "description": "Ore R.O.L. godute"},
    "permessi": {"fields": ['K641'], "description": "Ore di permessi"},

    # Campi aziendali
    "codice azienda": {"fields": [1000], "description": "Codice azienda del dipendente"},
    "codice dipendente": {"fields": [1100], "description": "Codice matricola del dipendente"},
    "ore contrattuali": {"fields": [1114], "description": "Ore settimanali contrattuali"},
    "part time": {"fields": [1391], "description": "Ore ridotte part-time (da Tabella Orario)"},
    "part-time": {"fields": [1391], "description": "Ore ridotte part-time"},

    # Soglie e limiti
    "soglia straordinario": {"fields": [887, 889], "description": "Soglia per attivazione straordinario (40h - assenze)"},
    "limite 250 ore": {"fields": [783], "description": "Limite annuale 250 ore straordinarie"},
    "cap 8 ore": {"fields": [907, 915], "description": "Cap di 8 ore straordinario diurno (SA→SB)"},
    "limite uscita": {"fields": [221, 222, 271, 272], "description": "Limite orario di uscita"},

    # GUGEST
    "gugest": {"fields": [900, 1801, 'K770', 'K771', 'K772', 'K773', 'K774'],
               "description": "Sistema GUGEST di gestione personalizzata"},
    "primo giro": {"fields": [770, 771, 887, 889], "description": "Primo giro settimanale GUGEST"},
    "secondo giro": {"fields": [782, 785, 788, 901, 929], "description": "Secondo giro giornaliero GUGEST"},

    # Campi di appoggio
    "appoggio": {"fields": [800, 801, 802, 803, 804, 805, 806, 807, 810, 811, 812, 820, 821, 887, 889, 890],
                 "description": "Campi di appoggio per calcoli temporanei"},
}

# ============================================================
# 2. CONCEPT → CAUSALE MAPPING
# ============================================================

CONCEPT_TO_CAUSALE: Dict[str, Dict] = {
    "straordinario diurno": {"codes": ["SA"], "slot": 506, "description": "Straordinario Diurno 1a fascia"},
    "straordinario prima fascia": {"codes": ["SA"], "slot": 506, "description": "Straordinario Diurno 1a fascia"},
    "straordinario seconda fascia": {"codes": ["SB"], "slot": 510, "description": "Straordinario Diurno 2a fascia"},
    "straordinario notturno": {"codes": ["SN"], "slot": 508, "description": "Straordinario Notturno"},
    "straordinario festivo diurno": {"codes": ["SF"], "slot": 507, "description": "Straordinario Festivo Diurno"},
    "straordinario festivo notturno": {"codes": ["SFN", "SNF"], "slot": 509, "description": "Straordinario Notturno Festivo"},
    "supplementare": {"codes": ["SP"], "slot": 505, "description": "Supplementare"},
    "maggiorazione notturna": {"codes": ["N"], "slot": 502, "description": "Maggiorazione Turno Notturno"},
    "maggiorazione diurna": {"codes": ["T"], "slot": 506, "description": "Maggiorazione Turno Diurno"},
    "maggiorazione festiva": {"codes": ["LFS"], "slot": 504, "description": "Maggiorazione Lavoro Festivo"},
    "maggiorazione notturna festiva": {"codes": ["NF"], "slot": 503, "description": "Maggiorazione Notturna Festiva"},
    "festività normale": {"codes": ["F"], "slot": 501, "description": "Festività Normale"},
    "festività non goduta": {"codes": ["FNG"], "slot": 501, "description": "Festività Non Goduta"},
    "festività patrono": {"codes": ["FP"], "slot": 501, "description": "Festività Patrono"},
    "festività in stipendio": {"codes": ["FX"], "slot": 501, "description": "Festività in Stipendio (variante B)"},
}

# ============================================================
# 3. CONCEPT → FORMULA MAPPING
# ============================================================

CONCEPT_TO_FORMULA: Dict[str, Dict] = {
    "riconoscimento turno": {"formulas": [5, 10], "fase": "IG/DG",
                            "description": "Riconosce il turno da timbrature (5) o da calcolate (10)"},
    "classificazione turno": {"formulas": [5, 10], "fase": "IG/DG",
                             "description": "Classifica il turno in MATT/POME/NOTT"},
    "determinazione turno": {"formulas": [5, 10], "fase": "IG/DG",
                            "description": "Determina il tipo di turno"},
    "azzeramento giornata": {"formulas": [1, 100], "fase": "IG",
                            "description": "Azzeramento campi inizio/fine giornata"},
    "inizio giornata": {"formulas": [1, 5, 10], "fase": "IG",
                        "description": "Formule di inizio giornata"},
    "fine giornata": {"formulas": [100, 110, 120, 130, 140, 200, 210], "fase": "FG",
                      "description": "Flusso principale di fine giornata"},
    "chiusura giornata": {"formulas": [200], "fase": "FG",
                          "description": "Formula finale di chiusura giornata"},
    "calcolo ore": {"formulas": [2122, 2107], "fase": "SUB",
                    "description": "Calcolo ore per singolo intervallo"},
    "conteggio ore": {"formulas": [2107], "fase": "SUB",
                      "description": "Conteggio ore con arrotondamento minuti"},
    "arrotondamento ore": {"formulas": [2123, 2124, 3002, 3003, 2140], "fase": "SUB",
                           "description": "Arrotondamento ore ai quarti"},
    "arrotondamento entrate": {"formulas": [2050], "fase": "IG",
                               "description": "Arrotondamento timbrature entrata (Conad)"},
    "arrotondamento uscite": {"formulas": [2051], "fase": "IG",
                              "description": "Arrotondamento timbrature uscita (Conad)"},
    "straordinario festivo": {"formulas": [130, 3004], "fase": "FG/SUB",
                              "description": "Gestione straordinario in giorno festivo"},
    "straordinario diurno": {"formulas": [140], "fase": "FG",
                             "description": "Gestione straordinario in giorno ordinario"},
    "straordinario notturno": {"formulas": [140], "fase": "FG",
                              "description": "Gestione straordinario in fascia notturna"},
    "maggiorazioni turnisti": {"formulas": [210], "fase": "FG",
                               "description": "Calcolo maggiorazioni per turnisti"},
    "premi turno": {"formulas": [210], "fase": "FG",
                    "description": "Calcolo premi/incentivi turno"},
    "gestione causali": {"formulas": [2115, 3015], "fase": "SUB",
                         "description": "Esplosione causali automatiche"},
    "esplodi causali": {"formulas": [2115, 3015], "fase": "SUB",
                        "description": "Assegnazione causali automatiche agli slot"},
    "festività": {"formulas": [2109, 3009], "fase": "SUB",
                  "description": "Gestione festività automatiche"},
    "gestione festività": {"formulas": [2109, 3009], "fase": "SUB",
                           "description": "Gestione giorni festivi"},
    "pausa pranzo": {"formulas": [3020], "fase": "SUB",
                     "description": "Gestione pausa pranzo 30 minuti"},
    "autorizzazione straordinario": {"formulas": [3017], "fase": "SUB",
                                     "description": "Gestione autorizzazioni straordinario (AUTS)"},
    "auts": {"formulas": [3017], "fase": "SUB",
             "description": "Autorizzazione straordinario"},
    "festivo": {"formulas": [2109, 3009], "fase": "SUB",
                "description": "Gestione giorno festivo (riconoscimento e accumulo)"},
    "giorno festivo": {"formulas": [2109, 3009], "fase": "SUB",
                       "description": "Gestione giorno festivo"},
    "cap straordinario": {"formulas": [2114, 3014], "fase": "SUB",
                          "description": "Ritocco SA/SB con cap 8 ore"},
    "ritocco sa sb": {"formulas": [2114, 3014], "fase": "SUB",
                      "description": "Scorporo eccedenza straordinario in SB"},
    "calcolo settimanale": {"formulas": [2100, 2105, 3000], "fase": "FG",
                            "description": "Calcolo ore a livello settimanale"},
    "straordinario settimanale": {"formulas": [3005], "fase": "SUB",
                                  "description": "Calcolo straordinario su base settimanale"},
    "warning ore": {"formulas": [2130, 3030], "fase": "SUB",
                    "description": "Alert ore carenti e soglia 250h annuali"},
    "alert ore": {"formulas": [2130, 3030], "fase": "SUB",
                  "description": "Avvisi per ore carenti e limite annuale"},
    "gugest": {"formulas": [2100, 2101, 2105, 2106], "fase": "FG",
               "description": "Sistema GUGEST di gestione personalizzata"},
    "dirigenti": {"formulas": [1000, 1100], "fase": "IG/FG",
                  "description": "Formule per dirigenti (non timbratori)"},
    "quadri": {"formulas": [1010, 1100], "fase": "IG/FG",
               "description": "Formule per quadri"},
    "chiamata": {"formulas": [2000], "fase": "FG",
                 "description": "Formula per dipendenti a chiamata"},
    "timbratura singola": {"formulas": [1020, 1120], "fase": "IG/FG",
                           "description": "Gestione dipendenti con timbratura singola"},
    "arrotondamento impiegati": {"formulas": [9001, 9002], "fase": "IG",
                                 "description": "Arrotondamento ai quarti per impiegati"},
    "conad gubbio": {"formulas": [2050, 2051, 2060], "fase": "IG",
                     "description": "Formule personalizzate Conad Gubbio"},
    "cap uscite": {"formulas": [2060], "fase": "IG",
                   "description": "Cap orario uscite a 20:05 (Conad)"},
}

# ============================================================
# 4. SYNONYM MAP
# Parole e frasi alternative → concetto canonico
# ============================================================

SYNONYM_MAP: Dict[str, str] = {
    # Ore
    "ore normali": "ore ordinarie",
    "ore base": "ore ordinarie",
    "ore regolari": "ore ordinarie",
    "ore standard": "ore ordinarie",
    "ore di presenza": "ore presenza",
    "ore lavorate": "ore lavorate",
    "ore di lavoro": "ore lavorate",
    "straordinario": "straordinario",
    "straord": "straordinario",
    "eccezionale": "straordinario",
    "extra": "straordinario",
    "ore extra": "ore straordinarie",
    "ore mancanti": "ore assenza",
    "assenze": "ore assenza",
    "assente": "ore assenza",
    "mancanza": "ore carenti",
    "carenza": "ore carenti",

    # Fasce orarie
    "notte": "notturno",
    "notturno": "notturno",
    "turno di notte": "turno notturno",
    "lavoro notturno": "notturno",
    "ore di notte": "ore notturne",
    "fascia notte": "fascia notturna",
    "diurno": "diurno",
    "giorno": "diurno",
    "di giorno": "diurno",
    "ore di giorno": "ore diurne",

    # Turni
    "mattino": "turno mattino",
    "mattina": "turno mattino",
    "turno del mattino": "turno mattino",
    "primo turno": "turno mattino",
    "pomeriggio": "turno pomeriggio",
    "turno del pomeriggio": "turno pomeriggio",
    "secondo turno": "turno pomeriggio",
    "sera": "turno notte",
    "turno della notte": "turno notturno",
    "terzo turno": "turno notturno",
    "turnista": "turnista",
    "turnista notturno": "turno notturno",
    "turnista notte": "turno notturno",
    "turnista di notte": "turno notturno",
    "turnista pomeriggio": "turno pomeriggio",
    "turnista mattino": "turno mattino",

    # Festività
    "festivo": "festivo",
    "festività": "festività",
    "domenica": "domenica",
    "sabato": "sabato",
    "weekend": "festivo",
    "giorno festivo": "giorno festivo",
    "giorno di festa": "giorno festivo",
    "non goduta": "festività non goduta",
    "patrono": "festività patrono",
    "santo patrono": "festività patrono",

    # Straordinario per tipo
    "sa": "straordinario diurno",
    "sb": "straordinario seconda fascia",
    "sn": "straordinario notturno",
    "sf": "straordinario festivo",
    "sfn": "straordinario festivo notturno",
    "snf": "straordinario festivo notturno",
    "sp": "supplementare",
    "supplementare": "supplementare",
    "ore supplementari": "supplementare",

    # Maggiorazioni
    "maggiorazione": "maggiorazione",
    "n": "maggiorazione notturna",
    "magg notturna": "maggiorazione notturna",
    "t": "maggiorazione turno diurno",
    "magg diurna": "maggiorazione diurna",
    "lfs": "maggiorazione festiva",
    "nf": "maggiorazione notturna festiva",
    "premio": "maggiorazione",
    "incentivo": "maggiorazione",
    "indennità": "maggiorazione",
    "bonus": "maggiorazione",

    # Calcoli
    "calcola": "calcola",
    "calcolare": "calcola",
    "calcolo": "calcola",
    "somma": "somma",
    "aggiungi": "somma",
    "accumula": "accumula",
    "totalizza": "accumula",
    "conteggia": "conteggio ore",
    "conteggio": "conteggio ore",
    "arrotonda": "arrotondamento",
    "arrotondare": "arrotondamento",
    "approssima": "arrotondamento",
    "tronca": "arrotondamento",
    "quarti d'ora": "arrotondamento quarti",
    "quarti": "arrotondamento quarti",

    # Giornata
    "avvio": "inizio giornata",
    "partenza": "inizio giornata",
    "inizializza": "inizio giornata",
    "resetta": "azzeramento giornata",
    "azzera": "azzeramento giornata",
    "pulisci": "azzeramento giornata",
    "svuota": "azzeramento giornata",
    "reset": "azzeramento giornata",
    "fine": "fine giornata",
    "chiusura": "fine giornata",
    "termine": "fine giornata",
    "finale": "fine giornata",

    # Presenze
    "presenza": "ore presenza",
    "presenze": "ore presenza",
    "timbratura": "timbratura",
    "timbra": "timbratura",
    "timbrato": "timbratura",
    "cartellino": "timbratura",
    "badge": "timbratura",
    "entrata": "entrata",
    "ingresso": "entrata",
    "uscita": "uscita",
    "uscire": "uscita",
    "inizio turno": "entrata",
    "fine turno": "uscita",

    # Causali
    "causale": "causale",
    "causali": "causali automatiche",
    "esplodi": "esplodi causali",
    "esplodi causali": "esplodi causali",
    "autorizzazione": "autorizzazione straordinario",
    "autorizza": "autorizzazione straordinario",
    "permesso": "autorizzazione straordinario",
    "auts": "auts",
    "autorizzato": "autorizzazione straordinario",

    # Pause
    "pranzo": "pausa pranzo",
    "mensa": "pausa pranzo",
    "pausa mensa": "pausa pranzo",
    "intervallo pranzo": "pausa pranzo",
    "pausa": "pausa pranzo",
    "break": "pausa pranzo",

    # Gestionali
    "gugest": "gugest",
    "flusso gugest": "gugest",
    "gestione personalizzata": "gugest",
    "conad": "conad gubbio",
    "conad gubbio": "conad gubbio",
    "gubbio": "conad gubbio",
    "dirigente": "dirigenti",
    "dirigenti": "dirigenti",
    "quadro": "quadri",
    "quadri": "quadri",
    "chiamata": "chiamata",
    "a chiamata": "chiamata",
    "operaio spezzato": "operaio spezzato",
    "ope": "operaio spezzato",
    "spezzato": "operaio spezzato",
    "part-time": "part time",
    "part time": "part time",
    "pt": "part time",

    # Soglie
    "limite": "soglia straordinario",
    "soglia": "soglia straordinario",
    "cap": "cap 8 ore",
    "tetto": "cap 8 ore",
    "massimo": "cap 8 ore",
    "250 ore": "limite 250 ore",
    "limite annuale": "limite 250 ore",
    "ore annuali": "limite 250 ore",
}

# ============================================================
# 5. SCENARIO → FORMULA CHAIN MAPPING
# Scenari tipici → sequenza di formule da applicare
# ============================================================

SCENARIO_FLOWS: Dict[str, Dict] = {
    "turnista_mattino": {
        "description": "Turnista con turno mattino",
        "flows": [
            {"name": "IG", "formulas": [1, 5], "description": "Azzeramento + riconoscimento turno (MATT)"},
            {"name": "FG", "formulas": [100, 110, 120, 140, 200, 210], "description": "Fine giornata standard con maggiorazioni"},
        ],
        "key_fields": [58, 900, 111, 141],
        "key_conditions": "Entrata tra 04:00 e 09:00 → 58=MATT, 900=1, prev. 06-14",
    },
    "turnista_pomeriggio": {
        "description": "Turnista con turno pomeriggio",
        "flows": [
            {"name": "IG", "formulas": [1, 5], "description": "Azzeramento + riconoscimento turno (POME)"},
            {"name": "FG", "formulas": [100, 110, 120, 140, 200, 210], "description": "Fine giornata standard con maggiorazioni"},
        ],
        "key_fields": [58, 900, 112, 142],
        "key_conditions": "Entrata tra 12:00 e 17:00 → 58=POME, 900=2, prev. 14-22",
    },
    "turnista_notte": {
        "description": "Turnista con turno notturno",
        "flows": [
            {"name": "IG", "formulas": [1, 5], "description": "Azzeramento + riconoscimento turno (NOTT)"},
            {"name": "FG", "formulas": [100, 110, 120, 140, 200, 210], "description": "Fine giornata con straordinario notturno"},
        ],
        "key_fields": [58, 900, 21, 21, 111, 141],
        "key_conditions": "Entrata tra 20:00 e 23:59 → 58=NOTT, 900=3, prev. 22-06. Ore notturne in campo 21.",
    },
    "dipendente_standard": {
        "description": "Dipendente standard con timbrature normali",
        "flows": [
            {"name": "IG", "formulas": [1], "description": "Azzeramento iniziale"},
            {"name": "FG", "formulas": [100, 110, 120, 130, 140, 200], "description": "Flusso FG completo"},
        ],
        "key_fields": [1, 2, 3, 4, 5, 200, 201, 202],
        "key_conditions": "Straordinario gestito dallo smistatore 120: se festivo→130, se ordinario→140",
    },
    "dirigente": {
        "description": "Dirigente che non timbra",
        "flows": [
            {"name": "IG", "formulas": [1000], "description": "Copia previsionale in calcolato"},
            {"name": "FG", "formulas": [1100], "description": "Gestione assenze su calcolato"},
        ],
        "key_fields": [111, 112, 141, 142, 251, 252, 271, 272, 608, 609],
        "key_conditions": "Se assenze ≥ previsionale → azzera tutto",
    },
    "quadro": {
        "description": "Quadro che può timbrare volontariamente",
        "flows": [
            {"name": "IG", "formulas": [1010], "description": "Copia previsionale solo se non ha timbrato"},
            {"name": "FG", "formulas": [1100], "description": "Gestione assenze su calcolato"},
        ],
        "key_fields": [111, 112, 141, 142, 201, 221, 251, 271],
        "key_conditions": "Se 201 o 221 valorizzati → rispetta timbrature reali, non sovrascrivere",
    },
    "dipendente_chiamata": {
        "description": "Dipendente a chiamata (tipo CHIA)",
        "flows": [
            {"name": "FG", "formulas": [2000], "description": "Se non timbrato→RIPO, se timbrato→copie calcolate"},
        ],
        "key_fields": [58, 200, 251, 271, 300, 305],
        "key_conditions": "300>305 → esci. 200=Z → 58=RIPO. Se CHIA non ancora→CHI. K3A4 somma veloce.",
    },
    "conad_gubbio": {
        "description": "Dipendente Conad Gubbio con arrotondamenti e cap uscite",
        "flows": [
            {"name": "IG", "formulas": [2050], "description": "Arrotondamento entrate + 2051/2060"},
            {"name": "IG", "formulas": [2051], "description": "Arrotondamento uscite (1° e 2° intervallo)"},
            {"name": "IG (dal 01/06/2023)", "formulas": [2060], "description": "Cap uscite a 20:05 per tutti gli intervalli"},
        ],
        "key_fields": [201, 221, 222, 251, 271, 272, 300],
        "key_conditions": "Se data ≥ 01/06/2023 → 2060 (cap 20:05). Ante → arrotondamento 2050/2051",
    },
    "impiegato_arrotondamento": {
        "description": "Impiegato con arrotondamento ai quarti d'ora",
        "flows": [
            {"name": "IG", "formulas": [9001, 9002], "description": "Arrotondamento ai quarti con riproporzionamento"},
        ],
        "key_fields": [250, 251, 252, 270, 271, 272, 800, 801, 802, 803, 804],
        "key_conditions": "Arrotonda tutti gli intervalli tranne l'ultimo (9001), poi 9002 sistema l'ultimo",
    },
    "gugest_a": {
        "description": "Sistema GUGEST variante A",
        "flows": [
            {"name": "FG (1° giro)", "formulas": [2100], "description": "GUGEST 1: inizializzazione, soglie, accumulo base"},
            {"name": "FG (2° giro)", "formulas": [2101], "description": "GUGEST 2: calcolo dettagliato per intervallo"},
        ],
        "subroutines": [2109, 2122, 2123, 2124, 2125, 2114, 2115, 2130],
        "key_fields": [770, 771, 772, 773, 887, 889, 900, 1801],
    },
    "gugest_b": {
        "description": "Sistema GUGEST variante B",
        "flows": [
            {"name": "FG (1° giro)", "formulas": [2105], "description": "GUGEST 1 B: loop intervalli già in 1° giro"},
            {"name": "FG (2° giro)", "formulas": [2106], "description": "GUGEST 2 B: identico a 2101"},
        ],
        "subroutines": [2109, 2122, 2123, 2124, 2125, 2114, 2115, 2130],
        "key_fields": [770, 771, 772, 773, 887, 889, 900, 1801],
    },
    "fg_b": {
        "description": "Sistema FG variante B (3xxx)",
        "flows": [
            {"name": "FG (1° giro)", "formulas": [3000], "description": "FG 1: con split data 01/06/2023"},
            {"name": "FG (2° giro)", "formulas": [3001], "description": "FG NEW: calcolo completo"},
        ],
        "subroutines": [3009, 2122, 2123, 2124, 3005, 3014, 3015, 3030, 3004, 3002, 3003, 3017],
        "key_fields": [770, 772, 775, 776, 788, 887, 889, 900, 1801],
    },
    "festivo_domenica": {
        "description": "Gestione giorno festivo/domenica",
        "flows": [
            {"name": "SUB", "formulas": [2109, 3009], "description": "Classifica tipo festività e accumula"},
            {"name": "FG", "formulas": [130, 3004], "description": "Straordinario festivo (se presente)"},
        ],
        "key_fields": [55, 684, 919, 918, 50, 51, 52, 1051, 1052],
        "key_conditions": "919=1→normale, 2→non goduta, 3→patrono, 4→FX. Se sabato (50=7) e 1=Z→nessuna.",
    },
    "straordinario_con_auts": {
        "description": "Straordinario con autorizzazione (AUTS)",
        "flows": [
            {"name": "SUB", "formulas": [3017], "description": "Legge AUTS da causali manuali 401-404"},
            {"name": "SUB", "formulas": [3005], "description": "Calcolo straordinario settimanale con limite AUTS"},
            {"name": "SUB", "formulas": [3014], "description": "Ritocco SA/SB"},
            {"name": "SUB", "formulas": [3004], "description": "Riclassifica straordinario festivo"},
            {"name": "SUB", "formulas": [3015], "description": "Assegnazione causali"},
        ],
        "key_fields": [401, 402, 403, 404, 431, 432, 433, 434, 820, 821, 907, 915],
        "key_conditions": "Se causale manuale = AUTS → 820=slot, 821=ore autorizzate. 3005 usa 820/821 come cap.",
    },
}

# ============================================================
# 6. BUSINESS RULES
# Regole di calcolo formalizzate
# ============================================================

BUSINESS_RULES: List[Dict] = [
    {
        "id": "BR001",
        "name": "Totale ore lavorate",
        "rule": "'K601' = 'K602' + 'K604' = 3 + 4",
        "fields": [3, 4, 'K601', 'K602', 'K604'],
        "description": "Le ore lavorate sono la somma di ore ordinarie e straordinario",
    },
    {
        "id": "BR002",
        "name": "Straordinario totale",
        "rule": "'K604' = 'K612' + 'K611' + 'K615' + 'K614' + 'K616'",
        "fields": ['K604', 'K612', 'K611', 'K615', 'K614', 'K616'],
        "description": "Straordinario totale = supplementare + diurno + festivo diurno + notturno + festivo notturno",
    },
    {
        "id": "BR003",
        "name": "Classificazione turno mattino",
        "rule": "Se entrata tra 04:00 e 09:00 → MATT (900=1, 06-14)",
        "fields": [201, 900, 58, 111, 141],
        "description": "Entrata in fascia 04-09 → turno mattino con orario previsionale 06-14",
    },
    {
        "id": "BR004",
        "name": "Classificazione turno pomeriggio",
        "rule": "Se entrata tra 12:00 e 17:00 → POME (900=2, 14-22)",
        "fields": [201, 900, 58, 112, 142],
        "description": "Entrata in fascia 12-17 → turno pomeriggio con orario previsionale 14-22",
    },
    {
        "id": "BR005",
        "name": "Classificazione turno notte",
        "rule": "Se entrata tra 20:00 e 23:59 → NOTT (900=3, 22-06)",
        "fields": [201, 900, 58, 111, 141],
        "description": "Entrata in fascia 20-24 → turno notte con orario previsionale 22-06",
    },
    {
        "id": "BR006",
        "name": "Straordinario non ammesso",
        "rule": "Se campo 1121 = 'N' → !4 (nessuno straordinario)",
        "fields": [1121, 4],
        "description": "Il flag 1121='N' blocca tutto lo straordinario",
    },
    {
        "id": "BR007",
        "name": "Riproporzionamento assenze",
        "rule": "Se 800(3+4+608+609) > 1 → 4=800-1, 3=1-608-609; altrimenti 3=800-608-609, 5=1-800",
        "fields": [1, 3, 4, 5, 608, 609, 800],
        "description": "Quando il totale lavorato+assenze supera il previsionale, la differenza è straordinario",
    },
    {
        "id": "BR008",
        "name": "Split straordinario festivo",
        "rule": "21>0 → 504=SFN; se 21>4 → 564=4, K21S4, !4; altrimenti 564=21, K4S21, !21. Poi 503=SF, 563=4",
        "fields": [4, 21, 503, 504, 563, 564, 'K615', 'K616'],
        "description": "Nei festivi: ore notturne → SFN (616), ore diurne residue → SF (615)",
    },
    {
        "id": "BR009",
        "name": "Split straordinario ordinario",
        "rule": "21>0 O 900=3 → 502=SN; split 21/4 come BR008. Poi 501=S, 561=4 residuo",
        "fields": [4, 21, 501, 502, 561, 562, 'K611', 'K614', 900],
        "description": "Nei giorni ordinari: ore notturne → SN (614), ore diurne residue → S (611)",
    },
    {
        "id": "BR010",
        "name": "Maggiorazioni turnisti",
        "rule": "21>0 → 505=N, 565=21; 890=3-21; 890>0 → 506=T, 566=890",
        "fields": [3, 21, 505, 506, 565, 566, 890, 'K625', 'K626'],
        "description": "Le ore notturne vengono maggiorate (N, 'K626'). Le ore diurne residue vengono maggiorate (T, 'K625')",
    },
    {
        "id": "BR011",
        "name": "Arrotondamento ai quarti (standard)",
        "rule": "Minuti <15=scarta, 15-29=+0.15, 30-44=+0.35, 45-59=+0.45",
        "fields": [73, 800],
        "description": "Arrotondamento standard ai quarti d'ora per ore ordinarie e straordinarie",
    },
    {
        "id": "BR012",
        "name": "Arrotondamento FG (dal 01/06/2023)",
        "rule": "Minuti <30=scarta, 30-59=+0.30",
        "fields": [3, 73, 800, 300],
        "description": "Nuovo arrotondamento semplificato alla mezz'ora, in vigore dal 01/06/2023",
    },
    {
        "id": "BR013",
        "name": "Soglia straordinario settimanale",
        "rule": "887 = 40:00 - 772 (assenze settimanali). Se 1391 > 0 → 887 = 1391 - 772",
        "fields": [887, 889, 772, 1391, 782, 788],
        "description": "La soglia per lo straordinario è 40h meno le assenze (o le ore part-time se 1391 esiste)",
    },
    {
        "id": "BR014",
        "name": "Cap 8 ore straordinario",
        "rule": "Se 907 > 8:00 → eccesso → 915 (SB). 907 max 8:00, 915 prende l'eccedenza",
        "fields": [907, 915, 774, 800],
        "description": "Lo straordinario diurno non può superare 8 ore. L'eccedenza va in SB (2a fascia)",
    },
    {
        "id": "BR015",
        "name": "Ore notturne fascia",
        "rule": "Fascia notturna standard: 22:00 - 06:00 per tutti i contratti",
        "fields": [21, 22, 811],
        "description": "Le ore tra le 22:00 e le 06:00 sono considerate in fascia notturna",
    },
    {
        "id": "BR016",
        "name": "Totale ore settimanali",
        "rule": "'K711' = 'K601' + 'K608' (ore lavorate + assenze retribuite)",
        "fields": ['K711', 'K601', 'K608'],
        "description": "Il totale ore settimanali è la somma di ore lavorate e assenze retribuite",
    },
    {
        "id": "BR017",
        "name": "Fascia notturna festivo",
        "rule": "Se festivo (55=I) + notturno (21>0) → 'K615', 'K616', causali SF/SFN",
        "fields": [55, 21, 4, 563, 564, 'K615', 'K616', 503, 504],
        "description": "Nei festivi con ore notturne: parte notturna → SFN ('K616'), parte diurna → SF ('K615')",
    },
    {
        "id": "BR018",
        "name": "Pausa pranzo 30 min",
        "rule": "Pausa pranzo minima obbligatoria di 30 minuti",
        "fields": [3020, 811, 812],
        "description": "La pausa pranzo deve essere di almeno 30 minuti, gestita dalla subroutine 3020",
    },
]

# ============================================================
# 7. COMPREHENSIVE FIELD DESCRIPTIONS
# Tutti i campi con descrizione business-friendly
# ============================================================

FIELD_DESCRIPTIONS: Dict[int, str] = {
    1: "Ore previsionali (da contratto/piano orario)",
    2: "Ore effettive (da timbrature)",
    3: "Ore ordinarie calcolate (presenza)",
    4: "Ore straordinarie calcolate",
    5: "Ore assenza",
    20: "Fascia diurna prima del notturno",
    21: "Fascia notturna (ore lavorate di notte)",
    22: "Fascia diurna dopo il notturno",
    50: "Giorno della settimana (1=Dom, 2=Lun...7=Sab)",
    51: "Giorno del mese (GG)",
    52: "Mese (MM)",
    53: "Anno (AAAA)",
    54: "Giorno dopo festivo (1=si)",
    55: "Giorno festivo (I=si, Z=no)",
    56: "Giorno prima festivo (1=si)",
    57: "Causale festività",
    58: "Tipo turno (MATT/POME/NOTT/RIPO/OPE/CHIA)",
    70: "Funzione built-in Campo70 (operazioni speciali)",
    71: "Campo70 - 1° operando / input",
    72: "Campo70 - 2° operando / input",
    73: "Campo70 - risultato",
    74: "Campo70 - 4° operando (bonus arrotondamento)",
    75: "Campo70 - 5° operando",
    76: "Campo70 - 6° operando",
    77: "Campo70 - 7° operando",
    78: "Campo70 - 8° operando",
    79: "Memoria punto formula (riservato)",
    80: "Entrata previsionale",
    81: "Uscita previsionale",
    82: "Entrata effettiva (da timbratura)",
    83: "Uscita effettiva (da timbratura)",
    84: "Entrata calcolata",
    85: "Uscita calcolata",
    86: "Bonus arrotondamento entrata",
    87: "Frazione arrotondamento entrata (minuti)",
    88: "Bonus arrotondamento uscita",
    89: "Frazione arrotondamento uscita (minuti)",
    100: "Numero intervalli previsionali",
    111: "Entrata previsionale 1° intervallo",
    112: "Entrata previsionale 2° intervallo",
    113: "Entrata previsionale 3° intervallo",
    114: "Entrata previsionale 4° intervallo",
    141: "Uscita previsionale 1° intervallo",
    142: "Uscita previsionale 2° intervallo",
    143: "Uscita previsionale 3° intervallo",
    144: "Uscita previsionale 4° intervallo",
    200: "Numero intervalli effettivi (timbrature)",
    201: "Entrata effettiva 1° intervallo (timbratura pari)",
    202: "Uscita effettiva 1° intervallo (timbratura dispari)",
    203: "Entrata effettiva 2° intervallo",
    204: "Uscita effettiva 2° intervallo",
    205: "Entrata effettiva 3° intervallo",
    206: "Uscita effettiva 3° intervallo",
    207: "Entrata effettiva 4° intervallo",
    208: "Uscita effettiva 4° intervallo",
    209: "Entrata effettiva 5° intervallo",
    210: "Uscita effettiva 5° intervallo",
    211: "Entrata effettiva 6° intervallo",
    212: "Uscita effettiva 6° intervallo",
    213: "Entrata effettiva 7° intervallo",
    214: "Uscita effettiva 7° intervallo",
    220: "Uscita effettiva 10° intervallo",
    221: "Entrata effettiva (timbratura, usata per arrotondamento)",
    222: "Uscita effettiva (timbratura, usata per arrotondamento)",
    250: "Numero intervalli calcolati",
    251: "Entrata calcolata 1° intervallo",
    252: "Entrata calcolata 2° intervallo",
    253: "Entrata calcolata 3° intervallo",
    254: "Entrata calcolata 4° intervallo",
    255: "Entrata calcolata 5° intervallo",
    256: "Entrata calcolata 6° intervallo",
    257: "Entrata calcolata 7° intervallo",
    271: "Uscita calcolata 1° intervallo",
    272: "Uscita calcolata 2° intervallo",
    273: "Uscita calcolata 3° intervallo",
    274: "Uscita calcolata 4° intervallo",
    275: "Uscita calcolata 5° intervallo",
    276: "Uscita calcolata 6° intervallo",
    277: "Uscita calcolata 7° intervallo",
    300: "Data giornata in elaborazione (AAAAMMGG)",
    301: "Data odierna (per confronto con 300)",
    302: "Data giorno precedente",
    305: "Data limite per split logica formula",
    311: "Data giorno successivo",
    350: "Totale ore lavorate (giornaliero)",
    351: "Differenza ore lavorate - ore previsionali",
    360: "Totale ore lavorate dopo arrotondamento",
    361: "Differenza ore lavorate - previsionali (arrotondato)",
    390: "Tipo calcolo (0=normale, altro=speciale/riposo)",
    391: "Flag salva timbrature calcolate come effettive",
    400: "Numero causali manuali inserite",
    401: "Causale manuale 1 - codice",
    402: "Causale manuale 2 - codice",
    403: "Causale manuale 3 - codice",
    404: "Causale manuale 4 - codice",
    411: "Causale manuale 1 - orario inizio",
    412: "Causale manuale 2 - orario inizio",
    413: "Causale manuale 3 - orario inizio",
    414: "Causale manuale 4 - orario inizio",
    421: "Causale manuale 1 - orario fine",
    422: "Causale manuale 2 - orario fine",
    423: "Causale manuale 3 - orario fine",
    424: "Causale manuale 4 - orario fine",
    431: "Causale manuale 1 - durata (ore)",
    432: "Causale manuale 2 - durata (ore)",
    433: "Causale manuale 3 - durata (ore)",
    434: "Causale manuale 4 - durata (ore)",
    441: "Causale manuale 1 - tipo (A=assenza, P=presenza)",
    442: "Causale manuale 2 - tipo (A=assenza, P=presenza)",
    443: "Causale manuale 3 - tipo (A=assenza, P=presenza)",
    444: "Causale manuale 4 - tipo (A=assenza, P=presenza)",
    500: "Modalità calcolo totali (DURATA)",
    501: "Slot causale automatica 1 - Festività/Straord",
    502: "Slot causale automatica 2 - Notturno/Magg",
    503: "Slot causale automatica 3 - NF/LFS",
    504: "Slot causale automatica 4 - LFS/SF",
    505: "Slot causale automatica 5 - SP/N",
    506: "Slot causale automatica 6 - SA/T",
    507: "Slot causale automatica 7 - SF/SA",
    508: "Slot causale automatica 8 - SN",
    509: "Slot causale automatica 9 - SNF/SN",
    510: "Slot causale automatica 10 - SB",
    561: "Ore causale automatica - slot 1",
    562: "Ore causale automatica - slot 2",
    563: "Ore causale automatica - slot 3",
    564: "Ore causale automatica - slot 4",
    565: "Ore causale automatica - slot 5",
    566: "Ore causale automatica - slot 6",
    567: "Ore causale automatica - slot 7",
    568: "Ore causale automatica - slot 8",
    569: "Ore causale automatica - slot 9",
    570: "Ore causale automatica - slot 10",
    684: "Flag festività non goduta",
    770: "Contatore numero settimana",
    771: "Ore settimanali lavorate (3+4)",
    772: "Assenze settimanali (608+609)",
    773: "Totale lavorato + assenze settimanali",
    774: "Straordinario settimanale cumulato (907)",
    775: "Totale settimanale FG (3+4+608+609)",
    776: "Lavorato + ordinario notturno FG",
    781: "Ore previste settimanali",
    782: "Ore lavorate + assenze settimanali",
    783: "Ore straordinarie annuali cumulate",
    784: "Supplementare settimanale",
    785: "Ore lavorate settimanali",
    788: "Totale settimana corrente",
    800: "Appoggio - temp straordinario, arrotondamento",
    801: "Appoggio - temp straordinario, puntatori",
    802: "Appoggio - durata intervallo, puntatori",
    803: "Appoggio - durata, puntatori loop",
    804: "Appoggio - temp, puntatori loop",
    805: "Appoggio - assenze, temp",
    806: "Appoggio - non timbrato, temp",
    807: "Appoggio - differenza assenze, temp",
    810: "Appoggio - unità minima incremento loop (00.01)",
    811: "Appoggio - entrata intervallo per sub P2122",
    812: "Appoggio - uscita intervallo per sub P2122",
    820: "Appoggio - indice intervallo autorizzato straordinario",
    821: "Appoggio - ore autorizzate straordinario",
    887: "Soglia straordinario settimanale (40h - assenze)",
    889: "Soglia supplementare part-time",
    890: "Appoggio - ore diurne per maggiorazioni",
    900: "Flag anti-loop / indicatore turno (1=MATT, 2=POME, 3=NOTT)",
    901: "Campo output causali - riservato",
    902: "Ore ordinarie notturne ('K902')",
    903: "Ore ordinarie festive notturne ('K903')",
    904: "Ore ordinarie festive ('K904')",
    905: "Ore ordinarie ('K905')",
    906: "Ore supplementari ('K906')",
    907: "Ore straordinario diurno SA ('K907')",
    908: "Ore domenicali ordinarie ('K908')",
    909: "Ore straordinario notturno SN ('K909')",
    910: "Ore straordinario festivo notturno SNF ('K910')",
    914: "Ore straordinario festivo SF ('K914')",
    915: "Ore straordinario seconda fascia SB ('K915')",
    918: "Ore festività ('K918')",
    919: "Tipo festività (1=normale, 2=non goduta, 3=patrono, 4=FX)",
    1000: "Codice azienda",
    1051: "Festività tipo 51 (patrono) per confronto 1051 U 51",
    1052: "Festività tipo 52 (patrono) per confronto 1052 U 52",
    1100: "Codice dipendente (matricola)",
    1114: "Ore settimanali contrattuali",
    1121: "Flag straordinario non ammesso (N=non ammesso)",
    1391: "Ore ridotte part-time (da Tabella Orario)",
    1801: "Contatore giri GUGEST (anti-ciclo)",
}

# ============================================================
# 8. CAUSALE DESCRIPTIONS
# ============================================================

CAUSALE_DESCRIPTIONS: Dict[str, str] = {
    "SA": "Straordinario Diurno 1a fascia (ore diurne oltre il normale)",
    "SB": "Straordinario Diurno 2a fascia (oltre 8h, eccedenza)",
    "SN": "Straordinario Notturno (ore notturne straordinarie)",
    "SF": "Straordinario Festivo Diurno (festivo diurno straordinario)",
    "SFN": "Straordinario Festivo Notturno (festivo notturno straordinario)",
    "SNF": "Straordinario Notturno Festivo (sinonimo SFN)",
    "SP": "Supplementare (ore supplementari part-time)",
    "N": "Maggiorazione Notturna (premio per lavoro notturno)",
    "NF": "Maggiorazione Notturna Festiva (notturno in giorno festivo)",
    "T": "Maggiorazione Turno Diurno (premio turno diurno)",
    "LFS": "Lavoro Festivo Straordinario (maggiorazione festiva)",
    "F": "Festività Normale",
    "FNG": "Festività Non Goduta",
    "FP": "Festività Patrono",
    "FX": "Festività in Stipendio",
    "AUTS": "Autorizzazione Straordinario (causale manuale)",
    "MATT": "Turno Mattino (06-14)",
    "POME": "Turno Pomeriggio (14-22)",
    "NOTT": "Turno Notte (22-06)",
    "RIPO": "Riposo (giorno non lavorato)",
    "OPE": "Operaio Spezzato (2 intervalli 08-12/13-17)",
    "CHIA": "Chiamata (dipendente a chiamata)",
    "CHI": "Chiamata effettuata",
}

# ============================================================
# 9. FORMULA DESCRIPTIONS (business-oriented)
# ============================================================

FORMULA_DESCRIPTIONS: Dict[int, str] = {
    1: "Azzeramento iniziale del flag turno (900) all'inizio della giornata",
    5: "Riconoscimento automatico del turno dalle timbrature effettive (MATT/POME/NOTT)",
    10: "Riconoscimento del turno dall'orario calcolato (variante Di Giornata)",
    100: "Prima formula FG: imposta modalità DURATA e azzera causali automatiche",
    110: "Riproporziona ore ordinarie/straordinario/assenze in base al totale lavorato",
    120: "Smistatore centrale: indirizza a 130 (festivo) o 140 (ordinario) in base al giorno",
    130: "Gestione straordinario in giorno festivo: separa notturno (SFN) da diurno (SF)",
    140: "Gestione straordinario in giorno ordinario: separa notturno (SN) da diurno (S)",
    200: "Formula finale FG: accumula ore ordinarie in 'K601'/'K602', chiama maggiorazioni",
    210: "Calcolo maggiorazioni turnisti: notturna (N) e diurna (T) con accumulo 'K626'/'K625'",
    1000: "IG Dirigenti: copia orario previsionale in calcolato per non-timbratori",
    1010: "IG Quadri: copia previsionale solo se non ci sono timbrature effettive",
    1020: "IG timbratura singola: interpreta ogni timbratura come entrata o uscita",
    1100: "FG Dirigenti/Quadri: gestisce assenze riducendo le ore calcolate",
    1120: "FG timbratura singola: gestione assenze parziali su 2 intervalli",
    2000: "FG chiamata: se non timbrato→RIPO, altrimenti copia e somma veloce",
    2050: "IG Conad: arrotondamento entrate alla mezz'ora/ora, chiama 2051 o 2060",
    2051: "IG Conad: arrotondamento uscite alla mezz'ora (1° e 2° intervallo)",
    2060: "IG Conad (dal 2023): cap uscite a 20:05 per tutti gli intervalli",
    2100: "GUGEST 1A: primo giro settimanale, soglie, accumulo base, chiama P2109",
    2101: "GUGEST 2A: secondo giro, calcolo per intervallo con P2122, arrotondamenti, causali",
    2105: "GUGEST 1B: come 2100 ma con loop intervalli già in 1° giro",
    2106: "GUGEST 2B: identico a 2101",
    2107: "Calcolo ore intervallo con arrotondamento ai quarti e classificazione",
    2109: "Gestione festività automatiche (tipo 1/2/3), accumulo 'K918'/'K630'/'K608'",
    2114: "Ritocco SA/SB: se straordinario > 8h, scorpora eccedenza in SB",
    2115: "Esplosione causali automatiche: assegna codici agli slot 501-510",
    2122: "Calcolo ore per singolo intervallo: classifica in 902-910 minuto per minuto",
    2123: "Arrotondamento quarti d'ora per ore ordinarie/festive (902-905, 908)",
    2124: "Arrotondamento quarti d'ora per ore straordinarie (906-907, 909-910, 914)",
    2130: "Warning: alert settimana con ore carenti e avvicinamento 250h annuali",
    3000: "FG 1: come 2100 ma con split data 01/06/2023 e P3009/P3002/P3003",
    3001: "FG NEW: calcolo completo con P3005/P3014/P3015/P3030 e gestione assenze domenica",
    3002: "Arrotondamento FG ante 01/06/2023: doppio livello in base a soglia 775",
    3003: "Arrotondamento FG dal 01/06/2023: semplificato, solo soglia 30 min",
    3004: "Riclassifica ore: sposta straordinario diurno (907) in festivo (914)",
    3005: "Calcolo straordinario settimanale: confronto 788 con soglia 887",
    3009: "Gestione festività variante B: include tipo FX (919=4)",
    3014: "Ritocco SA/SB variante B: logica più precisa per scorporo SB",
    3015: "Esplosione causali variante B: include FX (festività in stipendio)",
    3017: "Gestione AUTS: legge autorizzazioni straordinario da causali manuali",
    3020: "Gestione pausa pranzo: ricalcolo e forzatura 30 minuti",
    3030: "Warning variante B: identico a 2130, usato dal sistema FG 3xxx",
    9001: "Arrotondamento impiegati I: arrotonda tutti gli intervalli tranne l'ultimo",
    9002: "Arrotondamento impiegati II: sistema l'ultimo intervallo per far quadrare il totale",
}

# ============================================================
# 10. TIPO_TURNO_DESCRIPTIONS
# ============================================================

TIPO_TURNO_DESCRIPTIONS: Dict[str, str] = {
    "MATT": "Turno Mattino (06:00-14:00)",
    "POME": "Turno Pomeriggio (14:00-22:00)",
    "NOTT": "Turno Notte (22:00-06:00)",
    "RIPO": "Riposo (giorno non lavorato)",
    "OPE": "Operaio Spezzato (08-12 e 13-17, 2 intervalli)",
    "CHIA": "Chiamata (dipendente senza orario fisso)",
    "CHI": "Chiamata effettuata nel giorno corrente",
}

# ============================================================
# 11. QUERY EXPANDER
# Funzione principale: espande una query NL con il glossario
# ============================================================

def expand_query(user_request: str) -> Dict:
    """Espande una richiesta utente con contesto dal glossario.

    Analizza la richiesta, trova concetti di business riconosciuti,
    e restituisce:
    - I campi WinSarp coinvolti
    - Le formule correlate
    - Le causali correlate
    - Le business rules applicabili
    - Gli scenari matching
    - I sinonimi espansi

    Args:
        user_request: Richiesta in linguaggio naturale

    Returns:
        Dict con contesto arricchito per il classificatore LLM
    """
    low = user_request.lower()

    # Risolvi i sinonimi con word-boundary (evita match spuri tipo 'sa' in 'salve')
    resolved_text = resolve_synonyms(user_request)
    resolved_low = resolved_text.lower()

    # Trova concetti menzionati (sia nella query originale sia in quella risolta)
    matched_concepts = {}
    for concept, mapping in CONCEPT_TO_FIELD.items():
        if concept in low or concept in resolved_low:
            matched_concepts[concept] = mapping

    # Trova sinonimi e risolvi a concetti canonici (raccolti per dopo).
    # Usa resolve_synonyms (word-boundary per sigle) per evitare match spuri
    # tipo 'sa' dentro 'salve'.
    matched_synonyms = {}
    resolved_canonicals = set()
    # Rilevamento sinonimi con word-boundary coerente a resolve_synonyms
    import re as _re
    for synonym, canonical in SYNONYM_MAP.items():
        is_short = (" " not in synonym and len(synonym) <= 3)
        if is_short:
            patt = r"(?<![a-z0-9])" + _re.escape(synonym) + r"(?![a-z0-9])"
            if _re.search(patt, low):
                matched_synonyms[synonym] = canonical
                resolved_canonicals.add(canonical)
        else:
            if synonym in low:
                matched_synonyms[synonym] = canonical
                resolved_canonicals.add(canonical)
        # Se il canonico non è già matchato, aggiungilo ai concetti campo
        if canonical in matched_concepts or canonical in resolved_canonicals:
            if canonical not in matched_concepts and canonical in CONCEPT_TO_FIELD:
                matched_concepts[canonical] = CONCEPT_TO_FIELD[canonical]

    # Trova formule correlate (nella query originale o risolta)
    matched_formulas = {}
    for concept, mapping in CONCEPT_TO_FORMULA.items():
        if concept in low or concept in resolved_low:
            matched_formulas[concept] = mapping

    # Trova causali menzionate
    matched_causali = {}
    for concept, mapping in CONCEPT_TO_CAUSALE.items():
        if concept in low or concept in resolved_low:
            matched_causali[concept] = mapping

    # Applica i concetti canonici risolti dai sinonimi anche a formule/causali
    for canonical in resolved_canonicals:
        if canonical in CONCEPT_TO_FORMULA and canonical not in matched_formulas:
            matched_formulas[canonical] = CONCEPT_TO_FORMULA[canonical]
        if canonical in CONCEPT_TO_CAUSALE and canonical not in matched_causali:
            matched_causali[canonical] = CONCEPT_TO_CAUSALE[canonical]

    # Trova scenari matching
    matched_scenarios = {}
    for name, scenario in SCENARIO_FLOWS.items():
        # Matcha se la descrizione o le parole chiave appaiono nella richiesta
        desc = scenario["description"].lower()
        if any(term in low for term in desc.split()) or name.replace("_", " ") in low:
            matched_scenarios[name] = scenario

    # Trova business rules applicabili
    matched_rules = []
    for rule in BUSINESS_RULES:
        rule_words = rule["name"].lower().split()
        if any(w in low for w in rule_words):
            matched_rules.append(rule)

    # Aggrega tutti i campi unici
    all_fields = set()
    for m in matched_concepts.values():
        for f in m.get("fields", []):
            if isinstance(f, int):
                all_fields.add(f)

    all_formulas = set()
    for m in matched_formulas.values():
        for f in m.get("formulas", []):
            all_formulas.add(f)

    all_causali = set()
    for m in matched_causali.values():
        for c in m.get("codes", []):
            all_causali.add(c)

    # Costruisci contesto testuale per prompt
    context_parts = []

    if matched_concepts:
        context_parts.append("CONCETTI RICONOSCIUTI:")
        for concept, mapping in matched_concepts.items():
            fields_str = ", ".join(str(f) for f in mapping.get("fields", []))
            context_parts.append(f"  - '{concept}': campi [{fields_str}] — {mapping['description']}")

    if all_fields:
        context_parts.append("\nCAMPI COINVOLTI (con descrizione):")
        for f in sorted(all_fields):
            desc = FIELD_DESCRIPTIONS.get(f, "")
            if desc:
                context_parts.append(f"  - Campo {f}: {desc}")

    if matched_synonyms:
        context_parts.append("\nSINONIMI RICONOSCIUTI:")
        for syn, can in matched_synonyms.items():
            context_parts.append(f"  - '{syn}' → '{can}'")

    if matched_causali:
        context_parts.append("\nCAUSALI CORRELATE:")
        for concept, mapping in matched_causali.items():
            codes = ", ".join(mapping["codes"])
            context_parts.append(f"  - '{concept}': codici [{codes}] — {mapping['description']}")

    if all_causali:
        context_parts.append("\nDETTAGLIO CAUSALI:")
        for c in sorted(all_causali):
            desc = CAUSALE_DESCRIPTIONS.get(c, "")
            if desc:
                context_parts.append(f"  - {c}: {desc}")

    if matched_formulas:
        context_parts.append("\nFORMULE CORRELATE:")
        for concept, mapping in matched_formulas.items():
            formulas = ", ".join(str(f) for f in mapping["formulas"])
            context_parts.append(f"  - '{concept}': formule [{formulas}] ({mapping['fase']})")
            context_parts.append(f"    {mapping['description']}")

    if matched_scenarios:
        context_parts.append("\nSCENARI RICONOSCIUTI:")
        for name, scenario in matched_scenarios.items():
            context_parts.append(f"  - {scenario['description']}:")
            for flow in scenario["flows"]:
                forms = ", ".join(str(f) for f in flow["formulas"])
                context_parts.append(f"    {flow['name']}: [{forms}] — {flow['description']}")
            if "subroutines" in scenario:
                subs = ", ".join(str(f) for f in scenario["subroutines"])
                context_parts.append(f"    Subroutine chiamate: [{subs}]")
            if "key_conditions" in scenario:
                context_parts.append(f"    Condizioni: {scenario['key_conditions']}")

    if matched_rules:
        context_parts.append("\nREGOLE DI CALCOLO APPLICABILI:")
        for rule in matched_rules:
            context_parts.append(f"  - {rule['name']}: {rule['rule']}")
            context_parts.append(f"    {rule['description']}")

    context_text = "\n".join(context_parts)

    return {
        "matched_concepts": list(matched_concepts.keys()),
        "matched_synonyms": matched_synonyms,
        "matched_causali": list(matched_causali.keys()),
        "matched_formulas": list(matched_formulas.keys()),
        "matched_scenarios": list(matched_scenarios.keys()),
        "matched_rules": [r["id"] for r in matched_rules],
        "fields": sorted(all_fields),
        "formulas": sorted(all_formulas),
        "causali": sorted(all_causali),
        "context_text": context_text,
        "expanded_query": _build_expanded_query(user_request, matched_concepts, matched_synonyms, all_fields, all_formulas, all_causali),
    }


def _build_expanded_query(
    original: str,
    concepts: Dict,
    synonyms: Dict,
    fields: set,
    formulas: set,
    causali: set,
) -> str:
    """Costruisce una versione arricchita della query originale.

    Aggiunge alla fine della richiesta originale un riepilogo
    dei riferimenti tecnici WinSarp trovati, per aiutare l'LLM
    a classificare meglio.
    """
    parts = [original]

    if fields or formulas or causali:
        refs = []
        if fields:
            refs.append(f"campi: [{', '.join(str(f) for f in sorted(fields)[:10])}]")
        if formulas:
            refs.append(f"formule: [{', '.join(str(f) for f in sorted(formulas)[:5])}]")
        if causali:
            refs.append(f"causali: [{', '.join(sorted(causali)[:5])}]")
        parts.append(f"\n[Glossario: {'; '.join(refs)}]")

    return "\n".join(parts)


# ============================================================
# UTILITY: Resolve alias e sinonimi in una query
# ============================================================

def resolve_synonyms(text: str) -> str:
    """Sostituisce i sinonimi con i termini canonici nella query.

    - Chiavi lunghe (>3 char) o con spazi: matcha come sottostringa.
    - Chiavi brevi (sigle come 'n', 't', 'sa', 'sf'): matcha solo come
      parola intera (word boundary) per evitare cascate dentro altre parole
      (es. 'n' dentro 'con', 'sa' dentro 'cosa').
    Ordina per lunghezza decrescente, sostituisce una sola volta (no ricorsione).
    """
    import re as _re
    result = text.lower()
    # Ordina: prima le più lunghe per non frammentare le frasi
    for synonym in sorted(SYNONYM_MAP.keys(), key=len, reverse=True):
        if " " in synonym or len(synonym) > 3:
            # Sostituzione sottostringa per frasi
            if synonym in result:
                result = result.replace(synonym, SYNONYM_MAP[synonym])
        else:
            # Sigla breve: solo parola intera
            pattern = r"(?<![a-z0-9])" + _re.escape(synonym) + r"(?![a-z0-9])"
            result = _re.sub(pattern, SYNONYM_MAP[synonym], result)
    return result


def get_concept_for_field(field_num: int) -> List[str]:
    """Trova tutti i concetti di business che referenziano un campo."""
    concepts = []
    for concept, mapping in CONCEPT_TO_FIELD.items():
        if field_num in mapping.get("fields", []):
            concepts.append(concept)
    return concepts


def get_formula_for_field(field_num: int) -> List[int]:
    """Trova le formule che lavorano su un dato campo."""
    formulas = set()
    for concept, mapping in CONCEPT_TO_FORMULA.items():
        for f in mapping.get("formulas", []):
            for m in CONCEPT_TO_FIELD.get(concept, {}).get("fields", []):
                if m == field_num:
                    formulas.add(f)
    return sorted(formulas)
