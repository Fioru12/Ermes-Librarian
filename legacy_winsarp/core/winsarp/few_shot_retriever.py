"""
few_shot_retriever.py
Retriever per few-shot examples da FormuleWinsarpInUso.txt.
Data una richiesta utente, trova le formule piu' simili da usare come contesto.
"""
import logging
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

_logger = logging.getLogger(__name__)

FORMULE_IN_USO_PATH = Path("FormuleWinsarpInUso.txt")

# Pattern di base della sintassi WinSarp per classificazione
PATTERN_TAGS = {
    "riconoscimento_turno": r"(!\d{1,4})\s*\?\s*INDICATORE|900\s*[=<>]|58\s*=",
    "primo_giro": r"300\s+U\s+301|PRIMO\s*GIRO|770",
    "secondo_giro": r"SECONDO\s*GIRO|51\s+U\s+I\s+E\s+52\s+U\s+I",
    "accumulo_k": r"K\d{3}\s+[AILST]",
    "richiamo_r": r"\bR\s*\d{3,5}\b",
    "richiamo_p": r"\bP\s*\d{3,5}\b",
    "condizione_oraria": r"\d{2}\.\d{2}",
    "calcolo_ore": r"70\s*=|3\s*=\s*\d+|K601|K602",
    "straordinario": r"K61[0-9]|K62[0-9]|STRAORDINARIO|[Ss]traordinario",
    "festivo": r"55\s+U\s+I|K60[35]|FESTIVO|[Ff]estivo",
    "assenze": r"608|609|5\s*=\s*\d+|ASSENZE",
    "flag": r"50\s+U\s+'[2I]'|[K]\d{3}\s*[+-]\s*I",
    "maggiorazioni": r"K90[0-9]",
    "causali_automatiche": r"56[0-9]\s*=|501\s*=|F|SA|SB|SN|SP|SF|LFS|N|NF",
    "warning_ore": r"ATTENZIONE|783|70\s*=\s*'99'",
    "ritocco_sb_sa": r"2114|3014|915|907|RITOCCO",
    "esplode_causali": r"2115|3015|561\s*=\s*918|CODICE.*CAUSALE",
    "intervalli_orari": r"251|271|252|272|111|141",
}


@dataclass
class FormulaUsoEntry:
    numero: int
    body: str
    lunghezza: int
    tags: set[str] = field(default_factory=set)
    campi_letti: set[int] = field(default_factory=set)
    campi_scritti: set[int] = field(default_factory=set)
    k_register: set[str] = field(default_factory=set)
    r_calls: list[int] = field(default_factory=list)
    p_calls: list[int] = field(default_factory=list)
    ha_condizioni_if: bool = False
    ha_flag_turno: bool = False
    ha_operazioni_orarie: bool = False
    scopoSuggerito: str = ""
    keywords: list[str] = field(default_factory=list)
    embedding: Optional[list[float]] = None


