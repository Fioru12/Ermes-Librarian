"""
pattern_composer.py
Compositore pattern-based per formule WinSarp.
Usa le formule reali di FormuleWinsarpInUso.txt come template.
LLM identifica parametri, il composer applica modifiche deterministiche.
"""
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)

FORMULE_PATH = Path("FormuleWinsarpInUso.txt")


@dataclass
class PatternTemplate:
    id: int
    scopo: str
    body: str
    tags: set[str] = field(default_factory=set)


PATTERNS: dict[int, PatternTemplate] = {}


def _load_patterns() -> dict[int, PatternTemplate]:
    if PATTERNS:
        return PATTERNS
    if not FORMULE_PATH.exists():
        _logger.warning("File %s non trovato", FORMULE_PATH)
        return {}
    content = FORMULE_PATH.read_text(encoding="utf-8")
    blocks = re.split(r'\n\s*(?=formula\s+\d+)', content, flags=re.IGNORECASE)
    scopati = {
        5: "Riconoscimento automatico turno",
        10: "Riconoscimento turno su calendario",
        100: "Calcolo presenza con R 110",
        110: "Calcolo ore ordinarie/straordinarie con assenze",
        120: "Smistamento flag festivo/dominica",
        130: "Causale SFN e accumulo K601/K604",
        140: "Causale SN e accumulo straordinario",
        200: "Accumulo K601/K602 e richiamo P210",
        210: "Calcolo straordinario settimanale",
        1000: "Inizializzazione intervalli previsionali",
        1010: "Inizializzazione intervalli con timbrature",
        1020: "Reindirizzamento timbrature su intervalli",
        1100: "Calcolo ore con gestione assenze",
        1120: "Calcolo ore con assenze su intervalli",
        2000: "Riapertura giornata",
        2050: "Calcolo pausa pranzo",
        2051: "Calcolo pausa pranzo due turni",
        2060: "Taglio timbrature dopo 20:05",
        2100: "Primo giro completo",
        2101: "Secondo giro completo",
        2105: "Primo giro con pausa pranzo",
        2106: "Secondo giro con pausa pranzo",
        2107: "Calcolo maggiorazioni",
        2109: "Festivita automatiche",
        2114: "Ritocco SB/SA",
        2115: "Esplosione causali automatiche",
        2122: "Rilevazione orario notturno/festivo",
        2123: "Calcolo maggiorazioni per causali (1)",
        2124: "Calcolo maggiorazioni per causali (2)",
        2130: "Warning ore carenti",
        3000: "Primo giro GUGEST",
        3001: "Secondo giro GUGEST",
        3002: "Straordinario settimanale ante 01/06/2023",
        3003: "Straordinario settimanale post 01/06/2023",
        3004: "Maggiorazioni turnisti",
        3005: "Straordinario su GUGEST",
        3009: "Festivita automatiche GUGEST",
        3015: "Esplosione causali GUGEST",
        3017: "Gestione AUTS",
        3030: "Warning ore 250h",
    }
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = re.match(r'formula\s+(\d+)', block, re.IGNORECASE)
        if not m:
            continue
        num = int(m.group(1))
        body = block[m.end():].strip().replace('\r\n', '\n')
        tags = set()
        if re.search(r'900\s*[=<>]|58\s*=|INDICATORE', body[:200]):
            tags.add('turno')
        if re.search(r'K\d{3}\s+[AILST]', body):
            tags.add('accumulo_k')
        if re.search(r'\bR\s*\d+', body):
            tags.add('richiamo_r')
        if re.search(r'\bP\s*\d+', body):
            tags.add('richiamo_p')
        if re.search(r'608|609|5\s*=\s*\d+', body):
            tags.add('assenze')
        if re.search(r'55\s+U\s+I|K60[35]', body):
            tags.add('festivo')
        if re.search(r'K61[0-9]|K62[0-9]', body):
            tags.add('straordinario')
        if re.search(r'251|271|111|141', body):
            tags.add('intervalli')
        if re.search(r'300\s+U\s+301|PRIMO\s*GIRO|770', body):
            tags.add('primo_giro')
        if re.search(r'SECONDO\s*GIRO|783', body):
            tags.add('secondo_giro')
        if re.search(r'K90[0-9]', body):
            tags.add('maggiorazioni')
        if re.search(r'501\s*=|F"|SN|SF|SA|SB|LFS', body):
            tags.add('causali')
        PATTERNS[num] = PatternTemplate(
            id=num, scopo=scopati.get(num, f"Formula #{num}"),
            body=body, tags=tags,
        )
    _logger.info("Caricati %d pattern da %s", len(PATTERNS), FORMULE_PATH.name)
    return PATTERNS


