"""
intent_extractor.py
LLM-based Intent Extraction Layer for WinSarp formulas.

The LLM's ONLY job is to produce a structured JSON describing the business logic.
A deterministic translator (intent_translator.py) converts the JSON to actual WinSarp code.
This separation eliminates ALL syntax errors from the LLM path.
"""
import json
import logging
import re
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)


@dataclass
class IntentFieldOp:
    """A single field operation."""
    type: str  # "set", "reset", "add", "sub"
    field: int | str
    value: str | None = None
    source_field: int | None = None  # for "set field = other_field"


@dataclass
class IntentCondition:
    """A condition for IF blocks."""
    left_field: int | str
    operator: str  # "=", "#", ">", "<", ">=", "<="
    right_value: str  # "I", "Z", "'val'", or field number
    right_is_field: bool = False


@dataclass
class IntentKAccum:
    """K-register accumulation."""
    kreg: str  # "K615", "K616", etc.
    source_field: int | str  # field number to accumulate FROM
    operation: str = "A"  # "A" or "S"


@dataclass
class IntentBlock:
    """A block of operations (IF/THEN/ELSE or unconditional)."""
    conditions: list[IntentCondition] | None = None
    conditions_join: str = "E"  # "E" for AND, "O" for OR
    operations: list[IntentFieldOp] = field(default_factory=list)
    k_accumulations: list[IntentKAccum] = field(default_factory=list)
    sub_blocks: list["IntentBlock"] = field(default_factory=list)
    is_else: bool = False


@dataclass
class FormulaIntent:
    """Complete structured intent for a WinSarp formula."""
    intent: str  # short name: "straordinario_festivo", etc.
    phase: str  # "IG", "FG", "DG", "SUB"
    description: str  # human-readable summary
    input_fields: list[int] = field(default_factory=list)
    output_fields: list[int] = field(default_factory=list)
    causali: dict[str, str] = field(default_factory=dict)  # slot → value: {"503": "SFN"}
    blocks: list[IntentBlock] = field(default_factory=list)
    attachment: dict | None = None  # {"type": "after_r", "value": 130}
    k_registers: list[IntentKAccum] = field(default_factory=list)


# ── Constants for the LLM prompt ──────────────────────────────

