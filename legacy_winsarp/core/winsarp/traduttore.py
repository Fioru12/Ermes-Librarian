"""
Adapter: traduce la SpecificaFormula (richiesta utente) in Steps (logica intermedia).
"""
from typing import List
from legacy_winsarp.core.winsarp.validatore import SpecificaFormula, BloccoEsecuzione

def traduci_specifica_in_step(specifica: SpecificaFormula) -> List[str]:
    """Converte una specifica validata in una lista di step per il FormulaBuilder."""
    steps = []

    # 1. Setup iniziale
    if specifica.fase_esecuzione == BloccoEsecuzione.INIZIO_GIORNATA:
        steps.append("RESET 900")

    # 2. Traduzione Logica
    steps.append(f"# {specifica.scopo_formula}")

    if specifica.condizioni_azioni:
        # --- Path multi-condizione ---
        open_ifs = 0
        for i, ca in enumerate(specifica.condizioni_azioni):
            if i > 0:
                steps.append("ELSE")
            if ca.condizione is not None:
                steps.append(f"IF {ca.condizione} THEN")
                open_ifs += 1
            for campo in sorted(ca.azioni.keys()):
                steps.append(f"SET {campo} = {ca.azioni[campo]}")
        for _ in range(open_ifs):
            steps.append("ENDIF")
    else:
        # --- Path legacy (soglie_condizionali + campi_output + valori_output) ---
        n_cond = len(specifica.soglie_condizionali)

        if n_cond == 0:
            # Nessuna condizione: SET diretti
            for campo in specifica.campi_output:
                valore = specifica.valori_output.get(campo, "...")
                steps.append(f"SET {campo} = {valore}")

        elif n_cond == 1:
            # Condizione singola: IF/THEN/ENDIF
            steps.append(f"IF {specifica.soglie_condizionali[0]} THEN")
            for campo in specifica.campi_output:
                valore = specifica.valori_output.get(campo, "...")
                steps.append(f"SET {campo} = {valore}")
            steps.append("ENDIF")

        else:
            # Condizioni multiple: IF/ELSE/IF/ENDIF annidati
            steps.append(f"IF {specifica.soglie_condizionali[0]} THEN")
            for campo in specifica.campi_output:
                valore = specifica.valori_output.get(campo, "...")
                steps.append(f"SET {campo} = {valore}")
            for soglia in specifica.soglie_condizionali[1:]:
                steps.append("ELSE")
                steps.append(f"IF {soglia} THEN")
                for campo in specifica.campi_output:
                    valore = specifica.valori_output.get(campo, "...")
                    steps.append(f"SET {campo} = {valore}")
            for _ in specifica.soglie_condizionali:
                steps.append("ENDIF")

    # 3. Chiusura
    steps.append("VF")

    return steps
