"""
winsarp_parser.py
Parser strutturale WinSarp: depth-tracking char-by-char, gestisce tutti i pattern reali.
"""
from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

# ─────── DATA MODEL ───────

@dataclass
class Value:
    kind: str
    value: Any = None
    field: int | None = None
    def __str__(self) -> str:
        return f"{self.kind}({self.value or self.field})"

@dataclass
class Condition:
    left: Value
    operator: str
    right: Value
    connector: str | None = None
    next: Condition | None = None
    def __str__(self) -> str:
        s = f"{self.left} {self.operator} {self.right}"
        if self.next:
            s += f" {self.connector} {self.next}"
        return s

@dataclass
class Op:
    op_type: str
    field: int | str | None = None
    value: Value | None = None
    raw: str = ''
    def __repr__(self) -> str:
        return f"{self.op_type}({self.field})"

@dataclass
class Block:
    condition: str = ""
    actions: list[Op] = field(default_factory=list)
    jump: str | None = None
    fields_read: set[int] = field(default_factory=set)
    fields_written: set[int] = field(default_factory=set)

@dataclass
class ParsedFormula:
    id: int
    code: str
    blocks: list[Block] = field(default_factory=list)
    calls_r: list[int] = field(default_factory=list)
    calls_p: list[int] = field(default_factory=list)
    fields_read: set[int] = field(default_factory=set)
    fields_written: set[int] = field(default_factory=set)


# ─────── HELPERS ───────

def _classify_val(tok: str) -> Value:
    tok = tok.strip()
    if tok.startswith('"') or tok.startswith("'"):
        return Value('literal', tok.strip("\"'"))
    if tok.startswith('{') and tok.endswith('}'):
        inner = tok.strip('{}').strip()
        return Value('deref', None, int(inner) if inner.isdigit() else 0)
    if tok.startswith('K'):
        return Value('kreg', tok)
    if tok.isdigit():
        return Value('field', None, int(tok))
    if tok in ('I', 'Z'):
        return Value('indefinito', tok)
    return Value('literal', tok)


def _tokenize_line(line: str) -> list[str]:
    tokens = []
    i = 0
    while i < len(line):
        c = line[i]
        if c in '()':
            tokens.append(c)
            i += 1
        elif c == '{':
            j = line.index('}', i) + 1 if '}' in line[i:] else len(line)
            tokens.append(line[i:j])
            i = j
        elif c in ("'", '"'):
            q = c
            j = i + 1
            while j < len(line) and line[j] != q:
                j += 1
            tokens.append(line[i:j + 1])
            i = j + 1
        elif c == '!':
            tokens.append('!')
            i += 1
        elif c == '[':
            tokens.append('[')
            i += 1
        elif c == ']':
            tokens.append(']')
            i += 1
        elif c == '>':
            if i + 1 < len(line) and line[i + 1] == 'U':
                tokens.append('>=')
                i += 2
            elif i + 1 < len(line) and line[i + 1] == '=':
                tokens.append('>=')
                i += 2
            else:
                tokens.append('>')
                i += 1
        elif c == '<':
            if i + 1 < len(line) and line[i + 1] == 'U':
                tokens.append('<=')
                i += 2
            elif i + 1 < len(line) and line[i + 1] == '=':
                tokens.append('<=')
                i += 2
            else:
                tokens.append('<')
                i += 1
        elif c == '#':
            tokens.append('#')
            i += 1
        elif c == '=':
            tokens.append('=')
            i += 1
        elif c in ' \t':
            i += 1
        else:
            j = i
            while j < len(line) and line[j] not in '(){}[]<>#=! \t?\'"':
                j += 1
            token = line[i:j]
            # Split VF/VU/E when adjacent to digits: VF800 → VF + 800
            if (token.startswith('VF') or token.startswith('VU')) and len(token) > 2:
                tokens.append(token[:2])
                tokens.append(token[2:])
            elif token.startswith('E') and len(token) > 1 and token[1:].isdigit():
                tokens.append('E')
                tokens.append(token[1:])
            elif token in ('E', 'O', 'A', 'S', 'I', 'Z', 'VF', 'VU', 'U', 'UZ'):
                tokens.append(token)
            elif token.startswith('K') and (len(token) == 3 or len(token) == 4):
                tokens.append(token)
            elif token.startswith('V') and len(token) == 3 and token[1:].isdigit():
                tokens.append(token)
            elif token.startswith('P') and token[1:].isdigit():
                tokens.append('P')
                tokens.append(token[1:])
            elif token.startswith('R') and token[1:].isdigit():
                tokens.append('R')
                tokens.append(token[1:])
            else:
                tokens.append(token)
            i = j
    return tokens


