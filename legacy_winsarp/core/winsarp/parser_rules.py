"""
Libreria centralizzata delle regole di parsing per WinSarp.
Ogni espressione regolare utilizzata per identificare componenti di una formula
deve essere definita qui per garantire coerenza in tutto il sistema.
"""
import re

# ---- Chiamate Formula (R/P) ----
# Supporta spazi opzionali (es. R130, R 130)
CALL_R = re.compile(r'(?<![A-Za-z])R\s*(\d{2,5})(?![A-Za-z0-9])')
CALL_P = re.compile(r'(?<![A-Za-z])P\s*(\d{2,5})(?![A-Za-z0-9])')

# ---- Campi e Riferimenti ----
RESET_FIELDS = re.compile(r'!(\d{1,4})')
FIELD_REFS = re.compile(r'(?<!\w)(\d{1,4})(?!\w)')
BRACED_FIELD = re.compile(r'\{\s*(\d{1,4})\s*\}')
BRACKET_FIELD = re.compile(r'[\[\]](\d{1,4})')
K_FIELD = re.compile(r'K(\d{1,4})\s*[AS]')

# ---- Struttura Formula ----
FIELD_SET = re.compile(r'\(\s*!?(\d{1,4})\s*=')
COND_FIELD = re.compile(r'(?<!\w)(\d{1,4})\s*(?:U|UZ|>|<|=|#|>=|<=)')
RETURN_CODES = re.compile(r'\b(V11|V04|V05|V06|V07|V10|VF|VU|V02)\b')
OPERATORS = re.compile(r'(UZ|U|Z|O|E)(?=[;(:])')

# ---- Pattern composti ----
KEY_SUM = re.compile(r'K(\d{1,4})S(\d{1,4})')
FIELD_CMP = re.compile(
    r'\((\d{1,4})\s*(=|#|>|<|>=|<=|U|Z|>U|<U|UZ)\s*(?:\d{1,4}|"[^"]*"|\'[^\']*\'|[A-Z]+)\)'
)
VXX_REF = re.compile(r'\bV(\d{2})\b')
