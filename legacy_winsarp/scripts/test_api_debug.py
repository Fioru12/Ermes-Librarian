import logging, sys
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format='%(name)s - %(levelname)s - %(message)s')

from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph
from legacy_winsarp.core.rag_engine import _ollama_url

kg = KnowledgeGraph()
b = FormulaBuilder(kg)
result = b.generate(
    "Genera una formula per azzerare i campi 800 e 801", 
    "qwen3.5:4b", 
    _ollama_url(), 
    900
)
print('RESULT:', result)