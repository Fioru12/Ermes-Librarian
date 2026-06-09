"""
Test di validazione su TUTTE le formule del catalogo ufficiale WinSarp.

Estrae ogni formula dal file WinSarp_Formule.txt e la valida con:
  1. auto_fix_formula → quante vengono modificate
  2. parse_response   → quante passano senza errori

Nessuna chiamata LLM, nessuna generazione — solo formule note corrette.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.winsarp import auto_fix_formula, parse_response

CATALOGO = Path(__file__).parent.parent / "documenti" / "WinSarp" / "WinSarp_Formule.txt"


def estrai_formule(testo: str) -> list[dict]:
    """Estrae tutte le formule dal catalogo markdown.
    Ogni formula ha: id, nome, tipo, testo_codice."""
    formule = []
    current = None

    for line in testo.splitlines():
        # Rileva intestazione formula: ### <a name="ID"></a>ID — Nome
        m = re.match(r'^###\s+<a\s+name="(\d+)"\s*></a>\s*\d+\s*[—–-]\s*(.+)$', line)
        if m:
            current = {"id": int(m.group(1)), "nome": m.group(2).strip(), "tipo": None, "codice": ""}
            formule.append(current)
            continue

        if current is None:
            continue

        # Rileva tipo
        m2 = re.match(r'\*\*Tipo:\*\*\s*(.+)$', line)
        if m2:
            current["tipo"] = m2.group(1).strip()

        # Rileva blocco codice (``` ... ```)
        if line.strip() == "```":
            if current.get("in_codice"):
                current["in_codice"] = False
            else:
                current["in_codice"] = True
            continue

        if current.get("in_codice"):
            current["codice"] += line.strip()

    # Filtra formule con codice non vuoto
    return [f for f in formule if f["codice"]]


def test_catalogo():
    testo = CATALOGO.read_text(encoding="utf-8")
    formule = estrai_formule(testo)
    print(f"Trovate {len(formule)} formule nel catalogo\n")

    risultati = []
    for f in formule:
        codice_originale = f["codice"]
        codice_fixato, fixes = auto_fix_formula(codice_originale)
        parsed = parse_response(codice_fixato, "WinSarp")
        errori = parsed.get("errors", [])
        ha_auto_fix = len(fixes) > 0
        passa_validazione = len(errori) == 0

        risultati.append({
            "id": f["id"],
            "nome": f["nome"],
            "tipo": f["tipo"],
            "ha_auto_fix": ha_auto_fix,
            "fixes": fixes,
            "passa_validazione": passa_validazione,
            "errori": errori,
            "codice": codice_originale,
        })

    # Metriche
    totale = len(risultati)
    passano = sum(1 for r in risultati if r["passa_validazione"])
    falliscono = totale - passano
    con_auto_fix = sum(1 for r in risultati if r["ha_auto_fix"])
    auto_fix_necessari = [r for r in risultati if r["ha_auto_fix"]]
    falliti = [r for r in risultati if not r["passa_validazione"]]

    print(f"TOTALE FORMULE:           {totale}")
    print(f"VALIDAZIONE OK:           {passano} ({passano/totale*100:.1f}%)")
    print(f"VALIDAZIONE FALLITA:      {falliscono} ({falliscono/totale*100:.1f}%)")
    print(f"AUTO-FIX APPLICATO:       {con_auto_fix} ({con_auto_fix/totale*100:.1f}%)")

    if auto_fix_necessari:
        print(f"\n--- FORMULE CON AUTO-FIX ({len(auto_fix_necessari)}) ---")
        for r in auto_fix_necessari:
            print(f"  #{r['id']} {r['nome']}: fixes={r['fixes']}")

    if falliti:
        print(f"\n--- FORMULE CHE FALLISCONO VALIDAZIONE ({len(falliti)}) ---")
        for r in falliti:
            print(f"  #{r['id']} {r['nome']}: errori={r['errori']}")
    else:
        print("\nTUTTE LE FORMULE DEL CATALOGO SUPERANO LA VALIDAZIONE")

    # Verdetto
    soglia = 90.0
    tasso = passano / totale * 100
    if tasso >= soglia:
        print(f"\nSUPERATO: tasso validazione {tasso:.1f}% >= {soglia}%")
    else:
        print(f"\nNON SUPERATO: tasso validazione {tasso:.1f}% < {soglia}%")

    return risultati


if __name__ == "__main__":
    test_catalogo()
