import sys; sys.path.insert(0, ".")
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
import time, logging
logging.basicConfig(level=logging.WARNING)

from legacy_winsarp.core.rag_engine import build_chat_engine, get_index, init_llama_settings
init_llama_settings()
from legacy_winsarp.core.agent_runner import AgentRunner
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph

mod = "WinSarp"
model = "qwen3:8b" # Usiamo il nuovo modello

print("=== SMOKE TEST E2E: AVVIO... ===", flush=True)
idx = get_index(mod, model, "documenti", "chroma_db", "documenti/hash.json")
kg = KnowledgeGraph()

# 1. TEST RICERCA
print("\n--- 1. TEST RICERCA (CONSULTA CATALOGO) ---", flush=True)
engine = build_chat_engine(mod, model, idx, use_generation_prompt=False)
resp = engine.stream_chat("Cerca la formula per lo straordinario festivo")
print(f"Risposta: {str(resp)[:300]}...", flush=True)

# 2. TEST ANALISI
print("\n--- 2. TEST ANALISI (GRAFO FORMULE) ---", flush=True)
runner = AgentRunner(kg)
res = runner.analyze("Quali formule chiama la 130?", model)
print(f"Risposta: {res['response']}", flush=True)

# 3. TEST GENERAZIONE
print("\n--- 3. TEST GENERAZIONE (BOZZA AI) ---", flush=True)
engine2 = build_chat_engine(mod, model, idx, use_generation_prompt=True)
resp2 = engine2.stream_chat("Vorrei una formula per calcolare un bonus produzione del 10% sulle ore lavorate")
full_resp = ""
for tok in resp2.response_gen:
    full_resp += tok
print(f"Risposta: {full_resp[:500]}...", flush=True)
