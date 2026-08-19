"""
test_quality.py
Test di qualità per le risposte RAG.
Valuta l'accuratezza del sistema su un set di domande campione.
Usa metriche oggettive per misurare:
- Tasso di risposta corretta
- Tasso di fallback corretto (quando non trova)
- Tasso di confidenza appropriata
- Velocità media di risposta

Usage:
    pytest tests/test_quality.py -v
    python tests/test_quality.py  # esecuzione diretta
"""
import json
import os
import sys
import time
from pathlib import Path

# Aggiungi root progetto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import cfg
from legacy_winsarp.core.rag_engine import (
    build_chat_engine,
    check_ollama,
    get_index,
    get_source_nodes,
    init_llama_settings,
    score_to_confidence,
)
from legacy_winsarp.modules.winsarp import FALLBACK_PHRASES, clean_code, validate_winsarp

# ============================================================
# DATASET DI TEST — domande campione con risposte attese
# ============================================================
TEST_CASES = {
    "WinSarp": [
        {
            "query": "Dammi la formula per straordinario oltre 8 ore con causale ST",
            "expected": {
                "has_formula": True,  # deve trovare una formula
                "min_confidence": "media",  # confidenza almeno media
                "valid_winsarp": True,  # sintassi valida
            },
            "id": "straordinario_8h_st",
        },
        {
            "query": "Qual è la formula per calcolare il turno notturno?",
            "expected": {
                "has_formula": True,
                "min_confidence": "media",
                "valid_winsarp": True,
            },
            "id": "turno_notturno",
        },
        {
            "query": "Formula per arrotondamento entrata e uscita a quarti d'ora",
            "expected": {
                "has_formula": True,
                "min_confidence": "media",
                "valid_winsarp": True,
            },
            "id": "arrotondamento_quarti",
        },
        {
            "query": "Formula per gestione festività e weekend",
            "expected": {
                "has_formula": True,
                "min_confidence": "media",
                "valid_winsarp": True,
            },
            "id": "festivita_weekend",
        },
        {
            "query": "Qual è la formula per calcolare la pensione anticipata?",
            "expected": {
                "has_formula": False,  # non dovrebbe esistere nel catalogo WinSarp
                "is_fallback": True,  # dovrebbe rispondere con fallback
            },
            "id": "pensione_anticipata",
        },
        {
            "query": "Mostrami la formula per la gestione dei permessi non retribuiti",
            "expected": {
                "has_formula": True,
                "min_confidence": "media",
                "valid_winsarp": True,
            },
            "id": "permessi_non_retribuiti",
        },
        {
            "query": "Formula per calcolare il rateo orario da mensile",
            "expected": {
                "has_formula": True,
                "min_confidence": "bassa",
            },
            "id": "rateo_orario",
        },
    ]
}


