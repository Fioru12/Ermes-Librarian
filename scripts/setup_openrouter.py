"""
setup_openrouter.py
Setup rapido per configurare OpenRouter nel progetto Ermes.

Esempi modelli OpenRouter disponibili:
- deepseek/deepseek-chat        (default, ottimo rapporto qualità/prezzo)
- anthropic/claude-3.5-sonnet   (miglior ragionamento logico)
- openai/gpt-4o                 (comprensione naturale eccellente)
- google/gemini-pro             (buono per logiche complesse)
- meta-llama/llama-3.1-70b      (open source, molto potente)
"""

import sys
from pathlib import Path

def main():
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    print("=" * 60)
    print("OPENROUTER SETUP - Ermes Enterprise Knowledge Hub")
    print("=" * 60)
    print()
    
    # Mostra file .env esistente
    env_path = Path(__file__).parent.parent / ".env"
    env_example = Path(__file__).parent.parent / ".env.example"
    if env_path.exists():
        print(f"File .env esistente trovato")
        with open(env_path) as f:
            for line in f:
                if "OPENROUTER" in line:
                    print(f"  {line.strip()}")
    else:
        print("Nessun .env trovato. Copiando da .env.example...")
        if env_example.exists():
            import shutil
            shutil.copy(env_example, env_path)
            print("  .env creato!")
    
    print()
    print("PASSO 1: Ottieni la tua API key")
    print("  Vai su: https://openrouter.ai/keys")
    print("  Registra account e crea chiave API")
    print()
    
    print("PASSO 2: Aggiungi al .env")
    print("  OPENROUTER_API_KEY=sk-or-v1-...")
    print()
    
    print("PASSO 3: (Opzionale) Cambia modello")
    print("  Modifica DEFAULT_MODEL_ID nel .env:")
    print("    qwen3.5:9b  → deepseek/deepseek-chat (default)")
    print("    claude-sonnet → anthropic/claude-3.5-sonnet")
    print("    gpt-4o        → openai/gpt-4o")
    print()
    
    print("PASSO 4: Riavvia Ermes")
    print("  python launch.py")
    print()
    
    # Verifica se API key esiste
    from config import cfg
    if cfg.OPENROUTER_API_KEY:
        print("âœ… OPENROUTER_API_KEY già configurata!")
        from core.ai.llm_bridge import check_openrouter, _map_to_openrouter_model
        ok, msg = check_openrouter()
        print(f"  Status: {msg}")
        print(f"  Modello mappato: {cfg.DEFAULT_MODEL_ID} → {_map_to_openrouter_model(cfg.DEFAULT_MODEL_ID)}")
    else:
        print("âŒ OPENROUTER_API_KEY non configurata")
    
    print()
    print("=" * 60)

if __name__ == "__main__":
    main()