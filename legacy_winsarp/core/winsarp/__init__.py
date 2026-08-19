"""WinSarp domain logic — deterministica, senza dipendenze AI/LLM.

Moduli:
    catalog             → Parsing catalogo formule WinSarp
    transformer         → Trasformatore Lark IR → formula compatta
    linter              → Linter formule WinSarp
    validatore          → Validatore semantico formule
    traduttore          → Traduttore specifica → step
    patterns            → Pattern formula (IG, DG, FG, Sub)
    knowledge_graph     → Grafo conoscenza formule
    formula_graph       → Grafo dipendenze tra formule
    field_registry      → Registro campi WinSarp
    table_registry      → Registro tabelle/causali
    profile_registry    → Rilevamento profilo formula
    glossary            → Glossario semantico WinSarp
    workbook_retriever  → Retriever formule da workbook
    chunker             → Chunker semantico per formule
    pattern_learner     → Apprendimento pattern (legacy)
    pattern_learner_real → Apprendimento pattern (produzione)
    validator           → Validatore sintattico Lark
    rule_engine         → Generazione deterministica formule da richieste utente
    formula_patterns    → Enciclopedia strutturata dei pattern formula WinSarp
"""
