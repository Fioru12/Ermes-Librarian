"""
modules/winsarp.py
Modulo WinSarp per Ermes.
Prompt di sistema, validazione formule e pulizia codice WinSarp.
Eredita da BaseModule per integrazione nel sistema moduli.
"""
import re
from typing import Any

from .base import BaseModule

# ============================================================
# FALLBACK PHRASES — frasi che indicano assenza di formula
# Importate da app.py per riconoscere risposte "non trovato"
# ============================================================
FALLBACK_PHRASES = [
    "Nel catalogo non e' presente una formula per questo caso.",
    "nel catalogo non è presente una formula per questo caso",
    "non è presente una formula",
    "non trovo una formula",
    "non ho trovato una formula",
    "nessuna formula corrisponde",
]


def is_fallback(text: str) -> bool:
    low = text.lower()
    return any(p.lower() in low for p in FALLBACK_PHRASES)


# ============================================================
# PROMPT DI SISTEMA — MODULO WINSARP (focus retrieval)
# ============================================================
PROMPT_WINSARP = (
    "Sei WINSARP ASSISTANT, specializzato nel recupero di formule WinSarp "
    "dal catalogo ufficiale Data Services (Workbook Formule v1.0).\n\n"

    "REGOLE FONDAMENTALI:\n"
    "1. Usa SOLO le formule presenti nel contesto fornito qui sotto.\n"
    "2. Prima di rispondere, verifica che la formula richiesta sia "
    "esattamente nel contesto.\n"
    "3. Cita il numero formula (es. #130) e la categoria.\n"
    "4. NON generare codice. NON modificare la formula trovata.\n"
    "5. Se la formula non esiste nel catalogo, dilo chiaramente.\n\n"

    "FORMATO OUTPUT:\n"
    "🔢 Formula #N — NOME FORMULA\n"
    "```\n"
    "(codice formula)\n"
    "```\n"
    "📝 **Spiegazione:** Descrizione breve\n\n"

    "SE NON TROVI CORRISPONDENZA NEL CONTESTO:\n"
    "Rispondi testualmente: Nel catalogo non e' presente una formula per questo caso.\n"
    "NON inventare. NON generare codice."
)


PROMPT_GENERALE = (
    "Sei un assistente aziendale esperto.\n"
    "Rispondi in modo preciso e conciso basandoti esclusivamente "
    "sui documenti forniti.\n"
    "Se l'informazione non e' nei documenti, dillo chiaramente senza inventare.\n"
    "Rispondi sempre in italiano.\n"
)


# Dizionario prompt per modulo — usato da rag_engine.build_chat_engine()
PROMPTS = {"WinSarp": PROMPT_WINSARP}