INTENT_SCHEMA_DOC = """
# WinSarp Formula Intent Schema

You are a WinSarp business analyst. Your ONLY job is to understand the user's request
and produce a structured JSON describing the business logic. You NEVER write WinSarp code.

Output this JSON schema:
{
  "intent": "short_name_of_intent",
  "phase": "IG|FG|DG|SUB",
  "description": "one-line summary of what the formula does",
  "input_fields": [list of field numbers that are READ],
  "output_fields": [list of field numbers that are WRITTEN],
  "causali": {"field_number": "CAUSALE_CODE"},
  "blocks": [
    {
      "conditions": [{"left_field": 21, "operator": ">", "right_value": "Z"}],
      "conditions_join": "E",
      "operations": [
        {"type": "set", "field": 505, "value": "N"},
        {"type": "set", "field": 565, "source_field": 21}
      ],
      "sub_blocks": [],
      "is_else": false
    },
    {
      "conditions": [{"left_field": 890, "operator": ">", "right_value": "Z"}],
      "conditions_join": "E",
      "operations": [
        {"type": "set", "field": 506, "value": "T"},
        {"type": "set", "field": 566, "source_field": 890}
      ],
      "sub_blocks": [],
      "is_else": false
    }
  ],
  "k_registers": [
    {"kreg": "K626", "source_field": 565, "operation": "A"},
    {"kreg": "K625", "source_field": 566, "operation": "A"}
  ],
      "k_accumulations": [
        {"kreg": "K615", "source_field": 563, "operation": "A"}
      ],
      "sub_blocks": [],
      "is_else": false
    }
  ],
  "k_registers": [
    {"kreg": "K615", "source_field": 563, "operation": "A"},
    {"kreg": "K616", "source_field": 564, "operation": "A"}
  ],
  "attachment": {"type": "after_r", "value": 130}
}

================================================================================
# REAL FORMULA EXAMPLES (how actual WinSarp code maps to JSON)
================================================================================

--- EXAMPLE 1: Simple FG (Formula 210 — Maggiorazioni per Turnisti) ---
WinSarp code:
  21>Z((505="N")(565=21);
  (890=3S21);
  890>Z((506="T")(566=890);
  (K626A565)(K625A566);

JSON intent:
{
  "intent": "maggiorazioni_turnisti",
  "phase": "FG",
  "description": "Calcola maggiorazioni notturne (N) e diurne (T) per turnisti",
  "input_fields": [3, 21],
  "output_fields": [505, 506, 565, 566, 890],
  "causali": {"505": "N", "506": "T"},
  "blocks": [
    {
      "conditions": [{"left_field": 21, "operator": ">", "right_value": "Z"}],
      "operations": [
        {"type": "set", "field": 505, "value": "N"},
        {"type": "set", "field": 565, "source_field": 21}
      ]
    },
    {
      "conditions": [],
      "operations": [
        {"type": "set", "field": 890, "value": null, "source_field": 3, "subtract_field": 21}
      ]
    },
    {
      "conditions": [{"left_field": 890, "operator": ">", "right_value": "Z"}],
      "operations": [
        {"type": "set", "field": 506, "value": "T"},
        {"type": "set", "field": 566, "source_field": 890}
      ]
    }
  ],
  "k_registers": [
    {"kreg": "K626", "source_field": 565, "operation": "A"},
    {"kreg": "K625", "source_field": 566, "operation": "A"}
  ],
  "attachment": {"type": "subroutine", "value": "FG", "slot": "P210"}
}

--- EXAMPLE 2: Compound conditions with AND/OR (Formula 120 — Principale) ---
WinSarp code:
  4UZ(VU;1121U"N"((!4)VU;55UIO50UI(R130;R140;R200;

JSON:
{
  "intent": "smistatore_centrale",
  "phase": "FG",
  "description": "Instrada verso straordinario festivo (R130) o diurno (R140) o finale (R200)",
  "blocks": [
    {
      "conditions": [{"left_field": 4, "operator": "=", "right_value": "Z"}],
      "operations": [{"type": "comment", "value": "No straordinario, esci"}]
    },
    {
      "conditions": [{"left_field": 1121, "operator": "=", "right_value": "N"}],
      "operations": [{"type": "reset", "field": 4}, {"type": "comment", "value": "Flag N=nessuno straord"}]
    },
    {
      "conditions_join": "O",
      "conditions": [
        {"left_field": 55, "operator": "=", "right_value": "I"},
        {"left_field": 50, "operator": "=", "right_value": "I"}
      ],
      "operations": [{"type": "r_call", "value": "130"}],
      "sub_blocks": [
        {"operations": [{"type": "r_call", "value": "140"}]},
        {"operations": [{"type": "r_call", "value": "200"}]}
      ]
    }
  ]
}

--- EXAMPLE 3: Nested IF/THEN/ELSE (Formula 110 — Riproporziono) ---
WinSarp code:
  (800=3A4);1UZ((!3!5)(4=800)VU;
  (K800A608A609);
  800>1((4=800S1)(3=1S608S609)(!5)VU;
  (3=800S608S609)(!4)(5=1S800);R120;

JSON:
{
  "intent": "riproporziono_assenze",
  "phase": "FG",
  "description": "Riproporziona 3,4,5 in base alle assenze",
  "blocks": [
    {
      "operations": [
        {"type": "set", "field": 800, "value": null, "source_field": 3, "add_field": 4}
      ]
    },
    {
      "conditions": [{"left_field": 1, "operator": "=", "right_value": "Z"}],
      "operations": [
        {"type": "reset", "field": 3},
        {"type": "reset", "field": 5},
        {"type": "set", "field": 4, "source_field": 800}
      ],
      "k_accumulations": [{"kreg": "K800", "source_field": 608, "operation": "A"}, {"kreg": "K800", "source_field": 609, "operation": "A"}]
    },
    {
      "conditions": [{"left_field": 800, "operator": ">", "right_value": 1}],
      "operations": [
        {"type": "set", "field": 4, "value": null, "source_field": 800, "subtract_field": 1},
        {"type": "set", "field": 3, "value": null, "source_field": 1, "subtract_field": 608, "subtract_field_2": 609},
        {"type": "reset", "field": 5}
      ]
    },
    {
      "operations": [
        {"type": "set", "field": 3, "value": null, "source_field": 800, "subtract_field": 608, "subtract_field_2": 609},
        {"type": "reset", "field": 4},
        {"type": "set", "field": 5, "value": null, "source_field": 1, "subtract_field": 800},
        {"type": "r_call", "value": "120"}
      ]
    }
  ]
}

--- EXAMPLE 4: Compound AND with field range (Formula 2101 — 2° giro GUGEST) ---
WinSarp: 251>ZE271>Z((811=251)(812=271)P2122

JSON:
{
  "operations": [
    {
      "conditions_join": "E",
      "conditions": [
        {"left_field": 251, "operator": ">", "right_value": "Z"},
        {"left_field": 271, "operator": ">", "right_value": "Z"}
      ],
      "operations": [
        {"type": "set", "field": 811, "source_field": 251},
        {"type": "set", "field": 812, "source_field": 271},
        {"type": "p_call", "value": "2122"}
      ]
    }
  ]
}

--- EXAMPLE 5: OR conditions (Formula 3001 — FG NEW) ---
WinSarp: 50 U I O 300 U 302 O 300 U 311 (( K900 - I )

JSON:
{
  "conditions_join": "O",
  "conditions": [
    {"left_field": 50, "operator": "=", "right_value": "I"},
    {"left_field": 300, "operator": "=", "right_value": "302"},
    {"left_field": 300, "operator": "=", "right_value": "311"}
  ],
  "operations": [
    {"type": "set", "field": "K900", "value": null, "source_field": "K900", "subtract_field": "I"}
  ]
}

--- EXAMPLE 6: Causali explosion (Formula 3015) ---
WinSarp:
  914>Z((507="SF")(567=914)

JSON:
{
  "operations": [
    {"conditions": [{"left_field": 914, "operator": ">", "right_value": "Z"}], "operations": [
      {"type": "set", "field": 507, "value": "SF"},
      {"type": "set", "field": 567, "source_field": 914}
    ]}
  ]
}

================================================================================
# COMPLETE FIELD KNOWLEDGE (163 fields from 45 production formulas)
================================================================================

--- CORE FIELDS (1-59) ---
  1 = totale ore previsionale
  2 = flag tipo giornata
  3 = totale ore lavorate (read-only output)
  4 = ore straordinario/straord calcolato
  5 = differenza ore (previsionale - lavorato)
  6 = flag assenza
  7 = flag festivita
  8 = ore straordinario cap
 12 = flag turno
 14 = flag assenza
 15 = minuti residui arrotondamento
 17 = flag 14esima
 20 = flag notturno
 21 = ore notturne lavorate
 22 = flag notturno
 23 = flag notturno
 24 = flag notturno
 30 = minuti di arrotondamento
 35 = minuti di arrotondamento
 40 = flag superminimo
 45 = minuti di arrotondamento
 50 = flag domenica (I=si, Z=no)
 51 = flag festivita (I=si)
 52 = flag festivita
 55 = flag festivo (I=si, Z=no)
 58 = turno riconosciuto (MATT/POME/NOTT/RIPO/OPE/CHI/CHIA)
 59 = flag festivita

--- CAMPO70 / DIAGNOSTICA (70-78) ---
 70 = codice funzione (3=arr minuti, 15=arr impiegati, 20=arr entrata,
       21=arr uscita, 99=diagnostica)
 71 = messaggio diagnostica (stringa)
 72 = parametro diagnostica
 73 = parametro diagnostica
 74 = parametro diagnostica
 75 = parametro diagnostica
 76 = parametro diagnostica
 77 = parametro diagnostica
 78 = parametro diagnostica (reset)

--- TIMBRATURE PREVISIONALI (100-144) ---
100 = flag presenza (I=si, 2=non timbrata)
111 = entrata previsionale intervallo 1
112 = uscita previsionale intervallo 1
113 = entrata previsionale intervallo 2
114 = uscita previsionale intervallo 2
141 = entrata previsionale intervallo 3
142 = uscita previsionale intervallo 3
143 = entrata previsionale intervallo 4
144 = uscita previsionale intervallo 4

--- TIMBRATURE EFFETTIVE (200-229) ---
200 = entrata effettiva intervallo 1
201 = entrata effettiva copia 1
220 = uscita effettiva intervallo 1
221 = uscita effettiva copia 1
222 = uscita effettiva copia 2
223 = uscita effettiva copia 3
224 = uscita effettiva copia 4
225 = uscita effettiva copia 5
226 = uscita effettiva copia 6
227 = uscita effettiva copia 7

--- TIMBRATURE CALCOLATE (250-279) ---
250 = entrata calcolata 1
251 = entrata calcolata 1 (elaborata)
252 = entrata calcolata 2
253 = entrata calcolata 3
254 = entrata calcolata 4
255 = entrata calcolata 5
256 = entrata calcolata 6
257 = entrata calcolata 7
270 = uscita calcolata 1
271 = uscita calcolata 1 (elaborata)
272 = uscita calcolata 2
273 = uscita calcolata 3
274 = uscita calcolata 4
275 = uscita calcolata 5
276 = uscita calcolata 6
277 = uscita calcolata 7

--- DATA / SPECIALI (300-399) ---
300 = giorno mese (1-31)
301 = mese (1-12)
302 = giorno settimana (1=lun..7=dom)
305 = data limite skip
311 = flag sabato 5gg
390 = flag presenza previsionale

--- CAUSALI MANUALI / AUTS (400-499) ---
401 = causale manuale 1
402 = causale manuale 2
403 = causale manuale 3
404 = causale manuale 4
431 = ore autorizzate manuali 1
432 = ore autorizzate manuali 2
433 = ore autorizzate manuali 3
434 = ore autorizzate manuali 4

--- CAUSALI AUTOMATICHE (500-570) ---
500 = modalita FG ("DURATA")
501 = slot 1: S, F, FNG, FP, FX   (field 561 = ore)
502 = slot 2: SN, N               (field 562 = ore)
503 = slot 3: SF, NF              (field 563 = ore)
504 = slot 4: SFN, LFS            (field 564 = ore)
505 = slot 5: SP, N               (field 565 = ore)
506 = slot 6: SA, T               (field 566 = ore)
507 = slot 7: SF                  (field 567 = ore) — FREE slot
508 = slot 8: SN                  (field 568 = ore) — FREE slot
509 = slot 9: SNF                 (field 569 = ore) — FREE slot
510 = slot 10: SB                 (field 570 = ore) — FREE slot
CAUSALI SLOT RULES:
  Slots 501-504 are used by FG Standard (130/140).
  Slots 505-506 are used by FG Standard (210).
  Slots 507-510 are FREE — use these for NEW causali in FG Standard.
  For GUGEST: all slots 501-510 are managed by P2115/P3015.
  For FG NEW: all slots 501-510 are managed by P3015.

--- ASSENZE / MAGGIORAZIONI (600-799) ---
608 = ore assenza malattia
609 = ore assenza permessi
610 = ore assenza totali
611 = ore assenza retribuita
612 = ore assenza non retribuita
614 = ore assenza festiva
615 = ore assenza festiva
616 = ore assenza festiva
684 = flag festivita goduta
770 = flag presenze/reset
771 = ore ordinarie settimanali
772 = ore straordinario settimanali
773 = ore totali (771+772)
774 = ore lorde settimanali
775 = ore con assenze settimanali
776 = ore base settimanali
781 = flag accumulo sett
782 = contatore ore giornaliero
783 = accumulo ore annuale
784 = accumulo supplementare
785 = running total ore
788 = accumulo totale settimana
790 = accumulo supplem settimana
791 = flag accumulo
792 = flag accumulo

--- APPOGGIO / CALCOLO (800-899) ---
800 = temporaneo generico
801 = temporaneo generico
802 = temporaneo generico
803 = temporaneo generico
804 = temporaneo generico
805 = appoggio assenze 1120
806 = appoggio 1120
807 = appoggio 1120
810 = durata intervallo
811 = entrata intervallo
812 = uscita intervallo
813 = durata intervallo
820 = intervallo AUTS
821 = ore AUTS autorizzate
887 = soglia ore ordinarie
889 = soglia supplementari
890 = straord diurno residuo
891 = flag ore festive
892 = flag ore festive
899 = flag appoggio

--- GUGEST SETTIMANALI (900-929) ---
900 = flag turno (1=MATT,2=POME,3=NOTTE)
901 = ore notturne sett
902 = ore notturne ordinarie
903 = ore notturne festive
904 = ore straord festive
905 = ore ordinarie base
906 = ore supplementari
907 = ore straord annuale SA
908 = ore straord festive 2
909 = ore notturne sotto soglia
910 = ore notturne festive
914 = ore festive SF
915 = ore straord bassa fascia SB
918 = ore festive totali
919 = tipo festivita (1=norm,2=non god,3=patrono,4=sab5gg)
920 = ore festive residue
922 = flag turno
928 = flag notturno sett
929 = flag notturno sett

--- CUMULI ANNUALI (1000+) ---
1000 = ore totali anno
1051 = flag festivita anno
1052 = flag festivita anno
1100 = ore totali anno
1121 = flag straordinario (N=no)
1391 = ore part-time sett
1801 = flag primo giro eseguito

================================================================================
# COMPLETE K-REGISTER MAPPING (56 registers)
================================================================================

--- ACCOUNT (core totals) ---
  K601 = accumulo ore ordinarie (561+562+563+564+565+566)
  K602 = accumulo ore totali (field 3)
  K603 = accumulo ore ordinarie annue
  K604 = accumulo ore assenze retribuite
  K605 = accumulo ore assenze non retribuite
  K608 = accumulo ore assenze festive retribuite
  K609 = accumulo ore assenze
  K610 = accumulo ore totali (611+612+614+615+616)

--- RIPORTO CAUSALI ---
  K611 = ore S (straord diurno) → slot 501/561
  K612 = ore supplementari
  K614 = ore SN (straord notturno) → slot 502/562
  K615 = ore SF (straord festivo diurno) → slot 503/563
  K616 = ore SFN (straord festivo notturno) → slot 504/564
  K625 = ore T (trasferta) → slot 506/566
  K626 = ore N (indennita notturna) → slot 505/565
  K627 = ore straordinario festivo

--- SETTIMANALI GUGEST ---
  K770 = contatore giri settimana
  K771 = accumulo 3+4 settimanali
  K772 = accumulo assenze 608+609
  K774 = accumulo 907 settimanali
  K775 = accumulo totale (3+4+608+609)
  K776 = accumulo base (3+902+903+608+609)
  K781 = flag giorno
  K782 = accumulo ore giornaliere
  K783 = accumulo ore annuali 4
  K784 = accumulo 906
  K785 = running total
  K788 = accumulo (608+609+3)
  K790 = accumulo supplementare sett

--- ARROTONDAMENTO / TEMP ---
  K800 = temp arrotondamento
  K801 = risultato arrotondamento
  K802 = arr uscite
  K803 = overflow 24h
  K804 = arr residuo

--- CLASSIFICAZIONE (902-929) ---
  K902 = notturne ordinarie
  K903 = notturne festive
  K904 = straord festive
  K905 = ordinarie base
  K906 = supplementari
  K907 = straord annuale SA
  K908 = straord festive 2
  K909 = notturne sotto soglia
  K910 = notturne festive
  K914 = festive SF
  K915 = straord bassa fascia SB
  K918 = festive totali anno
  K900 = contatore giro

--- FESTIVITA / ASSENZE ---
  K251 = arr entrata effettiva
  K252 = arr entrata effettiva 2
  K271 = arr uscita calcolata
  K272 = arr uscita calcolata 2
  K629 = contatore fest non godute
  K630 = ore festive normali
  K631 = ore festive patrono
  K711 = ore annuali (K601+K608)

--- SUPPORTO ---
  K3 = arr ore totali
  K4 = arr ore straordinario
  K21 = swap ore notturne

================================================================================
# FLOW INTEGRATION RULES
================================================================================

EXISTING FLOWS:
  FG Standard: 100→R110→R120→R130/R140→R200→P210
  FG GUGEST A: 2100→R2101→P2109,P2122x7,P2123,P2124,P2125,P2114,P2115,P2130
  FG GUGEST B: 2105→R2106→(same P chain)
  FG NEW:      3000→R3001→P3002/3003,P3004,P3005,P3009,P3014,P3015,P3017
  IG:          1,5,10,1000,1010,1020 (indipendent per categoria)

ATTACHMENT POINTS:
  {"type": "after_r", "value": 130}
    = after R130/before R140 in FG Standard. Fields 800-899 free, causali 505-510 free.

  {"type": "after_r", "value": 140}
    = after R140/before R200 in FG Standard. Fields 800-899 free, causali 505-510 free.

  {"type": "new_phase", "value": "FG"}
    = standalone new FG formula

  {"type": "subroutine", "value": "GUGEST", "slot": "P2116"}
    = new P-called sub in GUGEST. Free P-slots: P2110-P2113,P2116-P2121,P2126-P2129,P2131-P2139

  {"type": "subroutine", "value": "NEW", "slot": "P3006"}
    = new P-called sub in NEW. Free P-slots: P3006-P3008,P3010-P3013,P3016,P3018-P3029

  {"type": "new_ig", "value": "category"}
    = new IG formula, uses fields 800-899 (805-809,822-886,890-899 free)

================================================================================
# RULES
================================================================================
1. "set" with "source_field" means: set field = value of source_field
2. "set" with "value" means: set field = literal value
3. "value" can be a literal string: "SFN", "I", "'100'", etc.
4. Field arithmetic:
   - Use "add_field" for addition: {"set","field":800,"source_field":3,"add_field":4} → 800=3A4
   - Use "subtract_field" for subtraction: {"set","field":4,"source_field":800,"subtract_field":1} → 4=800S1
   - For multiple subtractions: subtract_field, subtract_field_2
   - For K-register decrement: {"set","field":"K770","source_field":"K770","subtract_field":"I"}
5. k_accumulations define which K-registers accumulate which fields
   - Simple: {"kreg":"K601","source_field":3,"operation":"A"} → K601A3
   - Multi-field: {"kreg":"K771","source_field":3,"operation":"A"}, {"kreg":"K771","source_field":4,"operation":"A"} → K771A3A4
6. "attachment" tells where this formula hooks in. Choose from ATTACHMENT POINTS above.
7. Use "sub_blocks" for nested IF/ELSE chains (sequential blocks without conditions = ELSE chain)
8. Leave arrays empty if not applicable
9. "is_else": true means ELSE branch (NOT used for sequential IF chains)
10. If no condition, make "conditions" null
11. "conditions_join": "E"=AND, "O"=OR. Multiple conditions in one block = compound condition.
12. "r_call": jump to another formula, set "value" to formula ID
13. "p_call": call subroutine, set "value" to subroutine ID
14. "campo70": 3=arr minuti, 15=arr impiegati, 20=arr entrata, 21=arr uscita, 99=diagnostica
15. "comment": free text (maps to WinSarp "? text" comments)
16. "reset": zero-out a field: {"type":"reset","field":561}
17. CRITICAL: WinSarp has NO arithmetic operators (no +, -, *, /, x, M).
    Only field-to-field copy (source_field/add_field/subtract_field) and K-register accumulation.
    If the user requests multiplication/division, emit a comment and set the primary field.
    Example: for "K626 * 1.25", do: {"type":"set","field":800,"source_field":"K626"}
    and add a comment explaining the multiplier must be applied manually.
    NEVER put arithmetic expressions in value or source_field.
18. CRITICAL: Use FIELD KNOWLEDGE and K-REGISTER MAPPING above. NEVER invent fields or K-regs.
19. Causali codes: S, SN, SF, SFN, N, T, F, FNG, FP, FX, NF, LFS, SP, SA, SB, SNF.
    Map to correct slot (501-510). Each slot has a companion ore field (561-570).
    Setting causali slot 507 (free) requires setting field 567 with the hours.
20. Compound conditions use "conditions" array with "conditions_join": "E" or "O".
    In WinSarp: "E" = space or E, "O" = O between conditions.
    Example: 251>ZE271>Z → [{"left_field":251,"operator":">","right_value":"Z"}, {"left_field":271,"operator":">","right_value":"Z"}], "conditions_join":"E"
21. Sequential IF/THEN/ELSE (multiple blocks at same level) = chain of conditions.
    First matching condition executes its block. Represent as sequential blocks.
22. K-register subtraction: "operation": "S" means Kreg = Kreg - source_field.
    K-register increment: use source_field = "I" with operation "A".
"""


