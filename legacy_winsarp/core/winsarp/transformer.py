import re

from lark import Transformer


class WinSarpTransformer(Transformer):
    def __init__(self):
        super().__init__()
        self.v_counter = 2

    def start(self, items):
        out = "\n".join(str(i) for i in items)
        lines = out.split("\n")
        while lines and lines[-1].strip() == "VF":
            lines.pop()
        out = "\n".join(lines)
        out = re.sub(r'\)\s*\n\s*(V\w+)\s*', r') \1', out)
        out = re.sub(r'\)\s*\n\s*\(', r')(', out)
        out = re.sub(r'\(\s*(\(\s*[^()]+\s*\))\s*\)', r'\1', out)
        out = re.sub(
            r'(?<!\()\(!(\d+)\)(?:\(!(\d+)\))+',
            lambda m: '(!' + '!'.join(re.findall(r'\(!(\d+)\)', m.group(0))) + ')',
            out
        )
        out = re.sub(r'^\s*COMMENT\s+', '? ', out, flags=re.MULTILINE)
        out = "\n".join(line.rstrip() for line in out.split("\n"))
        return out.strip()

    def block(self, items):
        return items

    def set_stmt(self, items):
        field, expr = items
        return f"( {field} = {expr} )"

    def reset_stmt(self, items):
        return f"(!{items[0]})"

    def if_stmt(self, items):
        cond = items[0]
        then_raw = items[1]

        then_actions = []
        for a in then_raw:
            s = str(a)
            if s.startswith("(") or self._is_simple_jump(s):
                then_actions.append(s)
            else:
                then_actions.append(f"({s})")

        if len(items) == 2:
            return self._format_then(cond, then_actions)
        else:
            else_raw = items[2]
            else_actions = []
            for a in else_raw:
                s = str(a)
                if s.startswith("(") or self._is_simple_jump(s):
                    else_actions.append(s)
                else:
                    else_actions.append(f"({s})")

            then_terminal = then_actions and self._is_simple_jump(then_actions[-1])
            if then_terminal:
                return cond + " ( " + str(then_actions[0]) + "\n" + "\n".join(str(a) for a in else_actions)

            label = f"V{self.v_counter:02d}"
            self.v_counter += 1
            lines = [f"{cond} ( {label}"]
            lines.extend(str(a) for a in else_actions)
            lines.append(label)
            lines.extend(str(a) for a in then_actions)
            return "\n".join(lines)

    def r_stmt(self, items):
        return f"R{items[0]}"

    def p_stmt(self, items):
        return f"P{items[0]}"

    def vf_stmt(self, items):
        return "VF"

    def vu_stmt(self, items):
        return "VU"

    def k_stmt(self, items):
        field = items[0]
        parts = []
        for op_tree in items[1:]:
            op, val = op_tree
            parts.append(f"{op} {val}")
        return f"( K{field} {' '.join(parts)} )"

    def k_op(self, items):
        return [str(items[0]), str(items[1])]

    def expression(self, items):
        result = []
        for item in items:
            s = str(item)
            if s in ("A", "S", "+", "-", "*", "/"):
                op_map = {"A": "A", "S": "S", "+": "A", "-": "S", "*": "*", "/": "S"}
                result.append(op_map[s])
            else:
                result.append(s)
        return " ".join(result)

    def value(self, items):
        return self._compact_val(str(items[0]))

    def condition(self, items):
        result = []
        for item in items:
            s = str(item)
            if s in ("AND", "E"):
                result.append("E")
            elif s in ("OR", "O"):
                result.append("O")
            else:
                result.append(s)
        return " ".join(result)

    def comparison(self, items):
        left, op, right = [str(t) for t in items]
        op_map = {"=": "U", ">=": ">U", "<=": "<U", ">": ">", "<": "<", "#": "#", "!": "!"}
        op_w = op_map.get(op, op)
        right_w = self._compact_val(right)
        if right_w in ("0", "'0'", "Z"):
            right_w = "Z"
        return f"{left} {op_w} {right_w}"

    def ptr_start_stmt(self, items):
        return f"[{items[-1]}"

    def ptr_end_stmt(self, items):
        return f"]{items[-1]}"

    def goto_stmt(self, items):
        v = str(items[0])
        return f"V{v}" if v.isdigit() else v

    def mark_stmt(self, items):
        v = str(items[0])
        return f"V{v}" if v.isdigit() else v

    def comment_stmt(self, items):
        return f"? {items[0]}"

    def campo70_stmt(self, items):
        return f"( 70 = '{items[0]}' )"

    def field_stmt(self, items):
        return f"( {items[0]} )"

    # ---- helpers ----

    @staticmethod
    def _is_simple_jump(s: str) -> bool:
        s = s.strip().strip("()")
        if s in ("VF", "VU"):
            return True
        if s.startswith("R") or s.startswith("P"):
            return True
        if re.match(r'^V?\d{2}$', s):
            return True
        return bool(s.startswith("GOTO") or s.startswith("? "))

    @staticmethod
    def _compact_val(val: str) -> str:
        val = val.strip()
        if (val.startswith("'") and val.endswith("'")) or \
           (val.startswith('"') and val.endswith('"')):
            return val
        if val.upper() in ("I", "Z"):
            return val
        if val.startswith("{") or val.startswith("["):
            return val
        if re.fullmatch(r'V\d{2}', val):
            return val
        m = re.fullmatch(r'F\s*\(\s*(\d+)\s*\)', val, re.IGNORECASE)
        if m:
            return m.group(1)
        if not val.replace(".", "").replace("-", "").replace(",", "").isdigit():
            return f'"{val}"'
        return val

    def _format_then(self, cond, actions):
        if not actions:
            return cond + " ( )"
        if len(actions) == 1:
            a = str(actions[0])
            if self._is_simple_jump(a):
                return f"{cond} ( {a}"
            if a.startswith("("):
                inner = a[1:].lstrip()
                return f"{cond} (( {inner}"
            return f"{cond} (( {a}"
        else:
            last = str(actions[-1])
            rest = actions[:-1]
            if self._is_simple_jump(last):
                non_jump = "".join(
                    f"({a})" if not str(a).startswith("(") and not self._is_simple_jump(str(a)) else str(a)
                    for a in rest
                )
                return f"{cond} ({non_jump} {last}"
            else:
                joined = "".join(
                    f"({a})" if not str(a).startswith("(") else str(a)
                    for a in actions
                )
                return f"{cond} ({joined})"

    # Leaf nodes
    def FIELD(self, token): return str(token)
    def NUMBER(self, token): return str(token)
    def STRING(self, token): return str(token)
    def FIELD_REF(self, token): return str(token)
    def FLAG(self, token): return str(token)
    def EXPRESSION_REF(self, token): return str(token)
    def KOP(self, token): return str(token)