# ============================================================
# PROMPT DI SISTEMA — MODULO WINSARP (GENERAZIONE FORMULE)
# ============================================================
PROMPT_WINSARP_GENERAZIONE = (
    "Sei WINSARP GENERATOR, specializzato nella CREAZIONE di formule WinSarp funzionanti.\n\n"

    "REGOLA FONDAMENTALE:\n"
    "Genera SOLO formule WinSarp SINTATTICAMENTE CORRETTE E FUNZIONANTI.\n"
    "NON inventare sintassi. Usa SOLO operatori e strutture WinSarp valide.\n\n"

    "SINTASSI WINSARP COMPLETA:\n"
    "- Assegnazioni: (CAMPO=VALORE) o (CAMPO=!RIFERIMENTO!)\n"
    "- Condizionali (IF): (CONDIZIONE)CODICE_SE_VERO;CODICE_SE_FALSO;\n"
    "  Il ';' separa il ramo VERO dal ramo FALSO. MAI usare ';' per separare assegnazioni.\n"
    "- Operatori logici: E (AND), O (OR), >, <, =, >U, <U, U, #\n"
    "- Operatori aritmetici (solo su numeri interi, NON su orari): +, -, *, /\n"
    "- Operatori temporali (per orari sessagesimali): A (addizione), S (sottrazione)\n"
    "- Funzioni: Z (zero test), K (accumulo progressivo), P (perform), R (goto)\n"
    "- Codici ritorno: V11, V04, VF, VU, R110, R120, R200, ecc.\n"
    "- Campi temporanei: 71-78 (richiedono reset !71!72!78 prima dell'uso)\n"
    "- Campo 70: funzioni built-in ('1'=somma, '2'=differenza, '11'=durata intervallo, ecc.)\n\n"

    "OPERATORI SPECIALI:\n"
    "- !: Reset campo (es: !800 azzera il campo 800)\n"
    "- K: Accumulo progressivo (K601A561 = K601 += 561)\n"
    "- [ : Incrementa di 1\n"
    "- ] : Decrementa di 1\n"
    "- P: Perform (chiama formula e torna) es: P210\n"
    "- R: Goto (salta a formula senza tornare) es: R200;\n"
    "- V: Salta al prossimo ';' es: V05\n"
    "- VF: Termina formula\n\n"

    "COSTANTI NUMERICHE:\n"
    "- Apice singolo ' = numero intero (es: '480', '15')\n"
    "- Doppi apici \" = stringa o valore/100 (es: \"ST\", \"815\"=8.15)\n"
    "- Cappelletto ^ = orario sessagesimale (es: ^8.15^ = 8h15m)\n\n"

    "CAMPO 70 - FUNZIONI INTEGRATE (usa 71=entrata,72=uscita,73=risultato):\n"
    "- '1': Somma ore in 71+72 -> risultato in 73\n"
    "- '2': Differenza ore 71-72 -> risultato in 73\n"
    "- '11': Durata intervallo (71=entrata,72=uscita) -> 73\n"
    "- '20': Arrotonda entrata (71=ora,72=appross.,73=offset,74=bonus)\n"
    "- '21': Arrotonda uscita (71=ora,72=appross.,73=offset,74=bonus)\n"
    "- '22': Separa notturno/diurno (71=entrata,72=uscita) -> 71,72,73\n\n"

    "ESEMPI PRATICI (frammenti):\n"
    "  Reset campi: (!800!801!802!803!804);\n"
    "  Gestione mezzanotte: {83}<{82}({83}A'1440'={83});\n"
    "  Straordinario oltre 8h: {350}>'480'(!71!72!73)(71={350})(72='480')(70='2')(800=73);\n"
    "  Causale condizionale: {800}>'0'({800}=\"ST\");\n"
    "  Festivo: {55}U'1'(VF);\n\n"

    "ESEMPI REALI COMPLETI (formule dal catalogo ufficiale — studia la sintassi):\n\n"

    "Esempio 1 — Formula 130 (Straordinario Festivo e Festivo Notturno):\n"
    "---\n"
    "21UZ(V04;(504=\"SFN\");21>4((564=4)(K21S4)(!4)V05;\n"
    "(564=21)(K4S21)(!21);(503=\"SF\")(563=4)(!4);\n"
    "(K601A563A564)(K604A563A564)(K615A563)(K616A564);R200;\n"
    "---\n"
    "Scopo: classifica ore straordinarie in giorno festivo: notturne (campo 21) "
    "con causale SFN, diurne (campo 4) con causale SF. "
    "Aggiorna progressivi K601/K604 (ore), K615 (festivo notturno), K616 (festivo diurno).\n\n"

    "Esempio 2 — Formula 200 (Formula Finale):\n"
    "---\n"
    "(K601A3)(K602A3);900>Z(P210;\n"
    "---\n"
    "Scopo: accumula ore ordinarie in K601/K602, poi se c'e' turno attivo (900>0) chiama maggiorazioni (210).\n\n"

    "ERRORI COMUNI DA EVITARE:\n"
    "- MAI usare '->' nella formula (non e' un operatore WinSarp)\n"
    "- MAI usare ';' dentro ( ) per separare assegnazioni — ogni assegnazione ha le proprie ( )\n"
    "- MAI concatenare assegnazioni senza parentesi: 563=4503=\"SF\" e' SBAGLIATO, va (563=4)(503=\"SF\")\n"
    "- MAI usare + o - su orari sessagesimali: usa A (addizione) e S (sottrazione)\n"
    "- Ogni formula termina con ';' obbligatorio\n"
    "- I campi temporanei 71-78 vanno resettati con (!71!72!73...) prima di usare 70=\n\n"

    "FORMATO OUTPUT:\n"
    "Rispondi nel formato:\n"
    "[formula]\n"
    "(codice formula WinSarp funzionante)\n"
    "[/formula]\n"
    "[spiegazione]\n"
    "(breve spiegazione della formula)\n"
    "[/spiegazione]\n\n"

    "Se non sai generare la formula richiesta, rispondi:\n"
    "[formula]\n"
    "Non sono in grado di generare questa formula.\n"
    "[/formula]\n"
    "[spiegazione]\n"
    "Motivazione: ...\n"
    "[/spiegazione]\n\n"

    "LINGUA: Rispondi SEMPRE in italiano. Mai in inglese, portoghese o altre lingue.\n"
    "Se l'utente chiede in inglese, rispondi comunque in italiano.\n"
)


# Dizionario prompt per modulo — usato da rag_engine.build_chat_engine()
PROMPTS_GENERAZIONE = {"WinSarp": PROMPT_WINSARP_GENERAZIONE}