def _extract_jump_from_tokens(tokens: list[str], start: int) -> tuple[str | None, int]:
    """Try to extract a jump target from tokens starting at position start.
    Recognizes: Vxx, VF, VU, R NNN, P NNN.
    Returns (jump_string, new_pos) or (None, start).
    """
    if start >= len(tokens):
        return None, start
    t = tokens[start]
    if t in ('VF', 'VU') or (t.startswith('V') and len(t) == 3 and t[1:].isdigit()):
        return t, start + 1
    if t == 'R' and start + 1 < len(tokens) and tokens[start + 1].isdigit():
        return f"R {tokens[start + 1]}", start + 2
    if t == 'P' and start + 1 < len(tokens) and tokens[start + 1].isdigit():
        return f"P {tokens[start + 1]}", start + 2
    return None, start


def _split_block_from_tokens(tokens: list[str]) -> Block | None:
    """Parse one block from the front of the token list.
    Returns Block and modifies tokens in place.
    """
    if not tokens:
        return None

    pos = 0
    block = Block()

    # --- Phase 1: collect condition tokens (before any '(' ) ---
    cond_tokens = []
    while pos < len(tokens) and tokens[pos] != '(':
        cond_tokens.append(tokens[pos])
        pos += 1

    # --- Phase 2: collect paren groups and jump ---
    paren_actions = []
    paren_depth = 0
    paren_start = -1
    jump = None

    while pos < len(tokens):
        if tokens[pos] == '(':
            if paren_depth == 0:
                paren_start = pos
            paren_depth += 1
            # Peek ahead: if next tokens are Vxx, VF, VU and depth is 1, this is a jump target
            if paren_depth == 1:
                next_jump, _ = _extract_jump_from_tokens(tokens, pos + 1)
                if next_jump:
                    # This is a condition → jump block, like "200 U Z O 58 U 'RIPO' ( VF"
                    # We've already collected cond_tokens, now just set the jump
                    jump = next_jump
                    pos += 2  # consume '(' and the jump token
                    # Check if there are more paren-closing tokens after - might not have ')'
                    if pos < len(tokens) and tokens[pos] == ')':
                        pos += 1
                    # After a condition → jump block, stop
                    break
            pos += 1
        elif tokens[pos] == ')':
            paren_depth -= 1
            if paren_depth == 0 and paren_start >= 0:
                # Extract the paren content (without outer parens)
                inner = tokens[paren_start + 1:pos]
                paren_actions.append(tuple(inner))
                paren_start = -1
            pos += 1
        elif paren_depth > 0:
            pos += 1
        else:
            # At depth 0, after parens closed: could be a jump
            j, newpos = _extract_jump_from_tokens(tokens, pos)
            if j:
                jump = j
                pos = newpos
            else:
                pos += 1

    # Remove consumed tokens
    del tokens[:pos]

    # --- Phase 3: classify results ---
    cond_text = ' '.join(cond_tokens).strip()

    # Check condition → jump (no actions): "200 U Z O 58 U 'RIPO' ( VF"
    if cond_text and jump and not paren_actions:
        block.condition = cond_text
        block.jump = jump
        block.fields_read = _find_fields(cond_text)
        return block

    # Check condition + actions + optional jump
    if cond_text:
        block.condition = cond_text
        block.fields_read = _find_fields(cond_text)

    # Parse action paren groups
    for action_tuple in paren_actions:
        action_str = ' '.join(t for t in action_tuple if t != '(' and t != ')')
        ops = _parse_one_action_from_text(action_str)
        block.actions.extend(ops)

    if jump:
        block.jump = jump

    _update_field_analysis(block)

    if block.condition or block.actions or block.jump:
        return block

    return None


