"""
Field Registry — Conoscenza completa di tutti i campi, operatori e tabelle WinSarp.

Carica conoscenza strutturata da WinsarpGrammatica.txt e grammatica_compatta.txt,
integrata con i dati del workbook per fornire un modello di dominio completo.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

# ============================================================
# Tipi di campo
# ============================================================

FIELD_TYPE_TIMBRATURA = "timbratura"
FIELD_TYPE_CALCOLATA = "calcolata"
FIELD_TYPE_PREVISIONALE = "prevvisionale"
FIELD_TYPE_TOTALE = "totale"
FIELD_TYPE_FLAG = "flag"
FIELD_TYPE_CAUSALE = "causale"
FIELD_TYPE_APPOGGIO = "appoggio"
FIELD_TYPE_SISTEMA = "sistema"
FIELD_TYPE_K_TOTALE = "k_totale"


# ============================================================
# Modelli dati
# ============================================================

@dataclass
class FieldInfo:
    number: int
    name: str
    description: str
    field_type: str
    range_start: int | None = None
    range_end: int | None = None
    is_entrata: bool = False
    is_uscita: bool = False
    sub_fields: dict[int, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class Campo70Op:
    code: str
    name: str
    description: str
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class KTotalInfo:
    number: int
    name: str
    description: str
    num_tot: int | None = None


@dataclass
class ContractInfo:
    number: int
    name: str
    description: str
    timbra: bool = True
    max_entry_offset: str | None = None


@dataclass
class ArrayDef:
    id: str
    description: str
    start: int
    end: int
    paired_with: str | None = None
    is_entrata: bool = False
    is_uscita: bool = False


# ============================================================
# Registry completo
# ============================================================

class FieldRegistry:
    """Registro esaustivo di tutti i campi, operatori, totali e tabelle WinSarp."""

    # Campi individuali
    FIELDS: dict[int, FieldInfo] = {}
    # Array/Range definiti
    ARRAY_DEFS: dict[str, ArrayDef] = {}
    # Operazioni CAMPO70
    CAMPO70_OPS: dict[str, Campo70Op] = {}
    # ...

    def __init__(self) -> None:
        if not self.FIELDS:
            self._initialize()
    def _initialize(self) -> None:
        self._build_field_index()
        self._build_array_defs()  # NUOVO
        self._build_campo70_ops()
        self._build_k_totals()
        self._build_contracts()
        self._build_ranges()
        self._load_grammar()

    def _build_array_defs(self) -> None:
        """Definisce la struttura a matrice del tabellone."""
        self.ARRAY_DEFS = {
            "Prev": ArrayDef("Previsionale", "prev", 111, 150),
            "EntrateEff": ArrayDef("Entrate Effettive", "entrate_eff", 201, 220, paired_with="UsciteEff", is_entrata=True),
            "UsciteEff": ArrayDef("Uscite Effettive", "uscite_eff", 221, 240, paired_with="EntrateEff", is_uscita=True),
            "EntrateCalc": ArrayDef("Entrate Calcolate", "entrate_calc", 251, 270, paired_with="UsciteCalc", is_entrata=True),
            "UsciteCalc": ArrayDef("Uscite Calcolate", "uscite_calc", 271, 290, paired_with="EntrateCalc", is_uscita=True),
        }

    def get_array_containing_field(self, field_id: int) -> ArrayDef | None:
        for arr in self.ARRAY_DEFS.values():
            if arr.start <= field_id <= arr.end:
                return arr
        return None

    def _build_field_index(self) -> None:
        """Costruisce il database completo dei campi 1-999+."""
        fields: dict[int, FieldInfo] = {}

        # Totali giornalieri 1-6
        for n, desc in [(1, "Ore Previsionali (target giornaliero)"),
                        (2, "Ore Effettive (differenza orario effettivo)"),
                        (3, "Ore Calcolate (normalmente ordinarie)"),
                        (4, "Ore Straordinarie"),
                        (5, "Ore Assenza"),
                        (6, "Ore Assenza per controllo straordinario")]:
            fields[n] = FieldInfo(number=n, name=f"Campo{n}", description=desc, field_type=FIELD_TYPE_TOTALE)

        # Campi 7-19 = NON USARE
        for n in range(7, 20):
            fields[n] = FieldInfo(number=n, name=f"Campo{n}", description="NON USARE (riservato)", field_type=FIELD_TYPE_SISTEMA)

        # Fascia notturna 20-22
        fields[20] = FieldInfo(number=20, name="FasciaDiurnaPrima", description="Fascia diurna prima del notturno", field_type=FIELD_TYPE_TOTALE)
        fields[21] = FieldInfo(number=21, name="FasciaNotturna", description="Fascia notturna", field_type=FIELD_TYPE_TOTALE)
        fields[22] = FieldInfo(number=22, name="FasciaDiurnaDopo", description="Fascia diurna dopo del notturno", field_type=FIELD_TYPE_TOTALE)

        # Campi 23-49 = non documentati / liberi
        for n in range(23, 50):
            fields[n] = FieldInfo(number=n, name=f"Campo{n}", description="Campo generico", field_type=FIELD_TYPE_APPOGGIO)

        # Considerazioni sul giorno 50-58
        fields[50] = FieldInfo(number=50, name="GiornoSettimana", description="Giorno della settimana (1=dom, 7=sab)", field_type=FIELD_TYPE_FLAG)
        fields[51] = FieldInfo(number=51, name="GiornoGG", description="Giorno in elaborazione (GG)", field_type=FIELD_TYPE_FLAG)
        fields[52] = FieldInfo(number=52, name="MeseMM", description="Mese in elaborazione (MM)", field_type=FIELD_TYPE_FLAG)
        fields[53] = FieldInfo(number=53, name="AnnoAAAA", description="Anno in elaborazione (AAAA)", field_type=FIELD_TYPE_FLAG)
        fields[54] = FieldInfo(number=54, name="GiornoDopoFestivo", description="1 se giorno successivo a giorno festivo", field_type=FIELD_TYPE_FLAG)
        fields[55] = FieldInfo(number=55, name="GiornoFestivo", description="I se giorno festivo", field_type=FIELD_TYPE_FLAG, aliases=["FestivoFlag"])
        fields[56] = FieldInfo(number=56, name="GiornoPrimaFestivo", description="1 se giorno precedente a giorno festivo", field_type=FIELD_TYPE_FLAG)
        fields[57] = FieldInfo(number=57, name="CausaleFestivita", description="Causale di festività", field_type=FIELD_TYPE_CAUSALE)
        fields[58] = FieldInfo(number=58, name="TipoOrario", description="Tipo orario (da Turni Dipendenti: MATT/POME/NOTT/RIPO/OPE/CHIA)", field_type=FIELD_TYPE_FLAG, aliases=["TipoTurno"])

        # CAMPO70 operativo 70-79
        fields[70] = FieldInfo(number=70, name="Campo70", description="Definisce il tipo di operazione (vedi CAMPO70_OPS)", field_type=FIELD_TYPE_SISTEMA)
        for i in range(71, 79):
            fields[i] = FieldInfo(number=i, name=f"Campo70_InOut{i}", description="Input/Output per operazione Campo70", field_type=FIELD_TYPE_SISTEMA,
                                  aliases=["Campo70_Tmp"])
        fields[79] = FieldInfo(number=79, name="MemoriaPuntoFormula", description="RISERVATO — memoria punto formula", field_type=FIELD_TYPE_SISTEMA)

        # Formula di giornata 80-89
        fields[80] = FieldInfo(number=80, name="EntrataPrevisionale", description="Entrata Previsionale", field_type=FIELD_TYPE_PREVISIONALE, is_entrata=True)
        fields[81] = FieldInfo(number=81, name="UscitaPrevisionale", description="Uscita Previsionale", field_type=FIELD_TYPE_PREVISIONALE, is_uscita=True)
        fields[82] = FieldInfo(number=82, name="EntrataEffettiva", description="Entrata Effettiva", field_type=FIELD_TYPE_TIMBRATURA, is_entrata=True)
        fields[83] = FieldInfo(number=83, name="UscitaEffettiva", description="Uscita Effettiva", field_type=FIELD_TYPE_TIMBRATURA, is_uscita=True)
        fields[84] = FieldInfo(number=84, name="EntrataCalcolata", description="Entrata Calcolata", field_type=FIELD_TYPE_CALCOLATA, is_entrata=True)
        fields[85] = FieldInfo(number=85, name="UscitaCalcolata", description="Uscita Calcolata", field_type=FIELD_TYPE_CALCOLATA, is_uscita=True)
        fields[86] = FieldInfo(number=86, name="BonusArrotondamentoEntrata", description="Bonus arrotondamento generale ENTRATA", field_type=FIELD_TYPE_TOTALE)
        fields[87] = FieldInfo(number=87, name="FrazioneArrotondamentoEntrata", description="Frazione arrotondamento (minuti) generale ENTRATA", field_type=FIELD_TYPE_TOTALE)
        fields[88] = FieldInfo(number=88, name="BonusArrotondamentoUscita", description="Bonus arrotondamento generale USCITA", field_type=FIELD_TYPE_TOTALE)
        fields[89] = FieldInfo(number=89, name="FrazioneArrotondamentoUscita", description="Frazione arrotondamento (minuti) generale USCITA", field_type=FIELD_TYPE_TOTALE)
        for n in range(90, 100):
            fields[n] = FieldInfo(number=n, name=f"Campo{n}", description="NON USARE (riservato)", field_type=FIELD_TYPE_SISTEMA)

        # Orario previsionale 100-160
        fields[100] = FieldInfo(number=100, name="IntervalliPrev", description="Intervalli di lavoro Previsionali", field_type=FIELD_TYPE_PREVISIONALE)
        for i in range(1, 11):
            fields[100 + i] = FieldInfo(number=100 + i, name=f"DalleEntrata_{i}", description=f"Dalle entrata intervallo {i}", field_type=FIELD_TYPE_PREVISIONALE)
            fields[110 + i] = FieldInfo(number=110 + i, name=f"Entrata_{i}", description=f"ENTRATA intervallo {i}", field_type=FIELD_TYPE_PREVISIONALE, is_entrata=True)
            fields[120 + i] = FieldInfo(number=120 + i, name=f"AlleEntrata_{i}", description=f"Alle entrata intervallo {i}", field_type=FIELD_TYPE_PREVISIONALE)
            fields[130 + i] = FieldInfo(number=130 + i, name=f"DalleUscita_{i}", description=f"Dalle uscita intervallo {i}", field_type=FIELD_TYPE_PREVISIONALE)
            fields[140 + i] = FieldInfo(number=140 + i, name=f"Uscita_{i}", description=f"USCITA intervallo {i}", field_type=FIELD_TYPE_PREVISIONALE, is_uscita=True)
            fields[150 + i] = FieldInfo(number=150 + i, name=f"AlleUscita_{i}", description=f"Alle uscita intervallo {i}", field_type=FIELD_TYPE_PREVISIONALE)

        # Orario effettivo 200-240
        fields[200] = FieldInfo(number=200, name="IntervalliEff", description="Intervalli di lavoro effettivi", field_type=FIELD_TYPE_TIMBRATURA)
        for i in range(1, 21):
            fields[200 + i] = FieldInfo(number=200 + i, name=f"EntrataEff_{i}", description=f"Entrata effettiva intervallo {i}", field_type=FIELD_TYPE_TIMBRATURA, is_entrata=True)
            fields[220 + i] = FieldInfo(number=220 + i, name=f"UscitaEff_{i}", description=f"Uscita effettiva intervallo {i}", field_type=FIELD_TYPE_TIMBRATURA, is_uscita=True)

        # Orario calcolato 250-290
        fields[250] = FieldInfo(number=250, name="IntervalliCalc", description="Intervalli di lavoro calcolati", field_type=FIELD_TYPE_CALCOLATA)
        for i in range(1, 21):
            fields[250 + i] = FieldInfo(number=250 + i, name=f"EntrataCalc_{i}", description=f"Entrata calcolata intervallo {i}", field_type=FIELD_TYPE_CALCOLATA, is_entrata=True)
            fields[270 + i] = FieldInfo(number=270 + i, name=f"UscitaCalc_{i}", description=f"Uscita calcolata intervallo {i}", field_type=FIELD_TYPE_CALCOLATA, is_uscita=True)

        # Campi 300-399
        fields[300] = FieldInfo(number=300, name="DataGiornata", description="Data giornata in elaborazione (AAAAMMGG)", field_type=FIELD_TYPE_FLAG)
        fields[301] = FieldInfo(number=301, name="DataOggi", description="Data odierna (AAAAMMGG) per confronto 300 U 301", field_type=FIELD_TYPE_FLAG)
        fields[302] = FieldInfo(number=302, name="DataIeri", description="Data giorno precedente (AAAAMMGG) per confronto 300 U 302", field_type=FIELD_TYPE_FLAG)
        fields[305] = FieldInfo(number=305, name="DataLimiteFormula", description="Data limite per split logica formula (es. 01/06/2023)", field_type=FIELD_TYPE_FLAG)
        fields[311] = FieldInfo(number=311, name="DataDomani", description="Data giorno successivo (AAAAMMGG) per confronto 300 U 311", field_type=FIELD_TYPE_FLAG)
        fields[350] = FieldInfo(number=350, name="TotaleOreLavorate", description="Totale Ore Lavorate", field_type=FIELD_TYPE_TOTALE)
        fields[351] = FieldInfo(number=351, name="DiffOreLavPrev", description="Differenza Ore Lavorate - Ore Previsionali", field_type=FIELD_TYPE_TOTALE)
        fields[360] = FieldInfo(number=360, name="TotaleOreLavArrot", description="Totale Ore Lavorate dopo arrotondamento", field_type=FIELD_TYPE_TOTALE)
        fields[361] = FieldInfo(number=361, name="DiffOreLavPrevArrot", description="Differenza Ore Lavorate - Ore Previsionali (arrot.)", field_type=FIELD_TYPE_TOTALE)
        fields[390] = FieldInfo(number=390, name="TipoCalcolo", description="TipoCalcolo (0=normale, altro=speciale)", field_type=FIELD_TYPE_FLAG)
        fields[391] = FieldInfo(number=391, name="FlagSalvaCalcolate", description="Flag salva timbrature calcolate come effettive", field_type=FIELD_TYPE_FLAG)

        # Campi 400-499 causali manuali
        fields[400] = FieldInfo(number=400, name="NumCausaliMan", description="Numero di causali manuali imputate", field_type=FIELD_TYPE_CAUSALE)
        for i in range(1, 11):
            fields[400 + i] = FieldInfo(number=400 + i, name=f"CausaleCodice_{i}", description=f"Codice causale manuale {i}", field_type=FIELD_TYPE_CAUSALE)
            fields[410 + i] = FieldInfo(number=410 + i, name=f"CausaleInizio_{i}", description=f"Orario Inizio causale manuale {i}", field_type=FIELD_TYPE_CAUSALE)
            fields[420 + i] = FieldInfo(number=420 + i, name=f"CausaleFine_{i}", description=f"Orario Fine causale manuale {i}", field_type=FIELD_TYPE_CAUSALE)
            fields[430 + i] = FieldInfo(number=430 + i, name=f"CausaleDurata_{i}", description=f"Durata causale manuale {i}", field_type=FIELD_TYPE_CAUSALE)
            fields[440 + i] = FieldInfo(number=440 + i, name=f"CausaleTipo_{i}", description=f"Tipo causale manuale {i} (A=ASSENZA, P=PRESENZA)", field_type=FIELD_TYPE_CAUSALE)

        # Campi 500-599 causali automatiche
        fields[500] = FieldInfo(number=500, name="ModalitaCalcolo", description="Modalità di calcolo totali (DURATA)", field_type=FIELD_TYPE_CAUSALE)
        for i in range(1, 11):
            fields[500 + i] = FieldInfo(number=500 + i, name=f"CausaleAuto_{i}", description=f"Causale automatica slot {i} (S/SN/N/NF/SA/SP/SF/SB/LFS/F/FNG/FP/FX)", field_type=FIELD_TYPE_CAUSALE)
            fields[510 + i] = FieldInfo(number=510 + i, name=f"OreCausaleAuto_{i}", description=f"Ore causale automatica per tipo {i}", field_type=FIELD_TYPE_CAUSALE)
        for i in range(1, 11):
            fields[560 + i] = FieldInfo(number=560 + i, name=f"OreCausale_{i}", description=f"Ore causale automatica {i} (561=ordinario, 562=suppl, 563=SF, 564=SFN, 565=N, 566=T, 567=SNF, ...)", field_type=FIELD_TYPE_CAUSALE)

        # Totali giornalieri 600-799
        fields[600] = FieldInfo(number=600, name="PrimoTotaleProgr", description="Numero del primo totale progressivo", field_type=FIELD_TYPE_K_TOTALE)
        for n in range(601, 800):
            fields[n] = FieldInfo(number=n, name=f"Totale_{n}", description=f"Totale giornaliero/progressivo {n}", field_type=FIELD_TYPE_K_TOTALE)

        # Campi di appoggio 800-999
        for n in range(800, 1000):
            desc = "Campo di appoggio (libero per calcoli custom)"
            if n == 800:
                desc = "Campo appoggio 800 (temp straordinario, accumulo arrotondamento)"
            elif n == 801:
                desc = "Campo appoggio 801 (temp straordinario, puntatori)"
            elif n == 802:
                desc = "Campo appoggio 802 (durata intervallo, puntatori)"
            elif n == 803:
                desc = "Campo appoggio 803 (durata, puntatori loop)"
            elif n == 804:
                desc = "Campo appoggio 804 (temp, puntatori loop)"
            elif n == 805:
                desc = "Campo appoggio 805 (assenze, temp)"
            elif n == 806:
                desc = "Campo appoggio 806 (non timbrato, temp)"
            elif n == 807:
                desc = "Campo appoggio 807 (diff assenze, temp)"
            elif n == 810:
                desc = "Campo appoggio 810 (unita minima incremento loop)"
            elif n == 811:
                desc = "Campo appoggio 811 (entrata intervallo per subroutine)"
            elif n == 812:
                desc = "Campo appoggio 812 (uscita intervallo per subroutine)"
            elif n == 820:
                desc = "Campo appoggio 820 (indice intervallo autorizzato straord)"
            elif n == 821:
                desc = "Campo appoggio 821 (ore autorizzate straordinario)"
            elif n == 887:
                desc = "Campo appoggio 887 (soglia straordinario settimanale)"
            elif n == 889:
                desc = "Campo appoggio 889 (soglia supplementare part-time)"
            elif n == 890:
                desc = "Campo appoggio 890 (maggiorazione diurna)"
            elif n == 900:
                desc = "Flag anti-loop / indicatore turno (1=MATT, 2=POME, 3=NOTT)"
            fields[n] = FieldInfo(number=n, name=f"Appoggio{n}", description=desc, field_type=FIELD_TYPE_APPOGGIO)

        # Campi 1000-1114
        fields[1000] = FieldInfo(number=1000, name="CodiceAzienda", description="Codice azienda", field_type=FIELD_TYPE_FLAG)
        fields[1051] = FieldInfo(number=1051, name="FestivitaTipo51", description="Festività tipo 51 (patrono) per confronto 1051 U 51", field_type=FIELD_TYPE_FLAG)
        fields[1052] = FieldInfo(number=1052, name="FestivitaTipo52", description="Festività tipo 52 (patrono) per confronto 1052 U 52", field_type=FIELD_TYPE_FLAG)
        fields[1100] = FieldInfo(number=1100, name="CodiceDipendente", description="Codice dipendente", field_type=FIELD_TYPE_FLAG)
        fields[1114] = FieldInfo(number=1114, name="OreSettimanaliContr", description="Ore settimanali contrattuali", field_type=FIELD_TYPE_TOTALE)
        fields[1121] = FieldInfo(number=1121, name="FlagStraordNonAmmesso", description="Flag straordinario non ammesso (N=sì)", field_type=FIELD_TYPE_FLAG)
        fields[1391] = FieldInfo(number=1391, name="OreRidottePartTime", description="Ore ridotte part-time (da Tabella Orario)", field_type=FIELD_TYPE_TOTALE)
        fields[1801] = FieldInfo(number=1801, name="ContatoreGiriGugest", description="Contatore giri GUGEST (anticiclo)", field_type=FIELD_TYPE_APPOGGIO)

        self.FIELDS = fields

    def _build_campo70_ops(self) -> None:
        self.CAMPO70_OPS = {
            "1": Campo70Op(code="1", name="SommaOre",
                           description="Somma orari sessagesimali: 71 + 72 -> 73",
                           inputs={"71": "Primo addendo (hh.mm)", "72": "Secondo addendo (hh.mm)"},
                           outputs={"73": "Risultato somma (hh.mm)"}),
            "2": Campo70Op(code="2", name="DifferenzaOre",
                           description="Differenza orari sessagesimali: 71 - 72 -> 73",
                           inputs={"71": "Minuendo (hh.mm)", "72": "Sottraendo (hh.mm)"},
                           outputs={"73": "Risultato differenza (hh.mm)"}),
            "3": Campo70Op(code="3", name="SeparaOreMinuti",
                           description="Separa ore da minuti: 71 -> 72=ore, 73=minuti",
                           inputs={"71": "Orario in hh.mm"},
                           outputs={"72": "Ore (parte intera)", "73": "Minuti (parte decimale * 100)"}),
            "4": Campo70Op(code="4", name="OrarioInMinuti",
                           description="Trasforma orario (hh.mm) in minuti: 71 -> 73=minuti totali",
                           inputs={"71": "Orario in hh.mm"},
                           outputs={"73": "Minuti totali"}),
            "5": Campo70Op(code="5", name="MinutiInOrario",
                           description="Trasforma minuti in orario (hh.mm): 71=minuti -> 73=hh.mm",
                           inputs={"71": "Minuti totali"},
                           outputs={"73": "Orario in hh.mm"}),
            "8": Campo70Op(code="8", name="CentesimiInSessagesimi",
                           description="Da centesimi a sessagesimi: 71(hh.cc) -> 73(hh.mm)",
                           inputs={"71": "Orario in centesimi"},
                           outputs={"73": "Orario in sessagesimi"}),
            "9": Campo70Op(code="9", name="SessagesimiInCentesimi",
                           description="Da sessagesimi a centesimi: 71(hh.mm) -> 73(hh.cc)",
                           inputs={"71": "Orario in sessagesimi"},
                           outputs={"73": "Orario in centesimi"}),
            "11": Campo70Op(code="11", name="DurataIntervallo",
                           description="Durata intervallo (timbrature, gestisce mezzanotte): 71=Entrata, 72=Uscita -> 73=durata",
                           inputs={"71": "Entrata (hh.mm)", "72": "Uscita (hh.mm)"},
                           outputs={"73": "Durata intervallo in hh.mm (gestisce passaggio mezzanotte 23:xx-00:xx)"}),
            "20": Campo70Op(code="20", name="ArrotondaEntrata",
                           description="Arrotonda orario di ENTRATA: 71 con approssimazione 72, offset 73, bonus 74 -> 71 arrotondato",
                           inputs={"71": "Orario entrata", "72": "Approssimazione (min)", "73": "Offset", "74": "Bonus (min)"},
                           outputs={"71": "Orario arrotondato"}),
            "21": Campo70Op(code="21", name="ArrotondaUscita",
                           description="Arrotonda orario di USCITA: 71 con approssimazione 72, offset 73, bonus 74 -> 71 arrotondato",
                           inputs={"71": "Orario uscita", "72": "Approssimazione (min)", "73": "Offset", "74": "Bonus (min)"},
                           outputs={"71": "Orario arrotondato"}),
            "22": Campo70Op(code="22", name="SeparaNotturnoDiurno",
                           description="Separa notturno dal diurno per TURNO",
                           inputs={"71": "Entrata", "72": "Uscita"},
                           outputs={"71": "Diurno prima notturno", "72": "Notturno", "73": "Diurno dopo notturno"}),
            "30": Campo70Op(code="30", name="ConcatenaStringhe",
                           description="Concatena due stringhe",
                           inputs={"71": "Stringa 1", "72": "Stringa 2"},
                           outputs={"71": "Stringa concatenata"}),
            "31": Campo70Op(code="31", name="EstraiSottostringa",
                           description="Estrae sottostringa",
                           inputs={"71": "Stringa", "72": "Inizio", "73": "Numero caratteri"},
                           outputs={"71": "Sottostringa estratta"}),
            "32": Campo70Op(code="32", name="Trim",
                           description="Rimuove spazi (Trim)",
                           inputs={"71": "Stringa", "72": '"R"/"L"/altro"'},
                           outputs={"71": "Stringa trimmed"}),
            "41": Campo70Op(code="41", name="ScomponiData",
                           description="Scomponi data: 71=data -> 72-75",
                           inputs={"71": "Data AAAAMMGG"},
                           outputs={"72": "Giorno settimana", "73": "Giorno", "74": "Mese", "75": "Anno"}),
            "42": Campo70Op(code="42", name="DifferenzaDate",
                           description="Differenza date",
                           inputs={"71": "Data DA", "72": "Data A", "73": "Tipo (yyyy/m/d/ww)"},
                           outputs={"71": "Differenza"}),
            "43": Campo70Op(code="43", name="SommaGiorniAData",
                           description="Somma giorni a data",
                           inputs={"71": "Data", "72": "Offset giorni"},
                           outputs={"71": "Nuova data"}),
            "45": Campo70Op(code="45", name="GiornoSettimana",
                           description="Giorno settimana: 71=data -> 71 (1=dom, 7=sab)",
                           inputs={"71": "Data"},
                           outputs={"71": "Giorno settimana"}),
            "48": Campo70Op(code="48", name="PrimoUltimoGiornoMese",
                           description="Primo/Ultimo giorno mese: 71=data -> 71=primo, 72=ultimo",
                           inputs={"71": "Data"},
                           outputs={"71": "Primo giorno mese", "72": "Ultimo giorno mese"}),
            "50": Campo70Op(code="50", name="StatisticaCausale",
                           description="Somma durata causale nel periodo",
                           inputs={"71": "Data Inizio", "72": "Data Fine", "73": "Causale", "74": "Tipo (T/A/M)"},
                           outputs={"71": "Somma durata"}),
            "99": Campo70Op(code="99", name="DebugMostraCampi",
                           description="DEBUG — Mostra campi 71-78 in MsgBox (popup)",
                           inputs={"71-78": "Valori da mostrare in finestra di debug"}),
            "900": Campo70Op(code="900", name="DebugMostraTabellone",
                             description="DEBUG — Mostra Tabellone completo",
                             inputs={}),
        }

    def _build_k_totals(self) -> None:
        self.K_TOTALS = {
            601: KTotalInfo(601, "OreLavorate", "Totale Ore Lavorate", 1),
            602: KTotalInfo(602, "OreOrdinarie", "Totale Ore Ordinarie", 2),
            603: KTotalInfo(603, "LavoroFestivo", "Totale Lavoro Festivo", 3),
            604: KTotalInfo(604, "TotaleStraordinario", "Totale Straordinario", 4),
            605: KTotalInfo(605, "Festività", "Totale Festività", 5),
            608: KTotalInfo(608, "AssenzeRetribuite", "Totale Assenze Retribuite", 8),
            609: KTotalInfo(609, "AssenzeNonRetribuite", "Totale Assenze Non Retribuite", 9),
            610: KTotalInfo(610, "TotaleOreVarie", "Totale Ore Varie (612+611+615+614+616)", 10),
            611: KTotalInfo(611, "StraordinarioDiurno", "Totale Straordinario Diurno", 11),
            612: KTotalInfo(612, "Supplementare", "Totale Supplementare", 12),
            614: KTotalInfo(614, "StraordinarioNotturno", "Totale Straordinario Notturno", 14),
            615: KTotalInfo(615, "StraordinarioFestivoDiurno", "Totale Straordinario Festivo Diurno", 15),
            616: KTotalInfo(616, "StraordinarioFestivoNotturno", "Totale Straordinario Festivo Notturno", 16),
            621: KTotalInfo(621, "FlessibilitàLavorata", "Flessibilità Lavorata (banca ore positiva): ore eccedenti contratto accantonate nel conto flessibilità", 21),
            622: KTotalInfo(622, "FlessibilitàGoduta", "Flessibilità Goduta (banca ore negativa): ore di flessibilità fruite/recuperate", 22),
            625: KTotalInfo(625, "MaggiorazioneTurnoDiurno", "Totale Maggiorazione Turno Diurno", 25),
            626: KTotalInfo(626, "MaggiorazioneTurnoNotturno", "Totale Maggiorazione Turno Notturno", 26),
            627: KTotalInfo(627, "MaggiorazioneLavoroFestivo", "Totale Maggiorazione Lavoro Festivo", 27),
            629: KTotalInfo(629, "FestivitàNonGoduta", "Totale Festività Non Goduta", 29),
            630: KTotalInfo(630, "FestivitàNormale", "Totale Festività Normale", 30),
            631: KTotalInfo(631, "FerieGodute", "Totale Ferie Godute", 31),
            635: KTotalInfo(635, "ROLPermessi", "Totale R.O.L. / Permessi", 35),
            641: KTotalInfo(641, "TotalePermessi", "Totale Permessi", 41),
            651: KTotalInfo(651, "Malattia", "Totale Malattia", 51),
            711: KTotalInfo(711, "TotaleOreSettimanali", "Totale Ore Settimanali (progressivo)", 111),
            # Campi K usati internamente
            770: KTotalInfo(770, "ContatoreSettimane", "Contatore numero settimana"),
            771: KTotalInfo(771, "OreSettLavorate", "Ore settimanali lavorate (3+4)"),
            772: KTotalInfo(772, "AssenzeSettimanali", "Assenze settimanali (608+609)"),
            773: KTotalInfo(773, "LavoratoPiuAssenze", "Lavorato + Assenze (771+772)"),
            774: KTotalInfo(774, "StraordSettimanale", "Straordinario settimanale (907 accumulato)"),
            775: KTotalInfo(775, "TotaleSettimanaleFG", "Totale settimanale FG (3+4+608+609)"),
            776: KTotalInfo(776, "LavoratoPiuOrdNottFG", "Lavorato + ordinario notturno FG"),
            781: KTotalInfo(781, "OrePrevisteSett", "Ore previste settimanali"),
            782: KTotalInfo(782, "OreLavPiuAssSett", "Ore lavorate + assenze settimanali"),
            783: KTotalInfo(783, "OreStraordAnnuali", "Ore straordinarie annuali cumulate"),
            784: KTotalInfo(784, "SupplementareSett", "Supplementare settimanale"),
            785: KTotalInfo(785, "OreLavSett", "Ore lavorate settimanali"),
            788: KTotalInfo(788, "TotaleSettCorrente", "Totale settimana corrente"),
            790: KTotalInfo(790, "AccumuloSupplementare", "Accumulo supplementare"),
            800: KTotalInfo(800, "AppoggioK", "Appoggio per operazioni K"),
            900: KTotalInfo(900, "ContatoreGiorniGugest", "Contatore giorni GUGEST"),
            902: KTotalInfo(902, "OrdinarioNotturno", "Ordinario notturno"),
            903: KTotalInfo(903, "OrdinarioFestivoNotturno", "Ordinario festivo notturno"),
            904: KTotalInfo(904, "OrdinarioFestivo", "Ordinario festivo"),
            905: KTotalInfo(905, "Ordinario", "Ordinario"),
            906: KTotalInfo(906, "Supplementare", "Supplementare"),
            907: KTotalInfo(907, "StraordinarioDiurno", "Straordinario diurno"),
            908: KTotalInfo(908, "DomenicaleOrdinario", "Domenicale (ordinario)"),
            909: KTotalInfo(909, "StraordinarioNotturno", "Straordinario notturno"),
            910: KTotalInfo(910, "StraordinarioDomenicaleNott", "Straordinario domenicale notturno"),
            914: KTotalInfo(914, "StraordinarioFestivo", "Straordinario festivo"),
            915: KTotalInfo(915, "StraordinarioSecondaFascia", "Straordinario seconda fascia (SB)"),
            918: KTotalInfo(918, "OreFestività", "Ore festività"),
            919: KTotalInfo(919, "TipoFestività", "Tipo festività (1=normale, 2=non goduta, 3=patrono, 4=FX)"),
        }

    def _build_contracts(self) -> None:
        self.CONTRACTS = {
            1: ContractInfo(1, "Standard", "Contratto Standard — timbrature normali"),
            2: ContractInfo(2, "Dirigenti/Quadri", "Dipendenti che NON timbrano", timbra=False),
            3: ContractInfo(3, "Turnisti", "Dipendenti Turnisti — con max entrata posticipata", max_entry_offset="posticipata"),
        }

    def _build_ranges(self) -> None:
        self.RANGES = [
            FieldInfo(number=0, name="TotaliGiornalieri", description="1-6: Totali giornalieri", field_type=FIELD_TYPE_TOTALE, range_start=1, range_end=6),
            FieldInfo(number=0, name="NonUsare7_19", description="7-19: NON USARE (riservato)", field_type=FIELD_TYPE_SISTEMA, range_start=7, range_end=19),
            FieldInfo(number=0, name="FasciaNotturna", description="20-22: Fascia notturna/diurna", field_type=FIELD_TYPE_TOTALE, range_start=20, range_end=22),
            FieldInfo(number=0, name="GiornoFlags", description="50-58: Flags giorno e tipo turno", field_type=FIELD_TYPE_FLAG, range_start=50, range_end=58),
            FieldInfo(number=0, name="Campo70", description="70-79: Campo70 operativo + I/O", field_type=FIELD_TYPE_SISTEMA, range_start=70, range_end=79),
            FieldInfo(number=0, name="EntrateUsciteGiornata", description="80-89: Entrate/uscite prev/eff/calc", field_type=FIELD_TYPE_PREVISIONALE, range_start=80, range_end=89),
            FieldInfo(number=0, name="NonUsare90_99", description="90-99: NON USARE (riservato)", field_type=FIELD_TYPE_SISTEMA, range_start=90, range_end=99),
            FieldInfo(number=0, name="Previsionali", description="100-160: Orario previsionale (intervalli)", field_type=FIELD_TYPE_PREVISIONALE, range_start=100, range_end=160),
            FieldInfo(number=0, name="TimbratureEffettive", description="200-240: Timbrature effettive (entrate pari, uscite dispari)", field_type=FIELD_TYPE_TIMBRATURA, range_start=200, range_end=240),
            FieldInfo(number=0, name="Calcolate", description="250-290: Timbrature calcolate (251-270=entrate, 271-290=uscite)", field_type=FIELD_TYPE_CALCOLATA, range_start=250, range_end=290),
            FieldInfo(number=0, name="CausaliManuali", description="400-450: Causali manuali (10 slot)", field_type=FIELD_TYPE_CAUSALE, range_start=400, range_end=450),
            FieldInfo(number=0, name="CausaliAutomatiche", description="500-570: Causali automatiche", field_type=FIELD_TYPE_CAUSALE, range_start=500, range_end=570),
            FieldInfo(number=0, name="KTotali", description="600-799: Totali progressivi K (601-799)", field_type=FIELD_TYPE_K_TOTALE, range_start=600, range_end=799),
            FieldInfo(number=0, name="Appoggio", description="800-999: Campi di appoggio liberi per calcoli", field_type=FIELD_TYPE_APPOGGIO, range_start=800, range_end=999),
        ]

    def _load_grammar(self) -> None:
        """Carica conoscenza aggiuntiva dal file WinsarpGrammatica.txt."""
        path = Path(__file__).parent.parent.parent / "documenti" / "WinSarp" / "WinsarpGrammatica.txt"
        if not path.exists():
            _logger.warning("WinsarpGrammatica.txt non trovato, uso dati hardcoded")
            return
        try:
            text = path.read_text(encoding="utf-8")
            self._parse_grammar_fields(text)
            self._grammar_loaded = True
            _logger.info("Grammar loaded from %s", path)
        except Exception as e:
            _logger.warning("Errore caricamento grammar: %s", e)

    def _parse_grammar_fields(self, text: str) -> None:
        """Aggiorna descrizioni campi dal file grammatica."""
        for m in re.finditer(r'\{(\d+)\}\s*=\s*(.+)', text):
            num = int(m.group(1))
            desc = m.group(2).strip().rstrip()
            if num in self.FIELDS:
                self.FIELDS[num].description = desc

    # ============================================================
    # API di interrogazione
    # ============================================================

    def get_field(self, number: int) -> FieldInfo | None:
        return self.FIELDS.get(number)

    def get_range(self, number: int) -> FieldInfo | None:
        for r in self.RANGES:
            if r.range_start is not None and r.range_end is not None:
                if r.range_start <= number <= r.range_end:
                    return r
        return None

    def get_campo70_op(self, code: str) -> Campo70Op | None:
        return self.CAMPO70_OPS.get(code)

    def get_k_total(self, number: int) -> KTotalInfo | None:
        return self.K_TOTALS.get(number)

    def get_contract(self, number: int) -> ContractInfo | None:
        return self.CONTRACTS.get(number)

    def search_fields(self, query: str) -> list[FieldInfo]:
        """Cerca campi per nome, descrizione o numero."""
        q = query.lower()
        results = []
        for f in self.FIELDS.values():
            if str(f.number) == query:
                results.insert(0, f)
            elif q in f.name.lower() or q in f.description.lower():
                results.append(f)
            elif any(q in a.lower() for a in f.aliases):
                results.append(f)
        return results[:20]

    def get_entrata_uscita_pairs(self, field: int) -> dict[str, int | None]:
        """Data un'entrata o uscita, trova la controparte accoppiata."""
        f = self.FIELDS.get(field)
        if not f:
            return {"entrata": None, "uscita": None}
        if f.is_entrata:
            return {"entrata": field, "uscita": field + 20 if field < 250 else field + 20 if field < 270 else None}
        if f.is_uscita:
            return {"entrata": field - 20 if field > 220 else None, "uscita": field}
        return {"entrata": None, "uscita": None}

    def suggest_fields_for_intent(self, intent: str, text: str) -> dict[str, int]:
        """Dato un intent e testo richiesta, suggerisce campi rilevanti."""
        numbers = [int(n) for n in re.findall(r'\b(\d{2,4})\b', text) if 1 <= int(n) <= 9999]
        suggestions: dict[str, int] = {}

        if "entrata" in text.lower() or "251" in text or "201" in text:
            for n in numbers:
                if 201 <= n <= 257:
                    suggestions["entrata"] = n
                    break
            if "entrata" not in suggestions:
                suggestions["entrata"] = 251

        if "uscita" in text.lower() or "271" in text or "221" in text:
            for n in numbers:
                if 221 <= n <= 277:
                    suggestions["uscita"] = n
                    break
            if "uscita" not in suggestions:
                suggestions["uscita"] = 271

        if "flag" in text.lower() or "900" in text:
            suggestions["flag"] = next((n for n in numbers if n == 900), 900)

        return suggestions

    def is_field_valid(self, number: int, field_type: str | None = None) -> bool:
        """Verifica se un campo è valido per operazioni. Blocca range NON USARE."""
        # Blacklist rigida dei campi proibiti (NON USARE)
        forbidden_ranges = [
            (7, 19), (33, 39), (60, 69), (90, 99),
            (161, 197), (241, 248), (291, 299),
            (306, 309), (324, 329), (338, 349),
            (362, 389), (392, 399), (451, 499),
            (581, 598), (1017, 1049), (1054, 1099),
            (1106, 1108), (1137, 1150), (1167, 1170),
            (1209, 1210), (1218, 1220), (1224, 1299),
            (1400, 1400), (1491, 1499), (1591, 1599),
            (1659, 1659), (1668, 1670), (1688, 1690), (1693, 1697),
            (2004, 2019), (2021, 2039), (2041, 2099), (2208, 2210),
            (2395, 2399), (2507, 2507), (2551, 2557), (2588, 2590),
            (2702, 2710), (2741, 2799), (2800, 2800), (2802, 2899)
        ]
        for start, end in forbidden_ranges:
            if start <= number <= end:
                return False

        f = self.FIELDS.get(number)
        if not f:
            return False
        if field_type and f.field_type != field_type:
            return False
        return True

    def stats(self) -> dict[str, Any]:
        return {
            "total_fields": len(self.FIELDS),
            "ranges": len(self.RANGES),
            "campo70_ops": len(self.CAMPO70_OPS),
            "k_totals": len(self.K_TOTALS),
            "contracts": len(self.CONTRACTS),
            "grammar_loaded": self._grammar_loaded,
        }


# Singleton
registry: FieldRegistry = FieldRegistry()
