"""AI/LLM infrastructure.

Moduli:
    utils        → call_llm centralizzato (Ollama locale, fallback OpenRouter)
    llm_bridge    → Mappatura modelli e controllo raggiungibilita' OpenRouter
    providers     → Registry dei provider cloud approvati (Anthropic, Google,
                    Ollama, OpenAI-compatibili)
"""
