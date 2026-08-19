"""
chunker.py
Analizza formule WinSarp compatte e le spezza in "mattoncini logici"
(condizioni, azioni, accumuli K, flag, cicli) con metadata tagging.
Supporta retrieval multi-step per la generazione di formule complesse.
"""
import logging
import re
from dataclasses import dataclass

from legacy_winsarp.core.winsarp.workbook_retriever import FormulaEntry, WorkbookRetriever

_logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# DATACLASS CHUNK
# ──────────────────────────────────────────────
@dataclass
class SemanticChunk:
    chunk_id: str
    formula_id: int
    tipo: str               # condizione, azione_assegnazione, azione_reset, accumulo_k, flusso_chiamata, flusso_terminale, salto_etichetta, campo70, puntatore
    categoria: str          # confronto_campo, assegnazione_diretta, accumulo_ore, chiamata_subroutine, fine_formula, goto, reset_multiplo, incremento_puntatore, ...
    text: str               # testo originale del chunk
    campi: list[int]        # campi coinvolti
    logica: str             # descrizione in linguaggio naturale
    descrizione_formula: str = ""
    categoria_formula: str = ""

# ──────────────────────────────────────────────
# CHUNKER
# ──────────────────────────────────────────────
# Espressioni regolari per riconoscere pattern WinSarp compatti
# Ordine importante: pattern piu' specifici prima

RE_K_ACCUMULO = re.compile(
    r'K\s*(\d+)\s+([AS])\s+([^;()]+?)(?=\s*[);]|\s*$)',
    re.IGNORECASE
)

RE_RESET = re.compile(r'!(\d+)')

RE_RP_CHAIN = re.compile(r'\b([RP])(\d{3,4})\b')

RE_SEMPLICE_ASSIGN = re.compile(
    r'\(?\s*(\d{2,4})\s*=\s*((?:\d{2,4}|[A-Z]\w*|\'[^\']*\'|"[^"]*"|'
    r'\{\d+\}|F\(\d+\))(?:\s*[AS]\s*(?:\d{2,4}|[A-Z]\w*|\'[^\']*\'|"[^"]*"|\{\d+\}|F\(\d+\)))*)\s*\)?'
)

RE_VF_VU = re.compile(r'\b(VF|VU)\b')

RE_V_LABEL = re.compile(r'\b(V\d{2,3})\b')

RE_POINTER = re.compile(r'[\[\]](\d+)')

RE_CAMPO70 = re.compile(r'70\s*=\s*\'(\d+)\'')

RE_CONDITION = re.compile(
    r'(\d{2,4}|V\d{2,3})\s*([U#><E]|[<>]=|>=|<=|E|O)\s*'
    r'(Z|I|\d{2,4}|(?:\d{2}\.\d{2})|\'[^\']*\'|"[^"]*"|[A-Z]\w*)'
    r'(?:\s*[EO]\s*\d{2,4}\s*[U#><E]\s*(?:Z|I|\d{2,4}|(?:\d{2}\.\d{2})|\'[^\']*\'|"[^"]*"|[A-Z]\w*))*'
)

RE_COMMENT = re.compile(r'\?\s*(.*?)(?=[;)]|\Z)')

# Blocco condizionale: condizione seguita da parentesi con azioni
RE_IF_BLOCK = re.compile(
    r'('
    r'\d{2,4}\s*[U#><E]\s*(?:Z|I|\d{2,4}|(?:\d{2}\.\d{2})|\'[^\']*\'|"[^"]*"|[A-Z]\w*)'
    r'(?:\s*[EO]\s*\d{2,4}\s*[U#><E]\s*(?:Z|I|\d{2,4}|(?:\d{2}\.\d{2})|\'[^\']*\'|"[^"]*"|[A-Z]\w*))*'
    r')\s*\('
)


def _parse_campi(text: str) -> list[int]:
    return sorted(set(
        int(m) for m in re.findall(r'\b(\d{2,4})\b', text)
        if 1 <= int(m) <= 9999
    ))


def _logica_for_tipo(tipo: str, text: str) -> str:
    desc = {
        "condizione": "Condizione IF/THIN per selezione logica",
        "azione_assegnazione": "Assegnazione valore a campo",
        "azione_reset": "Azzera campo a zero/falso",
        "accumulo_k": "Accumulo (add/sottr) in progressivo K",
        "flusso_chiamata": "Chiamata a formula/subroutine",
        "flusso_terminale": "Terminatore di flusso (fine formula/salto)",
        "salto_etichetta": "Etichetta di salto condizionale",
        "campo70": "Operazione speciale Campo70",
        "puntatore": "Operazione su puntatore catena",
        "commento": "Commento esplicativo",
    }
    return desc.get(tipo, "Blocco logico WinSarp")