# ============================================================
# CLASSE MODULO WINSARP
# ============================================================
class WinSarpModule(BaseModule):
    """
    Modulo WinSarp per Ermes.
    Gestisce prompt, parsing e validazione specifici per WinSarp.
    """

    def __init__(self):
        super().__init__("WinSarp")

    def get_system_prompt(self) -> str:
        return PROMPT_WINSARP

    def parse_response(self, response: str) -> dict[str, Any]:
        return parse_response(response, "WinSarp")

    def validate_content(self, content: str) -> list:
        return validate_winsarp(content)

    def is_applicable(self, module_name: str) -> bool:
        return module_name.lower() == "winsarp"

    def supports_generation(self) -> bool:
        return True

    def has_formula_only(self) -> bool:
        return True

    def get_generation_prompt(self, user_request: str = "") -> str:
        from legacy_winsarp.core.formula_builder import FormulaBuilder
        from legacy_winsarp.core.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        builder = FormulaBuilder(kg)
        return builder.get_contextual_prompt(user_request)

    def get_formula_only_instruction(self) -> str:
        return (
            "\n\nRISPOSTA SOLO FORMULA: L'utente ha richiesto 'formula_only'. "
            "Rispondi ESCLUSIVAMENTE con il codice della formula, senza header, "
            "senza spiegazioni e senza testo aggiuntivo. Ritorna solo il codice compresso "
            "dentro un blocco di codice o come singola riga. "
            "Se non trovi una formula, rispondi esattamente: Nel catalogo non e' presente una formula per questo caso."
        )

    def get_retrieval_suggestions(self) -> list[str]:
        return [
            "Dammi la formula per straordinario oltre 8 ore con causale ST",
            "Qual è la formula per la gestione del turno notturno a mezzanotte?",
            "Mostrami la formula per arrotondare entrata e uscita a quarti d'ora",
            "Qual è la formula per verificare se il giorno è festivo o weekend?",
        ]

    def get_generation_suggestions(self) -> list[str]:
        return [
            "Crea una formula per calcolare lo straordinario notturno con maggiorazione 30%",
            "Genera una formula per calcolare il TFR proporzionale ai mesi lavorati",
            "Crea una formula per calcolare i contributi INPS su base oraria",
            "Genera una formula per calcolare le ferie maturate nell'anno corrente",
        ]

    def get_chat_placeholder(self, mode: str = "retrieval") -> str:
        if mode == "generazione" and self.supports_generation():
            return (
                "Descrivi la formula da proporre... "
                "(bozza AI separata dal catalogo ufficiale)"
            )
        return (
            "Cerca una formula... (es: dammi la formula per lo straordinario oltre 8 ore)"
        )


# ============================================================
# PATTERN REGEX PER IL PARSER — robusti e case-insensitive
# ============================================================
_RE_FORMULA = re.compile(r'\[\s*formula\s*\]', re.IGNORECASE)
_RE_SPIEGAZIONE = re.compile(r'\[\s*spiegazione\s*\]', re.IGNORECASE)
_RE_CODE_FENCE = re.compile(r'```[\w-]*')
_RE_BLOCK_CODE = re.compile(r'```[\w-]*\s*\n(.*?)```', re.DOTALL)
_RE_MULTI_SPACE = re.compile(r'\s+')


# ============================================================
# UTILITY INTERNA — RICERCA COMMENTO ? FUORI DA STRINGHE
# ============================================================
def _find_comment_start(line: str):
    """
    Restituisce l'indice del primo '?' che NON si trova all'interno di una
    stringa delimitata da apici singoli o doppi, oppure None se non esiste.

    Usata da clean_code() per rimuovere commenti WinSarp inline in modo sicuro,
    senza troncare valori letterali che contengono '?' come carattere dati.

    Esempio:
        '(500="DURATA?X"); ?commento' -> indice del secondo '?'
        '(500="DURATA?X")'            -> None
    """
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == '?' and not in_single and not in_double:
            return i
    return None


# ============================================================
# PULIZIA CODICE GREZZO DAL MODELLO
# ============================================================
def clean_code(raw: str) -> str:
    """
    Rimuove markdown, commenti WinSarp (?) e spazi extra dalla risposta grezza.
    Restituisce stringa vuota se non c'e' codice valido.

    Operazioni in ordine:
    1. Rimuove delimitatori markdown (```...```)
    2. Scarta righe che iniziano con '?' (commenti WinSarp interi)
    3. Tronca le righe al primo '?' fuori da stringhe (commenti inline)
       usando _find_comment_start per non toccare '?' dentro " o '
    4. Rimuove righe che iniziano con '#' (commenti Python/markdown residui)
    5. Unisce le righe con spazio (le formule WinSarp sono monoriga)
    6. Collassa spazi multipli
    7. NON aggiunge ';' finale — se manca e' validate_winsarp a segnalarlo
    """
    raw = _RE_CODE_FENCE.sub('', raw)
    raw = raw.replace('```', '').strip()

    lines = []
    for ln in raw.splitlines():
        stripped = ln.strip()

        if not stripped:
            continue
        if stripped.startswith('?'):
            continue
        if stripped.startswith('#'):
            continue

        if '?' in stripped:
            idx = _find_comment_start(stripped)
            if idx is not None:
                stripped = stripped[:idx].rstrip()

        if stripped:
            lines.append(stripped)

    code = ' '.join(lines).strip()
    code = _RE_MULTI_SPACE.sub(' ', code).strip()
    return code