# ============================================================
# METRICHE DI QUALITÀ
# ============================================================
class QualityMetrics:
    """Raccoglie e calcola le metriche di qualità delle risposte."""

    def __init__(self):
        self.total = 0
        self.formula_found = 0
        self.high_confidence = 0
        self.medium_confidence = 0
        self.low_confidence = 0
        self.correct_fallback = 0
        self.valid_syntax = 0
        self.invalid_syntax = 0
        self.errors = 0
        self.times = []

    def add_result(self, test_id: str, test_case: dict, result: dict):
        """Aggiunge il risultato di un test case alle metriche."""
        self.total += 1
        elapsed = result.get("elapsed", 0)
        self.times.append(elapsed)

        expected = test_case["expected"]
        has_formula = result.get("has_formula", False)
        is_fallback = result.get("is_fallback", False)
        confidence = result.get("confidence", "bassa")
        code = result.get("code", "")
        errors = result.get("errors", [])

        # Controlla se la formula è stata trovata (corretto)
        if expected.get("has_formula", False) and has_formula:
            self.formula_found += 1
        elif not expected.get("has_formula", True) and is_fallback:
            self.correct_fallback += 1
        elif expected.get("is_fallback", False) and is_fallback:
            self.correct_fallback += 1

        # Confidenza
        if confidence == "alta":
            self.high_confidence += 1
        elif confidence == "media":
            self.medium_confidence += 1
        else:
            self.low_confidence += 1

        # Sintassi
        if has_formula and code:
            if not errors:
                self.valid_syntax += 1
            else:
                self.invalid_syntax += 1
                result["syntax_errors"] = errors

        if errors:
            self.errors += 1

    @property
    def formula_success_rate(self) -> float:
        """Percentuale di formule trovate correttamente."""
        if self.total == 0:
            return 0.0
        return (self.formula_found + self.correct_fallback) / self.total * 100

    @property
    def avg_time(self) -> float:
        """Tempo medio di risposta."""
        if not self.times:
            return 0.0
        return sum(self.times) / len(self.times)

    @property
    def syntax_accuracy(self) -> float:
        """Percentuale di formule con sintassi valida."""
        total_formulas = self.valid_syntax + self.invalid_syntax
        if total_formulas == 0:
            return 0.0
        return self.valid_syntax / total_formulas * 100

    def to_dict(self) -> dict:
        return {
            "total_tests": self.total,
            "formula_found": self.formula_found,
            "correct_fallback": self.correct_fallback,
            "formula_success_rate_pct": round(self.formula_success_rate, 1),
            "high_confidence": self.high_confidence,
            "medium_confidence": self.medium_confidence,
            "low_confidence": self.low_confidence,
            "valid_syntax": self.valid_syntax,
            "invalid_syntax": self.invalid_syntax,
            "syntax_accuracy_pct": round(self.syntax_accuracy, 1),
            "avg_response_time_s": round(self.avg_time, 2),
            "total_errors": self.errors,
        }

    def print_report(self):
        """Stampa un report formattato delle metriche."""
        print("\n" + "=" * 50)
        print("   REPORT QUALITÀ RISPOSTE RAG")
        print("=" * 50)
        print(f"  Totale test:             {self.total}")
        print(f"  Formule trovate:         {self.formula_found}")
        print(f"  Fallback corretti:       {self.correct_fallback}")
        print(f"  Tasso successo:          {self.formula_success_rate:.1f}%")
        print(f"  Confidenza alta:         {self.high_confidence}")
        print(f"  Confidenza media:        {self.medium_confidence}")
        print(f"  Confidenza bassa:        {self.low_confidence}")
        print(f"  Sintassi valida:         {self.valid_syntax}")
        print(f"  Sintassi invalida:       {self.invalid_syntax}")
        print(f"  Accuratezza sintassi:    {self.syntax_accuracy:.1f}%")
        print(f"  Tempo medio risposta:    {self.avg_time:.2f}s")
        print(f"  Errori totali:           {self.errors}")
        print("=" * 50)


def is_fallback_response(text: str) -> bool:
    """Verifica se la risposta è un fallback 'non trovato'."""
    low = text.lower()
    return any(p.lower() in low for p in FALLBACK_PHRASES)


def evaluate_confidence(sources: list) -> str:
    """Determina il livello di confidenza dai source nodes."""
    if not sources:
        return "bassa"
    top_score = max((s.get("score", 0.0) for s in sources), default=0.0)
    return score_to_confidence(top_score)


