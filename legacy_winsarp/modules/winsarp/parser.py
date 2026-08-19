"""
modules/winsarp/parser.py
Parsing e pulizia delle risposte LLM per il modulo WinSarp.
Estrae codice formula e spiegazione dai tag [formula][/formula][spiegazione][/spiegazione].
"""
import re

_RE_FORMULA = re.compile(r'\[\s*formula\s*\]', re.IGNORECASE)
_RE_SPIEGAZIONE = re.compile(r'\[\s*spiegazione\s*\]', re.IGNORECASE)
_RE_CODE_FENCE = re.compile(r'```[\w-]*')
_RE_BLOCK_CODE = re.compile(r'```[\w-]*\s*\n(.*?)```', re.DOTALL)
_RE_MULTI_SPACE = re.compile(r'\s+')


def _find_comment_start(line: str):
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


def clean_code(raw: str) -> str:
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


def parse_response(full_response: str, modulo: str) -> dict:
    from .validator import auto_fix_formula, validate_winsarp

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
        code_raw = re.sub(r'\[/formula\].*', '', code_raw, flags=re.IGNORECASE).strip()
        result["code"] = clean_code(code_raw)
        result["exp"] = (header + "\n\n" + spiegazione).strip()
        result["has_split"] = True
    elif has_formula:
        parts = _RE_FORMULA.split(full_response, maxsplit=1)
        code_raw = parts[1].strip()
        code_raw = re.sub(r'\[/formula\].*', '', code_raw, flags=re.IGNORECASE).strip()
        result["code"] = clean_code(code_raw)
        result["exp"] = parts[0].strip()
        result["has_split"] = True
    elif has_code_block:
        m = _RE_BLOCK_CODE.search(full_response)
        if m:
            code_raw = m.group(1).strip()
        else:
            code_raw = ""
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
        result["code"] = ""
        result["exp"] = full_response
        result["has_split"] = False

    if result["code"]:
        fixed_code, fixes = auto_fix_formula(result["code"])
        if fixes:
            result["code"] = fixed_code
            result["auto_fixes"] = fixes
        result["errors"] = validate_winsarp(result["code"])
    return result