# ── Core extraction function ─────────────────────────────────

def extract_intent(user_request: str, model: str = "tencent/hy3:free",
                   timeout: int = 30) -> dict | None:
    """Call the LLM to extract a structured intent from a user request.

    Returns a dict matching FormulaIntent schema, or None on failure.
    The dict must pass validate_intent() before use.
    """
    from core.ai.utils import call_llm

    prompt = (
        f"{INTENT_SCHEMA_DOC}\n\n"
        f"USER REQUEST:\n{user_request}\n\n"
        "Respond ONLY with valid JSON. No explanations, no markdown.\n"
        "Output the JSON object matching the schema above."
    )

    try:
        raw = call_llm(
            prompt=prompt,
            model_id=model,
            temp=0.05,
            timeout=timeout,
        )
        if not raw or not raw.strip():
            _logger.warning("Empty response from LLM")
            return None
    except Exception as e:
        _logger.warning("LLM call failed: %s", e)
        return None

    return _parse_json_response(raw)


def _parse_json_response(raw: str) -> dict | None:
    """Extract the first JSON object from LLM output."""
    # Try to parse the entire output
    raw = raw.strip()
    # Remove markdown code fences
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    # Find JSON object
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        _logger.warning("No JSON object found in LLM response")
        return None

    json_str = m.group(0)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        _logger.warning("JSON decode error: %s", e)
        # Try to fix common issues
        json_str = _repair_json(json_str)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    return data


