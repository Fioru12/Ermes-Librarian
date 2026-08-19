import json
import logging
import math
import os
import re
from pathlib import Path

import httpx

from config import Config

_logger = logging.getLogger(__name__)
cfg = Config()

class SemanticCache:
    def __init__(self, cache_file: str = cfg.SEMANTIC_CACHE_FILE, similarity_threshold: float = 0.90):
        self.cache_file = cache_file
        self.similarity_threshold = similarity_threshold
        self.cache = self._load()

    def _load(self):
        if not os.path.exists(self.cache_file):
            return []
        try:
            with open(self.cache_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            _logger.error(f"Errore caricamento cache: {e}")
            return []

    def save(self):
        try:
            # Assicurati che la directory esista
            Path(self.cache_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            _logger.error(f"Errore salvataggio cache: {e}")

    @staticmethod
    def get_embedding(text: str) -> list[float]:
        try:
            url = cfg.OLLAMA_HOST
            if not url.startswith("http"):
                url = f"http://{url}"
            resp = httpx.post(
                f"{url}/api/embeddings",
                json={"model": cfg.EMBED_MODEL_ID, "prompt": text},
                timeout=60
            )
            if hasattr(resp, "raise_for_status"):
                resp.raise_for_status()
            return resp.json().get("embedding", [])
        except Exception as e:
            _logger.debug(f"Embedding non disponibile: {e}")
            return []

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm_v1 = math.sqrt(sum(a * a for a in v1))
        norm_v2 = math.sqrt(sum(b * b for b in v2))
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)

    @staticmethod
    def _extract_numbers(text: str) -> set:
        return set(re.findall(r'\b\d+\b', text))

    @staticmethod
    def _is_valid_response(response_data: dict) -> bool:
        """Valida che la risposta cachata non contenga pattern proibiti o sintassi rotta."""
        formula = response_data.get("formula", "") or ""
        raw = response_data.get("raw", "") or ""
        combined = formula + " " + raw

        # Pattern proibiti: label errate
        forbidden = ["V_START", "V_END", "V_SKIP", "V_DONE"]
        for pat in forbidden:
            if pat in combined:
                _logger.warning(f"Cache invalidato: contiene {pat}")
                return False

        # Mix di sintassi compatta e IR nello STESSO campo
        for field_name, field_val in [("formula", formula), ("raw", raw)]:
            if not field_val:
                continue
            has_compact = bool(re.search(r'\(\s*\d+\s*[=!<>]', field_val))
            has_ir_keywords = bool(re.search(r'\b(IF\s|THEN\s|ENDIF)\b', field_val))
            if has_compact and has_ir_keywords:
                _logger.warning(f"Cache invalidato: mix compatto+IR in {field_name}")
                return False
            # Nel campo formula, non devono comparire keyword IR
            if field_name == "formula":
                for kw in ("IF ", "THEN ", "ENDIF", "ELSE "):
                    if kw in field_val:
                        _logger.warning(f"Cache invalidato: keyword IR '{kw.strip()}' in formula")
                        return False

        # Sintassi gravemente rotta (virgolette non bilanciate per FIELD)
        for field_name, field_val in [("formula", formula), ("raw", raw)]:
            if not field_val:
                continue
            single_quotes = field_val.count("'")
            double_quotes = field_val.count('"')
            if single_quotes % 2 != 0:
                _logger.warning(f"Cache invalidato: apici singoli non bilanciati in {field_name}")
                return False
            if double_quotes % 2 != 0:
                _logger.warning(f"Cache invalidato: doppi apici non bilanciati in {field_name}")
                return False

        # Reset puro: la formula non deve contenere K, SET, IF, P, R, CAMPO70
        raw_lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
        is_pure_reset = all(
            ln.upper().startswith("RESET ") or ln.upper() in ("VF", "VU") or ln.startswith("#") or ln.startswith("//")
            for ln in raw_lines
        ) if raw_lines else False
        if is_pure_reset and re.search(r'\bK\d{1,4}\b', formula):
            _logger.warning("Cache invalidato: reset puro ma formula contiene K")
            return False

        return True

    def get(self, request_text: str, prompt_version: str | int = 0):
        embedding = self.get_embedding(request_text)
        if not embedding:
            return None

        best_match = None
        max_sim = 0.0

        for entry in self.cache:
            if entry.get("prompt_version") != prompt_version:
                continue
            sim = self.cosine_similarity(embedding, entry["embedding"])
            if sim > max_sim:
                max_sim = sim
                best_match = entry

        if max_sim >= self.similarity_threshold:
            # Controlla che i numeri nella richiesta corrispondano
            req_nums = self._extract_numbers(request_text)
            cached_nums = self._extract_numbers(best_match["request"])
            if req_nums and cached_nums and req_nums != cached_nums:
                _logger.debug(f"Cache scartato: numeri diversi {req_nums} vs {cached_nums}")
                return None
            # Valida la risposta prima di restituirla
            if not self._is_valid_response(best_match["response"]):
                _logger.warning("Cache hit ma risposta invalida, rimuovo entry")
                self.cache.remove(best_match)
                self.save()
                return None
            _logger.info(f"Cache hit: {max_sim:.4f}")
            return best_match["response"]

        return None

    def add(self, request_text: str, response_data: dict, prompt_version: str | int = 0):
        # Non cachare risposte invalide
        if not self._is_valid_response(response_data):
            _logger.warning("Risposta non cachata: non valida")
            return
        embedding = self.get_embedding(request_text)
        if not embedding:
            return

        self.cache.append({
            "request": request_text,
            "embedding": embedding,
            "response": response_data,
            "prompt_version": prompt_version,
        })
        self.save()
