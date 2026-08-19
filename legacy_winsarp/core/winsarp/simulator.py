"""
formula_simulator.py
Simulatore leggero di logica WinSarp per testare formule generate prima della certificazione.
Esegue step IR (Intermediate Representation) e verifica i risultati.
Supporta: SET, RESET, IF/ELSE/ENDIF, K-accumulo, CAMPO70, ADD/SUB (A/S), VF/Vxx/R.
"""
import re
import logging

_logger = logging.getLogger(__name__)


class FormulaSimulator:
    def __init__(self):
        self.fields = {}       # field_number → str_value
        self.kregs = {}        # Kregister → float_value
        self.labels = {}       # label_name → line_index
        self.calls = []        # trace of R/P calls
        self._precompute_labels = True

    def simulate(self, steps: list[str], input_fields: dict[str, str] | None = None) -> dict:
        """Esegue gli step IR con un contesto di input e ritorna i campi finali.

        Supporta:
        - SET field = value / SET field = expr (A/S compound)
        - RESET field
        - IF cond THEN ... ELSE ... ENDIF
        - CAMPO70 code
        - K reg A/S value (K-register add/sub)
        - field A value / field S value
        - VF / Vxx (goto label)
        - R NNN / P NNN (call tracking)
        """
        self.fields = dict(input_fields) if input_fields else {}
        self.kregs = {}
        self.calls = []

        if self._precompute_labels:
            self.labels = {}
            for idx, s in enumerate(steps):
                s = s.strip().upper()
                if s.startswith(("#", "//", "?")):
                    continue
                # Label: standalone Vxx
                if re.match(r'^V\d{2}$', s) or s in ('VF', 'VU'):
                    self.labels[s] = idx

        i = 0
        while i < len(steps):
            step = steps[i].strip()
            step_upper = step.upper()
            if not step or step.startswith(("#", "//", "?")):
                i += 1
                continue

            # IF cond THEN
            if step_upper.startswith("IF ") and step_upper.rstrip().endswith(" THEN"):
                cond = step[3:-5].strip()
                if self._eval_cond(cond):
                    i += 1
                    continue
                depth = 1
                while i < len(steps) and depth > 0:
                    i += 1
                    if i >= len(steps):
                        break
                    s = steps[i].strip().upper()
                    if s.startswith("IF "):
                        depth += 1
                    elif s == "ELSE" and depth == 1:
                        break
                    elif s == "ENDIF":
                        depth -= 1
                i += 1
                continue

            elif step_upper == "ELSE":
                depth = 1
                while i < len(steps) and depth > 0:
                    i += 1
                    if i >= len(steps):
                        break
                    s = steps[i].strip().upper()
                    if s.startswith("IF "):
                        depth += 1
                    elif s == "ENDIF":
                        depth -= 1
                i += 1
                continue

            elif step_upper == "ENDIF":
                i += 1
                continue

            # VF / VU / Vxx → goto
            if re.match(r'^V\d{2}$', step_upper) or step_upper in ('VF', 'VU'):
                target = self.labels.get(step_upper)
                if target is not None and target > i:
                    i = target
                    continue
                i += 1
                continue

            # R NNN → call
            m = re.match(r'^[Rr]\s+(\d+)$', step)
            if m:
                self.calls.append(f"R {m.group(1)}")
                i += 1
                continue

            # P NNN → pointer call
            m = re.match(r'^[Pp]\s+(\d+)$', step)
            if m:
                self.calls.append(f"P {m.group(1)}")
                i += 1
                continue

            # CAMPO70 code
            m = re.match(r'CAMPO70\s+(\S+)', step, re.IGNORECASE)
            if m:
                self.fields['70'] = m.group(1).strip("'\" ")
                i += 1
                continue

            # K reg A/S value  → K-register operation (supporta 'K800 A 15' e 'K 800 A 15')
            m = re.match(r'K\s*(\d{1,4})\s+(A|S)\s+(.+)', step, re.IGNORECASE)
            if m:
                kreg = 'K' + m.group(1)
                op = m.group(2).upper()
                val = self._resolve_numeric(m.group(3).strip())
                current = self.kregs.get(kreg, 0.0)
                if op == 'A':
                    self.kregs[kreg] = current + val
                else:
                    self.kregs[kreg] = current - val
                i += 1
                continue

            # field A/S value  → field add/sub
            m = re.match(r'(\d+)\s+(A|S)\s+(.+)', step, re.IGNORECASE)
            if m:
                field = m.group(1)
                op = m.group(2).upper()
                val = self._resolve_numeric(m.group(3).strip())
                current = self._get_field_numeric(field)
                result = current + val if op == 'A' else current - val
                self.fields[field] = self._fmt_val(result)
                i += 1
                continue

            # SET field = expression  (compound A/S or simple)
            m = re.match(r'SET\s+(\d+)\s*=\s*(.+)', step, re.IGNORECASE)
            if m:
                field = m.group(1)
                rhs = m.group(2).strip()
                # Compound: field = base A val1 S val2 ...
                parts_a = re.split(r'\s+A\s+', rhs, maxsplit=1)
                if len(parts_a) > 1:
                    base = self._resolve_numeric(parts_a[0])
                    total = base
                    for p in re.split(r'\s+[AS]\s+', parts_a[1]):
                        op_idx = 0
                        for ch in parts_a[1]:
                            if ch in 'AS':
                                break
                            op_idx += 1
                        # Find the op before this value
                    # Simpler: handle sequentially
                    total = base
                    buf = parts_a[1]
                    cur_op = 'A'
                    while buf:
                        m_op = re.match(r'\s*([AS])\s*', buf)
                        if m_op:
                            cur_op = m_op.group(1)
                            buf = buf[m_op.end():]
                        m_val = re.match(r'(.+?)(?:\s+[AS]\s+|$)', buf)
                        if m_val:
                            v = self._resolve_numeric(m_val.group(1).strip())
                            if cur_op == 'A':
                                total += v
                            else:
                                total -= v
                            buf = buf[m_val.end():]
                        else:
                            break
                    self.fields[field] = self._fmt_val(total)
                elif re.search(r'\s+S\s+', rhs):
                    parts = re.split(r'\s+S\s+', rhs)
                    base = self._resolve_numeric(parts[0])
                    for p in parts[1:]:
                        base -= self._resolve_numeric(p)
                    self.fields[field] = self._fmt_val(base)
                else:
                    self.fields[field] = self._resolve_val_flat(rhs)
                i += 1
                continue

            # RESET field
            m = re.match(r'RESET\s+(\d+)', step, re.IGNORECASE)
            if m:
                self.fields[m.group(1)] = '0'
                i += 1
                continue

            # Unknown step → skip
            i += 1

        return self.fields

    def _eval_cond(self, cond: str) -> bool:
        try:
            parts = re.split(r'([<>=#]+)', cond)
            if len(parts) != 3:
                return False
            left, op, right = [p.strip() for p in parts]
            # Per I/Z la comparazione e' speciale: Z = zero, I = true (non-zero)
            l_is_z = self._is_zero_val(left)
            r_is_z = self._is_zero_val(right)
            if op in ('=', 'U'):
                return l_is_z == r_is_z
            if op == '#':
                return l_is_z != r_is_z
            # Numeric comparisons
            l_val = self._resolve_numeric(left)
            r_val = self._resolve_numeric(right)
            if op == '<=':
                return l_val <= r_val
            if op == '<':
                return l_val < r_val
            if op == '>=':
                return l_val >= r_val
            if op == '>':
                return l_val > r_val
        except Exception:
            return False
        return False

    def _is_zero_val(self, val: str) -> bool:
        """Determina se un valore e' zero, sia come flag Z che come numero 0."""
        val = val.strip().strip("'\"")
        if val in self.fields:
            fv = self.fields[val].strip().strip("'\"")
            return self._is_zero_val_inner(fv)
        return self._is_zero_val_inner(val)

    @staticmethod
    def _is_zero_val_inner(val: str) -> bool:
        """Check if a resolved value represents zero."""
        if val.upper() in ('Z', 'N', ''):
            return True
        try:
            return abs(float(val.replace(',', '.'))) < 0.0001
        except (ValueError, TypeError):
            return False

    def _resolve_val_flat(self, val: str) -> str:
        """Risolve un valore: stringa quotata, deref field, o numero."""
        val = val.strip()
        if val.startswith("'") and val.endswith("'"):
            return val[1:-1]
        if val.startswith('"') and val.endswith('"'):
            return val[1:-1]
        if val in self.fields:
            return self.fields[val]
        if val.isdigit():
            return val
        return val

    def _resolve_numeric(self, val: str) -> float:
        """Risolve un valore numerico da espressione, deref, o field."""
        val = val.strip().strip("'\"")
        if val in self.fields:
            fv = self.fields[val]
            try:
                return float(fv)
            except (ValueError, TypeError):
                # Field value is non-numeric (e.g. 'I', 'Z', string)
                if fv.strip().upper() in ('I', 'Z', 'N'):
                    return 0.0
                return 0.0
        if val in ('I', 'Z'):
            return 0.0
        if val == 'N':
            return 0.0
        # Check deref {N}
        m = re.match(r'\{(\d+)\}', val)
        if m:
            f = m.group(1)
            try:
                return float(self.fields.get(f, '0'))
            except (ValueError, TypeError):
                return 0.0
        try:
            return float(val.replace(',', '.'))
        except (ValueError, TypeError):
            return 0.0

    def _get_field_numeric(self, field: str) -> float:
        try:
            return float(self.fields.get(field, '0'))
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _fmt_val(val: float) -> str:
        if val == int(val):
            return str(int(val))
        return f"{val:.2f}"

    def get_kreg(self, name: str) -> float:
        return self.kregs.get(name.upper(), 0.0)

    def get_field(self, name: str) -> str:
        return self.fields.get(name, '0')

    def get_calls(self) -> list[str]:
        return list(self.calls)
