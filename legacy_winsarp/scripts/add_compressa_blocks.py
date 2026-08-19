"""Aggiunge blocchi **Formula compressa:** mancanti a WinSarp_Formule.txt e ricostruisce KG."""
import os, sys, re, json
sys.path.insert(0, os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"

from config import cfg

# === 1. Leggi codici compatti da FormuleWinsarp.txt ===
raw_path = os.path.join(cfg.DOCS_DIR, "WinSarp", "FormuleWinsarp.txt")
with open(raw_path, "r", encoding="utf-8") as f:
    raw_text = f.read()

# Estrai sezioni "formula N ..."
raw_sections = re.split(r"\n(?=formula\s+\d+)", raw_text)
compact_codes = {}
for sec in raw_sections:
    sec = sec.strip()
    if not sec:
        continue
    m = re.match(r"formula\s+(\d+)", sec)
    if m:
        fid = int(m.group(1))
        # Il codice è tutto dopo la prima riga "formula N"
        lines = sec.splitlines()
        code_lines = []
        for line in lines[1:]:
            stripped = line.strip()
            if stripped and not stripped.startswith("formula "):
                code_lines.append(line.rstrip())
        code = "\n".join(code_lines).strip()
        if code:
            compact_codes[fid] = code

print(f"Codici estratti da FormuleWinsarp.txt: {len(compact_codes)} formule")
print(f"IDs: {sorted(compact_codes.keys())}")

# === 2. Leggi WinSarp_Formule.txt ===
ws_path = os.path.join(cfg.DOCS_DIR, "WinSarp", "WinSarp_Formule.txt")
with open(ws_path, "r", encoding="utf-8") as f:
    ws_text = f.read()

# === 3. Trova sezioni formula che NON hanno **Formula compressa:** ===
# Dividi per sezioni (---)
sections = [sec.strip() for sec in re.split(r"\n---\n", ws_text) if sec.strip()]

updates = 0
new_sections = []
for sec in sections:
    lines = sec.splitlines()
    # Trova heading formula
    heading = None
    for ln in lines:
        m = re.match(r'^### <a name="(\d+)">', ln)
        if m:
            heading = int(m.group(1))
            break
    
    has_compressa = any("**Formula compressa:**" in ln for ln in lines)
    
    if heading and not has_compressa and heading in compact_codes:
        # Aggiungi **Formula compressa:** prima della sezione di spiegazione
        # Cerca la fine della sezione scopo o della tabella logica
        code = compact_codes[heading]
        code_block = f"\n**Formula compressa:**\n```\n{code}\n```"
        
        # Inserisci dopo **Scopo:** o **Logica principale:** o dopo la tabella
        insert_after = -1
        for i, ln in enumerate(lines):
            if ln.startswith("**Logica principale:**") or ln.startswith("**Struttura:**"):
                insert_after = i
                # Trova la fine della tabella (prossima riga vuota o ---)
                for j in range(i+1, len(lines)):
                    if lines[j].strip() == "" or lines[j].startswith("---"):
                        insert_after = j
                        break
                break
        
        if insert_after < 0:
            # Inserisci dopo l'ultima riga di **Scopo:**
            for i, ln in enumerate(lines):
                if ln.startswith("**Scopo:**"):
                    insert_after = i
                    # Trova la fine del testo dello scopo
                    for j in range(i+1, len(lines)):
                        if not lines[j].strip() or lines[j].startswith("**") or lines[j].startswith("##") or lines[j].startswith("###"):
                            insert_after = j
                            break
                    break
        
        if insert_after >= 0:
            new_lines = lines[:insert_after+1] + [code_block] + lines[insert_after+1:]
            sec = "\n".join(new_lines)
            updates += 1
            print(f"  Aggiunto Formula compressa per F{heading} ({len(code)} chars)")
        else:
            print(f"  ATTENZIONE: F{heading} - non trovo dove inserire")
            sec = lines[0] + code_block + "\n" + "\n".join(lines[1:])
            updates += 1
    
    new_sections.append(sec)

print(f"\nAggiornate: {updates} formule")

# === 4. Ricostruisci il file ===
new_text = "\n---\n".join(new_sections)

# Backup del file originale
import shutil
backup = ws_path + ".bak"
if not os.path.exists(backup):
    shutil.copy2(ws_path, backup)
    print(f"Backup creato: {backup}")

# Scrivi nuovo file
with open(ws_path, "w", encoding="utf-8") as f:
    f.write(new_text)
print(f"File aggiornato: {ws_path}")

# === 5. Ricostruisci catalogo JSON ===
from pathlib import Path
from legacy_winsarp.core.winsarp.catalog import parse_catalog_text, save_catalog_json, CATALOGO_JSON_PATH
catalog = save_catalog_json(source_path=Path(ws_path))
print(f"\nCatalogo JSON salvato: {len(catalog)} formule")
missing = [f for f in sorted(compact_codes.keys()) if f not in [c["id"] for c in catalog]]
print(f"Ancora mancanti dal parser: {missing}")

# === 6. Ricostruisci Knowledge Graph ===
from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph, save_graph
kg = KnowledgeGraph()
kg.build_graph(catalog)
save_graph(kg.to_dict())
print(f"KG ricostruito: {len(kg.formulas)} nodi")