def find_best_pattern(user_request: str) -> tuple[int, PatternTemplate] | None:
    patterns = _load_patterns()
    if not patterns:
        return None
    query_lower = user_request.lower()
    parole_chiave = {p.lower() for p in re.findall(r'\b([A-Za-z]{3,})\b', query_lower)}
    scored: list[tuple[float, int, PatternTemplate]] = []
    for num, pt in patterns.items():
        score = 0.0
        body_lower = pt.body.lower()
        for pw in parole_chiave:
            if pw in body_lower:
                score += 2.0
        scopo_lower = pt.scopo.lower()
        for pw in parole_chiave:
            if pw in scopo_lower:
                score += 5.0
        if "turno" in parole_chiave and "turno" in pt.tags:
            score += 20.0
        if "straordinario" in parole_chiave and "straordinario" in pt.tags:
            score += 20.0
        if any(a in parole_chiave for a in ["assenze", "assenza"]) and "assenze" in pt.tags:
            score += 20.0
        if "festivo" in parole_chiave and "festivo" in pt.tags:
            score += 20.0
        if any(a in parole_chiave for a in ["primo", "giro"]) and "primo_giro" in pt.tags:
            score += 25.0
        if any(a in parole_chiave for a in ["secondo", "giro"]) and "secondo_giro" in pt.tags:
            score += 25.0
        if "maggiorazione" in parole_chiave and "maggiorazioni" in pt.tags:
            score += 25.0
        if "causale" in parole_chiave and "causali" in pt.tags:
            score += 20.0
        if "notturno" in parole_chiave and "intervalli" in pt.tags:
            score += 15.0
        if "presenza" in parole_chiave or "durata" in parole_chiave and num == 100:
            score += 20.0
        if num in (1000, 1010, 1020) and parole_chiave - {'di', 'il', 'la', 'le', 'gli', 'con', 'che', 'per'} - {'intervalli', 'timbratura', 'timbrature', 'inizializzazione', 'reindirizzamento'}:
            score *= 0.1
        if score > 0:
            scored.append((score, num, pt))
    if not scored:
        return None  # Nessun pattern matcha — non cadere su formula 5 come fallback silenzioso
    scored.sort(key=lambda x: -x[0])
    return (scored[0][1], scored[0][2])


def extract_parameters_via_llm(user_request: str, pattern: PatternTemplate,
                                model: str = "tencent/hy3:free", timeout: int = 30) -> dict | None:
    try:
        from core.ai.utils import call_llm
    except ImportError:
        return None
    prompt = (
        f"Sei un analista WinSarp. Data una richiesta utente e un template formula, "
        f"identifica i valori specifici che l'utente menziona e che vanno inseriti nel template.\n\n"
        f"TEMPLATE FORMULA #{pattern.id}: {pattern.scopo}\n"
        f"```\n{pattern.body}\n```\n\n"
        f"RICHIESTA UTENTE:\n{user_request}\n\n"
        f"COMPITO: Estrai i parametri dalla richiesta dell'utente in formato JSON.\n"
        f"Regole:\n"
        f"- 'turni': lista di oggetti con 'nome', 'ora_inizio', 'ora_fine', 'flag' se la richiesta riguarda turni\n"
        f"- 'campi': oggetto con parametri (nome: valore) per altri campi menzionati\n"
        f"- 'k_register': [Kxxx] per accumuli menzionati\n"
        f"- 'r_calls': [numero] per chiamate R menzionate\n"
        f"- 'p_calls': [numero] per chiamate P menzionate\n"
        f"- 'causali': lista di oggetti con 'sigla', 'campo', 'valore' per causali\n"
        f"- 'assenze': true/false se la richiesta riguarda assenze\n"
        f"- 'festivo': true/false se la richiesta riguarda festivita\n\n"
        f"Se non trova parametri, output '{{}}'.\n"
        f"Output SOLO JSON.\n"
    )
    try:
        raw = call_llm(prompt=prompt, model_id=model, temp=0.1, timeout=timeout)
        if not raw.strip():
            return None
        import json as _json
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return None
        return _json.loads(m.group(0))
    except Exception as e:
        _logger.warning("Parameter extraction error: %s", e)
        return None