def _repair_json(s: str) -> str:
    """Attempt to repair common JSON formatting issues from LLM output."""
    # Replace single quotes with double quotes (but not inside strings)
    s = re.sub(r"(?<!\\)'", '"', s)
    # Remove trailing commas
    s = re.sub(r',\s*\}', '}', s)
    s = re.sub(r',\s*\]', ']', s)
    return s


def validate_intent(data: dict) -> list[str]:
    """Validate a parsed intent dict. Returns list of error messages (empty = valid)."""
    errors = []

    if not isinstance(data, dict):
        return ["Response is not a dict"]

    intent = data.get("intent")
    if not intent or not isinstance(intent, str):
        errors.append("Missing or invalid 'intent'")

    phase = data.get("phase")
    if phase not in ("IG", "FG", "DG", "SUB"):
        errors.append(f"Invalid phase: {phase}")

    blocks = data.get("blocks", [])
    if not isinstance(blocks, list):
        errors.append("'blocks' must be a list")
    else:
        for i, block in enumerate(blocks):
            be = _validate_block(block, i)
            errors.extend(be)

    return errors


def _validate_block(block: dict, idx: int) -> list[str]:
    errors = []
    if not isinstance(block, dict):
        return [f"block[{idx}] is not a dict"]
    ops = block.get("operations", [])
    if not isinstance(ops, list):
        errors.append(f"block[{idx}].operations must be a list")
    for j, op in enumerate(ops):
        if not isinstance(op, dict):
            errors.append(f"block[{idx}].operations[{j}] not a dict")
            continue
        op_type = op.get("type")
        if op_type not in ("set", "reset", "add", "sub", "r_call", "p_call", "campo70", "comment"):
            errors.append(f"block[{idx}].operations[{j}]: invalid type '{op_type}'")
        field = op.get("field")
        if field is None and op_type not in ("r_call", "p_call", "campo70", "comment"):
            errors.append(f"block[{idx}].operations[{j}]: missing 'field'")
    return errors