def _find_fields(text: str) -> set[int]:
    fields: set[int] = set()
    for m in re.finditer(r'\{(\d+)\}|\b(\d{2,})\b', text):
        if m.group(1):
            fields.add(int(m.group(1)))
        elif m.group(2):
            v = int(m.group(2))
            if v > 9:
                fields.add(v)
    return fields


def _parse_one_action_from_text(text: str) -> list[Op]:
    """Parse a single action like '801 = 200', '!900', 'K803 A 24', etc."""
    text = text.strip()
    if not text:
        return []

    # Reset operation: !field
    if text.startswith('!'):
        parts = text[1:].strip().split('!')
        return [Op('RESET', int(p.strip())) for p in parts if p.strip().isdigit()]

    # Pointer open: [field
    if text.startswith('['):
        parts = text[1:].strip().split()
        if parts and parts[0].isdigit():
            return [Op('PTR_OPEN', int(parts[0]))]
        return [Op('UNKNOWN', raw=text)]

    # Pointer close: ]field
    if text.startswith(']'):
        parts = text[1:].strip().split()
        if parts and parts[0].isdigit():
            return [Op('PTR_CLOSE', int(parts[0]))]
        return [Op('UNKNOWN', raw=text)]

    # CAMPO70: 70='code'
    m = re.match(r"70\s*=\s*'(\d+)'$", text)
    if m:
        return [Op('CAMPO70', 70, Value('literal', m.group(1)))]

    # CAMPO70 string variant: 70="code"
    m = re.match(r'70\s*=\s*"(\d+)"$', text)
    if m:
        return [Op('CAMPO70', 70, Value('literal', m.group(1)))]

    # Deref operation with assignment: {83}A'1440'={83}
    m = re.match(r'\{(\d+)\}\s*(A|S)\s*([^=]+)=\s*\{(\d+)\}$', text)
    if m:
        fid = int(m.group(1))
        op = m.group(2)
        val = _classify_val(m.group(3).strip())
        target = int(m.group(4))
        op_type = 'ADD' if op == 'A' else 'SUB'
        return [Op(op_type, fid, val), Op('SET', target, Value('deref', None, fid))]

    # Deref ADD/SUB without assignment: {83}A'1440'
    m = re.match(r'\{(\d+)\}\s*(A|S)\s*(.+)$', text)
    if m:
        fid = int(m.group(1))
        op = m.group(2)
        val = _classify_val(m.group(3).strip())
        op_type = 'ADD' if op == 'A' else 'SUB'
        return [Op(op_type, fid, val)]

    # K-register operation with multiple addends: K771 A 3 A 4 → ADD K771 3 + ADD K771 4
    m = re.match(r'(K\d+)\s*(A|S)\s+(.+)$', text)
    if m:
        kname = m.group(1)
        ktype = m.group(2)
        rest = m.group(3).strip()
        opmap = {'A': 'ADD', 'S': 'SUB'}
        parts = re.split(r'\s+[AS]\s+', rest)
        ops = []
        for p in parts:
            p = p.strip()
            if p in ('I', 'Z'):
                ops.append(Op(opmap[ktype], kname, Value('indefinito', p)))
            else:
                ops.append(Op(opmap[ktype], kname, _classify_val(p)))
        return ops

    # K-register = operation: K803 = 24
    m = re.match(r'(K\d+)\s*=\s*(.+)$', text)
    if m:
        kname = m.group(1)
        val = _classify_val(m.group(2).strip())
        return [Op('SET', kname, val)]

    # K-register increment/decrement: K770 + 1, K801+'30', K770 - I
    m = re.match(r"(K\d+)\s*([+-])\s*(.+)$", text)
    if m:
        kname = m.group(1)
        op = m.group(2)
        val_raw = m.group(3).strip()
        opmap = {'+': 'ADD', '-': 'SUB'}
        # Use _classify_val with original raw (preserving quotes)
        if val_raw in ('I', 'Z'):
            return [Op(opmap[op], kname, Value('indefinito', val_raw))]
        return [Op(opmap[op], kname, _classify_val(f'\'{val_raw}\'' if val_raw.isdigit() else val_raw))]

    # Compound field assignment: 3 = 800 S 608 S 609 → SET 3 800 + SUB 3 608 + SUB 3 609
    m = re.match(r'(\d+)\s*=\s*(.+)$', text)
    if m:
        fid = int(m.group(1))
        rhs = m.group(2).strip()
        m_neg = re.match(r'-\s*(\d+)$', rhs)
        if m_neg:
            return [Op('SET', fid, Value('literal', -int(m_neg.group(1))))]
        parts_s = re.split(r'\s+S\s+', rhs)
        parts_a = re.split(r'\s+A\s+', rhs)
        if len(parts_s) > 1:
            ops = [Op('SET', fid, _classify_val(parts_s[0]))]
            for p in parts_s[1:]:
                ops.append(Op('SUB', fid, _classify_val(p)))
            return ops
        elif len(parts_a) > 1:
            ops = [Op('SET', fid, _classify_val(parts_a[0]))]
            for p in parts_a[1:]:
                ops.append(Op('ADD', fid, _classify_val(p)))
            return ops
        else:
            val = _classify_val(rhs)
            return [Op('SET', fid, val)]

    # Field ADD single: 801 A 200
    m = re.match(r'(\d+)\s*A\s+(.+)$', text)
    if m:
        fid = int(m.group(1))
        val = _classify_val(m.group(2).strip())
        return [Op('ADD', fid, val)]

    # Field SUB: 801 S 200
    m = re.match(r'(\d+)\s*S\s+(.+)$', text)
    if m:
        fid = int(m.group(1))
        val = _classify_val(m.group(2).strip())
        return [Op('SUB', fid, val)]

    return [Op('UNKNOWN', raw=text)]