def _fmt_ora(s: str) -> str:
    s = s.strip("'\" ")
    if s.isdigit():
        return f'{int(s):02d}.00'
    if '.' in s:
        parts = s.split('.')
        if len(parts) == 2 and parts[1].isdigit():
            return f'{int(parts[0]):02d}.{int(parts[1]):02d}'
        return s
    return s


_TURNO_BLOCK_RE = re.compile(
    r"\{\s*801\s*\}\s*>\s*U\s*'(\d{2}\.\d{2})'\s*E\s*\{\s*801\s*\}\s*<\s*U\s*'(\d{2}\.\d{2})'\s*"
    r"\(\s*\(\s*58\s*=\s*\"([A-Z]+)\"\s*\)"
)


def compose_formula(pattern: PatternTemplate, params: dict | None = None) -> str:
    if not params:
        return pattern.body
    formula = pattern.body
    turni = params.get("turni", [])
    if turni and pattern.id in (5, 10):
        blocks = list(_TURNO_BLOCK_RE.finditer(formula))
        if not blocks:
            return formula
        # Sostituisci dall'ultimo al primo per non invalidare le posizioni
        for i in reversed(range(min(len(turni), len(blocks)))):
            t = turni[i]
            m = blocks[i]
            nome = str(t.get("nome", "")).upper().strip("'\"") or m.group(3)
            ora_inizio = _fmt_ora(str(t.get("ora_inizio", m.group(1))))
            ora_fine = _fmt_ora(str(t.get("ora_fine", m.group(2))))
            flag = str(t.get("flag", "")).strip("'\"")
            nuovo = (
                f"{{ 801 }} > U '{ora_inizio}' E {{ 801 }} < U '{ora_fine}' "
                f"(( 58 = \"{nome}\" )"
            )
            formula = formula[:m.start()] + nuovo + formula[m.end():]
            # Aggiorna 900 = flag nel resto dopo questo blocco (usa stesso blocco + offset)
            if flag:
                block_end = m.start() + len(nuovo)
                before = formula[:block_end]
                after = formula[block_end:]
                after = re.sub(r"900\s*=\s*'[^']*'", f"900 = '{flag}'", after, count=1)
                formula = before + after
    k_regs = params.get("k_register", [])
    for k in k_regs:
        k_line = f"( {k} A 3 A 4 )"
        if k_line not in formula:
            formula = re.sub(r'(\s*VF\s*)$', f"\n{k_line}\nVF", formula)
    r_calls = params.get("r_calls", [])
    for r in r_calls:
        r_line = f"R {r}"
        if r_line not in formula:
            formula = re.sub(r'(\s*VF\s*)$', f"\n{r_line}\nVF", formula)
    p_calls = params.get("p_calls", [])
    for p in p_calls:
        p_line = f"P {p}"
        if p_line not in formula:
            formula = re.sub(r'(\s*VF\s*)$', f"\n{p_line}\nVF", formula)
    return formula.strip()


def generate(user_request: str, model: str = "tencent/hy3:free",
             timeout: int = 30) -> dict:
    result = find_best_pattern(user_request)
    if not result:
        return {"success": False, "error": "Nessun pattern trovato"}
    num, pattern = result
    params = extract_parameters_via_llm(user_request, pattern, model, timeout)
    formula = compose_formula(pattern, params)
    fase = "IG"
    if "primo_giro" in pattern.tags or "secondo_giro" in pattern.tags:
        fase = "FG"
    elif "turno" in pattern.tags:
        fase = "IG"
    elif "causali" in pattern.tags:
        fase = "DG"
    return {
        "success": True,
        "formula": formula,
        "template_id": num,
        "template_scopo": pattern.scopo,
        "params_used": list(params.keys()) if params else [],
        "fase": fase,
        "chars": len(formula),
    }