class FewShotRetriever:
    """Carica e indicizza FormuleWinsarpInUso.txt per retrieval few-shot."""

    def __init__(self, path: Path = FORMULE_IN_USO_PATH):
        self.path = path
        self.entries: dict[int, FormulaUsoEntry] = {}
        self._loaded = False
        self._embedder = None
        self._embeddings: dict[int, list[float]] = {}

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            except ImportError:
                self._embedder = None
        return self._embedder

    def _embed_text(self, text: str) -> list[float]:
        enc = self._get_embedder()
        if enc is None:
            return []
        return enc.encode(text, normalize_embeddings=True).tolist()

    def _build_embeddings(self) -> None:
        """Costruisce embedding semantici per tutte le formule caricate."""
        if self._embeddings:
            return
        if self._get_embedder() is None:
            _logger.info("sentence-transformers non disponibile, skip embedding")
            return
        texts = []
        ids = []
        for num, entry in self.entries.items():
            text = f"{entry.scopoSuggerito}. {entry.body}"
            if entry.tags:
                text += " " + " ".join(entry.tags)
            texts.append(text)
            ids.append(num)
        if not texts:
            return
        try:
            vectors = self._embedder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            for num, vec in zip(ids, vectors):
                self._embeddings[num] = vec.tolist()
            _logger.info("Calcolati embedding per %d formule", len(self._embeddings))
        except Exception as e:
            _logger.warning("Errore calcolo embedding: %s", e)

    def search_semantic(self, query: str, top_k: int = 3) -> list[FormulaUsoEntry]:
        """Cerca formule per similarita' semantica (embedding)."""
        if not self._loaded:
            if not self.load():
                return []
        self._build_embeddings()
        if not self._embeddings:
            _logger.info("Embedding non disponibili, fallback a search keyword")
            return self.search(query, top_k=top_k)

        import numpy as np
        qvec = np.array(self._embed_text(query))
        if qvec.size == 0:
            return self.search(query, top_k=top_k)

        scored: list[tuple[float, int]] = []
        for num, vec in self._embeddings.items():
            score = float(np.dot(qvec, np.array(vec)))
            scored.append((score, num))

        scored.sort(key=lambda x: -x[0])
        results = [self.entries[num] for _, num in scored[:top_k]]
        _logger.debug("Semantic search: query=%s, top=%d", query[:60], len(results))
        return results

    def load(self) -> bool:
        """Parse FormuleWinsarpInUso.txt in entries strutturate."""
        if not self.path.exists():
            _logger.warning("File %s non trovato", self.path)
            return False

        content = self.path.read_text(encoding="utf-8")
        blocks = re.split(r'\n\s*(?=formula\s+\d+)', content, flags=re.IGNORECASE)

        for block in blocks:
            block = block.strip()
            if not block:
                continue
            m = re.match(r'formula\s+(\d+)', block, re.IGNORECASE)
            if not m:
                continue
            num = int(m.group(1))
            body = block[m.end():].strip()
            if not body:
                continue

            entry = self._parse_entry(num, body)
            self.entries[num] = entry

        self._loaded = True
        _logger.info("Caricate %d formule in uso da %s", len(self.entries), self.path)
        return True

    def _parse_entry(self, num: int, body: str) -> FormulaUsoEntry:
        body_clean = re.sub(r'\s*\?.*', '', body)  # rimuovi commenti
        tags: set[str] = set()

        # Tag per pattern sintattici
        for tag, pattern in PATTERN_TAGS.items():
            if re.search(pattern, body_clean, re.IGNORECASE):
                tags.add(tag)

        # Campi letti (a sinistra di operatore = < >)
        campi_letti = set()
        for m in re.finditer(r'(?<!\d)(\d{2,4})\s*(?=[=<>])', body_clean):
            v = int(m.group(1))
            if 1 <= v <= 5000:
                campi_letti.add(v)

        # Campi scritti
        campi_scritti = set()
        for m in re.finditer(r'\(?\s*!(\d{2,4})\)?', body_clean):
            v = int(m.group(1))
            if 1 <= v <= 5000:
                campi_scritti.add(v)
        for m in re.finditer(r'\(\s*(\d{2,4})\s*=', body_clean):
            v = int(m.group(1))
            if 1 <= v <= 5000:
                campi_scritti.add(v)

        # K register
        k_register = set(re.findall(r'\b(K\d{3})\b', body_clean))

        # R calls
        r_calls = [int(x) for x in re.findall(r'\bR\s*(\d{2,5})\b', body_clean)]

        # P calls
        p_calls = [int(x) for x in re.findall(r'\bP\s*(\d{2,5})\b', body_clean)]

        ha_condizioni_if = bool(re.search(r'\bVF\b|\bVU\b|\bV\d{2}\b', body_clean))
        ha_flag_turno = bool(re.search(r'900\s*=|50\s+U\s+[\'I2]', body_clean))
        ha_operazioni_orarie = bool(re.search(r"'\d{2}\.\d{2}'|\d{2}\.\d{2}", body_clean))

        # Keywords from body
        keywords = re.findall(r'\b[A-Z]{2,}\b', body_clean)
        keywords = [k for k in keywords if len(k) >= 2 and not k.startswith('K')]

        # Scopo suggerito
        scopo = self._guess_scopo(num, tags)

        return FormulaUsoEntry(
            numero=num,
            body=body,
            lunghezza=len(body),
            tags=tags,
            campi_letti=campi_letti,
            campi_scritti=campi_scritti,
            k_register=k_register,
            r_calls=r_calls,
            p_calls=p_calls,
            ha_condizioni_if=ha_condizioni_if,
            ha_flag_turno=ha_flag_turno,
            ha_operazioni_orarie=ha_operazioni_orarie,
            scopoSuggerito=scopo,
            keywords=keywords,
        )

    def _guess_scopo(self, num: int, tags: set[str]) -> str:
        # Use commenti nel body o mappa nota
        SCOPATI: dict[int, str] = {
            5: "Riconoscimento automatico turno (MATT/POME/NOTT/RIPO)",
            10: "Riconoscimento turno su calendario (OPE/MATT/POME/NOTT)",
            100: "Calcolo presenza con R 110",
            110: "Calcolo ore ordinarie/straordinarie con gestione assenze",
            120: "Smistamento in base a flag festivo/dominica",
            130: "Causale SFN e accumulo K601/K604",
            140: "Causale SN e accumulo straordinario",
            200: "Accumulo K601/K602 e richiamo P210",
            210: "Calcolo straordinario settimanale",
            1000: "Inizializzazione intervalli previsionali",
            1010: "Inizializzazione intervalli con timbrature",
            1020: "Reindirizzamento timbrature su intervalli",
            1100: "Calcolo ore con gestione assenze (primo giro)",
            1120: "Calcolo ore con gestione assenze su intervalli",
            2000: "Riapertura giornata CHIA/CHI",
            2050: "Calcolo pausa pranzo (storico)",
            2051: "Calcolo pausa pranzo su due turni",
            2060: "Taglio timbrature dopo le 20:05",
            2100: "Primo giro completo con straordinario e festivo",
            2101: "Secondo giro completo con accumuli K e P calls",
            2105: "Primo giro con pausa pranzo",
            2106: "Secondo giro con pausa pranzo",
            2107: "Calcolo maggiorazioni su primo/secondo giro",
            2109: "Festivita automatiche con gestione non godute",
            2114: "Ritocco SB/SA (max 8h)",
            2115: "Esplosione causali automatiche",
            2122: "Rilevazione orario notturno/festivo/domenicale",
            2123: "Calcolo maggiorazioni per causali (parte 1)",
            2124: "Calcolo maggiorazioni per causali (parte 2)",
            2130: "Warning ore carenti settimanali",
            2140: "Somma ore ordinarie+straordinarie",
            3000: "Primo giro GUGEST",
            3001: "Secondo giro GUGEST",
            3002: "Calcolo straordinario settimanale ante 01/06/2023",
            3003: "Calcolo straordinario settimanale post 01/06/2023",
            3004: "Maggiorazioni turnisti",
            3005: "Calcolo straordinario su GUGEST",
            3009: "Festivita automatiche GUGEST",
            3014: "Ritocco SB/SA GUGEST",
            3015: "Esplosione causali automatiche GUGEST",
            3017: "Gestione AUTS",
            3030: "Warning ore carenti con avvicinamento 250h",
            9001: "Calcolo ore a scaglioni con R9002",
            9002: "Calcolo ore scaglione",
        }
        if num in SCOPATI:
            return SCOPATI[num]
        if "primo_giro" in tags:
            return "Formula per primo giro di elaborazione"
        if "secondo_giro" in tags:
            return "Formula per secondo giro di elaborazione"
        if "riconoscimento_turno" in tags:
            return "Riconoscimento automatico turno"
        return "Formula WinSarp"

    def search(self, query: str, top_k: int = 3) -> list[FormulaUsoEntry]:
        """Cerca le formule piu' rilevanti per la query."""
        if not self._loaded:
            if not self.load():
                return []

        query_lower = query.lower()

        # Estrai pattern chiave dalla query
        query_campi = set(re.findall(r'\b(\d{2,4})\b', query))
        parole_chiave = {p.lower() for p in re.findall(r'\b([A-Za-z]{3,})\b', query_lower)}

        scored: list[tuple[float, FormulaUsoEntry]] = []

        for entry in self.entries.values():
            score = 0.0

            # 1. Match tag (peso: 20 ciascuno)
            for tag in entry.tags:
                tag_words = tag.replace('_', ' ')
                if any(w in tag_words for w in parole_chiave) or tag in query_lower:
                    score += 20.0
                # parole parziali
                for qw in parole_chiave:
                    if qw in tag_words or tag_words.startswith(qw) or qw.startswith(tag_words):
                        score += 10.0

            # 2. Match campi (peso: 5 per campo)
            for c in entry.campi_letti | entry.campi_scritti:
                if str(c) in query:
                    score += 5.0

            # 3. Match testo nel body (peso: 3 per parola)
            body_lower = entry.body.lower()
            for pw in parole_chiave - {'formula', 'winsarp', 'campo', 'calcolo', 'ore'}:
                if pw in body_lower:
                    score += 3.0

            # 4. Keyword match (peso: 5)
            for kw in entry.keywords:
                if kw.lower() in parole_chiave:
                    score += 5.0

            # 5. Termini specifici per tag (bonus semantico)
            if "turno" in parole_chiave and "riconoscimento_turno" in entry.tags:
                score += 30.0
            if "straordinario" in parole_chiave and "straordinario" in entry.tags:
                score += 30.0
            if "festivo" in parole_chiave and "festivo" in entry.tags:
                score += 30.0
            if any(a in parole_chiave for a in ["assenze", "assenza", "malattia"]) and "assenze" in entry.tags:
                score += 25.0
            if any(a in parole_chiave for a in ["primo", "giro", "2100"]) and "primo_giro" in entry.tags:
                score += 25.0
            if any(a in parole_chiave for a in ["secondo", "giro", "2101"]) and "secondo_giro" in entry.tags:
                score += 25.0
            if "maggiorazione" in parole_chiave and "maggiorazioni" in entry.tags:
                score += 25.0
            if "causale" in parole_chiave and "causali_automatiche" in entry.tags:
                score += 20.0
            if any(a in parole_chiave for a in ["notturno", "notte", "nott"]) and "condizione_oraria" in entry.tags:
                score += 15.0
            if "warning" in parole_chiave or "carenti" in parole_chiave and "warning_ore" in entry.tags:
                score += 25.0
            if any(a in parole_chiave for a in ["sb", "sa", "ritocco"]) and "ritocco_sb_sa" in entry.tags:
                score += 25.0
            if "auts" in parole_chiave and "gestione_auts" in entry.tags:
                score += 25.0

            # 6. Penalta' per formule troppo corte (meno di 100 char) se la query sembra complessa
            if entry.lunghezza < 100 and len(parole_chiave) > 4:
                score *= 0.3

            # 7. Penalta' per formule di inizializzazione semplice se la query menziona logica
            if entry.numero in (1000, 1010) and any(w in parole_chiave for w in ["calcolo", "accumulo", "straordinario"]):
                score *= 0.2

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: -x[0])
        results = [e for _, e in scored[:top_k]]
        _logger.debug("Few-shot retrieval: query=%s, top=%d risultati", query[:60], len(results))
        return results

    def format_few_shot_section(self, query: str, top_k: int = 3) -> str:
        """Formatta le formule trovate come sezione few-shot per il prompt."""
        entries = self.search(query, top_k=top_k)
        if not entries:
            return ""

        lines = []
        lines.append("### ESEMPI REALI DI FORMULE WinSarp IN PRODUZIONE ###")
        lines.append("Usa questi esempi come riferimento strutturale per la formula da generare.\n")

        for i, e in enumerate(entries, 1):
            lines.append(f"--- ESEMPIO REALE {i} (Formula #{e.numero}: {e.scopoSuggerito}) ---")
            if e.r_calls:
                lines.append(f"[Richiama: R{' R'.join(str(x) for x in e.r_calls)}]")
            if e.p_calls:
                lines.append(f"[Procedure: P{' P'.join(str(x) for x in e.p_calls)}]")
            if e.k_register:
                lines.append(f"[Accumuli K: {' '.join(sorted(e.k_register))}]")
            lines.append(e.body.strip())
            lines.append("")  # blank line

        return "\n".join(lines)

    def get_by_numero(self, num: int) -> Optional[FormulaUsoEntry]:
        if not self._loaded:
            self.load()
        return self.entries.get(num)