# ============================================================
# BILANCIAMENTO PARENTESI (stack-based, salta stringhe)
# ============================================================
def _looks_like_if_opener(s: str, pos: int) -> bool:
    """
    Determina se una '(' alla posizione 'pos' e' l'apertura di un costrutto
    IF-THEN-ELSE di WinSarp, nel qual caso non ha una ')' corrispondente
    (viene chiusa implicitamente da ';').

    Pattern riconosciuti:
    - FIELDUZ(TRUE;FALSE;)         : 21UZ(V04;...
    - FIELD>VALUE(TRUE;FALSE;)     : 21>4((564=4)(K21S4)(!4)V05;...
    - FIELD>Z(TRUE;FALSE;)         : 900>Z(P210;
    - COND1OCOND2(TRUE;FALSE;)     : 21UZO900U'3'(V04;...
    - (COND)(TRUE;FALSE;)          : (505="N")(565=21);...

    Tutte le altre '(' e ')' devono essere bilanciate.
    """
    if pos <= 0 or s[pos] != '(':
        return False

    prev = s[pos - 1]

    # Caso 1: preceduta da > (es: COND>VALUE()
    if prev == '>':
        return True

    # Caso 2: preceduta da lettera dopo un campo (es: UZ, U, Z)
    if prev.isalpha():
        # Verifica che non sia preceduta da = (assegnazione)
        if pos >= 2:
            p2 = s[pos - 2]
            if p2 == '=':
                return False
        return True

    # Caso 3: preceduta da ')' — costrutto (COND)(TRUE;FALSE;)
    if prev == ')':
        return True

    # Caso 4: preceduta da apice — fine di valore stringa in condizione composta
    if prev in ("'", '"') and pos >= 2:
        # Guarda 3 caratteri indietro: cerca pattern come NUM='VAL'(
        for j in range(pos - 2, max(pos - 10, 0) - 1, -1):
            if s[j].isdigit():
                # Abbiamo un campo numerico prima dell'apice
                if j > 0 and s[j - 1] in ('O', 'E', '>', '<', '=', 'U', 'Z'):
                    return True
                return True
            if s[j] in (';', '(', ')'):
                break
        return True

    # Caso 5: preceduta da numero e non da parentesi di assegnazione
    if prev.isdigit():
        # Controlla se e' una condizione: cerca (NUMERO prima del digit
        # pattern tipico: NUM>VAL( o VALNUM(
        if pos >= 2:
            p2 = s[pos - 2]
            if p2 == '=':
                return False  # (NUMERO=VALORE) — assegnazione, non IF
            if p2.isdigit() or p2 == '>' or p2 == '<' or p2.isalpha():
                return True
        return True

    # Caso 6: preceduta da } — chiusura di {FIELD} in {FIELD}<{VALUE}(IF)
    # Pattern: {801}<{800}((K802A'24');...;)
    return prev == '}'


# ============================================================
# BILANCIAMENTO PARENTESI (stack-based, salta stringhe)
# ============================================================
def _check_balance(s: str) -> list[str]:
    """
    Analizza il bilancio di parentesi tonde {} e graffe {{}} in una stringa,
    saltando i contenuti delle stringhe (sia singoli che doppi apici).

    Usa _looks_like_if_opener() per identificare le '(' che fanno parte
    del costrutto IF WinSarp (aperte da >, U, UZ, ecc.) e che non hanno
    una ')' corrispondente.
    """
    errors = []
    stack = []  # ogni elemento: (opener, posizione)
    pairs = {'(': ')', '{': '}'}
    in_single = False
    in_double = False

    for i, ch in enumerate(s):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double

        if in_single or in_double:
            continue

        if ch in pairs:
            stack.append((ch, i))
        elif ch == ')':
            if stack and stack[-1][0] == '(':
                stack.pop()
            else:
                errors.append(
                    f"Parentesi ')' inaspettata alla posizione {i} — "
                    "manca la '(' corrispondente"
                )
        elif ch == '}':
            if stack and stack[-1][0] == '{':
                stack.pop()
            else:
                errors.append(
                    f"Graffa '}}' inaspettata alla posizione {i} — "
                    "manca la '{{' corrispondente"
                )

    for opener, pos in stack:
        if opener == '(' and _looks_like_if_opener(s, pos):
            continue  # Parentesi IF WinSarp — si chiude implicitamente
        expected = pairs[opener]
        name = "tonda" if opener == '(' else "graffa"
        errors.append(
            f"Parentesi {name} '{opener}' aperta alla posizione {pos} "
            f"senza la '{expected}' corrispondente"
        )

    return errors