def _update_field_analysis(block: Block):
    for op in block.actions:
        if op.op_type in ('SET', 'ADD', 'SUB', 'RESET'):
            if isinstance(op.field, int):
                block.fields_written.add(op.field)
            if isinstance(op.field, str) and op.field.startswith('K'):
                pass  # K-register ops don't read/write normal fields
            if op.value and op.value.kind == 'field' and op.value.field:
                block.fields_read.add(op.value.field)
            if op.value and op.value.kind == 'deref' and op.value.field:
                block.fields_read.add(op.value.field)
        if op.op_type in ('POINTER_INC', 'POINTER_DEC'):
            if isinstance(op.field, str) and op.field.startswith('K'):
                pass  # K-pointer operations
        if op.op_type == 'CAMPO70':
            block.fields_written.add(70)
        if op.op_type in ('PTR_OPEN', 'PTR_CLOSE'):
            if isinstance(op.field, int):
                block.fields_read.add(op.field)


# ─────── MAIN PARSER ───────

def _is_vxx(tok: str | None) -> bool:
    return bool(tok and (re.match(r'^V\d{2}$', tok) or tok in ('VF', 'VU')))

def _tokenize_and_group_parens(line: str) -> list:
    """Tokenize a single line and return a list of groups.
    Each group is either:
      - ('text', str) for non-paren text
      - ('paren', [tokens_inside], was_closed) for a parenthesized group
      - ('jump_paren', jump_token) for ( Vxx / ( VF / ( VU (no closing paren)
    """
    tokens = _tokenize_line(line)
    result = []
    pos = 0
    while pos < len(tokens):
        t = tokens[pos]
        if t == '(':
            # Check if it's a jump-paren: ( Vxx / ( VF / ( VU
            nt = tokens[pos + 1] if pos + 1 < len(tokens) else None
            if nt in ('VF', 'VU') or (nt and nt.startswith('V') and len(nt) == 3 and nt[1:].isdigit()):
                # ( Vxx without closing paren = jump
                result.append(('jump_paren', nt))
                pos += 2
                # Skip optional closing paren
                if pos < len(tokens) and tokens[pos] == ')':
                    pos += 1
                continue
            # Check for ( R NNN / ( P NNN (call in paren)
            if nt == 'R' and pos + 2 < len(tokens) and tokens[pos + 2].isdigit():
                result.append(('jump_paren', f"R {tokens[pos + 2]}"))
                pos += 3
                if pos < len(tokens) and tokens[pos] == ')':
                    pos += 1
                continue
            if nt == 'P' and pos + 2 < len(tokens) and tokens[pos + 2].isdigit():
                result.append(('jump_paren', f"P {tokens[pos + 2]}"))
                pos += 3
                if pos < len(tokens) and tokens[pos] == ')':
                    pos += 1
                continue
            # Regular paren group - find matching close
            depth = 1
            inner = []
            was_closed = False
            jump_inside = None
            pos += 1  # skip '('
            while pos < len(tokens) and depth > 0:
                if tokens[pos] == '(':
                    depth += 1
                    inner.append(tokens[pos])
                elif tokens[pos] == ')':
                    depth -= 1
                    if depth > 0:
                        inner.append(tokens[pos])
                elif depth == 1:
                    # At depth 1 (inside outer, after inner action): check for jump
                    # Handles: ((action) Vxx  (outer never closed)
                    nxt = tokens[pos + 1] if pos + 1 < len(tokens) else None
                    if _is_vxx(tokens[pos]) and (nxt is None or nxt in (')', '(')):
                        jump_inside = tokens[pos]
                        pos += 1
                        break
                    if tokens[pos] in ('R', 'P') and nxt and nxt.isdigit():
                        nxt2 = tokens[pos + 2] if pos + 2 < len(tokens) else None
                        if nxt2 is None or nxt2 in (')', '('):
                            jump_inside = f"{tokens[pos]} {nxt}"
                            pos += 2
                            break
                    inner.append(tokens[pos])
                else:
                    inner.append(tokens[pos])
                pos += 1
            if depth == 0:
                was_closed = True
            result.append(('paren', inner, was_closed, jump_inside))
        elif t == ')':
            # Stray closing paren - treat as text
            result.append(('text', ')'))
            pos += 1
        else:
            result.append(('text', t))
            pos += 1
    return result


