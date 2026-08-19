"""
Test isolato per OpenRouter - non modifica codice esistente.
Verifica connessione, generazione formule e fallback.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importa config per triggerare load_dotenv() e ottenere cfg
from config import cfg

def main():
    ok = failed = 0

    print("="*60)
    print("TEST OPENROUTER - ERMES")
    print("="*60)

    key = (os.environ.get("OPENROUTER_API_KEY", "")
           or cfg.OPENROUTER_API_KEY)
    base_url = (os.environ.get("OPENROUTER_BASE_URL", "")
                or cfg.OPENROUTER_BASE_URL)
    has_key = bool(key and key.strip())

    print(f"\nAPI Key configurata: {'Si' if has_key else 'No'}")
    if not has_key:
        print("  -> Imposta OPENROUTER_API_KEY in .env")
        print(f"  .env: {os.path.join(os.path.dirname(__file__), '.env')}")
        failed += 1
    else:
        ok += 1

    # --- TEST: Chiamata HTTP diretta ---
    if has_key:
        print("\n--- TEST: Chiamata HTTP diretta a OpenRouter ---")
        import urllib.request, urllib.error
        url = base_url.rstrip("/") + "/chat/completions"
        body = json.dumps({
            "model": "tencent/hy3:free",
            "messages": [{"role": "user", "content": "Ciao"}],
            "max_tokens": 10,
        }).encode()
        req = urllib.request.Request(url, data=body,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            content = data["choices"][0]["message"].get("content") or data["choices"][0]["message"].get("reasoning", "")
            print(f"  Risposta: {content[:100]}")
            ok += 1
        except Exception as e:
            print(f"  ERRORE: {e}")
            failed += 1

    # --- TEST: Generazione formula via formula_builder ---
    if has_key:
        print("\n--- TEST: Generazione formula via formula_builder ---")
        from legacy_winsarp.core.formula_builder import WinSarpBuilder
        from legacy_winsarp.core.winsarp.formula_patterns import PATTERNS, fill_template
        from legacy_winsarp.core.winsarp.rule_engine import _extract_params

        pat = PATTERNS.get("fg_split_festivo")
        if pat:
            params = _extract_params("straordinario festivo 130", pat)
            ir = fill_template(pat, params)
            builder = WinSarpBuilder()
            compact = builder.build_compact(ir)
            print(f"  Formula 130 generata ({len(compact)} chars):")
            for line in compact.split("\n")[:6]:
                print(f"    {line}")
            ok += 1
        else:
            print("  Pattern fg_split_festivo non trovato")
            failed += 1

    # --- RIEPILOGO ---
    print(f"\n{'='*60}")
    print(f"OK: {ok}  |  FAILED: {failed}")
    if failed == 0:
        print("TUTTI I TEST PASSATI - OpenRouter pronto")
    else:
        print("QUALCHE TEST FALLITO - Verificare")
    print('='*60)
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