# ============================================================
# BILANCIAMENTO APICI (conteggio semplice, salta stringhe opposte)
# ============================================================
def _check_quote_balance(s: str) -> list[str]:
    errors = []
    in_single = False
    in_double = False
    for ch in s:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
    if in_single:
        errors.append("Apici singoli non bilanciati")
    if in_double:
        errors.append("Doppi apici non bilanciati")
    return errors


# ============================================================
# VALIDAZIONE FORMULE WINSARP
# ============================================================
def validate_winsarp(code: str) -> list:
    """
    Analizza il codice WinSarp e restituisce una lista di errori trovati.
    Lista vuota = formula sintatticamente corretta.

    Controlli eseguiti:
    - Formula vuota
    - Terminazione con ';'
    - Bilanciamento parentesi
    - Bilanciamento apici
    - Campi vietati
    - Reset campi temporanei (70=)
    - Operatori orari corretti
    - Gestione mezzanotte per intervalli
    - Sintassi assegnazioni
    - Riferimenti a campi validi
    """
    errors = []
    s = code.strip()

    if not s:
        return ["Formula vuota."]

    # Controllo terminazione
    if not s.endswith(';'):
        errors.append(
            "La formula non termina con ';' — probabilmente e' incompleta o troncata."
        )

    # Controllo bilanciamento parentesi (stack-based, salta stringhe)
    bal_errors = _check_balance(s)
    errors.extend(bal_errors)

    # Controllo bilanciamento apici
    q_errors = _check_quote_balance(s)
    errors.extend(q_errors)

    # Controllo campi vietati
    forbidden = [
        (r'\([7-9]\d*[=\)]', "Campi 7-9 vietati (NON USARE)"),
        (r'\(1[0-9]\d*[=\)]', "Campi 10-19 vietati (NON USARE)"),
        (r'\(6[0-9]\d*[=\)]', "Campi 60-69 vietati (NON USARE)"),
        (r'\(9[0-9]\d*[=\)]', "Campi 90-99 vietati (NON USARE)"),
        (r'\(79\d*[=\)]', "Campo 79 riservato — non usare direttamente"),
    ]
    for pat, msg in forbidden:
        if re.search(pat, s):
            errors.append(msg)

    # Controllo reset campi temporanei (70=)
    seen_70 = set()
    prev_end = 0
    for match in re.finditer(r'\(70=', s):
        pos = match.start()
        window = s[prev_end:pos]
        # Se c'e' un'assegnazione diretta a 71-78 (es: (71=VALUE)) nel blocco,
        # il reset !7x non serve — l'assegnazione inizializza gia' il campo
        direct_assign = re.findall(r'\(7[1-8]=', window)
        has_reset = bool(re.search(r'!\s*7[1-8]', window))
        if not has_reset and not direct_assign:
            msg = (
                f"(70= alla pos. {pos}: manca reset !7x nel blocco precedente. "
                "Aggiungere (!71!72!73) prima dell'operazione con (70=...)."
            )
            if msg not in seen_70:
                # Se e' il reset a inizio formula, segnala ma non bloccare
                if prev_end == 0:
                    msg += " (NOTA: se (71=VALUE) precede direttamente, il reset e' opzionale)"
                errors.append(msg)
                seen_70.add(msg)
        prev_end = match.end()

    # Controllo operatori orari
    if re.search(r"\{\d+\}\s*[+\-]\s*['\"]", s):
        errors.append(
            "Uso di + o - su valori sessagesimali. "
            "Usare A (addizione) e S (sottrazione) per operazioni su orari."
        )

    # Controllo gestione mezzanotte per intervalli
    if re.search(r'\{2[5-7]\d\}', s) and not re.search(r'\{83\}<\{82\}', s):
        errors.append(
            "Formula con intervalli calcolati (251-290) senza gestione mezzanotte. "
            "Aggiungere: {83}<{82}({83}A'1440'={83});"
        )

    # Controllo sintassi assegnazioni
    # Verifica che le assegnazioni abbiano formato corretto (CAMPO=VALORE)
    assignments = re.findall(r'\((\d+)=([^)]*)\)', s)
    for field, value in assignments:
        # Verifica che il campo sia numerico
        if not field.isdigit():
            errors.append(f"Campo non numerico: {field}")
        # Verifica che il valore non sia vuoto
        if not value.strip():
            errors.append(f"Valore vuoto per campo {field}")

    # Controllo riferimenti a campi validi
    # Verifica che i riferimenti !NUMERO! abbiano formato corretto
    refs = re.findall(r'!(\d+)!', s)
    for ref in refs:
        if not ref.isdigit():
            errors.append(f"Riferimento campo non valido: !{ref}!")
        # Verifica che non sia un campo vietato
        if re.match(r'^[7-9]$', ref) or re.match(r'^1[0-9]$', ref) or re.match(r'^6[0-9]$', ref) or re.match(r'^9[0-9]$', ref):
            errors.append(f"Riferimento a campo vietato: !{ref}!")

    # ============================================================
    # VALIDAZIONE SEMANTICA — coerenza campo/valore
    # ============================================================
    _validate_semantic_coherence(s, errors)

    # Controllo codici di ritorno
    # Verifica che i codici R siano seguiti da punto e virgola
    if re.search(r'R\d+(?![;\d])', s):
        errors.append(
            "Codice di ritorno R senza punto e virgola finale. "
            "Usare formato: R110;"
        )

    # Controllo operatori aritmetici non supportati
    # Verifica che non ci siano operatori non supportati
    unsupported_ops = ['%', '^', '**']
    for op in unsupported_ops:
        if op in s:
            errors.append(f"Operatore non supportato: {op}")

    # ============================================================
    # NUOVI CONTROLLI 2026-06
    # ============================================================

    # Controllo '->' (NON e' un operatore WinSarp)
    if '->' in s:
        errors.append(
            "Operatore '->' non valido in WinSarp. "
            "Usa (70='1') per somma o (70='2') per differenza."
        )

    # Controllo ';' dentro parentesi tonde usato come separatore assegnazioni
    # Pattern: (NUMERO=NUMERO;NUMERO=NUMERO) -- ';' non separa assegnazioni
    semi_in_parens = re.findall(r'\(\d+=[^()]*;\d+=', s)
    if semi_in_parens:
        errors.append(
            "';' usato dentro ( ) per separare assegnazioni. "
            "Ogni assegnazione va in parentesi propria: (A=B)(C=D) non (A=B;C=D)."
        )

    # Controllo assegnazioni concatenate senza parentesi
    # Una assegnazione valida inizia con (CAMPO=VALORE).
    # Se troviamo CAMPO=VALORE non preceduto da (, e' concatenata illegalmente.
    for m in re.finditer(r'(?<!\()\b(\d{2,4}=[^\s;()]+)', s):
        # Escludi pattern che fanno parte di sintassi valida (es: R200, V04, P210)
        val = m.group(1)
        if val[0].isdigit():
            prefix = s[max(0, m.start()-1):m.start()]
            if prefix != '(' and '=' in val:
                errors.append(
                    f"Assegnazione '{val}' senza parentesi. "
                    f"Ogni assegnazione va in ( ): (CAMPO=VALORE)."
                )

    # Controllo + o - su orari (campi 81-83 o valori sessagesimali)
    time_op = re.findall(r'\^[\d.]+\^\s*[+-]\s*', s)
    if time_op:
        errors.append(
            "+ o - su valore sessagesimale (^...^). "
            "Usare A (addizione) o S (sottrazione) per orari."
        )

    # Controllo + o - in assegnazioni a campi orari 81-83
    # I campi 81-83 sono orari: usare A o S, non + o -
    for m in re.finditer(r'\(8[1-3]=([^)]+)', s):
        val = m.group(1)
        if '+' in val or '-' in val:
            field = m.group(0)[1:3]  # '81', '82', '83'
            errors.append(
                f"+ o - in assegnazione a campo orario {field} (81-83). "
                "Usare A (addizione) o S (sottrazione) per orari."
            )

    return errors