def _parse_actions_from_inner(inner_tokens: list[str]) -> list[Op]:
    """Parse paren inner tokens into a list of Op actions.
    Handles both single-action (no inner parens) and multi-action (inner parens)."""
    # Check if inner contains `(` at depth 0 → multi-action
    has_sub_parens = any(t == '(' for t in inner_tokens)
    if has_sub_parens:
        groups = _split_inner_into_actions(inner_tokens)
        ops = []
        for g in groups:
            txt = ' '.join(t for t in g if t != ')' and t != '(')
            ops.extend(_parse_one_action_from_text(txt))
        return ops
    else:
        txt = ' '.join(t for t in inner_tokens if t != ')' and t != '(')
        return _parse_one_action_from_text(txt)


def _build_blocks_from_groups(groups: list, line_idx: int = 0) -> list[Block]:
    """Build Block(s) from a parsed line."""
    blocks: list[Block] = []
    i = 0
    n = len(groups)

    def _parse_actions_from_paren(idx):
        """Parse actions from a paren group at index idx, return (ops, jump_inside)."""
        _, inner, _, jump_inside = groups[idx]
        ops = _parse_actions_from_inner(inner)
        return ops, jump_inside

    def _try_jump_from_text(idx):
        """Check if group at idx is text representing a jump."""
        if idx < n and groups[idx][0] == 'text':
            return _extract_jump_from_text(groups[idx][1])
        return None

    while i < n:
        gtype, gval = groups[i][0], groups[i][1]

        if gtype == 'text':
            cond_parts = [gval]

            i += 1
            while i < n and groups[i][0] == 'text':
                cond_parts.append(groups[i][1])
                i += 1

            cond_text = ' '.join(cond_parts).strip()

            # Check for standalone R NNN or P NNN → call block
            call_match = re.match(r'^[RP]\s*\d+$', cond_text)
            if call_match:
                blocks.append(Block(jump=cond_text))
                continue

            # Check for standalone Vxx/VF/VU → label
            if _is_vxx(cond_text):
                blocks.append(Block(condition=cond_text))
                continue
            block = Block(condition=cond_text, fields_read=_find_fields(cond_text))

            if i < n and groups[i][0] == 'paren':
                ops, jump_inside = _parse_actions_from_paren(i)
                block.actions = ops
                if jump_inside:
                    block.jump = jump_inside
                i += 1
                _update_field_analysis(block)

                jt = _try_jump_from_text(i)
                if jt:
                    block.jump = jt
                    i += 1

                while i < n and groups[i][0] == 'paren':
                    ops2, jump_inside2 = _parse_actions_from_paren(i)
                    block.actions.extend(ops2)
                    if jump_inside2 and not block.jump:
                        block.jump = jump_inside2
                    i += 1
                    _update_field_analysis(block)

                    jt = _try_jump_from_text(i)
                    if jt:
                        block.jump = jt
                        i += 1

            elif i < n and groups[i][0] == 'jump_paren':
                block.jump = groups[i][1]
                i += 1

            if block.condition or block.actions or block.jump:
                blocks.append(block)

        elif gtype == 'paren':
            ops, jump_inside = _parse_actions_from_paren(i)
            block = Block()
            block.actions = ops
            if jump_inside:
                block.jump = jump_inside
            i += 1
            _update_field_analysis(block)

            jt = _try_jump_from_text(i)
            if jt:
                block.jump = jt
                i += 1

            while i < n and groups[i][0] == 'paren':
                ops2, jump_inside2 = _parse_actions_from_paren(i)
                block.actions.extend(ops2)
                if jump_inside2 and not block.jump:
                    block.jump = jump_inside2
                i += 1
                _update_field_analysis(block)

                jt = _try_jump_from_text(i)
                if jt:
                    block.jump = jt
                    i += 1

            blocks.append(block)

        elif gtype == 'jump_paren':
            blocks.append(Block(jump=groups[i][1]))
            i += 1

        else:
            i += 1

    return blocks


