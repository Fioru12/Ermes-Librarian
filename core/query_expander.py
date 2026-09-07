"""
core/query_expander.py
Enterprise Query Expansion and Synonym Disambiguation.
Expands business terminology, Italian labor/corporate acronyms, and common synonyms
to maximize recall in BM25/FTS5 and dense semantic search.
"""
from __future__ import annotations

import re

# Glossario di sinonimi e acronimi aziendali frequenti (italiano/inglese aziendale)
ENTERPRISE_SYNONYMS: dict[str, list[str]] = {
    "tfr": ["trattamento fine rapporto", "liquidazione"],
    "ccnl": ["contratto collettivo nazionale", "accordo nazionale lavoro"],
    "cedolino": ["busta paga", "prospetto paga", "retribuzione"],
    "busta paga": ["cedolino", "prospetto paga", "stipendio"],
    "malattia": ["certificato medico", "inps malattia", "visita fiscale", "prognosi"],
    "certificato medico": ["malattia", "inps", "assenza medica"],
    "smart working": ["lavoro agile", "lavoro da remoto", "telelavoro", "lavoro a distanza"],
    "lavoro agile": ["smart working", "telelavoro", "lavoro da remoto"],
    "ferie": ["piano ferie", "giorni di congedo", "riposo annuale"],
    "permessi": ["rol", "riduzione orario lavoro", "permessi retribuiti", "ex festivita"],
    "rol": ["riduzione orario lavoro", "permessi retribuiti"],
    "maternita": ["congedo parentale", "congedo maternita", "astensione obbligatoria"],
    "paternita": ["congedo paternita", "congedo parentale"],
    "straordinario": ["lavoro straordinario", "ore eccedenti", "maggiorazione"],
    "dimissioni": ["recesso contratto", "risoluzione rapporto", "preavviso dimissioni"],
    "preavviso": ["termini di preavviso", "indennita mancato preavviso"],
    "infortunio": ["inail", "infortunio sul lavoro", "denuncia infortunio"],
    "badge": ["marcatempo", "timbratura", "cartellino presenze", "rilevazione presenze"],
    "timbratura": ["badge", "marcatempo", "rilevazione presenze"],
    "rimborso spese": ["nota spese", "trasferta", "giustificativi spesa", "diaria"],
    "trasferta": ["rimborso spese", "missione", "indennita trasferta"],
    "vpn": ["accesso remoto", "connessione protetta", "rete aziendale"],
    "wifi": ["rete wireless", "connessione ospiti", "accesso internet"],
    "gdpr": ["privacy", "trattamento dati personali", "dpo", "informativa privacy"],
    "dpo": ["responsabile protezione dati", "data protection officer", "gdpr"],
    "sicurezza": ["dvr", "documento valutazione rischi", "rspp", "dispositivi protezione"],
    "dvr": ["documento valutazione rischi", "sicurezza sul lavoro", "testo unico 81"],
    "formazione": ["corsi obbligatori", "piano formativo", "crediti formativi"],
}


def expand_query(query: str, max_expansions: int = 3) -> list[str]:
    """
    Data una query utente, genera varianti di ricerca arricchite
    con sinonimi aziendali e acronimi espansi.

    Restituisce una lista di stringhe di ricerca (la prima e' sempre la query originale).
    """
    cleaned = query.strip()
    if not cleaned:
        return [query]

    expanded_terms: list[str] = []
    lowered = cleaned.lower()

    # 1. Ricerca corrispondenze esatte nel glossario
    for term, syns in ENTERPRISE_SYNONYMS.items():
        # Match intera parola
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, lowered):
            for s in syns[:2]:
                if s not in lowered and s not in expanded_terms:
                    expanded_terms.append(s)

    results = [cleaned]
    if expanded_terms:
        # Aggiunge una variante con OR logico per FTS5 o frase combinata
        combined = f"{cleaned} " + " ".join(expanded_terms[:max_expansions])
        results.append(combined.strip())

    return results
