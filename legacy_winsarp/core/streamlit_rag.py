"""
streamlit_rag.py
Wrappers Streamlit per core/rag_engine.py.
Fornisce caching streamlit e UI calls per le funzioni RAG.
"""
import logging

import streamlit as st

from legacy_winsarp.core.rag_engine import check_ollama_uncached
from legacy_winsarp.core.rag_engine import get_index as _get_index_pure

_logger = logging.getLogger(__name__)


@st.cache_data(ttl=10)
def check_ollama(model_id: str) -> tuple[bool, str]:
    """
    Verifica che Ollama sia attivo e che i modelli necessari siano presenti.
    Cached 10 secondi per evitare subprocess ad ogni rerun.
    """
    return check_ollama_uncached(model_id)


@st.cache_resource(show_spinner=False)
def get_index(
    modulo: str,
    model_id: str,
    base_docs_dir: str,
    base_chroma_path: str,
    hash_file: str,
    cache_buster: str = "",
):
    """
    Carica o crea l'indice ChromaDB per il modulo specificato.
    Cached con st.cache_resource — usa cache_buster per invalidamento.

    Il parametro cache_buster invalida la cache quando il contenuto
    documentale cambia (es. hash directory modificato).
    """
    _ = (model_id, cache_buster)
    return _get_index_pure(
        modulo, model_id, base_docs_dir, base_chroma_path, hash_file,
    )