def _is_formula_call(tokens: list[str]) -> bool:
    """Check if tokens represent 'R NNN' or 'P NNN'."""
    return (len(tokens) == 2 and tokens[0] in ('R', 'P') and tokens[1].isdigit())


def _is_label(tokens: list[str], idx: int) -> bool:
    """Check if a single token is a label like V06."""
    if idx == 1 and tokens[0] and tokens[0].startswith('V') and len(tokens[0]) == 3 and tokens[0][1:].isdigit():
        return True
    return False


def _extract_jump_from_text(text: str) -> str | None:
    text = text.strip()
    m = re.match(r'^(V\d{2}|VF|VU)$', text)
    if m:
        return m.group(1)
    m = re.match(r'^(R|P)\s*(\d+)$', text)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return None


def _split_inner_into_actions(inner_tokens: list[str]) -> list[list[str]]:
    """Split inner tokens into separate action groups at top-level paren boundaries.
    E.g. ['(', '58', '=', '"MATT"', ')', '(', '111', '=', "'06'", ')']
    → [['58', '=', '"MATT"'], ['111', '=', "'06'"]]
    """
    groups = []
    i = 0
    while i < len(inner_tokens):
        if inner_tokens[i] == '(':
            depth = 1
            j = i + 1
            while j < len(inner_tokens) and depth > 0:
                if inner_tokens[j] == '(':
                    depth += 1
                elif inner_tokens[j] == ')':
                    depth -= 1
                if depth > 0:
                    j += 1
            # Extract the content between the outer parens
            group_content = inner_tokens[i + 1:j]
            # Filter out parens within the group that are at the outer level
            # (for deeply nested cases, the recursion handles it)
            if group_content:
                groups.append(group_content)
            i = j + 1  # skip past ')'
        elif inner_tokens[i] in ('!', '[') or (inner_tokens[i].isdigit() and i + 1 < len(inner_tokens)):
            # Unparenthesized action (unlikely but handle)
            groups.append(inner_tokens[i:])
            break
        else:
            i += 1
    return groups