# ── Conversion to FormulaIntent dataclass ─────────────────────

def intent_from_dict(data: dict) -> FormulaIntent | None:
    """Convert a validated dict to FormulaIntent dataclass."""
    errors = validate_intent(data)
    if errors:
        _logger.warning("Intent validation errors: %s", errors)
        return None

    blocks = []
    for b in data.get("blocks", []):
        block = _block_from_dict(b)
        blocks.append(block)

    k_regs = []
    for kr in data.get("k_registers", []):
        k_regs.append(IntentKAccum(
            kreg=kr.get("kreg", ""),
            source_field=kr.get("source_field", 0),
            operation=kr.get("operation", "A"),
        ))

    return FormulaIntent(
        intent=data.get("intent", ""),
        phase=data.get("phase", "DG"),
        description=data.get("description", ""),
        input_fields=data.get("input_fields", []),
        output_fields=data.get("output_fields", []),
        causali=data.get("causali", {}),
        blocks=blocks,
        attachment=data.get("attachment"),
        k_registers=k_regs,
    )


def _block_from_dict(b: dict) -> IntentBlock:
    """Convert a block dict to IntentBlock."""
    conditions = None
    raw_conds = b.get("conditions")
    if raw_conds:
        conditions = []
        for c in raw_conds:
            conditions.append(IntentCondition(
                left_field=c.get("left_field", 0),
                operator=c.get("operator", "="),
                right_value=c.get("right_value", ""),
                right_is_field=c.get("right_is_field", False),
            ))

    operations = []
    for op in b.get("operations", []):
        operations.append(IntentFieldOp(
            type=op.get("type", "set"),
            field=op.get("field", 0),
            value=op.get("value"),
            source_field=op.get("source_field"),
        ))

    k_accums = []
    for ka in b.get("k_accumulations", []):
        k_accums.append(IntentKAccum(
            kreg=ka.get("kreg", ""),
            source_field=ka.get("source_field", 0),
            operation=ka.get("operation", "A"),
        ))

    sub_blocks = []
    for sb in b.get("sub_blocks", []):
        sub_blocks.append(_block_from_dict(sb))

    return IntentBlock(
        conditions=conditions,
        conditions_join=b.get("conditions_join", "E"),
        operations=operations,
        k_accumulations=k_accums,
        sub_blocks=sub_blocks,
        is_else=b.get("is_else", False),
    )