class WinSarpChunker:
    """Spezza formule WinSarp in mattoncini semantici con metadata."""

    def __init__(self, retriever: WorkbookRetriever):
        self.retriever = retriever
        self.chunks: list[SemanticChunk] = []
        self._indexed = False
        if self.retriever and len(self.retriever.entries) > 0:
            self.chunk_all()

    def chunk_all(self):
        """Processa tutte le formule del workbook e produce chunks."""
        self.chunks.clear()
        chunk_id = 0
        for entry in self.retriever.entries.values():
            formula_chunks = self._chunk_formula(entry)
            for c in formula_chunks:
                c.chunk_id = f"chunk_{chunk_id}"
                chunk_id += 1
                self.chunks.append(c)
        _logger.info("Chunking completato: %d chunks da %d formule", len(self.chunks), len(self.retriever.entries))
        self._indexed = True

    def _chunk_formula(self, entry: FormulaEntry) -> list[SemanticChunk]:
        chunks: list[SemanticChunk] = []
        formula = entry.formula

        # 1. Estrai commenti
        for m in RE_COMMENT.finditer(formula):
            start = m.start()
            text = m.group(1).strip()
            if text:
                chunks.append(SemanticChunk(
                    chunk_id="",
                    formula_id=entry.codice,
                    tipo="commento",
                    categoria="documentazione",
                    text=f"? {text}",
                    campi=[],
                    logica=text,
                    descrizione_formula=entry.descrizione,
                    categoria_formula=entry.categoria,
                ))

        # 2. Trova blocchi condizionali (IF condition ( azioni ))
        #    Sostituiamo temporaneamente i blocchi gia' processati per evitare doppioni
        processed_spans: list[tuple[int, int]] = []

        for m in RE_IF_BLOCK.finditer(formula):
            cond_text = m.group(1).strip()
            cond_start = m.start()
            cond_end = m.end()  # include la '('

            # Salta se dentro uno span gia' processato
            if any(ps[0] <= cond_start < ps[1] for ps in processed_spans):
                continue

            campi_cond = _parse_campi(cond_text)

            # Trova la ) di chiusura bilanciata
            depth = 1
            i = cond_end
            while i < len(formula) and depth > 0:
                if formula[i] == '(':
                    depth += 1
                elif formula[i] == ')':
                    depth -= 1
                i += 1
            action_text = formula[cond_end:i-1]  # escludi la )

            chunk_text = cond_text
            chunk_type = "condizione"

            # Classifica il tipo di condizione
            if "U" in cond_text:
                categoria = "confronto_uguaglianza"
            elif "#" in cond_text:
                categoria = "confronto_diversita"
            elif ">" in cond_text or "<" in cond_text:
                if "E" in cond_text or "O" in cond_text:
                    categoria = "confronto_composto"
                else:
                    categoria = "confronto_ordinale"
            else:
                categoria = "confronto_semplice"

            def logica_condizione(ct: str) -> str:
                if ">Z" in ct:
                    return "Se campo maggiore di zero"
                if "UZ" in ct:
                    return "Se campo uguale a zero"
                if "UI" in ct:
                    return "Se campo uguale a VERO"
                if "UO" in ct:
                    return "Se campo uguale a uno dei valori"
                return f"Condizione: {ct[:60]}"

            chunks.append(SemanticChunk(
                chunk_id="",
                formula_id=entry.codice,
                tipo=chunk_type,
                categoria=categoria,
                text=cond_text,
                campi=campi_cond,
                logica=logica_condizione(cond_text),
                descrizione_formula=entry.descrizione,
                categoria_formula=entry.categoria,
            ))

            # Analizza le azioni dentro il blocco THEN
            action_chunks = self._extract_actions_from_block(action_text, entry)
            for ac in action_chunks:
                ac.logica = f"THEN: {ac.logica}"
            chunks.extend(action_chunks)

            processed_spans.append((cond_start, i))

        # 3. Estrai K accumulo non dentro blocchi gia' processati
        for m in RE_K_ACCUMULO.finditer(formula):
            if any(ps[0] <= m.start() < ps[1] for ps in processed_spans):
                continue
            k_field = int(m.group(1))
            op = "Aggiungi" if m.group(2).upper() == "A" else "Sottrai"
            val = m.group(3).strip()
            chunks.append(SemanticChunk(
                chunk_id="",
                formula_id=entry.codice,
                tipo="accumulo_k",
                categoria=f"accumulo_{op.lower()}",
                text=m.group(0),
                campi=[k_field] + _parse_campi(val),
                logica=f"{op} {val} sul progressivo K{k_field}",
                descrizione_formula=entry.descrizione,
                categoria_formula=entry.categoria,
            ))

        # 4. Estrai R/P chain calls
        for m in RE_RP_CHAIN.finditer(formula):
            if any(ps[0] <= m.start() < ps[1] for ps in processed_spans):
                continue
            tipo = "P" if m.group(1) == "P" else "R"
            target = int(m.group(2))
            nome_target = ""
            te = self.retriever.find_by_codice(target)
            if te:
                nome_target = f" ({te.descrizione})"
            chunks.append(SemanticChunk(
                chunk_id="",
                formula_id=entry.codice,
                tipo="flusso_chiamata",
                categoria=f"chiamata_{tipo.lower()}",
                text=m.group(0),
                campi=[target],
                logica=f"{'Chiama subroutine' if tipo == 'P' else 'Salta a'} formula {target}{nome_target}",
                descrizione_formula=entry.descrizione,
                categoria_formula=entry.categoria,
            ))

        # 5. Estrai VF/VU
        for m in RE_VF_VU.finditer(formula):
            if any(ps[0] <= m.start() < ps[1] for ps in processed_spans):
                continue
            t = m.group(1)
            chunks.append(SemanticChunk(
                chunk_id="",
                formula_id=entry.codice,
                tipo="flusso_terminale",
                categoria="fine_formula" if t == "VF" else "salto_ultimo_periodo",
                text=t,
                campi=[],
                logica="Termina formula (VF)" if t == "VF" else "Salta all'ultimo periodo logico (VU)",
                descrizione_formula=entry.descrizione,
                categoria_formula=entry.categoria,
            ))

        # 6. Estrai V-label (salti/etichette)
        for m in RE_V_LABEL.finditer(formula):
            if any(ps[0] <= m.start() < ps[1] for ps in processed_spans):
                continue
            label = m.group(1)
            if label in ("VF", "VU"):
                continue  # gia' catturati sopra
            # Determina se e' MARK o GOTO in base al contesto
            before = formula[max(0, m.start()-10):m.start()]
            is_goto = bool(re.search(r'(\(|;)\s*$', before))
            chunks.append(SemanticChunk(
                chunk_id="",
                formula_id=entry.codice,
                tipo="salto_etichetta",
                categoria="goto" if is_goto else "mark",
                text=label,
                campi=[],
                logica=f"{'Salta a' if is_goto else 'Marca posizione'} etichetta {label}",
                descrizione_formula=entry.descrizione,
                categoria_formula=entry.categoria,
            ))

        # 7. Estrai operazioni puntatore
        for m in RE_POINTER.finditer(formula):
            if any(ps[0] <= m.start() < ps[1] for ps in processed_spans):
                continue
            field = int(m.group(1))
            ch = formula[m.start()]
            op = "push" if ch == "[" else "pop"
            chunks.append(SemanticChunk(
                chunk_id="",
                formula_id=entry.codice,
                tipo="puntatore",
                categoria=f"{op}_catena",
                text=m.group(0),
                campi=[field],
                logica=f"{'Inizia' if op == 'push' else 'Termina'} catena puntatori su campo {field}",
                descrizione_formula=entry.descrizione,
                categoria_formula=entry.categoria,
            ))

        # 8. Estrai assignazioni non dentro blocchi
        for m in RE_SEMPLICE_ASSIGN.finditer(formula):
            if any(ps[0] <= m.start() < ps[1] for ps in processed_spans):
                continue
            # Salta se contiene operatori di condizione
            raw = m.group(0)
            if re.search(r'[U#]', raw) and not re.search(r'=', raw):
                continue
            target = int(m.group(1))
            val = m.group(2).strip()
            chunks.append(SemanticChunk(
                chunk_id="",
                formula_id=entry.codice,
                tipo="azione_assegnazione",
                categoria="assegnazione_diretta",
                text=f"{target} = {val}",
                campi=[target] + _parse_campi(val),
                logica=f"Imposta campo {target} = {val}",
                descrizione_formula=entry.descrizione,
                categoria_formula=entry.categoria,
            ))

        # 9. Estrai reset non dentro blocchi
        for m in RE_RESET.finditer(formula):
            if any(ps[0] <= m.start() < ps[1] for ps in processed_spans):
                continue
            field = int(m.group(1))
            chunks.append(SemanticChunk(
                chunk_id="",
                formula_id=entry.codice,
                tipo="azione_reset",
                categoria="reset_campo",
                text=f"!{field}",
                campi=[field],
                logica=f"Azzera campo {field}",
                descrizione_formula=entry.descrizione,
                categoria_formula=entry.categoria,
            ))

        # 10. Estrai CAMPO70
        for m in RE_CAMPO70.finditer(formula):
            if any(ps[0] <= m.start() < ps[1] for ps in processed_spans):
                continue
            fn = m.group(1)
            chunks.append(SemanticChunk(
                chunk_id="",
                formula_id=entry.codice,
                tipo="campo70",
                categoria=f"funzione_{fn}",
                text=m.group(0),
                campi=[70],
                logica=f"Operazione speciale Campo70 funzione {fn}",
                descrizione_formula=entry.descrizione,
                categoria_formula=entry.categoria,
            ))

        return chunks

    def _extract_actions_from_block(self, action_text: str, entry: FormulaEntry) -> list[SemanticChunk]:
        """Analizza il testo dentro un blocco THEN/azione e produce chunks per ogni azione."""
        chunks: list[SemanticChunk] = []
        # Divide per ) che separa azioni multiple dentro lo stesso THEN
        # Es: (!3!5)(4=800)VU -> azioni: !3!5, 4=800, VU

        # Normalizza: processa a livello di singole parentesi
        actions = []
        depth = 0
        current = ""
        for ch in action_text:
            if ch == '(':
                if depth > 0:
                    current += ch
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0 and current.strip():
                    actions.append(current.strip())
                    current = ""
                elif depth > 0:
                    current += ch
                # depth = 0: fine gruppo, eventuale testo dopo
            else:
                if depth > 0:
                    current += ch
                else:
                    # Testo tra un gruppo e l'altro (es. VF, VU, comandi)
                    if ch == ';':
                        if current.strip():
                            actions.append(current.strip())
                            current = ""
                    else:
                        current += ch
        if current.strip():
            actions.append(current.strip())

        for act in actions:
            # Classifica il tipo di azione
            if act.upper() in ("VF", "VU"):
                chunks.append(SemanticChunk(
                    chunk_id="", formula_id=entry.codice,
                    tipo="flusso_terminale",
                    categoria="fine_formula" if act == "VF" else "salto_ultimo_periodo",
                    text=act, campi=[],
                    logica="Termina formula" if act == "VF" else "Salta all'ultimo periodo",
                    descrizione_formula=entry.descrizione,
                    categoria_formula=entry.categoria,
                ))
            elif re.match(r'[RP]\d+', act):
                m = re.match(r'([RP])(\d+)', act)
                if m:
                    t = "P" if m.group(1) == "P" else "R"
                    target = int(m.group(2))
                    chunks.append(SemanticChunk(
                        chunk_id="", formula_id=entry.codice,
                        tipo="flusso_chiamata",
                        categoria=f"chiamata_{t.lower()}",
                        text=act, campi=[target],
                        logica=f"{'Chiama' if t == 'P' else 'Salta a'} formula {target}",
                        descrizione_formula=entry.descrizione,
                        categoria_formula=entry.categoria,
                    ))
            elif act.startswith('!'):
                fields = re.findall(r'!(\d+)', act)
                for f in fields:
                    chunks.append(SemanticChunk(
                        chunk_id="", formula_id=entry.codice,
                        tipo="azione_reset",
                        categoria="reset_campo",
                        text=f"!{f}", campi=[int(f)],
                        logica=f"Azzera campo {f}",
                        descrizione_formula=entry.descrizione,
                        categoria_formula=entry.categoria,
                    ))
            elif re.search(r'\d{2,4}\s*=', act):
                m = re.match(r'(\d{2,4})\s*=\s*(.+)', act)
                if m:
                    target = int(m.group(1))
                    val = m.group(2).strip()
                    chunks.append(SemanticChunk(
                        chunk_id="", formula_id=entry.codice,
                        tipo="azione_assegnazione",
                        categoria="assegnazione_diretta",
                        text=act, campi=[target] + _parse_campi(val),
                        logica=f"Imposta campo {target} = {val}",
                        descrizione_formula=entry.descrizione,
                        categoria_formula=entry.categoria,
                    ))
            else:
                # Azione generica
                chunks.append(SemanticChunk(
                    chunk_id="", formula_id=entry.codice,
                    tipo="azione_assegnazione",
                    categoria="azione_generica",
                    text=act, campi=_parse_campi(act),
                    logica=f"Operazione: {act[:60]}",
                    descrizione_formula=entry.descrizione,
                    categoria_formula=entry.categoria,
                ))

        return chunks

    # ──────────────────────────────────────────────
    # RICERCA CHUNK
    # ──────────────────────────────────────────────
    def search(self, query: str, top_k: int = 5) -> list[tuple[SemanticChunk, float]]:
        """Cerca chunk per keyword matching con scoring."""
        if not self._indexed:
            self.chunk_all()

        query_lower = query.lower()
        tokens = [t for t in re.findall(r'\w+', query_lower) if len(t) > 2]
        field_nums = [int(t) for t in tokens if t.isdigit() and 1 <= int(t) <= 9999]

        scored = []
        for chunk in self.chunks:
            score = 0.0
            text = (chunk.logica + " " + chunk.text + " " + chunk.categoria).lower()

            for t in tokens:
                if t in text:
                    score += 1.0

            # Bonus: match su campi specifici
            for f in field_nums:
                if f in chunk.campi:
                    score += 3.0

            # Bonus: matching tipo chunk
            tipo_keywords = {
                "condizione": ["se", "if", "condizione", "quando"],
                "accumulo": ["accumula", "progressivo", "k ", "totale"],
                "reset": ["azzera", "resetta", "cancella"],
                "chiamata": ["chiama", "subroutine", "richiama", "salta"],
                "assegnazione": ["imposta", "set", "assegna", "scrivi"],
                "arrotondamento": ["arrotonda", "quarto", "minuti", "ora"],
                "festivo": ["festivo", "festivita", "domenica", "patrono"],
                "straordinario": ["straordinario", "diurno", "notturno", "sa", "sb"],
                "turno": ["turno", "matt", "pome", "nott", "ripo"],
                "pausa": ["pausa", "pranzo", "intervallo"],
            }
            for tip, kws in tipo_keywords.items():
                if any(kw in query_lower for kw in kws) and tip in chunk.tipo:
                    score += 2.0

            if score > 0:
                scored.append((chunk, score))

        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def search_by_type(self, tipo: str, top_k: int = 5) -> list[SemanticChunk]:
        """Filtra chunk per tipo."""
        if not self._indexed:
            self.chunk_all()
        filtered = [c for c in self.chunks if c.tipo == tipo]
        return filtered[:top_k]

    def search_by_field(self, campo: int, top_k: int = 5) -> list[SemanticChunk]:
        """Trova chunk che coinvolgono un campo specifico."""
        if not self._indexed:
            self.chunk_all()
        filtered = [c for c in self.chunks if campo in c.campi]
        return filtered[:top_k]

    def build_multi_step_context(self, query: str, top_k: int = 6) -> str:
        """Costruisce un contesto multi-chunk per il prompt LLM.

        Recupera chunk di TIPO diverso ma tutti rilevanti per la query,
        per dare al LLM esempi di pattern multipli.
        """
        results = self.search(query, top_k=top_k * 2)

        # Seleziona chunk di tipo diverso per coprire piu' pattern
        seen_tipi = set()
        selected = []
        for chunk, score in results:
            if chunk.tipo not in seen_tipi or len(selected) < top_k // 2:
                seen_tipi.add(chunk.tipo)
                selected.append((chunk, score))
            if len(selected) >= top_k:
                break

        # Se non basta, aggiungi altri chunk
        if len(selected) < top_k:
            for chunk, score in results:
                if (chunk, score) not in selected:
                    selected.append((chunk, score))
                if len(selected) >= top_k:
                    break

        lines = [
            "### ESEMPI DI PATTERN WINsarp RILEVANTI (dal catalogo) ###",
            ""
        ]
        for chunk, score in selected:
            lines.append(f"[Fonte: #{chunk.formula_id} - {chunk.descrizione_formula[:40]}]")
            lines.append(f"  Tipo: {chunk.tipo} / {chunk.categoria}")
            lines.append(f"  Pattern: {chunk.text}")
            lines.append(f"  Logica: {chunk.logica}")
            if chunk.campi:
                lines.append(f"  Campi: {', '.join(str(c) for c in chunk.campi)}")
            lines.append(f"  Score: {score:.1f}")
            lines.append("")

        return "\n".join(lines)

    def is_available(self) -> bool:
        return len(self.retriever.entries) > 0
