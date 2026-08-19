"""
modules/winsarp/validator.py
Validazione formule WinSarp: bilanciamento parentesi, apici, campi vietati,
coerenza semantica e auto-correzione.
"""
import re

# ============================================================
# MAPPA SEMANTICA CAMPI WINSARP
# ============================================================
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


# ============================================================
# BILANCIAMENTO PARENTESI
# ============================================================
def _looks_like_if_opener(s: str, pos: int) -> bool:
    if pos <= 0 or s[pos] != '(':
        return False
    prev = s[pos - 1]
    if prev == '>':
        return True
    if prev.isalpha():
        return not (pos >= 2 and s[pos - 2] == '=')
    if prev == ')':
        return True
    if prev in ("'", '"') and pos >= 2:
        for j in range(pos - 2, max(pos - 10, 0) - 1, -1):
            if s[j].isdigit():
                if j > 0 and s[j - 1] in ('O', 'E', '>', '<', '=', 'U', 'Z'):
                    return True
                return True
            if s[j] in (';', '(', ')'):
                break
        return True
    if prev.isdigit():
        if pos >= 2:
            p2 = s[pos - 2]
            if p2 == '=':
                return False
            if p2.isdigit() or p2 == '>' or p2 == '<' or p2.isalpha():
                return True
        return True
    return prev == '}'


def _check_balance(s: str) -> list[str]:
    errors = []
    stack = []
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
                    f"Parentesi ')' inaspettata alla posizione {i}"
                )
        elif ch == '}':
            if stack and stack[-1][0] == '{':
                stack.pop()
            else:
                errors.append(
                    f"Graffa '}}' inaspettata alla posizione {i}"
                )
    for opener, pos in stack:
        if opener == '(' and _looks_like_if_opener(s, pos):
            continue
        expected = pairs[opener]
        name = "tonda" if opener == '(' else "graffa"
        errors.append(
            f"Parentesi {name} '{opener}' aperta alla posizione {pos} "
            f"senza la '{expected}' corrispondente"
        )
    return errors


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


def _validate_semantic_coherence(code: str, errors: list) -> None:
    assignment_pattern = re.findall(r'\((\d+)=("[^"]*"|\'[^\']*\')\)', code)
    for field_num, raw_value in assignment_pattern:
        value = raw_value.strip('"').strip("'").upper()
        field = int(field_num)
        matched_categories = []
        for cat_name, cat_fields in _FIELD_SEMANTIC_MAP.items():
            if field in cat_fields:
                matched_categories.append(cat_name)
        for cat_name, cat_fields in _FIELD_SEMANTIC_MAP.items():
            if (cat_name in value or value.startswith(cat_name[:4])) and (not matched_categories or cat_name not in matched_categories):
                errors.append(
                    f"Incoerenza semantica: campo {field_num} usato per '{value}'"
                )

    time_fields = {81, 82, 83}
    for match in re.finditer(r'\((\d+)=(\d+)\)', code):
        field = int(match.group(1))
        val = match.group(2)
        if field not in time_fields and field not in range(71, 79) and val.isdigit() and len(val) == 4:
            errors.append(
                f"Possibile errore: campo {field} assegnato a valore numerico '{val}' "
                f"che sembra un orario. I campi orari sono 81-83."
            )


# ============================================================
# VALIDAZIONE PRINCIPALE
# ============================================================
def validate_winsarp(code: str) -> list:
    errors = []
    s = code.strip()
    if not s:
        return ["Formula vuota."]
    if not s.endswith(';'):
        errors.append("La formula non termina con ';'.")
    bal_errors = _check_balance(s)
    errors.extend(bal_errors)
    q_errors = _check_quote_balance(s)
    errors.extend(q_errors)

    forbidden = [
        (r'\([7-9]\d*[=\)]', "Campi 7-9 vietati"),
        (r'\(1[0-9]\d*[=\)]', "Campi 10-19 vietati"),
        (r'\(6[0-9]\d*[=\)]', "Campi 60-69 vietati"),
        (r'\(9[0-9]\d*[=\)]', "Campi 90-99 vietati"),
        (r'\(79\d*[=\)]', "Campo 79 riservato"),
    ]
    for pat, msg in forbidden:
        if re.search(pat, s):
            errors.append(msg)

    seen_70 = set()
    prev_end = 0
    for match in re.finditer(r'\(70=', s):
        pos = match.start()
        window = s[prev_end:pos]
        direct_assign = re.findall(r'\(7[1-8]=', window)
        has_reset = bool(re.search(r'!\s*7[1-8]', window))
        if not has_reset and not direct_assign:
            msg = f"(70= alla pos. {pos}: manca reset !7x nel blocco precedente."
            if msg not in seen_70:
                if prev_end == 0:
                    msg += " (NOTA: se (71=VALUE) precede, il reset e' opzionale)"
                errors.append(msg)
                seen_70.add(msg)
        prev_end = match.end()

    if re.search(r'\{\d+\}\s*[+\-]\s*["\']', s):
        errors.append("Uso di + o - su valori sessagesimali. Usare A/S.")
    if re.search(r'\{2[5-7]\d\}', s) and not re.search(r'\{83\}<\{82\}', s):
        errors.append("Formula con intervalli senza gestione mezzanotte.")

    if '->' in s:
        errors.append("Operatore '->' non valido in WinSarp.")
    semi_in_parens = re.findall(r'\(\d+=[^()]*;\d+=', s)
    if semi_in_parens:
        errors.append("';' dentro ( ) per separare assegnazioni.")
    for m in re.finditer(r'(?<!\()\b(\d{2,4}=[^\s;()]+)', s):
        val = m.group(1)
        if val[0].isdigit():
            prefix = s[max(0, m.start()-1):m.start()]
            if prefix != '(' and '=' in val:
                errors.append(f"Assegnazione '{val}' senza parentesi.")

    _validate_semantic_coherence(s, errors)
    if re.search(r'R\d+(?![;\d])', s):
        errors.append("Codice R senza punto e virgola finale.")
    for op in ['%', '^', '**']:
        if op in s:
            errors.append(f"Operatore non supportato: {op}")
    time_op = re.findall(r'\^[\d.]+\^\s*[+-]\s*', s)
    if time_op:
        errors.append("+ o - su valore sessagesimale (^...^). Usare A/S.")
    for m in re.finditer(r'\(8[1-3]=([^)]+)', s):
        val = m.group(1)
        if '+' in val or '-' in val:
            errors.append("+ o - in campo orario 81-83. Usare A/S.")
    return errors


# ============================================================
# AUTO-CORREZIONE
# ============================================================
def auto_fix_formula(code: str) -> tuple[str, list[str]]:
    if not code or not code.strip():
        return code, []
    original = code.strip()
    fixed = original
    fixes = []

    if not fixed.endswith(';'):
        fixed += ';'
        fixes.append("Aggiunto ';' finale mancante")

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

    open_b = fixed.count('{')
    close_b = fixed.count('}')
    if open_b > close_b:
        need_b = open_b - close_b
        if fixed.rstrip().endswith(';'):
            fixed = fixed.rstrip()[:-1] + '}' * need_b + ';'
        else:
            fixed += '}' * need_b
        fixes.append(f"Aggiunte {need_b} graffe '}}' mancanti")
    if fixed.count('"') % 2 != 0:
        fixed += '"'
        fixes.append("Aggiunto doppio apice finale mancante")
    if fixed.count("'") % 2 != 0:
        fixed += "'"
        fixes.append("Aggiunto apice singolo finale mancante")
    fixed = re.sub(r'\s+', ' ', fixed).strip()
    if fixed == original:
        return code, []
    return fixed, fixes
