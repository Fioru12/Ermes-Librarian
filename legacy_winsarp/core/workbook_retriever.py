"""
workbook_retriever.py
Cerca nel workbook WinSarp_Formule.txt la formula piu' simile
a una richiesta e costruisce un prompt arricchito per il generatore.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)

WORKBOOK_PATH = Path("documenti/WinSarp/WinSarp_Formule.txt")
GRAPH_PATH = Path("data/winsarp_graph.json")

# Mappatura campi frequenti da workbook
CAMPI_FREQUENTI = {
    "1": "Ore previsionali (da contratto)",
    "2": "Ore effettive (da timbrature)",
    "3": "Ore ordinarie calcolate",
    "4": "Ore straordinarie calcolate",
    "5": "Ore assenza",
    "50": "Flag domenica (I=sì/Domenica, Z=no, oppure 1=Dom…7=Sab)",
    "55": "Flag festivo (I=sì, Z=no)",
    "58": "Tipo turno (MATT/POME/NOTT/RIPO/OPE/CHIA)",
    "70": "Funzioni built-in Campo70",
    "100": "Numero intervalli previsionali",
    "111/141": "Inizio/fine previsionale 1° intervallo",
    "112/142": "Inizio/fine previsionale 2° intervallo",
    "200-229": "Timbrature effettive (entrate pari, uscite dispari)",
    "250": "Numero intervalli calcolati",
    "251-257": "Entrate calcolate (251=1° interv, 252=2° interv, 253=3° interv…)",
    "271-277": "Uscite calcolate  (271=1° interv, 272=2° interv, 273=3° interv…)",
    "300": "Data giornata in elaborazione",
    "390": "TipoCalcolo",
    "561-570": "Causali automatiche ore per tipo",
    "608": "Totale assenze retribuite (progressivo)",
    "609": "Totale assenze non retribuite (progressivo)",
    "684": "Flag festività non goduta",
    "800-899": "Campi di appoggio uso custom",
    "900": "Flag anti-loop / indicatore turno",
    "1000": "Codice azienda",
    "1100": "Codice dipendente",
    "1114": "Ore settimanali contrattuali",
    "1391": "Ore ridotte part-time",
}

TOTALI_K6XX = {
    "K601": "Ore Lavorate",
    "K602": "Ore Ordinarie",
    "K603": "Lavoro Festivo",
    "K604": "Totale Straordinario",
    "K605": "Festività",
    "K608": "Totale Assenze Retribuite",
    "K609": "Totale Assenze Non Retribuite",
    "K611": "Straordinario Diurno",
    "K612": "Supplementare",
    "K614": "Straordinario Notturno",
    "K615": "Straordinario Festivo Diurno",
    "K616": "Straordinario Festivo Notturno",
    "K625": "Maggiorazione Turno Diurno",
    "K626": "Maggiorazione Turno Notturno",
    "K627": "Maggiorazione Lavoro Festivo",
    "K629": "Festività Non Goduta",
    "K631": "Ferie Godute",
    "K635": "R.O.L. Goduti",
    "K641": "Totale Permessi Goduti",
    "K651": "Malattia",
    "K711": "Totale Ore Settimanali",
}

CONTRATTI = {
    "1": "Standard (timbrature normali)",
    "2": "Dirigenti/Quadri (non timbrano)",
    "3": "Turnisti",
}

# Catene di formule dal workbook
CATENE = {
    "standard_inizio": [1, 5, 10],
    "standard_fine": [100, 110, 120, 130, 140, 200, 210],
    "dirigenti_inizio": [1000, 1010],
    "dirigenti_fine": [1100],
    "chiamata_fine": [2000],
    "person_inizio": [2050, 2051, 2060, 9001, 9002],
    "gugest_a_fine": [2100, 2101],
    "gugest_b_fine": [2105, 2106],
    "fg_fine": [3000, 3001],
}

# Subroutine chiamate da ogni formula (da workbook)
SUBROUTINE_MAP = {
    2101: [2109, 2122, 2123, 2124, 2125, 2114, 2115, 2130],
    2100: [2109],
    3000: [3009, 3002, 3003, 3017],
    3001: [3009, 2122, 2123, 2124, 3005, 3014, 3015, 3030],
    200: [210],
    2050: [2051, 2060],
    9001: [9002],
}


class FormulaEntry:
    def __init__(self, codice: int, descrizione: str, tipo: str, categoria: str,
                 formula: str, scopo: str, campi: List[str] = None,
                 chiama: List[int] = None, chiamato_da: List[int] = None):
        self.codice = codice
        self.descrizione = descrizione
        self.tipo = tipo        # "Inizio Giornata", "Fine Giornata", "Subroutine"
        self.categoria = categoria
        self.formula = formula
        self.scopo = scopo
        self.campi = campi or []
        self.chiama = chiama or []
        self.chiamato_da = chiamato_da or []


class WorkbookRetriever:
    def __init__(self, workbook_path: Path = WORKBOOK_PATH, graph_path: Path = GRAPH_PATH):
        self.entries: Dict[int, FormulaEntry] = {}
        self.graph_data: Optional[Dict] = None
        self._errore = None

        # Carica grafo se esiste
        if graph_path.exists():
            try:
                self.graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
                _logger.info("Grafo caricato: %d nodi", len(self.graph_data.get("nodes", {})))
            except Exception as e:
                _logger.warning("Grafo non caricabile: %s", e)

        # Carica workbook
        if workbook_path.exists():
            self._parse_workbook(workbook_path)
        else:
            self._errore = f"Workbook non trovato: {workbook_path}"

    def _parse_workbook(self, path: Path):
        text = path.read_text(encoding="utf-8")
        # Trova ogni sezione formula: ### <a name="N"></a>... fino a --- o fine file
        sections = re.split(r'\n---\n', text)
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            # Controlla se questa sezione contiene una formula
            m = re.search(
                r'### <a name="(\d+)"></a>\d+\s*[-\u2014]\s*(.+?)\n',
                sec
            )
            if not m:
                continue
            codice = int(m.group(1))
            descrizione = m.group(2).strip()

            # Estrai Tipo
            tipo_m = re.search(r'\*\*Tipo:\*\*\s*(.+?)(?:\n|$)', sec)
            tipo = tipo_m.group(1).strip() if tipo_m else ""

            # Estrai Scopo
            scopo_m = re.search(r'\*\*Scopo:\*\*\s*\n*(.+?)(?=\n\*\*Formula|\n---|\Z)', sec, re.DOTALL)
            scopo = scopo_m.group(1).strip() if scopo_m else ""
            scopo = re.sub(r'\s+', ' ', scopo)

            # Estrai formula compressa tra ``` e ```
            formula_m = re.search(r'```\n(.+?)```', sec, re.DOTALL)
            formula = formula_m.group(1).strip() if formula_m else ""

            categoria = self._categoria_from_tipo(tipo, descrizione, formula)

            campi = list(set(re.findall(r'\b(\d{2,4})\b', formula + scopo)))

            chiama = [int(x) for x in re.findall(r'\b[RP](\d{3,4})\b', formula)]

            entry = FormulaEntry(
                codice=codice,
                descrizione=descrizione,
                tipo=tipo,
                categoria=categoria,
                formula=formula,
                scopo=scopo,
                campi=campi,
                chiama=chiama,
            )
            self.entries[codice] = entry

        for e in self.entries.values():
            for c in e.chiama:
                if c in self.entries:
                    self.entries[c].chiamato_da.append(e.codice)

        _logger.info("Workbook parsed: %d formule", len(self.entries))

    def _categoria_from_tipo(self, tipo: str, descrizione: str, formula: str) -> str:
        if "Subroutine" in tipo:
            return "Subroutine"
        if "Inizio" in tipo:
            if "Arrotondamento" in descrizione or "Cap" in descrizione:
                return "Personalizzato"
            if "Dirigenti" in descrizione or "Quadri" in descrizione:
                return "Dirigenti"
            if "chiamata" in descrizione:
                return "A Chiamata"
            if "Turno" in descrizione:
                return "Turnisti"
            return "Standard"
        if "Fine" in tipo:
            if "GUGEST" in descrizione or "FG" in descrizione:
                return "Gestione Personalizzata"
            if "Dirigenti" in descrizione or "Quadri" in descrizione:
                return "Dirigenti"
            if "chiamata" in descrizione:
                return "A Chiamata"
            if "Maggiorazioni" in descrizione:
                return "Turnisti"
            if "Straordinario" in descrizione:
                return "Straordinario"
            if "Formula finale" in descrizione or "PRIMA" in descrizione:
                return "Standard"
            return "Standard"
        return "Standard"

    def search(self, query: str, top_k: int = 3) -> List[Tuple[FormulaEntry, float]]:
        """Cerca formule: match esatto (codice) -> keyword matching."""
        if not self.entries:
            return []

        # 1. Match esatto (Formula ID) - priorità assoluta
        m = re.search(r'(?:formula|codice)\s*#?\s*(\d+)', query, re.IGNORECASE)
        if m:
            codice = int(m.group(1))
            entry = self.find_by_codice(codice)
            if entry:
                return [(entry, 100.0)]
        
        # 2. Keyword matching esistente
        query_lower = query.lower()
        tokens = [t for t in re.findall(r'\w+', query_lower) if len(t) > 2]

        scored = []
        for entry in self.entries.values():
            score = 0
            text = (entry.descrizione + " " + entry.scopo + " " + entry.formula).lower()
            for t in tokens:
                if t in text:
                    score += 1
            # Bonus: match esatto su codice
            for t in tokens:
                if t.isdigit() and int(t) == entry.codice:
                    score += 10
            if score > 0:
                scored.append((entry, score))

        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def find_by_codice(self, codice: int) -> Optional[FormulaEntry]:
        return self.entries.get(codice)

    def build_chain_context(self, codice: int) -> str:
        """Costruisce contesto di catena per una formula."""
        entry = self.find_by_codice(codice)
        if not entry:
            return ""

        lines = []
        lines.append(f"Formula #{codice} - {entry.descrizione}")
        lines.append(f"Tipo: {entry.tipo} ({entry.categoria})")

        if entry.chiamato_da:
            lines.append(f"Chiamata da: #{', #'.join(str(c) for c in entry.chiamato_da)}")
        if entry.chiama:
            lines.append(f"Chiama: #{', #'.join(str(c) for c in entry.chiama)}")

        # Trova la catena di appartenenza
        for chain_name, chain in CATENE.items():
            if codice in chain:
                idx = chain.index(codice)
                pre = f"#{chain[idx-1]}" if idx > 0 else "(inizio)"
                post = f"#{chain[idx+1]}" if idx < len(chain)-1 else "(fine)"
                lines.append(f"Catena '{chain_name}': precedente={pre}, successiva={post}")
                break

        lines.append(f"Scopo: {entry.scopo[:200]}")
        return "\n".join(lines)

    def suggest_placement(self, codice: int, tipo: str, categoria: str = "") -> Dict[str, str]:
        """Suggerisce dove inserire una formula basandosi su tipo e categoria."""
        entry = self.find_by_codice(codice) if isinstance(codice, int) else None
        cat = categoria or (entry.categoria if entry else "")

        if "Subroutine" in tipo:
            called_by = f" #{', #'.join(str(c) for c in entry.chiamato_da)}" if entry and entry.chiamato_da else ""
            return {
                "aggancio": "Formula separata (Subroutine)",
                "ponte": f"Richiamabile via P {codice}{called_by}"
            }

        if "Inizio" in tipo:
            if "Dirigenti" in cat or "Quadri" in cat:
                return {
                    "aggancio": "Dopo #1010",
                    "ponte": "Aggiungi P [CodiceNuovaFormula] in #1010"
                }
            if "Personalizzato" in cat or "Arrotondamento" in cat:
                return {
                    "aggancio": "Tra #5 e #1000",
                    "ponte": "Aggiungi P [CodiceNuovaFormula] in #5 o #1000"
                }
            return {
                "aggancio": "Tra #10 e #1000",
                "ponte": "Aggiungi P [CodiceNuovaFormula] in #10"
            }

        if "Fine" in tipo:
            if "Gestione" in cat:
                return {
                    "aggancio": "Template #3000/#3001",
                    "ponte": "Aggiungi P [CodiceNuovaFormula] in #3000"
                }
            if "Dirigenti" in cat or "Quadri" in cat:
                return {
                    "aggancio": "Template #1100",
                    "ponte": "Aggiungi P [CodiceNuovaFormula] in #1100"
                }
            if "A Chiamata" in cat:
                return {
                    "aggancio": "Template #2000",
                    "ponte": "Aggiungi P [CodiceNuovaFormula] in #2000"
                }
            if "Straordinario" in cat or "Turnisti" in cat:
                return {
                    "aggancio": "Flusso #120 -> #130/#140 -> #200",
                    "ponte": "Aggiungi P [CodiceNuovaFormula] in #130 o #140"
                }
            return {
                "aggancio": "Flusso #100 -> #110 -> #120 -> ... -> #200",
                "ponte": "Aggiungi P [CodiceNuovaFormula] tra #120 e #200"
            }

        return {"aggancio": "Da definire", "ponte": "Da definire"}

    def build_enriched_prompt(self, user_request: str) -> str:
        """Costruisce un prompt arricchito con l'esempio piu' relevante dal workbook."""
        # Cerca formula simile
        results = self.search(user_request, top_k=2)
        example_section = ""
        chain_section = ""
        placement_section = ""

        if results:
            best = results[0][0]
            example_section = (
                "ESEMPIO REALE DAL WORKBOOK (usalo come riferimento):\n"
                f"Formula #{best.codice} - {best.descrizione}\n"
                f"Tipo: {best.tipo}\n"
                f"Scopo: {best.scopo[:300]}\n"
                f"Codice:\n"
                f"{best.formula}\n"
            )
            if len(results) > 1:
                second = results[1][0]
                example_section += (
                    f"\nAlternativa: Formula #{second.codice} - {second.descrizione}\n"
                )

            # Catena
            chain_section = "CONTESTO DI CATENA:\n"
            chain_section += self.build_chain_context(best.codice)

            # Placement
            placement_data = self.suggest_placement(best.codice, best.tipo, best.categoria)
            placement_section = "POSIZIONAMENTO SUGGERITO:\n"
            placement_section += f"  Aggancio: {placement_data.get('aggancio', 'N/A')}\n"
            placement_section += f"  Ponte: {placement_data.get('ponte', 'N/A')}\n"

        prompt = (
            "Genera SOLO step IR strutturati per una formula WinSarp.\n"
            "Il sistema convertira' automaticamente in sintassi WinSarp compatta.\n"
            "NON scrivere sintassi compatta — scrivi SOLO step IR.\n\n"

            "COMANDI IR DISPONIBILI:\n"
            "  SET N = valore         (assegnazione campo N al valore)\n"
            "  RESET N                (azzera campo N)\n"
            "  IF condizione THEN     (condizionale — su riga separata)\n"
            "  ELSE                   (ramo else — su riga separata)\n"
            "  ENDIF                  (fine condizionale — su riga separata)\n"
            "  R N                    (salta/chain a formula N)\n"
            "  P N                    (chiama subroutine N, ritorna qui)\n"
            "  VF                     (fine formula / return)\n"
            "  VU                     (salta all'ultimo periodo logico)\n"
            "  K N A/S val [...]      (accumulo: A=aggiungi, S=sottrai)\n"
            "  CAMPO70 n              (imposta funzione built-in 70='n')\n"
            "  FIELD N                (riferimento campo senza assegnazione)\n"
            "  GOTO label             (salta a label formato Vxx: V02, V04, V10...)\n"
            "  MARK label             (marca posizione, formato Vxx: V02, V04, V10...)\n"
            "  COMMENT testo | # testo (commento)\n"
            "  {N}                    (dereferenza campo N)\n"
            "  [N                     (push su catena pointer — inizio catena)\n"
            "  ]N                     (pop da catena pointer — fine catena)\n\n"

            "OPERATORI CONDIZIONE: =, #, >, <, >=, <=\n"
            "OPERATORI LOGICI: AND (=E), OR (=O) — restano inline nella riga IF.\n\n"

            "REGOLE:\n"
            "- OGNI comando su una riga separata. MAI IF/THEN/ELSE/ENDIF sulla stessa riga.\n"
            "- USA SOLO NUMERI per i campi, MAI variabili.\n"
            "- I flag: I = VERO, Z = FALSO — NON si quotano mai.\n"
            "- Numeri con apici: '100'. Stringhe con doppi apici: \"MATT\".\n"
            "- Riferimenti campo: F(N) nelle espressioni (es. SET 900 = F(3) + F(4)).\n"
            "- K = accumulo: K N A valore / K N S valore\n"
            "- Le label MARK/GOTO usano SEMPRE formato Vxx (V02, V04, V10...). MAI V_START, V_END, V_SKIP, V_DONE.\n"
            "- VF termina la formula. R N salta a formula N. P N chiama subroutine e torna.\n"
            "- Per agganciare a un flusso, aggiungi R [numero_flusso] o P [numero_flusso] alla fine.\n"
            "- Le condizioni vanno nella riga IF, NON nella riga THEN.\n"
            "    CORRETTO: IF 800 >= Z THEN /   RESET 801 / ENDIF\n"
            "    SBAGLIATO: IF THEN /   {800} >U Z ( RESET 801 / ENDIF\n\n"

            "ESEMPI IR:\n"
            "IF 55 = I THEN\n"
            "  P 2109\n"
            "ENDIF\n"
            "RESET 4\n"
            "RESET 5\n"
            "R 120\n"
            "VF\n\n"
            "IF 800 >= 1 THEN\n"
            "  RESET 251\n"
            "  RESET 271\n"
            "  RESET 252\n"
            "ELSE\n"
            "  SET 801 = '0'\n"
            "ENDIF\n"
            "K 601 A 3\n"
            "K 602 A 3\n"
            "VF\n\n"
            "SET 900 = {800} S {801}\n"
            "[800\n"
            "K 802 A {801}\n"
            "]800\n"
            "R 2106\n"
            "VF\n\n"
            "- VALORI LETTERALI: usa 'valore' (con apici) per numeri:\n"
            "    SET 900 = '100'             -> ( 900 = '100' )\n"
            "    SET 802 = 85                -> ( 802 = 85 )  [campo, non letterale]\n"
            "- STRINGHE: usa \"stringa\" (doppi apici) in IF e SET:\n"
            '    IF 50 = "RIPO" THEN\n'
            "- ESPRESSIONI: usa +, -, *, / (vengono convertiti in A, S, *, S):\n"
            "    SET 800 = F(3) + F(4)       -> ( 800 = 3 A 4 )\n"
            "- CONDIZIONI IF: NON usare F() nelle condizioni. Usa numeri diretti:\n"
            "    CORRETTO: IF 50 = \"AUTS\" THEN\n"
            "    SBAGLIATO: IF F(50) = \"AUTS\" THEN\n"
            "- ENDIF opzionale: se manca, viene aggiunto automaticamente.\n"
            "- ELSE IF cond THEN si espande automaticamente in ELSE+IF annidato.\n"
            "- R N termina la formula e salta a formula N (chain).\n"
            "- P N chiama subroutine N e ritorna.\n"
            "- IF/THEN/ELSE/ENDIF in MAIUSCOLO.\n"
            "- USA SOLO NUMERI per i campi (800, 801, mai SESSO, RET1).\n"
            "- RESET N significa SET N = Z (azzerare il campo a falso/zero).\n"
            "- AND/E resta nella stessa riga IF. NON annidare.\n"
            "- NON mettere IF/THEN/ELSE/ENDIF dentro un SET.\n\n"

            "COSTANTI SPECIALI (NON quotare, NON confondere con numeri):\n"
            "  I = VERO / flag attivo (es. 55 = I  -> giorno festivo)\n"
            "  Z = FALSO / flag zero   (es. 4 = Z   -> nessuna ora straordinaria)\n"
            "  ATTENZIONE: 50 = I significa 'giorno e' domenica (flag True)', NON 50 = 7!\n\n"

            "CAMPI COMUNI:\n"
        )
        # Aggiunge campi frequenti
        for campo, desc in list(CAMPI_FREQUENTI.items())[:20]:
            prompt += f"  {campo} = {desc}\n"

        prompt += (
            "\nTOTALI PROGRESSIVI K6xx:\n"
        )
        for k, desc in list(TOTALI_K6XX.items())[:10]:
            prompt += f"  {k} = {desc}\n"

        prompt += (
            "\nCONTRATTI:\n"
            "  1 = Standard, 2 = Dirigenti/Quadri, 3 = Turnisti\n\n"

            "FUNZIONI:\n"
            "  AVERAGE(c1, c2, ...) = media aritmetica\n"
            "  SUM(c1, c2, ...) = somma\n"
            "  MIN(campo, limite) = valore minimo\n"
            "  MAX(campo, limite) = valore massimo\n"
            "  ROUND(campo, decimali) = arrotondamento (NON esiste in WinSarp, "
            "implementa manualmente con CAMPO70 3 + condizioni)\n\n"

            "K accumulo - formati:\n"
            "  K N A 'val'           accumula valore su campo N\n"
            "  K N S 'val'           sottrae valore dal campo N\n"
            "  K N A val1 A val2     accumula multipli valori\n"
            "  Dove 'val' e' numerico o un campo F(N)\n\n"

            "COMPILAZIONE OUTPUT (SOLO PER RIFERIMENTO — NON scrivere in compatto!):\n"
            "  I tuoi step IR (IF/THEN/ENDIF, SET, RESET, K, R, P, VF, VU, CAMPO70,\n"
            "  GOTO, MARK, COMMENT, { }, [ ], ] )\n"
            "  verranno tradotti automaticamente in sintassi WinSarp compatta.\n"
            "  Esempi di traduzione (tu scrivi IR → sistema produce compatto):\n"
            "    IF 800 = 1 THEN     → 800 U '1' ( azione\n"
            "    AND                  → E    OR → O\n"
            "    RESET N              → ( !N )\n"
            "    SET N = 100          → ( N = '100' )\n"
            "    SET N = \"STR\"       → ( N = \"STR\" )\n"
            "    SET N = I            → ( N = I )\n"
            "    SET N = { 801 }      → ( N = { 801 } )\n"
            "    K N A val            → ( K{N}A{val} )\n"
            "    K N A { 801 }        → ( K N A { 801 } )\n"
            "    GOTO V02             → V02\n"
            "    MARK V02             → V02\n"
            "    COMMENT testo        → ? testo\n"
            "    [ N                  → [N\n"
            "    ] N                  → ]N\n"
            "  Azioni multiple nel THEN: mettile su righe separate.\n"
            "  NON scrivere direttamente U, !, parentesi, V-label —\n"
            "  SCRIVI SOLO STEP IR standard (IF/THEN/ENDIF/SET/RESET/K/R/P/VF/VU/CAMPO70/GOTO/MARK/COMMENT).\n\n"
        )

        if example_section:
            prompt += example_section + "\n"
        if chain_section:
            prompt += chain_section + "\n"
        if placement_section:
            prompt += placement_section + "\n"

        prompt += (
            "ESEMPI:\n"
            "  IF 800 = 1 THEN\n"
            "    SET 900 = 0\n"
            "  ELSE\n"
            "    SET 900 = AVERAGE(801, 802, 803)\n"
            "  ENDIF\n"
            "  IF 804 >= 12 THEN\n"
            "    SET 900 = F(900) * 80 / 100\n"
            "  ELSE\n"
            "    SET 900 = F(900) * 60 / 100\n"
            "  ENDIF\n"
            "  K 800 A F(900)\n"
            "  CAMPO70 3\n"
            "  R 110\n\n"
            "STRUTTURA A INTERVALLI E PAUSA PRANZO:\n"
            "  Le formule 2101/2106 (GUGEST) e 3001 (FG) processano ogni giorno in 7 intervalli.\n"
            "  Ogni intervallo ha: entrata (251=1°, 252=2°, ...257=7°) e uscita (271=1°, 272=2°, ...277=7°).\n"
            "  La PAUSA PRANZO e' la durata tra l'uscita del 1° intervallo (271) e l'entrata del 2° (252).\n"
            "  Calcolo: (!71!72!73)(71=252)(72=271)(70='2')(800=73);  (70='2' = differenza 71-72)\n"
            "  REGOLA CAMPO70: dopo SET 71 = 252 e SET 72 = 271, CAMPO70 2 scrive il risultato in **73**.\n"
            "  Usa SEMPRE SET 800 = 73 (o SET 801 = 73) — MAI {71} S {72} o espressioni deref dirette.\n"
            "  La subroutine va inserita DOPO P2122 e PRIMA di P2123 nel flusso 2101/2106.\n"
            "  NON deve modificare i totali finali: 3, 4, K601, K602, K603, K604, K605, K608, K609.\n"
            "  Usa SOLO campi di appoggio 800-899 per i risultati.\n\n"
            "FLOW REALE FORMULA 2101 (da workbook):\n"
            "  251 > Z E 271 > Z (( 811 = 251 )( 812 = 271 ) P2122\n"
            "  252 > Z E 272 > Z (( 811 = 252 )( 812 = 272 ) P2122\n"
            "  ... fino a 257/277\n"
            "  P2123\n"
            "  P2124\n"
            "  P2125\n"
            "  La NUOVA subroutine pausa pranzo va DOPO i 7 P2122 e PRIMA di P2123.\n\n"
            "ESEMPIO IR PER NUOVA SUBROUTINE PAUSA PRANZO (da generare):\n"
            "  COMMENT Pausa pranzo ricalcolo\n"
            "  IF 58 != \"MATT\" AND 58 != \"POME\" THEN\n"
            "    GOTO VF\n"
            "  ENDIF\n"
            "  IF 251 = Z OR 271 = Z OR 252 = Z OR 272 = Z THEN\n"
            "    GOTO VF\n"
            "  ENDIF\n"
            "  RESET 71\n  RESET 72\n  RESET 73\n  RESET 800\n  RESET 801\n"
            "  SET 71 = 252\n"
            "  SET 72 = 271\n"
            "  CAMPO70 2\n"
            "  SET 800 = 73\n"
            "  IF 800 < Z THEN\n"
            "    K 800 A '24'\n"
            "  ENDIF\n"
            "  IF 800 >= '00.01' AND 800 <= '00.29' THEN\n"
            "    SET 801 = 271 + '00.30'\n"
            "    IF 801 < 252 THEN\n"
            "      SET 252 = 801\n"
            "    ENDIF\n"
            "  ENDIF\n"
            "  VF\n\n"
            "PATTERN DA FORMULE REALI (traduci in IR, NON scrivere in compatto):\n"
            "- IF campo = ZERO THEN / GOTO label (es. IF 21 = Z THEN / GOTO V04 / ENDIF)\n"
            "- IF campo > valore THEN / multipli SET + RESET + K + GOTO / ENDIF\n"
            "- IF cond1 AND cond2 THEN / SET stringa + SET campi / ENDIF\n"
            "- Pointer catena: [campo / azioni / ]campo\n"
            "- SET campo = {deref1} S {deref2}   (dereferenza con sottrazione)\n"
            "- Accumulo catena: K N A val1 A val2\n"
            "- RESET multipli su righe separate\n"
            "- Numeri orari: '06.00', '14.00', '22.00' con apici.\n"
            "- Stringhe turno: \"MATT\", \"POME\", \"NOTT\", \"RIPO\", \"CHIA\" con doppi apici.\n"
            "- Causali: \"SFN\", \"SN\", \"S\", \"F\", \"N\", \"T\", \"AUTS\" con doppi apici.\n"
            "- Flag: I = VERO/attivo, Z = FALSO/zero (MAI quotare I e Z).\n"
            "- Non generare MAI campi inesistenti. Usa 800-899 per appoggio, 900 per flag turno.\n"
            "- VF sempre alla fine. R N o P N per catena/chiamata dopo VF.\n"
            "- MARK label all'inizio. GOTO label per salti condizionali.\n\n"
            f"Richiesta: {user_request}\n\n"
            "Rispondi SOLO con gli step."
        )
        return prompt

    def is_available(self) -> bool:
        return len(self.entries) > 0