# ============================================================
# MAPPA SEMANTICA CAMPI WINSARP
# ============================================================
# Mappa di campi con i valori attesi per rilevare incongruenze logiche
_FIELD_SEMANTIC_MAP = {
    "DURATA": {500, 83, 81, 82},
    "STRAORDINARIO": {561, 562, 563, 570},
    "MAGGIORAZIONE": {562},
    "TFR": {600, 601, 610, 611, 620},
    "INPS": {300, 301, 302, 303, 304, 310},
    "IRPEF": {400, 401, 402, 403, 410},
    "ASSENZA": {510, 511, 512, 513},
    "FESTIVO": {520, 521, 522},
    "PERMESSO": {510, 530, 531},
    "RIMBORSO": {540, 541, 542},
    "TRATTENUTA": {550, 551, 552},
    "AZZERAMENTO": {100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110},
    "ORARIO": {81, 82, 83},
}


def _validate_semantic_coherence(code: str, errors: list) -> None:
    """
    Validazione semantica: controlla che i campi usati corrispondano
    al significato atteso dei valori. Rileva incongruenze logiche.

    Esempio: (561="DURATA") è sbagliato perché 561 è per straordinari, non durata.
             (500="STRAORDINARIO") è sbagliato perché 500 è per durata, non straordinari.
    """
    s = code

    # Controllo 1: per ogni assegnazione (CAMPO="VALORE"), verifica coerenza
    assignment_pattern = re.findall(r'\((\d+)=("[^"]*"|\'[^\']*\')\)', s)
    for field_num, raw_value in assignment_pattern:
        value = raw_value.strip('"').strip("'").upper()
        field = int(field_num)

        # Cerca a quale categoria appartiene il valore
        matched_categories = []
        for cat_name, cat_fields in _FIELD_SEMANTIC_MAP.items():
            if field in cat_fields:
                matched_categories.append(cat_name)

        # Se il valore assomiglia a una categoria, controlla se il campo è appropriato
        for cat_name, cat_fields in _FIELD_SEMANTIC_MAP.items():
            if (cat_name in value or value.startswith(cat_name[:4])) and (not matched_categories or cat_name not in matched_categories):
                suggested = sorted(cat_fields)[0] if cat_fields else field
                errors.append(
                    f"Incoerenza semantica: campo {field_num} usato per '{value}' "
                    f"(campo {field_num} è per {', '.join(matched_categories) if matched_categories else 'altro scopo'}). "
                    f"Probabilmente vuoi dire campo {suggested}."
                )

    # Controllo 2: campi numerici con valori che sembrano orari ma senza operatori orari
    time_fields = {81, 82, 83}
    for match in re.finditer(r'\((\d+)=(\d+)\)', s):
        field = int(match.group(1))
        val = match.group(2)
        if field in time_fields and len(val) <= 4:
            # OK — orario tipo 0830
            pass
        elif field not in time_fields and field not in range(71, 79) and val.isdigit() and len(val) == 4:
            # Escludi campi temporanei 71-78 (sono numerici generici)
            errors.append(
                f"Possibile errore: campo {field} assegnato a valore numerico '{val}' "
                f"che sembra un orario. I campi orari sono 81-83."
            )


