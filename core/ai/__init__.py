"""AI/LLM infrastructure — bridge LLM, embedding, caching, RAG.

Moduli:
    utils               → Chiamate LLM centralizzate (OpenRouter/Ollama)
    llm_bridge          → Factory LLM (OpenRouterLLM, Ollama)
    semantic_cache      → Cache semantica per risposte LLM
    memory              → Memoria conversazionale
    response_cache      → Cache risposte HTTP
    chain_of_thought    → Generazione CoT per formule
"""