def run_quality_test(module_name: str = "WinSarp", test_ids: list = None) -> QualityMetrics:
    """
    Esegue il test di qualità su un modulo specifico.

    Args:
        module_name: nome del modulo da testare
        test_ids: lista di ID test da eseguire (None = tutti)

    Returns:
        QualityMetrics con i risultati
    """
    metrics = QualityMetrics()
    test_cases = TEST_CASES.get(module_name, [])
    if not test_cases:
        print(f"❌ Nessun test case trovato per modulo '{module_name}'")
        return metrics

    if test_ids:
        test_cases = [tc for tc in test_cases if tc["id"] in test_ids]

    # Inizializza LlamaIndex
    init_llama_settings()

    # Verifica Ollama con timeout breve
    try:
        ollama_ok, ollama_msg = check_ollama(cfg.DEFAULT_MODEL_ID)
    except Exception as e:
        print(f"❌ Ollama non raggiungibile: {e}")
        return metrics
    if not ollama_ok:
        print(f"❌ Ollama non disponibile: {ollama_msg}")
        print("⚠️  I test di qualità richiedono Ollama in esecuzione.")
        print("   Esegui 'ollama serve' e riprova.")
        return metrics

    # Carica indice
    print(f"\n📂 Caricamento indice per modulo '{module_name}'...")
    index = get_index(
        module_name,
        cfg.DEFAULT_MODEL_ID,
        cfg.DOCS_DIR,
        cfg.CHROMA_DIR,
        cfg.HASH_FILE,
        cache_buster="quality_test",
    )

    if index is None:
        print(f"❌ Impossibile caricare indice per '{module_name}'")
        return metrics

    # Costruisci chat engine
    chat_engine = build_chat_engine(module_name, cfg.DEFAULT_MODEL_ID, index)

    print(f"\n🧪 Esecuzione {len(test_cases)} test per '{module_name}'...")
    print("-" * 50)

    for tc in test_cases:
        query = tc["query"]
        test_id = tc["id"]
        print(f"\n  [{test_id}] Query: {query[:60]}...")

        try:
            t_start = time.time()
            response = chat_engine.chat(query)
            t_elapsed = time.time() - t_start
            answer = response.response

            # Recupera fonti
            sources = get_source_nodes(module_name, cfg.DEFAULT_MODEL_ID, index, query)
            confidence = evaluate_confidence(sources)

            # Pulisci e valida
            code = clean_code(answer) if answer else ""
            is_fallback = is_fallback_response(answer)
            has_formula = bool(code and not is_fallback)
            errors = validate_winsarp(code) if code else []

            result = {
                "has_formula": has_formula,
                "is_fallback": is_fallback,
                "confidence": confidence,
                "code": code,
                "errors": errors,
                "elapsed": t_elapsed,
                "answer_preview": answer[:100] + ("..." if len(answer) > 100 else ""),
            }

            metrics.add_result(test_id, tc, result)

            # Stampa risultato
            status = "✅" if (
                (tc["expected"].get("has_formula", False) and has_formula) or
                (tc["expected"].get("is_fallback", False) and is_fallback)
            ) else "❌"
            print(f"  {status} Confidenza: {confidence} | Tempo: {t_elapsed:.1f}s")
            if errors:
                print(f"     ⚠️ Errori sintassi: {', '.join(errors[:2])}")

        except Exception as e:
            print(f"  ❌ Errore: {e}")
            metrics.errors += 1

    print("\n" + "-" * 50)
    return metrics


def export_metrics_to_json(metrics: QualityMetrics, filepath: str = "logs/quality_report.json"):
    """Esporta le metriche in un file JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": metrics.to_dict(),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n📊 Report salvato in: {filepath}")
    return data


# ============================================================
# MAIN
# ============================================================
def main():
    """Esecuzione diretta dello script di test qualità."""
    print("\n" + "=" * 50)
    print("   TEST DI QUALITÀ RISPOSTE RAG")
    print("=" * 50)

    # Esegui test per tutti i moduli disponibili
    from ui.sidebar_ui import list_modules
    moduli = list_modules(cfg.DOCS_DIR)

    if not moduli:
        print("❌ Nessun modulo trovato in /documenti")
        return

    overall_metrics = QualityMetrics()
    for modulo in moduli:
        if modulo in TEST_CASES:
            m = run_quality_test(modulo)
            # Aggrega metriche
            overall_metrics.total += m.total
            overall_metrics.formula_found += m.formula_found
            overall_metrics.correct_fallback += m.correct_fallback
            overall_metrics.high_confidence += m.high_confidence
            overall_metrics.medium_confidence += m.medium_confidence
            overall_metrics.low_confidence += m.low_confidence
            overall_metrics.valid_syntax += m.valid_syntax
            overall_metrics.invalid_syntax += m.invalid_syntax
            overall_metrics.errors += m.errors
            overall_metrics.times.extend(m.times)

    overall_metrics.print_report()
    export_metrics_to_json(overall_metrics)

    # Soglie di accettazione
    if overall_metrics.formula_success_rate >= 60.0:
        print("\n✅ SUPERATO: tasso di successo >= 60%")
    else:
        print(f"\n⚠️  ATTENZIONE: tasso di successo {overall_metrics.formula_success_rate:.1f}% < 60%")

    if overall_metrics.syntax_accuracy >= 70.0:
        print("✅ SUPERATO: accuratezza sintassi >= 70%")
    else:
        print(f"⚠️  ATTENZIONE: accuratezza sintassi {overall_metrics.syntax_accuracy:.1f}% < 70%")


if __name__ == "__main__":
    main()
