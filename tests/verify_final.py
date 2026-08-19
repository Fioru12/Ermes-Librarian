import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

def test_verify_final_behavior():
    print("\n--- TEST DI VERIFICA FINALE ---")
    
    # 1. Test Reset Rapido
    res1 = client.post("/api/formula/generate", json={"query": "azzera i campi 900 e 901", "module": "WinSarp"})
    data1 = res1.json()
    assert res1.status_code == 200
    assert data1["formula"] == "!900!901"
    print(f"✅ Reset Rapido: {data1['formula']} (Sorgente: {data1['source']})")

    # 2. Test Complesso (Catalog Retrieval)
    res2 = client.post("/api/formula/generate", json={"query": "calcola straordinario festivo notturno", "module": "WinSarp"})
    data2 = res2.json()
    assert res2.status_code == 200
    assert data2["source"] == "catalog"
    assert "formula" in data2
    print(f"✅ Complesso: {data2['name']} - ID: {data2['formula_id']} (Sorgente: {data2['source']})")
    
    print("--- VERIFICA COMPLETATA CON SUCCESSO ---\n")