def _semantic_fix_field(code: str) -> tuple[str, list[str]]:
    """
    Auto-correzione semantica: corregge automaticamente i campi
    usati in modo incongruente. Restituisce (codice_fissato, fix_applicati).
    """
    fixes = []
    original = code

    # Mappa inversa: da valore atteso al campo corretto
    value_to_field = {}
    for cat_name, cat_fields in _FIELD_SEMANTIC_MAP.items():
        for f in cat_fields:
            value_to_field.setdefault(cat_name, []).append(f)

    # Pattern: (NUMERO_CAMPO="VALORE")
    def _fix_assignment(match):
        nonlocal fixes
        field = int(match.group(1))
        value = match.group(2).strip('"').strip("'").upper()

        # Trova il campo corretto per questo valore
        for cat_name, cat_fields in _FIELD_SEMANTIC_MAP.items():
            if (cat_name in value or value.startswith(cat_name[:4])) and field not in cat_fields:
                suggested = sorted(cat_fields)[0]
                if suggested != field:
                    fixes.append(
                        f"Campo {field} corretto in {suggested} per '{value}'"
                    )
                    return f'({suggested}={match.group(2)})'
        return match.group(0)

    fixed = re.sub(r'\((\d+)=("[^"]*"|\'[^\']*\')\)', _fix_assignment, code)

    if fixed == original:
        return code, []
    return fixed, fixes


