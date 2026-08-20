# Glossario di Dominio WinSarp — Business Glossary Completo

> **Progetto:** Ermes Enterprise Knowledge Hub
> **Modulo:** WinSarp (Formule HR/Lavoro Dipendente)
> **Data:** 2026-07-07
> **Descrizione:** Estrazione completa e strutturata di tutta la terminologia di dominio presente nel codebase, organizzata per categorie.

---

## Indice

1. [CAMPI (Fields)](#1-campi-fields)
2. [TOTALI K (K-Totals)](#2-totali-k-k-totals)
3. [FORMULE (Formulas)](#3-formule-formulas)
4. [INTENT (Intents)](#4-intent-intents)
5. [CONTRATTI (Contracts)](#5-contratti-contracts)
6. [CATENE (Chains)](#6-catene-chains)
7. [SUBROUTINE (Subroutine Calls)](#7-subroutine-subroutine-calls)
8. [PATTERNS (Formula Patterns)](#8-patterns-formula-patterns)
9. [SINONIMI / ALIAS (Synonyms)](#9-sinonimi--alias-synonyms)
10. [GRAMMAR (Lark Grammar)](#10-grammar-lark-grammar)
11. [FLUSSI (Flows)](#11-flussi-flows)
12. [PROFILI (Profiles)](#12-profili-profiles)
13. [CAUSALI (Cause Codes)](#13-causali-cause-codes)
14. [CAMPO70 Operations](#14-campo70-operations)
15. [Vxx Labels](#15-vxx-labels)
16. [LINTER Rules](#16-linter-rules)
17. [KNOWLEDGE GRAPH](#17-knowledge-graph)
18. [GAP DI CONOSCENZA](#18-gap-di-conoscenza)

---

## 1. CAMPI (Fields)

### 1.1 Totali Giornalieri (1-6)

| Campo | Nome | Descrizione | Tipo |
|-------|------|-------------|------|
| 1 | OrePrevisionali | Ore previsionali (target giornaliero, da contratto) | TOTALE |
| 2 | OreEffettive | Ore effettive (differenza orario effettivo, da timbrature) | TOTALE |
| 3 | OreCalcolate | Ore calcolate (normalmente ordinarie) | TOTALE |
| 4 | OreStraordinarie | Ore straordinarie calcolate | TOTALE |
| 5 | OreAssenza | Ore assenza | TOTALE |
| 6 | OreAssenzaControlloStraord | Ore assenza per controllo straordinario | TOTALE |

### 1.2 Riservati / NON USARE (7-19, 90-99)

**Range 7-19:** Campi riservati — NON USARE.
**Range 90-99:** Campi riservati — NON USARE.

### 1.3 Fascia Notturna (20-22)

| Campo | Nome | Descrizione | Tipo |
|-------|------|-------------|------|
| 20 | FasciaDiurnaPrima | Fascia diurna prima del notturno | TOTALE |
| 21 | FasciaNotturna | Fascia notturna | TOTALE |
| 22 | FasciaDiurnaDopo | Fascia diurna dopo del notturno | TOTALE |

### 1.4 Campi Generici (23-49)

Campi 23-49: non documentati / liberi per uso generico (tipo APPOGGIO).

### 1.5 Flags Giorno e Tipo Turno (50-58)

| Campo | Nome | Descrizione | Tipo | Alias |
|-------|------|-------------|------|-------|
| 50 | GiornoSettimana | Giorno della settimana (1=dom, 7=sab) | FLAG | — |
| 51 | GiornoGG | Giorno in elaborazione (GG) | FLAG | — |
| 52 | MeseMM | Mese in elaborazione (MM) | FLAG | — |
| 53 | AnnoAAAA | Anno in elaborazione (AAAA) | FLAG | — |
| 54 | GiornoDopoFestivo | 1 se giorno successivo a giorno festivo | FLAG | — |
| 55 | GiornoFestivo | I se giorno festivo | FLAG | FestivoFlag |
| 56 | GiornoPrimaFestivo | 1 se giorno precedente a giorno festivo | FLAG | — |
| 57 | CausaleFestivita | Causale di festivita | CAUSALE | — |
| 58 | TipoOrario | Tipo orario (MATT/POME/NOTT/RIPO/OPE/CHIA) | FLAG | TipoTurno |

### 1.6 Campo70 Operativo (70-79)

| Campo | Nome | Descrizione | Tipo |
|-------|------|-------------|------|
| 70 | Campo70 | Definisce il tipo di operazione built-in | SISTEMA |
| 71-78 | Campo70_InOut | Input/Output per operazione Campo70 (alias: Campo70_Tmp) | SISTEMA |
| 79 | MemoriaPuntoFormula | RISERVATO — memoria punto formula | SISTEMA |

### 1.7 Entrate/Uscite di Giornata (80-89)

| Campo | Nome | Descrizione | Tipo |
|-------|------|-------------|------|
| 80 | EntrataPrevisionale | Entrata Previsionale | PREVISIONALE |
| 81 | UscitaPrevisionale | Uscita Previsionale | PREVISIONALE |
| 82 | EntrataEffettiva | Entrata Effettiva | TIMBRATURA |
| 83 | UscitaEffettiva | Uscita Effettiva | TIMBRATURA |
| 84 | EntrataCalcolata | Entrata Calcolata | CALCOLATA |
| 85 | UscitaCalcolata | Uscita Calcolata | CALCOLATA |
| 86 | BonusArrotondamentoEntrata | Bonus arrotondamento generale ENTRATA | TOTALE |
| 87 | FrazioneArrotondamentoEntrata | Frazione arrotondamento (minuti) generale ENTRATA | TOTALE |
| 88 | BonusArrotondamentoUscita | Bonus arrotondamento generale USCITA | TOTALE |
| 89 | FrazioneArrotondamentoUscita | Frazione arrotondamento (minuti) generale USCITA | TOTALE |

### 1.8 Orario Previsionale (100-160)

| Campo(i) | Nome | Descrizione |
|----------|------|-------------|
| 100 | IntervalliPrev | Numero intervalli di lavoro previsionali |
| 101-110 | DalleEntrata | Dalle entrata intervallo 1-10 |
| 111-120 | Entrata | ENTRATA intervallo 1-10 |
| 121-130 | AlleEntrata | Alle entrata intervallo 1-10 |
| 131-140 | DalleUscita | Dalle uscita intervallo 1-10 |
| 141-150 | Uscita | USCITA intervallo 1-10 |
| 151-160 | AlleUscita | Alle uscita intervallo 1-10 |

### 1.9 Orario Effettivo / Timbrature (200-240)

| Campo(i) | Nome | Descrizione |
|----------|------|-------------|
| 200 | IntervalliEff | Numero intervalli di lavoro effettivi |
| 201-220 | EntrataEff | Entrata effettiva intervallo 1-20 (numeri pari) |
| 221-240 | UscitaEff | Uscita effettiva intervallo 1-20 (numeri dispari) |

### 1.10 Orario Calcolato (250-290)

| Campo(i) | Nome | Descrizione |
|----------|------|-------------|
| 250 | IntervalliCalc | Numero intervalli di lavoro calcolati |
| 251-270 | EntrataCalc | Entrata calcolata intervallo 1-20 |
| 271-290 | UscitaCalc | Uscita calcolata intervallo 1-20 |

### 1.11 Campi Data e Sistema (300-399)

| Campo | Nome | Descrizione |
|-------|------|-------------|
| 300 | DataGiornata | Data giornata in elaborazione (AAAAMMGG) |
| 301 | DataOggi | Data odierna (AAAAMMGG) per confronto 300 U 301 |
| 302 | DataIeri | Data giorno precedente (AAAAMMGG) per confronto 300 U 302 |
| 305 | DataLimiteFormula | Data limite per split logica formula (es. 01/06/2023) |
| 311 | DataDomani | Data giorno successivo (AAAAMMGG) per confronto 300 U 311 |
| 350 | TotaleOreLavorate | Totale Ore Lavorate |
| 351 | DiffOreLavPrev | Differenza Ore Lavorate - Ore Previsionali |
| 360 | TotaleOreLavArrot | Totale Ore Lavorate dopo arrotondamento |
| 361 | DiffOreLavPrevArrot | Differenza Ore Lavorate - Ore Previsionali (arrot.) |
| 390 | TipoCalcolo | TipoCalcolo (0=normale, altro=speciale) |
| 391 | FlagSalvaCalcolate | Flag salva timbrature calcolate come effettive |

### 1.12 Causali Manuali (400-450)

| Campo(i) | Nome | Descrizione |
|----------|------|-------------|
| 400 | NumCausaliMan | Numero di causali manuali imputate |
| 401-410 | CausaleCodice | Codice causale manuale 1-10 |
| 411-420 | CausaleInizio | Orario Inizio causale manuale 1-10 |
| 421-430 | CausaleFine | Orario Fine causale manuale 1-10 |
| 431-440 | CausaleDurata | Durata causale manuale 1-10 |
| 441-450 | CausaleTipo | Tipo causale manuale (A=ASSENZA, P=PRESENZA) |

### 1.13 Causali Automatiche (500-599)

| Campo(i) | Nome | Descrizione |
|----------|------|-------------|
| 500 | ModalitaCalcolo | Modalita di calcolo totali (DURATA) |
| 501-510 | CausaleAuto | Codice causale automatica slot 1-10 |
| 511-520 | OreCausaleAuto | Ore causale automatica per tipo |
| 561-570 | OreCausale | Ore causale automatica per tipo descrittivo |

### 1.14 Slot Causali Automatiche (501-510)

| Slot | Codice | Descrizione | Campo Sorgente | Formula Rif |
|------|--------|-------------|----------------|-------------|
| 501 | F/FNG/FP/FX | Festivita (normale/non goduta/patrono/FX) | 918 | 2115/3015 |
| 502 | N/NF | Maggiorazione notturna / notturna festiva | 902, 903 | 2115/3015 |
| 503 | NF/LFS | Maggiorazione notturna festiva / lavoro festivo | 903, 904, 908 | 2115/3015 |
| 504 | LFS/SF | Maggiorazione lavoro festivo / straord. festivo | 904, 908, 914 | 2115/3015 |
| 505 | SP/N | Supplementare / maggiorazione notturna | 906 | 2115/3015 |
| 506 | SA/T | Straordinario diurno / maggiorazione diurna | 907 | 2115/3015 |
| 507 | SF/SA | Straordinario festivo / straord. diurno | 914 | 2115/3015 |
| 508 | SN | Straordinario notturno | 909 | 2115/3015 |
| 509 | SNF/SN | Straordinario notturno festivo / notturno | 910 | 2115/3015 |
| 510 | SB | Straordinario seconda fascia | 915 | 2114/3014 |

### 1.15 Totali Progressivi K (600-799)

Vedi sezione [TOTALI K](#2-totali-k-k-totals).

### 1.16 Campi di Appoggio (800-999)

| Campo | Nome | Descrizione |
|-------|------|-------------|
| 800 | Appoggio800 | Temp straordinario, accumulo arrotondamento |
| 801 | Appoggio801 | Temp straordinario, puntatori |
| 802 | Appoggio802 | Durata intervallo, puntatori |
| 803 | Appoggio803 | Durata, puntatori loop |
| 804 | Appoggio804 | Temp, puntatori loop |
| 805 | Appoggio805 | Assenze, temp |
| 806 | Appoggio806 | Non timbrato, temp |
| 807 | Appoggio807 | Diff assenze, temp |
| 810 | Appoggio810 | Unita minima incremento loop |
| 811 | Appoggio811 | Entrata intervallo per subroutine P2122 |
| 812 | Appoggio812 | Uscita intervallo per subroutine P2122 |
| 820 | Appoggio820 | Indice intervallo autorizzato straordinario |
| 821 | Appoggio821 | Ore autorizzate straordinario |
| 887 | Appoggio887 | Soglia straordinario settimanale |
| 889 | Appoggio889 | Soglia supplementare part-time |
| 890 | Appoggio890 | Maggiorazione diurna |
| 900 | FlagTurno | Flag anti-loop / indicatore turno (1=MATT, 2=POME, 3=NOTT) |
| 800-998 | Appoggio | Campi di appoggio liberi per calcoli custom |

### 1.17 Campi Aziendali (1000+)

| Campo | Nome | Descrizione |
|-------|------|-------------|
| 1000 | CodiceAzienda | Codice azienda |
| 1051 | FestivitaTipo51 | Festivita tipo 51 (patrono) per confronto 1051 U 51 |
| 1052 | FestivitaTipo52 | Festivita tipo 52 (patrono) per confronto 1052 U 52 |
| 1100 | CodiceDipendente | Codice dipendente |
| 1114 | OreSettimanaliContr | Ore settimanali contrattuali |
| 1121 | FlagStraordNonAmmesso | Flag straordinario non ammesso (N = si) |
| 1391 | OreRidottePartTime | Ore ridotte part-time (da Tabella Orario) |
| 1801 | ContatoreGiriGugest | Contatore giri GUGEST (anticiclo) |

### 1.18 Range Proibiti (Forbidden)

I seguenti range NON possono essere usati in nessuna formula:
7-19, 33-39, 60-69, 90-99, 161-197, 241-248, 291-299,
306-309, 324-329, 338-349, 362-389, 392-399, 451-499,
581-598, 1017-1049, 1054-1099, 1106-1108, 1137-1150,
1167-1170, 1209-1210, 1218-1220, 1224-1299, 1400,
1491-1499, 1591-1599, 1659, 1668-1670, 1688-1690,
1693-1697, 2004-2019, 2021-2039, 2041-2099, 2208-2210,
2395-2399, 2507, 2551-2557, 2588-2590, 2702-2710,
2741-2799, 2800, 2802-2899.

### 1.19 Array Definitions

| ID | Descrizione | Start | End | Accoppiato |
|----|-------------|-------|-----|------------|
| Prev | Previsionale | 111 | 150 | — |
| EntrateEff | Entrate Effettive | 201 | 220 | UsciteEff |
| UsciteEff | Uscite Effettive | 221 | 240 | EntrateEff |
| EntrateCalc | Entrate Calcolate | 251 | 270 | UsciteCalc |
| UsciteCalc | Uscite Calcolate | 271 | 290 | EntrateCalc |

---

## 2. TOTALI K (K-Totals)

### 2.1 Totali Principali (601-651)

| K | Nome | Descrizione | NumTot |
|---|------|-------------|--------|
| K601 | OreLavorate | Totale Ore Lavorate | 1 |
| K602 | OreOrdinarie | Totale Ore Ordinarie | 2 |
| K603 | LavoroFestivo | Totale Lavoro Festivo | 3 |
| K604 | TotaleStraordinario | Totale Straordinario (612+611+615+614+616) | 4 |
| K605 | Festivita | Totale Festivita | 5 |
| K608 | AssenzeRetribuite | Totale Assenze Retribuite | 8 |
| K609 | AssenzeNonRetribuite | Totale Assenze Non Retribuite | 9 |
| K610 | TotaleOreVarie | Totale Ore Varie (612+611+615+614+616) | 10 |
| K611 | StraordinarioDiurno | Totale Straordinario Diurno | 11 |
| K612 | Supplementare | Totale Supplementare | 12 |
| K614 | StraordinarioNotturno | Totale Straordinario Notturno | 14 |
| K615 | StraordinarioFestivoDiurno | Totale Straordinario Festivo Diurno | 15 |
| K616 | StraordinarioFestivoNotturno | Totale Straordinario Festivo Notturno | 16 |
| K621 | FlessibilitaLavorata | Flessibilita Lavorata (banca ore positiva) | 21 |
| K622 | FlessibilitaGoduta | Flessibilita Goduta (banca ore negativa) | 22 |
| K625 | MaggiorazioneTurnoDiurno | Totale Maggiorazione Turno Diurno | 25 |
| K626 | MaggiorazioneTurnoNotturno | Totale Maggiorazione Turno Notturno | 26 |
| K627 | MaggiorazioneLavoroFestivo | Totale Maggiorazione Lavoro Festivo | 27 |
| K629 | FestivitaNonGoduta | Totale Festivita Non Goduta | 29 |
| K630 | FestivitaNormale | Totale Festivita Normale | 30 |
| K631 | FerieGodute | Totale Ferie Godute | 31 |
| K635 | ROLPermessi | Totale R.O.L. / Permessi | 35 |
| K641 | TotalePermessi | Totale Permessi | 41 |
| K651 | Malattia | Totale Malattia | 51 |
| K711 | TotaleOreSettimanali | Totale Ore Settimanali (progressivo) | 111 |

### 2.2 Totali Interni / Appoggio (770-919)

| K | Nome | Descrizione |
|---|------|-------------|
| K770 | ContatoreSettimane | Contatore numero settimana |
| K771 | OreSettLavorate | Ore settimanali lavorate (3+4) |
| K772 | AssenzeSettimanali | Assenze settimanali (608+609) |
| K773 | LavoratoPiuAssenze | Lavorato + Assenze (771+772) |
| K774 | StraordSettimanale | Straordinario settimanale (907 accumulato) |
| K775 | TotaleSettimanaleFG | Totale settimanale FG (3+4+608+609) |
| K776 | LavoratoPiuOrdNottFG | Lavorato + ordinario notturno FG |
| K781 | OrePrevisteSett | Ore previste settimanali |
| K782 | OreLavPiuAssSett | Ore lavorate + assenze settimanali |
| K783 | OreStraordAnnuali | Ore straordinarie annuali cumulate |
| K784 | SupplementareSett | Supplementare settimanale |
| K785 | OreLavSett | Ore lavorate settimanali |
| K788 | TotaleSettCorrente | Totale settimana corrente |
| K790 | AccumuloSupplementare | Accumulo supplementare |
| K800 | AppoggioK | Appoggio per operazioni K |
| K900 | ContatoreGiorniGugest | Contatore giorni GUGEST |
| K902 | OrdinarioNotturno | Ordinario notturno |
| K903 | OrdinarioFestivoNotturno | Ordinario festivo notturno |
| K904 | OrdinarioFestivo | Ordinario festivo |
| K905 | Ordinario | Ordinario (ore ordinarie diurne) |
| K906 | Supplementare | Supplementare |
| K907 | StraordinarioDiurno | Straordinario diurno |
| K908 | DomenicaleOrdinario | Domenicale (ordinario) |
| K909 | StraordinarioNotturno | Straordinario notturno |
| K910 | StraordinarioDomenicaleNott | Straordinario domenicale notturno |
| K914 | StraordinarioFestivo | Straordinario festivo |
| K915 | StraordinarioSecondaFascia | Straordinario seconda fascia (SB) |
| K918 | OreFestivita | Ore festivita |
| K919 | TipoFestivita | Tipo festivita (1=normale, 2=non goduta, 3=patrono, 4=FX) |

---

## 3. FORMULE (Formulas)

Catalogo completo di 56 formule (54 reali + 2 placeholder: 2125, 2140).

### 3.1 Inizio Giornata (IG)

| ID | Nome | Categoria |
|----|------|-----------|
| 1 | Azzeramenti di inizio giornata | Standard |
| 5 | Riconoscimento Turno e cambio del previsionale | Turnisti |
| 1000 | Dirigenti (non timbratori) | Dirigenti |
| 1010 | Quadri | Dirigenti/Quadri |
| 1020 | Dipendenti che timbrano una volta per intervallo | Speciale |
| 2050 | Conad Gubbio — Arrotondamento entrate | Personalizzato |
| 2051 | Conad Gubbio — Arrotondamento uscite | Personalizzato |
| 2060 | Cap uscite 20:05 (dal 01/06/2023) | Personalizzato |
| 9001 | Arrotondamento Impiegati (I) | Arrotondamento |
| 9002 | Arrotondamento Impiegati (II) | Arrotondamento |

### 3.2 Di Giornata (DG)

| ID | Nome | Categoria |
|----|------|-----------|
| 10 | Determinazione del turno e cambio del previsionale | Turnisti |

### 3.3 Fine Giornata (FG)

| ID | Nome | Categoria |
|----|------|-----------|
| 100 | PRIMA FORMULA — Azzeramenti | Standard |
| 110 | Riproporziono 3, 4 e 5 in base alle assenze | Standard |
| 120 | Principale (smistatore FG) | Standard |
| 130 | Straordinario Festivo e Festivo Notturno | Straordinario |
| 140 | Straordinario Diurno e Notturno | Standard |
| 200 | Formula Finale | Standard |
| 210 | Maggiorazioni per Turnisti | Turnisti |
| 1100 | PRIMA FORMULA per Dirigenti e Quadri | Dirigenti |
| 1120 | PRIMA FORMULA per dip. che timbrano una volta | Speciale |
| 2000 | PRIMA FORMULA per dipendenti a chiamata | A Chiamata |
| 2100 | GUGEST 1 — Calcolo settimanale (variante A) | Gestione Personalizzata |
| 2101 | GUGEST 2 — Calcolo giornaliero (variante A) | Gestione Personalizzata |
| 2105 | GUGEST 1 — Calcolo settimanale (variante B) | Gestione Personalizzata |
| 2106 | GUGEST 2 — Calcolo giornaliero (variante B) | Gestione Personalizzata |
| 3000 | FG 1 — Formula gestione principale | Gestione Personalizzata |
| 3001 | FG NEW — Formula gestione aggiornata | Gestione Personalizzata |

### 3.4 Subroutine (SUB)

| ID | Nome | Categoria |
|----|------|-----------|
| 2107 | Conteggio ore con arrotondamento minuti | Calcolo |
| 2109 | Gestione festivita automatiche (variante A) | Festivita |
| 2114 | Ritocco SA/SB (cap 8 ore straordinario) | Straordinario |
| 2115 | Esplode causali automatiche (variante A) | Causali |
| 2122 | Calcolo ore per singolo intervallo | Calcolo |
| 2123 | Arrotondamento minuti ore ordinarie/festive | Arrotondamento |
| 2124 | Arrotondamento minuti ore straordinarie | Arrotondamento |
| 2125 | GUGEST 22 — placeholder vuoto | — |
| 2130 | Warning ore carenti / soglia 250h annuali (A) | Alert |
| 2140 | Arrotondamento base | Arrotondamento |
| 3002 | FG 2 — Arrotondamento ore (ante 01/06/2023) | Arrotondamento |
| 3003 | FG 2 NEW — Arrotondamento ore (dal 01/06/2023) | Arrotondamento |
| 3004 | Straordinario Festivo | Straordinario |
| 3005 | Calcolo straordinario settimanale | Straordinario |
| 3009 | Gestione festivita automatiche (variante B) | Festivita |
| 3014 | Ritocco SA/SB (variante B) | Straordinario |
| 3015 | Esplode causali automatiche (variante B) | Causali |
| 3017 | Gestione autorizzazioni straordinario (AUTS) | Straordinario |
| 3020 | Pausa pranzo — ricalcolo e forzatura 30 min | Pausa Pranzo |
| 3030 | Warning ore carenti / soglia 250h annuali (B) | Alert |

---

## 4. INTENT (Intents)

### 4.1 Intent Riconosciuti (34 totali)

| Intent | Confidence | Builder Function | IR Builder |
|--------|-----------|-----------------|------------|
| reset_puro | 1.0 | _build_reset_puro | ir_reset_puro |
| riconoscimento_turno | 0.9 | build_riconoscimento_turno | ir_riconoscimento_turno |
| calcolo_presenza | 0.85 | build_calcolo_presenza | ir_calcolo_presenza |
| gestione_auts | 0.85 | build_gestione_auts | — |
| warning_ore | 0.8 | build_warning_ore | — |
| maggiorazioni_turnisti | 0.85 | build_maggiorazioni_turnisti | — |
| ritocco_sa_sb | 0.85 | build_ritocco_sa_sb | — |
| straordinario_festivo | 0.85 | build_straordinario_festivo | — |
| straordinario_notturno | 0.85 | build_straordinario_notturno | — |
| straordinario_diurno | 0.85 | build_straordinario_diurno | — |
| straordinario_settimanale | 0.8 | build_straordinario_settimanale | — |
| avispa | 0.9 | build_avispa | — |
| flusso_fg | 0.8 | build_flusso_fg | — |
| gugest_a | 0.9 | build_gugest_a | — |
| gugest_b | 0.9 | build_gugest_b | — |
| fg_b | 0.9 | build_fg_b | — |
| primo_giro | 0.85 | build_primo_giro | — |
| secondo_giro | 0.85 | build_secondo_giro | — |
| riferimento_formula | 0.95 | build_riferimento_formula | — |
| azzeramento_giornata | 0.8 | build_azzeramento_giornata | — |
| finale_giornata | 0.8 | build_finale_giornata | — |
| riconoscimento_causale | 0.8 | build_riconoscimento_causale | — |
| festivita | 0.75 | build_festivita | — |
| pausa_pranzo | 0.8 | build_pausa_pranzo | — |
| arrotondamento_impiegati | 0.85 | build_arrotondamento_impiegati | — |
| arrotondamento_quarti | 0.7 | build_arrotondamento_quarti | ir_arrotondamento_quarti |
| arrotondamento | 0.8 | build_arrotondamento | ir_arrotondamento |
| gestione_assenze | 0.7 | build_gestione_assenze | ir_gestione_assenze |
| k_accumulo | 0.75 | build_k_accumulo | ir_k_accumulo |
| catena_formule | 0.65 | build_catena_formule | ir_catena_formule |
| riferimento_causale | 0.6 | build_riferimento_causale | — |
| set_field | 0.85 | — | ir_set_field |
| condizionale_generico | 0.6 | build_condizionale_generico | ir_condizionale_generico |
| durata_intervallo | — | build_durata_intervallo | ir_durata_intervallo |

### 4.2 Keyword per Intent

| Intent | Trigger Keywords |
|--------|-----------------|
| riconoscimento_turno | turno, riconoscimento, turnista, 251, 271 |
| maggiorazioni_turnisti | maggiorazione, turno, turnista |
| straordinario_festivo | straordinario, festivo, sf, domenica, sfn |
| straordinario_notturno | straordinario, notturno, sn, notte |
| straordinario_diurno | straordinario, diurno, ordinario |
| pausa_pranzo | pausa, pranzo, 3020 |
| warning_ore | warning, carenti, ore, alert, 250 |
| avispa | avispa |
| gugest_a/gugest_b | gugest |
| azzeramento_giornata | inizio giornata, azzeramento, giornata |
| arrotondamento | arrotondamento, arrotonda, approssima, quarti d\'ora |
| catena_formule | catena, chain, collega, richiama, chiama, salta a |
| gestione_assenze | assenza, assenze, carenti |
| reset_puro | azzera, resetta, svuota, annulla (senza parole azione) |
| k_accumulo | accumula, accumulo, K, K77, K60, aggiungi a, somma a |
| flusso_fg | flusso |
| riconoscimento_causale | esplode, esplodi, estrai, causale, slot, 501 |

---

## 5. CONTRATTI (Contracts)

| ID | Nome | Descrizione | Timbra | MaxEntrata | Formule IG | Formule FG |
|----|------|-------------|--------|------------|------------|------------|
| 1 | Standard | Contratto Standard — timbrature normali | Si | — | 1, 5, 10, 2050, 2051, 2060, 9001, 9002 | 100, 110, 120, 130, 140, 200, 210 |
| 2 | Dirigenti/Quadri | Dipendenti che NON timbrano | No | — | 1000, 1010 | 1100 |
| 3 | Turnisti | Dipendenti Turnisti — con max entrata posticipata | Si | posticipata | 1, 5, 10 | 100, 110, 120, 130, 140, 200, 210 |

**Fascia notturna standard:** 22:00 - 06:00 (per tutti i contratti).

---

## 6. CATENE (Chains)

| Nome Catena | Formule (in ordine di esecuzione) |
|-------------|----------------------------------|
| standard_inizio | 1, 5, 10 |
| standard_fine | 100, 110, 120, 130, 140, 200, 210 |
| dirigenti_inizio | 1000, 1010 |
| dirigenti_fine | 1100 |
| chiamata_fine | 2000 |
| person_inizio | 2050, 2051, 2060, 9001, 9002 |
| gugest_a_fine | 2100, 2101 |
| gugest_b_fine | 2105, 2106 |
| fg_fine | 3000, 3001 |

---

## 7. SUBROUTINE (Subroutine Calls)

### 7.1 Mappa Chiamate P (Perform) — da workbook_retriever.py

| Formula Chiamante | Chiama (P) |
|-------------------|------------|
| 2101 | 2109, 2122, 2123, 2124, 2125, 2114, 2115, 2130 |
| 2100 | 2109 |
| 3000 | 3009, 3002, 3003, 3017 |
| 3001 | 3009, 2122, 2123, 2124, 3005, 3014, 3015, 3030 |
| 200 | 210 |
| 2050 | 2051, 2060 |
| 9001 | 9002 |

### 7.2 Mappa Salti R (Goto) — da table_registry.py

| Da | A | Tipo | Descrizione |
|----|---|------|-------------|
| 100 | 110 | R | FineGiornata: 100 -> 110 (R110) |
| 110 | 120 | R | FineGiornata: 110 -> 120 (R120) |
| 120 | 130 | R | FineGiornata: 120 -> 130 se festivo (R130) |
| 120 | 140 | R | FineGiornata: 120 -> 140 se ordinario (R140) |
| 120 | 200 | R | FineGiornata: 120 -> 200 default (R200) |
| 130 | 200 | R | FineGiornata: 130 -> 200 (R200) |
| 140 | 200 | R | FineGiornata: 140 -> 200 (R200) |
| 200 | 210 | P | FineGiornata: 200 chiama 210 se turno attivo (P210) |
| 2050 | 2051 | R | Arrot. entrate chiama arrot. uscite (R2051) |
| 2050 | 2060 | R | Arrot. entrate chiama cap uscite (R2060, dal 01/06/2023) |
| 9001 | 9002 | R | Arrot. impiegati I chiama II (R9002) |

### 7.3 Flussi completi con Relazioni

```
FineGiornata: 100 -> 110 (R110) -> 120 (R120) -> 130/140 (R130/R140) -> 200 (R200) -> 210 (P210)
GUGEST A:    2100 -> 2101 (chain) con P2109, P2122, P2123, P2124, P2125, P2114, P2115, P2130
FG B:        3000 -> 3001 (chain) con P3009, P2122, P2123, P2124, P3005, P3014, P3015, P3030
"""

## 8. PATTERNS (Formula Patterns)

### 8.1 Pattern per Tipo

| Tipo | Conteggio | Codici |
|------|-----------|--------|
| IG (Inizio Giornata) | 11 | 1, 5, 1000, 1010, 1020, 2050, 2051, 2060, 9001, 9002, 10 (DG) |
| FG (Fine Giornata) | 16 | 100, 110, 120, 130, 140, 200, 210, 1100, 1120, 2000, 2100, 2101, 2105, 2106, 3000, 3001 |
| SUB (Subroutine) | 20 | 2107, 2109, 2114, 2115, 2122, 2123, 2124, 2125, 2130, 2140, 3002, 3003, 3004, 3005, 3009, 3014, 3015, 3017, 3020, 3030 |
| DG (Di Giornata) | 1 | 10 |

### 8.2 Pattern per Categoria

| Categoria | Conteggio | Codici |
|-----------|-----------|--------|
| Standard | 6 | 1, 100, 110, 120, 140, 200 |
| Turnisti | 3 | 5, 10, 210 |
| Dirigenti | 2 | 1000, 1100 |
| Dirigenti/Quadri | 1 | 1010 |
| Speciale | 2 | 1020, 1120 |
| Personalizzato | 3 | 2050, 2051, 2060 |
| Straordinario | 7 | 130, 2114, 3004, 3005, 3014, 3017, 3000 |
| Gestione Personalizzata | 6 | 2100, 2101, 2105, 2106, 3000, 3001 |
| Arrotondamento | 8 | 2123, 2124, 2140, 3002, 3003, 9001, 9002 |
| Festivita | 2 | 2109, 3009 |
| Causali | 2 | 2115, 3015 |
| Calcolo | 2 | 2107, 2122 |
| Alert | 2 | 2130, 3030 |
| Pausa Pranzo | 1 | 3020 |
| A Chiamata | 1 | 2000 |
| Placeholder | 1 | 2125 |

### 8.3 Arrotondamento Lookup Tables

**Pattern 2123/2124 — Arrotondamento ai quarti d\'ora (ordinario e straordinario):**

| Minuti residui (73) | Azione | Incremento |
|---------------------|--------|------------|
| < 15.00 | Scarta (nessun arrotondamento) | 0 |
| < 30.00 | Aggiungi 0.15 (15 min) | +0.15 |
| < 45.00 | Aggiungi 0.35 (35 min) | +0.35 |
| <U 59.00 | Aggiungi 0.45 (45 min) | +0.45 |

**Pattern 3003 — Arrotondamento FG dal 01/06/2023:**

| Minuti residui (73) | Azione |
|---------------------|--------|
| < 30.00 | Nessun arrotondamento |
| <U 59.00 | Aggiungi 0.30 (30 min) |

**Pattern 3002 — Arrotondamento ante 01/06/2023 (due livelli):**
- Se 775 > soglia (40h o 1391): usa arrotondamento a 15/30/45 min
- Se 775 <= soglia: arrotondamento semplice (<30 scarta, <U59 +0.30)

---

## 9. SINONIMI / ALIAS (Synonyms)

Solo 3 alias documentati nel codebase:

| Campo | Alias | Fonte |
|-------|-------|-------|
| 55 | FestivoFlag | field_registry.py: aliases |
| 58 | TipoTurno | field_registry.py: aliases |
| 71-78 | Campo70_Tmp | field_registry.py: aliases (tutti i campi 71-78) |

**Nota:** Nessun formale dizionario di sinonimi business-level esiste nel codebase. Ad esempio, non ci sono mapping per "ore ordinarie" = "campo 3", "ore normali" = "campo 3", ecc.

---

## 10. GRAMMAR (Lark Grammar)

### 10.1 Token-Soup Grammar (winsarp_compact.lark — 34 lines, 34 token definitions)

```
?start: formula
formula: item*
item: NUMBER | STRING | TIME_VALUE | FIELD_REF
    | FLAG | LABEL | CALL_R | CALL_P | KOP | LOGIC_OP | COMPARATOR
    | RESET_OP | ASSIGN_OP | KW_K | KW_VF | KW_VU
    | LPAREN | RPAREN | PTR_OPEN | PTR_CLOSE
```

**Token definitions:**

| Token | Pattern/Value | Descrizione |
|-------|---------------|-------------|
| LPAREN | "(" | Parentesi aperta |
| RPAREN | ")" | Parentesi chiusa |
| RESET_OP | "!" | Operatore reset |
| ASSIGN_OP | "=" | Operatore assegnazione |
| KW_K | "K" | Parola chiave K (accumulo) |
| KW_VF | "VF" | Fine formula |
| KW_VU | "VU" | Salta all\'ultimo periodo logico |
| CALL_R | /R[0-9]+/ | Chiamata R (goto formula) |
| CALL_P | /P[0-9]+/ | Chiamata P (perform subroutine) |
| PTR_OPEN | /\[[0-9]+/ | Pointer open (incrementa) |
| PTR_CLOSE | /\][0-9]+/ | Pointer close (decrementa) |
| NUMBER | /[0-9]+/ | Numero intero |
| KOP | "A" | "S" | Operatore K (Accumula/Sottrai) |
| LOGIC_OP | "E" | "O" | Operatori logici (E=AND, O=OR) |
| COMPARATOR | ">" | "<" | ">=" | "<=" | ">U" | "<U" | "#" | "U" | "Z" | Operatori di confronto |
| STRING | /"[^"]*"/ | /'[^']*'/ | Stringhe (doppi o singoli apici) |
| TIME_VALUE | /\^[0-9]+\.[0-9]+\^/ | Valore temporale sessagesimale |
| FIELD_REF | /\{[0-9]+\}/ | Riferimento campo dereferenziato |
| FLAG | "I" | "Z" | Flag (I=vero, Z=falso) |
| LABEL | /V[0-9]+/ | Label Vxx per salti |

### 10.2 Full Grammar (winsarp.lark — 87 lines)

**Produzioni principali:**
```
start: compact_statement+
compact_statement: compact_block
compact_block: "(" compact_inner ")"+
compact_inner: compact_assignment | compact_reset | compact_conditional
              | compact_k | compact_call | compact_return | compact_campo70 | compact_ptr
```

**Statement definitions:**

| Produzione | Sintassi | Esempio |
|------------|----------|---------|
| compact_assignment | FIELD "=" compact_value | (900 = \'1\') |
| compact_reset | "!" FIELD | (!900) |
| compact_conditional | "(" condition ")" compact_code (";" compact_code)? ";" | (cond)(then_code;else_code;) |
| compact_k | "K" FIELD compact_k_op+ | K601A3 |
| compact_call | ("R" | "P") NUMBER | R110, P210 |
| compact_return | "VF" | "VU" | LABEL | VF |
| compact_campo70 | "70=" C70_CODE | (70=\'2\') |
| compact_ptr | ("[" FIELD | "]" FIELD) | [800 |

**Operatori completi:**
```
KOP: "A" | "S"
LOGIC_OP: "E" | "O" | "AND" | "OR"
COMPARATOR: "=" | ">" | "<" | ">=" | "<=" | ">U" | "<U" | "#" | "!" | "U" | "Z"
```

**Parser:** Earley (algoritmo), start symbol "formula".

---

## 11. FLUSSI (Flows)

### 11.1 Fine Giornata

| Nome Flusso | Formule |
|-------------|---------|
| fine_giornata_standard | 100, 110, 120, 130, 140, 200, 210 |
| fine_giornata_dirigenti | 1100 |
| fine_giornata_timbratura_singola | 1120 |
| fine_giornata_chiamata | 2000 |
| fine_giornata_gugest_a | 2100, 2101 |
| fine_giornata_gugest_b | 2105, 2106 |
| fine_giornata_fg_b | 3000, 3001 |

### 11.2 Inizio Giornata

| Nome Flusso | Formule |
|-------------|---------|
| inizio_giornata_standard | 1, 5, 10 |
| inizio_giornata_dirigenti | 1000, 1010 |
| inizio_giornata_quadri | 1010 |
| inizio_giornata_timbratura_singola | 1020 |
| inizio_giornata_conad | 2050, 2051, 2060 |
| inizio_giornata_arrotondamento_impiegati | 9001, 9002 |

---

## 12. PROFILI (Profiles)

### 12.1 Profilo Unico Definito

**Nome:** turnista_completo
**Match Threshold:** 0.8
**Keywords:** turnista, due intervalli, pausa pranzo, straordinario, maggiorazioni

**Architettura:**
1. Formula 5 (riconoscimento turno su prima entrata field 200)
2. Formula 1020 (costruzione intervalli da timbrature dirette)
3. Formula 3001 (elaborazione FG)

**IR Steps (62 step) — Struttura:**

**Fase IG — Azzeramenti iniziali:**
- Reset 900 (flag turno)
- Reset 800-804 (campi appoggio)

**Fase IG — Riconoscimento turno:**
- Se 200 > Z: classifica entrata in fasce 04-09 (MATT), 12-17 (POME), 20-24 (NOTT)
- Imposta 900 (1=MATT, 2=POME, 3=NOTT), 58 (TipoOrario), 111/141 (previsionali)

**Fase DG — Costruzione due intervalli:**
- Primo intervallo: entrata=200, uscita=201 -> 251/271
- Secondo intervallo: entrata=202, uscita=203 -> 252/272

**Fase FG — Elaborazione completa:**
- Reset settimanali se giorno 2 (lunedi)
- Reset annuali se 1 gennaio
- Gestione festivita (P3009)
- Accumulo K3A4, K775
- Arrotondamento date-based (ante/dal 01/06/2023)
- Autorizzazioni straordinario (P3017)
- Calcolo straordinario e maggiorazioni
- Cap 776 su 40h o ore contrattuali
- Accumulatori K602, K626, K627, K612, K611, K615, K614, K616, K604, K783, K601
- Totale settimanale K711
- Reset campi output 901-929
- Anti-loop K900

---

## 13. CAUSALI (Cause Codes)

### 13.1 Codici Causale Completi

**Straordinario:**

| Codice | Nome | Descrizione | Slot |
|--------|------|-------------|------|
| SA | Straordinario Diurno (1a fascia) | Straordinario diurno prima fascia | 506/507 |
| SB | Straordinario Diurno (2a fascia) | Straordinario diurno seconda fascia | 510 |
| SN | Straordinario Notturno | Straordinario notturno | 502/508 |
| SF | Straordinario Festivo Diurno | Straordinario festivo diurno | 503/507 |
| SFN | Straordinario Festivo Notturno | Straordinario festivo notturno | 504/509 |
| SNF | Straordinario Notturno Festivo | Straordinario notturno festivo | 509 |

**Supplementare:**

| Codice | Nome | Descrizione | Slot |
|--------|------|-------------|------|
| SP | Supplementare | Ore supplementari | 505 |

**Maggiorazioni:**

| Codice | Nome | Descrizione | Slot |
|--------|------|-------------|------|
| N | Maggiorazione Notturna | Maggiorazione turno notturno | 502/505, 565 |
| NF | Maggiorazione Notturna Festiva | Maggiorazione notturna festiva | 503 |
| T | Maggiorazione Turno Diurno | Maggiorazione turno diurno | 506, 566 |
| LFS | Lavoro Festivo Straordinario | Maggiorazione lavoro festivo | 504 |

**Festivita:**

| Codice | Nome | Descrizione | Slot | Tipo (919) |
|--------|------|-------------|------|------------|
| F | Festivita Normale | Festivita normale | 501 | 1 |
| FNG | Festivita Non Goduta | Festivita non goduta | 501 | 2 |
| FP | Festivita Patrono | Festivita patrono | 501 | 3 |
| FX | Festivita in Stipendio | Festivita in stipendio (variante B) | 501 | 4 |

**Tipi Orario (campo 58):**

| Codice | Nome | Descrizione | Fascia Oraria |
|--------|------|-------------|---------------|
| MATT | Turno Mattino | Turno mattino | 06-14 |
| POME | Turno Pomeriggio | Turno pomeriggio | 14-22 |
| NOTT | Turno Notte | Turno notte | 22-06 |
| RIPO | Riposo | Giorno di riposo | — |
| OPE | Operaio Spezzato | Operaio con spezzatura (2 intervalli) | 08-12/13-17 |
| CHIA | Chiamata | Dipendente a chiamata | — |
| CHI | Chiamata (effettuata) | Chiamata effettuata | — |

**Autorizzazioni:**

| Codice | Nome | Descrizione |
|--------|------|-------------|
| AUTS | Autorizzazione Straordinario | Autorizzazione straordinario (causale manuale 401-404) |

**Flag tipo causale manuale (campi 441-450):**

| Codice | Nome | Descrizione |
|--------|------|-------------|
| A | Assenza | Flag tipo causale manuale: ASSENZA |
| P | Presenza | Flag tipo causale manuale: PRESENZA |

---

## 14. CAMPO70 Operations

### 14.1 Catalogo Completo

| Code | Nome | Input -> Output | Descrizione |
|------|------|----------------|-------------|
| 1 | SommaOre | 71 + 72 -> 73 | Somma orari sessagesimali |
| 2 | DifferenzaOre | 71 - 72 -> 73 | Differenza orari sessagesimali |
| 3 | SeparaOreMinuti | 71 -> 72 = ore, 73 = minuti | Separa ore da minuti |
| 4 | OrarioInMinuti | 71 -> 73 = minuti totali | Trasforma orario (hh.mm) in minuti |
| 5 | MinutiInOrario | 71 = minuti -> 73 = hh.mm | Trasforma minuti in orario |
| 8 | CentesimiInSessagesimi | 71 (hh.cc) -> 73 (hh.mm) | Da centesimi a sessagesimi |
| 9 | SessagesimiInCentesimi | 71 (hh.mm) -> 73 (hh.cc) | Da sessagesimi a centesimi |
| 11 | DurataIntervallo | 71 = Entrata, 72 = Uscita -> 73 | Durata intervallo (gestisce mezzanotte) |
| 20 | ArrotondaEntrata | 71 con approx 72, offset 73, bonus 74 -> 71 | Arrotonda orario di ENTRATA |
| 21 | ArrotondaUscita | 71 con approx 72, offset 73, bonus 74 -> 71 | Arrotonda orario di USCITA |
| 22 | SeparaNotturnoDiurno | 71 = Entrata, 72 = Uscita -> 71/72/73 | Separa notturno dal diurno per TURNO |
| 30 | ConcatenaStringhe | 71 + 72 -> 71 | Concatena due stringhe |
| 31 | EstraiSottostringa | 71, 72 = Inizio, 73 = Numero caratteri -> 71 | Estrae sottostringa |
| 32 | Trim | 71, 72 = "R"/"L"/altro -> 71 | Rimuove spazi (Trim) |
| 41 | ScomponiData | 71 = data -> 72 = g.sett., 73 = giorno, 74 = mese, 75 = anno | Scomponi data |
| 42 | DifferenzaDate | 71 = DA, 72 = A, 73 = Tipo -> 71 | Differenza date |
| 43 | SommaGiorniAData | 71 = Data, 72 = Offset giorni -> 71 | Somma giorni a data |
| 45 | GiornoSettimana | 71 = data -> 71 (1=dom, 7=sab) | Giorno settimana |
| 48 | PrimoUltimoGiornoMese | 71 = data -> 71 = primo, 72 = ultimo | Primo/Ultimo giorno mese |
| 50 | StatisticaCausale | 71 = DataInizio, 72 = DataFine, 73 = Causale, 74 = Tipo (T/A/M) -> 71 = Somma | Somma durata causale nel periodo |
| 99 | DebugMostraCampi | 71-78 | DEBUG — MsgBox con valori campi |
| 900 | DebugMostraTabellone | — | DEBUG — MsgBox Tabellone completo |

### 14.2 Pattern di Utilizzo Tipico

**Calcolo durata intervallo:**
```
(!71!72!73)(71=251)(72=271)(70='2')(800=73)
```

**Arrotondamento entrata:**
```
(71=800)(72='15')(!73!74)(70='20')(800=71)
```

**Separazione ore/minuti per arrotondamento quarti:**
```
(71=902)(70='3')(902=72)(!800)    [73 contiene i minuti residui]
```

---

## 15. Vxx Labels

### 15.1 Label usate nelle formule

| Label | Dove e Definita | Dove e Riferita |
|-------|----------------|-----------------|
| V02 | 5, 140, 2051, 2109, 3000, 3009 | 130, 2051, 2130, 3004, 3030 |
| V03 | 2107, 2122 | — |
| V04 | 5, 130, 140, 2109 | 130, 140, 2051 |
| V05 | 130, 140, 2051 | 130, 140, 2051 |
| V06 | 2051, 2130, 3030 | 2130, 3030 |
| V07 | 2123, 2124 | 2051, 2123, 2124 |
| V08 | 2107, 2123, 2124, 2130, 3002, 3030 | 2107, 2123, 2124 |
| V09 | 3002 | 2123, 2124, 9001 |
| V10 | 2051 | 130, 140, 2051, 3002 |
| V11 | 5, 3002 | 5, 3002 |
| V12 | 2130, 3030 | 2130, 3030 |
| V13 | 2100 | — |
| V14 | 2107 | 2107, 2122 |
| V15 | 3000 | — |
| V16 | 2051, 2123, 2124 | — |
| V24 | 2105, 2123 | — |
| V25 | 2123, 2124 | — |
| V31 | 2123, 2124 | — |
| V32 | 2123, 2124 | — |
| V39 | 2123, 2124 | — |
| V40 | 2123, 2124 | — |

### 15.2 Convenzioni Label

- **Vxx** = label numerica (V02, V04, V10...), MAI V_START, V_END, V_SKIP, V_DONE
- MARK definisce la label, GOTO salta ad essa
- Usate per implementare salti condizionali all\'interno della stessa formula
- Equivalgono a goto labels nel linguaggio WinSarp

---

## 16. LINTER Rules

### 16.1 Codici Errore (da linter.py)

| Codice | Descrizione | Severita |
|--------|-------------|----------|
| E001 | Nessuno step IR | error |
| E002 | VF mancante alla fine della formula | error |
| E003 | VF extra dopo fine formula | error |
| E004 | Codice irraggiungibile dopo VF/R/P incondizionato | error |
| E005 | R/P target non esiste nel workbook | error |
| E006 | Vxx usata (GOTO) ma mai definita (MARK) | error |
| E007 | Vxx definita (MARK) ma mai usata (GOTO) | warning |
| E008 | Lettura campo prima di scrittura nella stessa formula | warning |
| E009 | Flag I/Z usato come numerico o viceversa | warning |
| E010 | Ciclo: R/P target punta a se stesso o a catena chiusa | error |
| L001 | Token non valido alla posizione N (parsing Lark) | error |
| L002 | Errore di parsing Lark generico | error |
| L003 | Parentesi chiusa senza apertura (depth < 0) | error |
| L004 | Parentesi non chiuse (depth > 0 — WinSarp permette) | warning |

### 16.2 Regole di Validazione Semantica

1. **Terminazione VF:** Ogni formula deve terminare con VF
2. **Codice raggiungibile:** Dopo VF/R/P incondizionato, il codice non e raggiungibile
3. **Target R/P validi:** I codici chiamati via R/P devono esistere nel workbook
4. **Label scope:** Ogni Vxx referenziata deve avere un MARK corrispondente
5. **Field init:** Un campo non puo essere letto prima di essere scritto
6. **Type checking:** I flag I/Z non possono essere usati in contesti numerici e viceversa
7. **Loop detection:** Non devono esistere cicli di chiamate R/P

---

## 17. KNOWLEDGE GRAPH

### 17.1 Struttura Nodi

Ogni nodo formula contiene i seguenti attributi:

| Attributo | Tipo | Descrizione |
|-----------|------|-------------|
| id | int | Numero formula |
| name | str | Nome descrittivo |
| tipo | str | IG/FG/DG/Subroutine |
| tipo_cat | str | inizio/fine/giornata/sub |
| tipo_order | int | Ordine di elaborazione (1=IG, 2=FG, 3=DG, 4=SUB) |
| scopo | str | Descrizione dello scopo |
| code | str | Sintassi compatta |
| reset_fields | list[int] | Campi azzerati (!N) |
| k_fields | list[int] | Campi usati in K accumulo |
| braced_refs | list[int] | Riferimenti dereferenziati {N} |
| numeric_refs | list[int] | Tutti i numeri referenziati |
| calls_r | list[int] | Salti R a formule |
| calls_p | list[int] | Chiamate P a subroutine |
| all_calls | list[int] | Unione di calls_r + calls_p |
| return_codes | list[str] | Codici di ritorno (VF, VU, Vxx) |
| operators | list[str] | Operatori usati (UZ, E, O, Z) |
| comparisons | dict | Confronti (campo -> lista {op, val}) |
| bracket_refs | list[int] | Riferimenti pointer [N / ]N |
| key_sum | list[dict] | Pattern KfieldSfield |
| called_by | list[int] | Formule che chiamano questa |

### 17.2 Tipi di Archi

| Tipo | Descrizione |
|------|-------------|
| calls_r | Arco diretto: formula A salta (R) a formula B |
| calls_p | Arco diretto: formula A chiama (P) formula B |
| called_by | Arco inverso (derivato): chi chiama questa formula |

### 17.3 Statistiche Grafo

- **Nodi:** ~56 (tutte le formule del catalogo)
- **Archi diretti (calls_r + calls_p):** ~30+
- **Campi unici referenziati:** ~100+
- **Operatori unici:** U, Z, E, O, UZ
- **File persistenza:** data/winsarp_graph.json

### 17.4 Field Read/Write Analysis (da formula_graph.py)

Ogni formula viene analizzata automaticamente per determinare:

**Written fields** (campi su cui la formula scrive):
- RESET (!N) -> write N
- SET (N = val) -> write N
- K (K N A/S val) -> write N
- Pointer ([N / ]N) -> write N

**Read fields** (campi che la formula legge):
- Braced derefs ({N}) -> read N
- Conditions (N U / N > / N < val) -> read N
- VALUES nelle assegnazioni -> read

### 17.5 Insertion Point Suggestion (da formula_graph.py)

Il grafo suggerisce dove agganciare una nuova formula basandosi su:
1. Campi letti/scritti dalla nuova formula
2. Flusso dati nel grafo (chi produce un campo, chi lo consuma)
3. Similarita di campo tra nuova formula e formule esistenti

---

## 18. GAP DI CONOSCENZA

### 18.1 Categorie Assenti

| # | Categoria | Descrizione |
|---|-----------|-------------|
| 1 | Business Entities | Nessuna definizione formale di entita: dipendente, azienda, contratto, turno, festivita, straordinario, maggiorazione, supplementare |
| 2 | Profili Contrattuali | Solo 1 profilo definito (turnista_completo). Manca profili per: standard_impiegato, dirigente, chiamata, conad, part-time |
| 3 | Data Types | I tipi campo (time, counter, flag, string, code) non sono formalizzati per ogni campo nel registro |
| 4 | Validation Rules | Nessuna regola di validazione formale per range, obbligatorieta, consistenza tra campi |
| 5 | Contract -> Flow Mapping | Mappa esplicita contratto -> flusso formula non formalizzata (esiste solo implicita in CONTRATTI.formulas_ig/fg) |
| 6 | Stato/Macchina Vita | Modello del ciclo di vita giornata lavorativa (IG -> DG -> FG -> subs) non formalizzato come macchina a stati |
| 7 | Business Rules | Regole business (es. "straordinario solo se autorizzato", "pausa pranzo minima 30 min") non formalizzate |
| 8 | Dizionario Sinonimi | Solo 3 alias tecnici; nessun dizionario business-level per sinonimi di concetti |
| 9 | Gerarchia Entita | Nessuna gerarchia di business entities o tassonomia del dominio |
| 10 | Regole di Calcolo | Logica di calcolo (es. come K601 deriva da 3+4, come K604 = K612+K611+K615+K614+K616) non formalizzata come regole |

### 18.2 Priorita di Riempimento Consigliata

1. **Profili contrattuali** — Creare profili per standard, dirigente, chiamata, conad, part-time
2. **Tipi Dato e Validazione** — Associare data type e validation rules a ogni campo
3. **Mappa Contratto -> Flusso** — Formalizzare quale flusso appartiene a quale contratto
4. **Regole Business** — Estrarre regole di calcolo dal workbook e formalizzarle
5. **Dizionario Sinonimi** — Creare mapping business-level per concetti (es. "ore ordinarie" ~ "ore normali" ~ "campo 3")
6. **Entita Business** — Definire formalmente dipendente, turno, contratto, festivita, etc.

---

## Appendice A: File Sorgenti del Codebase

| File | Percorso Assoluto |
|------|-------------------|
| workbook_retriever.py | C:\ProgettoRAG_DEV\core\workbook_retriever.py |
| field_registry.py | C:\ProgettoRAG_DEV\core\field_registry.py |
| table_registry.py | C:\ProgettoRAG_DEV\core\table_registry.py |
| profile_registry.py | C:\ProgettoRAG_DEV\core\profile_registry.py |
| intent_builder.py | C:\ProgettoRAG_DEV\core\intent_builder.py |
| intent_embeddings.py | C:\ProgettoRAG_DEV\core\intent_embeddings.py |
| formula_patterns.py | C:\ProgettoRAG_DEV\core\formula_patterns.py |
| lark_validator.py | C:\ProgettoRAG_DEV\core\lark_validator.py |
| winsarp.lark | C:\ProgettoRAG_DEV\core\winsarp.lark |
| winsarp_compact.lark | C:\ProgettoRAG_DEV\core\winsarp_compact.lark |
| winsarp_catalog.py | C:\ProgettoRAG_DEV\core\winsarp_catalog.py |
| knowledge_graph.py | C:\ProgettoRAG_DEV\core\knowledge_graph.py |
| formula_graph.py | C:\ProgettoRAG_DEV\core\formula_graph.py |
| chain_of_thought.py | C:\ProgettoRAG_DEV\core\chain_of_thought.py |
| linter.py | C:\ProgettoRAG_DEV\core\linter.py |
| intent_router.py | C:\ProgettoRAG_DEV\core\intent_router.py |
| formula_builder.py | C:\ProgettoRAG_DEV\core\formula_builder.py |
| winsarp_catalog.json | C:\ProgettoRAG_DEV\data\winsarp_catalog.json |
| winsarp_graph.json | C:\ProgettoRAG_DEV\data\winsarp_graph.json |
| winsarp_graph_enriched.json | C:\ProgettoRAG_DEV\data\winsarp_graph_enriched.json |
| WinSarp_Formule.txt | C:\ProgettoRAG_DEV\documenti\WinSarp\WinSarp_Formule.txt |

## Appendice B: Statistiche del Glossario

| Categoria | Elementi | Note |
|-----------|----------|------|
| CAMPI documentati | ~150 + range | Descrizioni individuali nel FieldRegistry |
| CAMPI range proibiti | 300+ | In 30+ intervalli di forbidden ranges |
| TOTALI K | 45 | K601-K919 con nome e descrizione |
| FORMULE | 56 | 54 reali + 2 placeholder (2125, 2140) |
| INTENT | 34 | Con confidence e builder function |
| CONTRATTI | 3 | Standard, Dirigenti/Quadri, Turnisti |
| CATENE | 9 | Sequenze formula per flusso |
| SUBROUTINE relations | 28+ | Chiamate P e salti R |
| PATTERNS | 48 | Pattern per tipo e categoria |
| SINONIMI | 3 | Solo alias tecnici (55, 58, 71-78) |
| CAUSALI | 24 | Codici (+ 7 tipi orario, + 2 flag) |
| CAMPO70 operations | 22 | Operazioni built-in codici 1-900 |
| PROFILI | 1 | Solo turnista_completo |
| FLUSSI | 12 | 6 IG + 6 FG |
| Vxx labels | 22 | V02-V40 usate nelle formule |
| LINTER rules | 14 | Codici E001-E010, L001-L004 |
| GRAMMAR tokens | 34 | Token nella winsarp_compact.lark |
| Lark productions | 25+ | Produzioni nella winsarp.lark |

---

*Glossario generato il 2026-07-07 dal codebase Ermes Enterprise Knowledge Hub (modulo WinSarp).*