def parse_formula(code: str, formula_id: int = 0) -> ParsedFormula:
    parsed = ParsedFormula(id=formula_id, code=code)

    code_norm = code.replace('\r\n', '\n')
    lines = code_norm.split('\n')

    for line_idx, line in enumerate(lines):
        raw_line = line
        # Remove inline comments
        qpos = line.find('?')
        if qpos >= 0:
            line = line[:qpos]
        line = line.strip()
        if not line:
            continue

        groups = _tokenize_and_group_parens(line)
        line_blocks = _build_blocks_from_groups(groups, line_idx)

        # Post-process: split blocks that have both cond+actions but should be separate
        # e.g., "200 U Z O 58 U 'RIPO' ( VF" — cond_text= "200 U Z O 58 U 'RIPO'"
        # The 'O' splits into two conditions
        # For now, handle 'R NNN' continuation lines
        for blk in line_blocks:
            # Merge repeated actions (already done by _build_blocks_from_groups)
            parsed.blocks.append(blk)

    # Post-process: collect calls and summary fields
    for block in parsed.blocks:
        if block.jump and block.jump.startswith('R '):
            parsed.calls_r.append(int(block.jump[2:]))
        if block.jump and block.jump.startswith('P '):
            parsed.calls_p.append(int(block.jump[2:]))
        parsed.fields_read |= block.fields_read
        parsed.fields_written |= block.fields_written

    return parsed


# ═══════════════════════════════════════════════
# Block Emitter — converte list[Block] → compact WinSarp
# ═══════════════════════════════════════════════

def _emit_val(val: Value | None) -> str:
    """Convert a Value to compact WinSarp string."""
    if val is None:
        return ''
    if val.kind == 'literal':
        v = val.value
        if v is None:
            return ''
        if isinstance(v, str):
            return f"'{v}'"
        return str(v)
    if val.kind == 'field':
        return str(val.field) if val.field is not None else ''
    if val.kind == 'deref':
        return f"{{ {val.field} }}"
    if val.kind == 'indefinito':
        return str(val.value) if val.value else 'I'
    if val.kind == 'kreg':
        return str(val.value) if val.value else ''
    return ''


def _emit_op(op: Op) -> str:
    """Convert an Op back to compact WinSarp action syntax."""
    if op.raw:
        return op.raw
    if op.op_type == 'SET':
        return f"{op.field} = {_emit_val(op.value)}"
    if op.op_type == 'ADD':
        return f"{op.field} A {_emit_val(op.value)}"
    if op.op_type == 'SUB':
        return f"{op.field} S {_emit_val(op.value)}"
    if op.op_type == 'RESET':
        return f"!{op.field}"
    if op.op_type in ('POINTER_INC', 'POINTER_DEC'):
        opchar = '+' if op.op_type == 'POINTER_INC' else '-'
        itype = op.value.value if op.value and op.value.value else 'I'
        return f"{op.field} {opchar} {itype}"
    if op.op_type == 'CAMPO70':
        code = op.value.value if op.value and op.value.value else ''
        return f"70='{code}'"
    if op.op_type == 'PTR_OPEN':
        return f"[{op.field}"
    if op.op_type == 'PTR_CLOSE':
        return f"]{op.field}"
    if op.op_type == 'UNKNOWN':
        return op.raw or str(op.field or '')
    return str(op.field) if op.field else ''


