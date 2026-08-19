"""
Modulo validatore: la 'Dogana' per il sintetizzatore di formule.
Questo modulo definisce lo schema della SpecificaFormula che l'LLM deve compilare
e implementa le regole di validazione deterministiche per garantire
che nessuna formula generata violi i vincoli di sicurezza del sistema.
"""

from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Optional, Set
from enum import Enum

class BloccoEsecuzione(str, Enum):
    INIZIO_GIORNATA = "IG"
    DI_GIORNATA = "DG"
    FINE_GIORNATA = "FG"
    SUBROUTINE = "SUB"

# REGISTRI_BLOCCATI_SISTEMA: Registri critici di sistema che l'LLM non deve mai scrivere.
# Derivato dall'analisi statica dei pattern di WinSarp esistenti.
REGISTRI_BLOCCATI_SISTEMA: Set[int] = {
    # Flag di sistema critici (semafori e diagnostici)
    70, 900,
    # Registri di Sincronizzazione a basso livello
    1, 2, 3, 4, 5,
    # Registri di sistema usati nel flusso standard IG/DG/FG
    58, 100, 111, 112, 141, 142
}

class CondizioneAzione(BaseModel):
    condizione: Optional[str] = Field(
        None,
        description="Condizione logica (es. '70 > 170'). null = else/catch-all (nessuna condizione)."
    )
    azioni: Dict[int, str] = Field(
        ...,
        description="Mappa campo_output → valore WinSarp per questa condizione. "
                    "Es: {'99': \"'50'\", '85': \"'NOTT'\"}. Valori costanti tra apici singoli."
    )

class SpecificaFormula(BaseModel):
    # 4. Meta-informazioni e Posizionamento
    scopo_formula: str = Field(..., description="Breve descrizione di cosa deve fare la formula")
    fase_esecuzione: BloccoEsecuzione = Field(
        ...,
        description="Fase del flusso in cui risiede la formula (IG, DG, FG o Subroutine)"
    )

    # 1. Analisi Logica
    logica_passo_passo: str = Field(..., description="Spiegazione in italiano semplice della logica")

    # 2. Gestione Registri
    campi_input: List[int] = Field(..., description="Lista dei campi che la formula deve leggere")
    campi_output: List[int] = Field(default=[], description="Lista dei campi che la formula deve scrivere")

    # Gestione Flag di Stato e Anti-Loop
    campi_state_flag: List[int] = Field(
        default=[],
        description="Registri usati come flag di controllo (es: Campo 900 per bloccare i loop)"
    )

    # 3. Elementi Tecnici
    causali_richieste: List[str] = Field(default=[], description="Eventuali causali testuali (es: 'NOTT')")
    flag_attivazione: Optional[str] = Field(None, description="Eventuali flag (es: 'I', 'Z') da settare")
    soglie_condizionali: List[str] = Field(default=[], description="Condizioni logiche (es: '> 400', '<= 15')")

    # Condizioni Temporali / Storiche
    validita_temporale: Optional[str] = Field(
        None,
        description="Eventuali vincoli di data per l'applicazione (es: '>= 01/06/2023')"
    )

    # Mappatura output → valori letterali
    valori_output: Dict[int, str] = Field(
        default={},
        description="Mappa campo_output → valore WinSarp (es: {99: \"'50'\", 85: \"'NOTT'\"}). Valori letterali vanno tra apici ('valore')."
    )

    # Multi-condizione: sostituisce soglie_condizionali + campi_output + valori_output
    condizioni_azioni: List[CondizioneAzione] = Field(
        default=[],
        description="Lista ordinata di (condizione, azioni). Se popolata, sostituisce "
                    "soglie_condizionali, campi_output e valori_output."
    )

    def _campi_output_aggregati(self) -> List[int]:
        """Restituisce tutti i campi output da qualsiasi fonte."""
        if self.condizioni_azioni:
            campi = set()
            for ca in self.condizioni_azioni:
                campi.update(ca.azioni.keys())
            return sorted(campi)
        return self.campi_output

    @model_validator(mode="after")
    def esegui_controlli_dogana(self) -> "SpecificaFormula":
        # Determine which output path is active
        using_cond_azioni = bool(self.condizioni_azioni)

        if using_cond_azioni:
            # --- Path multi-condizione ---
            if not any(ca.azioni for ca in self.condizioni_azioni):
                if self.fase_esecuzione != BloccoEsecuzione.SUBROUTINE:
                    raise ValueError(
                        "LOGIC ERROR: condizioni_azioni deve avere almeno una condizione con azioni non vuote."
                    )
            all_campi = self._campi_output_aggregati()
            for campo in all_campi:
                if campo in REGISTRI_BLOCCATI_SISTEMA:
                    raise ValueError(
                        f"CRITICAL ERROR: Tentativo di sovrascrittura del registro protetto {campo}. "
                        f"La formula per '{self.scopo_formula}' è stata bloccata."
                    )
        else:
            # --- Path legacy (campi_output + valori_output) ---
            # 0. Controllo coerenza valori_output con campi_output
            for campo in self.valori_output:
                if campo not in self.campi_output:
                    raise ValueError(
                        f"LOGIC ERROR: Il campo {campo} in valori_output non è dichiarato in campi_output."
                    )
            for campo in self.campi_output:
                if campo not in self.valori_output:
                    raise ValueError(
                        f"LOGIC ERROR: Il campo {campo} in campi_output non ha un valore in valori_output."
                    )
            # 1. Controllo Collisioni di Memoria
            for campo in self.campi_output:
                if campo in REGISTRI_BLOCCATI_SISTEMA:
                    raise ValueError(
                        f"CRITICAL ERROR: Tentativo di sovrascrittura del registro protetto {campo}. "
                        f"La formula per '{self.scopo_formula}' è stata bloccata."
                    )

            # 2. Controllo Coerenza Logica (Input vs Output)
            if not self.campi_output and self.fase_esecuzione != BloccoEsecuzione.SUBROUTINE:
                raise ValueError(
                    "LOGIC ERROR: Una formula in fase DG/FG deve scrivere almeno in un campo_output."
                )

            # 3. Controllo di Coerenza delle Soglie
            if "pausa" in self.scopo_formula.lower() and not self.soglie_condizionali:
                raise ValueError(
                    "SINTAX ERROR: Rilevata logica a scaglioni senza soglie_condizionali dichiarate."
                )

        return self