# ============================================================
# AUTO-CORREZIONE FORMULE
# ============================================================
def auto_fix_formula(code: str) -> tuple[str, list[str]]:
    """
    Corregge automaticamente gli errori sintattici più comuni nelle formule WinSarp.
    Include sia correzioni sintattiche che semantiche.
    Restituisce (codice_fissato, lista_errori_risolti).
    """
    if not code or not code.strip():
        return code, []

    original = code.strip()
    fixed = original
    fixes = []

    # Fix 1: Aggiunge ';' finale se mancante (errore più comune)
    if not fixed.endswith(';'):
        fixed += ';'
        fixes.append("Aggiunto ';' finale mancante")

    # Fix 2: Bilancia parentesi — solo se nessun IF-opener WinSarp coinvolto
    # Se il codice ha IF-opener, skippa il fix per non rompere la sintassi
    has_if_opener = any(
        ch == '(' and ci > 0 and _looks_like_if_opener(fixed, ci)
        for ci, ch in enumerate(fixed)
    )
    if not has_if_opener:
        open_p = fixed.count('(')
        close_p = fixed.count(')')
        if open_p > close_p:
            need = open_p - close_p
            if fixed.rstrip().endswith(';'):
                fixed = fixed.rstrip()[:-1] + ')' * need + ';'
            else:
                fixed += ')' * need
            fixes.append(f"Aggiunte {need} parentesi ')' mancanti")

    # Fix 3: Bilancia parentesi graffe — stile semplice
    open_b = fixed.count('{')
    close_b = fixed.count('}')
    if open_b > close_b:
        need_b = open_b - close_b
        if fixed.rstrip().endswith(';'):
            fixed = fixed.rstrip()[:-1] + '}' * need_b + ';'
        else:
            fixed += '}' * need_b
        fixes.append(f"Aggiunte {need_b} graffe '}}' mancanti")

    # Fix 4: Bilancia doppi apici
    if fixed.count('"') % 2 != 0:
        fixed += '"'
        fixes.append("Aggiunto doppio apice finale mancante")

    # Fix 5: Bilancia apici singoli
    if fixed.count("'") % 2 != 0:
        fixed += "'"
        fixes.append("Aggiunto apice singolo finale mancante")

    # Fix 6: Correzione semantica campi
    fixed_sem, sem_fixes = _semantic_fix_field(fixed)
    if sem_fixes:
        fixed = fixed_sem
        fixes.extend(sem_fixes)

    # Fix 7: Spazi multipli → singolo
    fixed = re.sub(r'\s+', ' ', fixed).strip()

    if fixed == original:
        return code, []  # Nessuna modifica

    return fixed, fixes


# ============================================================
# PARSING RISPOSTA MODELLO — Regex permissivo
# is_fallback utilizzata da app.py (importata da FALLBACK_PHRASES)
# ============================================================
def parse_response(full_response: str, modulo: str) -> dict:
    """
    Divide la risposta del modello in header + codice + spiegazione (WinSarp)
    oppure restituisce il testo grezzo (altri moduli).

    Il parsing usa _RE_FORMULA e _RE_SPIEGAZIONE (Regex case-insensitive)
    per gestire le variazioni di capitalizzazione che i modelli LLM producono.
    """
    result = {
        "code": "",
        "exp": "",
        "raw": full_response,
        "has_split": False,
        "errors": [],
    }

    if modulo != "WinSarp":
        return result

    has_formula = bool(_RE_FORMULA.search(full_response))
    has_spiegazione = bool(_RE_SPIEGAZIONE.search(full_response))
    has_code_block = bool(_RE_BLOCK_CODE.search(full_response))

    if has_formula and has_spiegazione:
        parts = _RE_FORMULA.split(full_response, maxsplit=1)
        header = parts[0].strip()
        rest = _RE_SPIEGAZIONE.split(parts[1], maxsplit=1)
        code_raw = rest[0].strip()
        spiegazione = rest[1].strip() if len(rest) > 1 else ""
        # Rimuove [/formula] eccessivo
        code_raw = re.sub(r'\[/formula\].*', '', code_raw, flags=re.IGNORECASE).strip()
        result["code"] = clean_code(code_raw)
        result["exp"] = (header + "\n\n" + spiegazione).strip()
        result["has_split"] = True

    elif has_formula:
        parts = _RE_FORMULA.split(full_response, maxsplit=1)
        code_raw = parts[1].strip()
        # Rimuove [/formula] eccessivo
        code_raw = re.sub(r'\[/formula\].*', '', code_raw, flags=re.IGNORECASE).strip()
        result["code"] = clean_code(code_raw)
        result["exp"] = parts[0].strip()
        result["has_split"] = True

    elif has_code_block:
        # Estrai il contenuto del primo blocco di codice
        m = _RE_BLOCK_CODE.search(full_response)
        if m:
            code_raw = m.group(1).strip()
        else:
            code_raw = ""
        # Il resto (prima e dopo il blocco) e' spiegazione
        parts = _RE_BLOCK_CODE.split(full_response, maxsplit=1)
        exp_parts = [p.strip() for p in [parts[0], parts[2]] if p.strip()]
        result["exp"] = "\n\n".join(exp_parts)
        result["code"] = clean_code(code_raw)
        result["has_split"] = True

    elif has_spiegazione:
        parts = _RE_SPIEGAZIONE.split(full_response, maxsplit=1)
        result["code"] = clean_code(parts[0])
        result["exp"] = parts[1].strip() if len(parts) > 1 else ""
        result["has_split"] = True

    else:
        # Non processare testo normale come codice WinSarp
        # Se non ci sono marker di formula, lascia la risposta così com'è
        result["code"] = ""
        result["exp"] = full_response
        result["has_split"] = False

    if result["code"]:
        # Auto-correzione: prova a fixare errori comuni
        fixed_code, fixes = auto_fix_formula(result["code"])
        if fixes:
            result["code"] = fixed_code
            result["auto_fixes"] = fixes
        result["errors"] = validate_winsarp(result["code"])

    return result