def _emit_actions(ops: list[Op]) -> list[str]:
    """Convert a list of Op to compact action strings, handling compound operators."""
    if not ops:
        return []
    # Compound SET+SUB: 3 = 800 S 608 S 609
    if (ops[0].op_type == 'SET' and len(ops) > 1
            and all(o.op_type == 'SUB' for o in ops[1:])
            and all(o.field == ops[0].field for o in ops)
            and isinstance(ops[0].field, int)):
        rest = ' S '.join(_emit_val(o.value) for o in ops[1:])
        return [f"{ops[0].field} = {_emit_val(ops[0].value)} S {rest}"]
    # Compound SET+ADD: 800 = 3 A 4 A 5
    if (ops[0].op_type == 'SET' and len(ops) > 1
            and all(o.op_type == 'ADD' for o in ops[1:])
            and all(o.field == ops[0].field for o in ops)
            and isinstance(ops[0].field, int)):
        rest = ' A '.join(_emit_val(o.value) for o in ops[1:])
        return [f"{ops[0].field} = {_emit_val(ops[0].value)} A {rest}"]
    # Compound 2-op SUB (legacy): 887 = '40.00' S 772
    if (len(ops) == 2 and ops[0].op_type == 'SUB' and ops[1].op_type == 'SUB'
            and ops[0].field == ops[1].field and isinstance(ops[0].field, int)):
        return [f"{ops[0].field} = {_emit_val(ops[0].value)} S {_emit_val(ops[1].value)}"]
    # Compound 2-op ADD (legacy): 800 = 3 A 4
    if (len(ops) == 2 and ops[0].op_type == 'ADD' and ops[1].op_type == 'ADD'
            and ops[0].field == ops[1].field and isinstance(ops[0].field, int)):
        return [f"{ops[0].field} = {_emit_val(ops[0].value)} A {_emit_val(ops[1].value)}"]
    # K-reg with multiple A/S
    if (isinstance(ops[0].field, str) and ops[0].field.startswith('K')):
        same_type = all(o.op_type == ops[0].op_type for o in ops)
        same_field = all(o.field == ops[0].field for o in ops)
        if same_type and same_field:
            sep = ' A ' if ops[0].op_type == 'ADD' else ' S '
            vals = sep.join(_emit_val(o.value) for o in ops)
            return [f"{ops[0].field} {ops[0].op_type[0]} {vals}"]  # A or S
    # RESET group: !112!142
    if all(o.op_type == 'RESET' for o in ops):
        fields = ''.join(f"!{o.field}" for o in ops)
        return [fields]
    # Default: each op individually
    return [_emit_op(op) for op in ops]


def emit_block(block: Block) -> str | None:
    """Emit a single Block as compact WinSarp line. Returns None for empty."""
    cond = block.condition.strip() if block.condition else ''
    has_actions = bool(block.actions)
    jump = block.jump.strip() if block.jump else ''

    if not cond and not has_actions and jump and re.match(r'^[RP]\s+\d+$', jump):
        return jump

    if cond and _is_vxx(cond) and not has_actions and not jump:
        return cond

    action_texts = _emit_actions(block.actions) if has_actions else []

    if cond and not action_texts and jump:
        return f"{cond} ( {jump}"

    if cond and action_texts:
        parts = [f"{cond} (("]
        parts.append(f" {action_texts[0]} )")
        for at in action_texts[1:]:
            parts.append(f"({at} )")
        if jump:
            parts.append(f" {jump}")
        return ''.join(parts)

    if action_texts and not cond:
        parts = [f"( {at} )" for at in action_texts]
        if jump:
            parts.append(f" {jump}")
        return ''.join(parts)

    return cond if cond else None


def emit_formula(blocks: list[Block]) -> str:
    """Convert list[Block] → compact WinSarp formula text."""
    lines = [emit_block(b) for b in blocks]
    return '\n'.join(line for line in lines if line)


def summarize(parsed: ParsedFormula, max_blocks: int = 30) -> dict:
    return {
        'id': parsed.id,
        'n_blocks': len(parsed.blocks),
        'fields_read': sorted(parsed.fields_read),
        'fields_written': sorted(parsed.fields_written),
        'calls_r': sorted(parsed.calls_r),
        'calls_p': sorted(parsed.calls_p),
        'n_chars': len(parsed.code),
        'blocks': [
            {
                'cond': (b.condition[:50] + '...') if len(b.condition) > 50 else b.condition if b.condition else None,
                'n_actions': len(b.actions),
                'action_types': [a.op_type for a in b.actions[:6]],
                'jump': b.jump,
                'R': sorted(b.fields_read),
                'W': sorted(b.fields_written),
            }
            for b in parsed.blocks[:max_blocks]
        ]
    }
