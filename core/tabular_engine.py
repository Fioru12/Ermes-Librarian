"""core/tabular_engine.py
Motore Sandboxed di Interrogazione e Analisi Dati Tabulari (CSV, Excel XLSX, JSON).

Permette l'esecuzione di query SQL in sola lettura (SELECT, aggregazioni SUM/AVG/COUNT,
filtri WHERE, GROUP BY, ORDER BY) su file CSV ed Excel caricati nelle biblioteche,
senza memorizzare database persistenti aggiuntivi e garantendo isolamento e sicurezza.
"""

from __future__ import annotations

import contextlib
import csv
import io
import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any
from zipfile import ZipFile

_logger = logging.getLogger("ermes.tabular")

# Parole chiave SQL ammesse per interrogazioni in sola lettura
_READONLY_KEYWORDS = {"select", "with", "explain"}
_FORBIDDEN_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "truncate",
    "replace",
    "attach",
    "detach",
    "pragma",
    "reindex",
    "vacuum",
    "transaction",
    "commit",
    "rollback",
    "savepoint",
}


class TabularQueryError(ValueError):
    """Sollevata quando una query tabulare non è valida o non sicura."""


@dataclass
class ColumnInfo:
    name: str
    data_type: str  # TEXT, INTEGER, REAL


@dataclass
class TableSchema:
    table_name: str
    columns: list[ColumnInfo]
    row_count: int
    sample_rows: list[dict[str, Any]]


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_ms: float
    markdown_table: str


def sanitize_column_name(name: str, index: int) -> str:
    """Sanitizza il nome di una colonna per renderlo un identificatore SQL valido."""
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", str(name).strip())
    clean = re.sub(r"_+", "_", clean).strip("_")
    if not clean or clean[0].isdigit():
        clean = f"col_{clean or index}"
    return clean.lower()


def _clean_numeric_str(v: str) -> str:
    """Rimuove separatori delle migliaia e normalizza il separatore decimale a punto."""
    v = v.strip()
    if "," in v and "." in v:
        if v.rfind(".") > v.rfind(","):
            return v.replace(",", "")
        return v.replace(".", "").replace(",", ".")
    if "," in v:
        return v.replace(",", ".")
    return v


def infer_data_type(values: list[str]) -> str:
    """Inferisce il tipo SQLite per una lista di valori campione."""
    non_empty = [v.strip() for v in values if v and v.strip()]
    if not non_empty:
        return "TEXT"

    is_int = True
    for v in non_empty:
        # Se contiene punto o virgola con cifre decimali, non è un intero
        if "." in v or "," in v:
            is_int = False
            break
        try:
            int(v)
        except ValueError:
            is_int = False
            break
    if is_int:
        return "INTEGER"

    is_float = True
    for v in non_empty:
        try:
            float(_clean_numeric_str(v))
        except ValueError:
            is_float = False
            break
    if is_float:
        return "REAL"

    return "TEXT"


def _validate_table_name(table_name: str) -> None:
    """L'identificatore va dentro l'SQL per interpolazione (SQLite non supporta il
    parametro sui nomi di tabella): ogni chiamante futuro di questo motore "sandboxed"
    che passasse un nome non hardcoded lo trasformerebbe in identifier injection.
    """
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table_name):
        raise TabularQueryError(f"Nome tabella non valido: {table_name!r}")


def load_csv_to_sqlite(conn: sqlite3.Connection, table_name: str, content: bytes) -> TableSchema:
    """Carica un file CSV in una tabella SQLite in-memory."""
    _validate_table_name(table_name)
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not all_rows:
        raise TabularQueryError("Il file CSV è vuoto o non contiene righe valide")

    header_raw = all_rows[0]
    data_rows = all_rows[1:] if len(all_rows) > 1 else []

    # Genera colonne sanitizzate
    seen_names: set[str] = set()
    columns: list[ColumnInfo] = []
    for idx, raw_name in enumerate(header_raw, start=1):
        col_name = sanitize_column_name(raw_name, idx)
        unique_name = col_name
        counter = 1
        while unique_name in seen_names:
            unique_name = f"{col_name}_{counter}"
            counter += 1
        seen_names.add(unique_name)

        col_sample = [r[idx - 1] for r in data_rows[:100] if len(r) >= idx]
        col_type = infer_data_type(col_sample)
        columns.append(ColumnInfo(name=unique_name, data_type=col_type))

    # Crea tabella
    col_defs = ", ".join(f'"{col.name}" {col.data_type}' for col in columns)
    # table_name validato da _validate_table_name sopra; col_defs viene da sanitize_column_name.
    conn.execute(f'CREATE TABLE "{table_name}" ({col_defs})')  # nosec B608

    # Inserisci dati
    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'  # nosec B608: table_name validato sopra, i valori passano da conn.execute(insert_sql, params)

    sample_rows: list[dict[str, Any]] = []
    rows_to_insert: list[list[Any]] = []

    for r_idx, row in enumerate(data_rows):
        padded_row: list[Any] = []
        row_dict: dict[str, Any] = {}
        for c_idx, col in enumerate(columns):
            val_str = row[c_idx].strip() if c_idx < len(row) else ""
            if col.data_type == "INTEGER" and val_str:
                try:
                    val: Any = int(val_str.replace(",", ""))
                except ValueError:
                    val = None
            elif col.data_type == "REAL" and val_str:
                try:
                    val = float(val_str.replace(",", "."))
                except ValueError:
                    val = None
            else:
                val = val_str if val_str else None

            padded_row.append(val)
            row_dict[col.name] = val

        rows_to_insert.append(padded_row)
        if r_idx < 5:
            sample_rows.append(row_dict)

    conn.executemany(insert_sql, rows_to_insert)
    conn.commit()

    return TableSchema(
        table_name=table_name,
        columns=columns,
        row_count=len(rows_to_insert),
        sample_rows=sample_rows,
    )


def load_xlsx_to_sqlite(conn: sqlite3.Connection, table_name: str, content: bytes) -> TableSchema:
    """Carica il primo foglio di un file Excel XLSX in una tabella SQLite in-memory."""
    _validate_table_name(table_name)
    from xml.etree import ElementTree

    with ZipFile(io.BytesIO(content)) as archive:
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))  # nosec B314
            shared_strings = ["".join(item.itertext()).strip() for item in root.findall(f"{ns}si")]

        worksheet_paths = sorted(
            name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")
        )
        if not worksheet_paths:
            raise TabularQueryError("Nessun foglio di calcolo trovato nel file XLSX")

        sheet_root = ElementTree.fromstring(archive.read(worksheet_paths[0]))  # nosec B314
        all_rows: list[list[str]] = []

        for row_node in sheet_root.findall(f".//{ns}row"):
            current_row: list[str] = []
            for cell in row_node.findall(f"{ns}c"):
                kind = cell.attrib.get("t", "")
                val_node = cell.find(f"{ns}v")
                val = val_node.text if val_node is not None and val_node.text is not None else ""
                if kind == "s" and val.isdigit() and int(val) < len(shared_strings):
                    val = shared_strings[int(val)]
                elif kind == "inlineStr":
                    val = "".join(cell.itertext()).strip()
                current_row.append(val.strip())
            if any(current_row):
                all_rows.append(current_row)

    if not all_rows:
        raise TabularQueryError("Il foglio Excel è vuoto")

    header_raw = all_rows[0]
    data_rows = all_rows[1:] if len(all_rows) > 1 else []

    seen_names: set[str] = set()
    columns: list[ColumnInfo] = []
    for idx, raw_name in enumerate(header_raw, start=1):
        col_name = sanitize_column_name(raw_name, idx)
        unique_name = col_name
        counter = 1
        while unique_name in seen_names:
            unique_name = f"{col_name}_{counter}"
            counter += 1
        seen_names.add(unique_name)

        col_sample = [r[idx - 1] for r in data_rows[:100] if len(r) >= idx]
        col_type = infer_data_type(col_sample)
        columns.append(ColumnInfo(name=unique_name, data_type=col_type))

    col_defs = ", ".join(f'"{col.name}" {col.data_type}' for col in columns)
    # table_name validato da _validate_table_name sopra; col_defs viene da sanitize_column_name.
    conn.execute(f'CREATE TABLE "{table_name}" ({col_defs})')  # nosec B608

    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'  # nosec B608: table_name validato sopra, i valori passano da conn.execute(insert_sql, params)

    sample_rows: list[dict[str, Any]] = []
    rows_to_insert: list[list[Any]] = []

    for r_idx, row in enumerate(data_rows):
        padded_row: list[Any] = []
        row_dict: dict[str, Any] = {}
        for c_idx, col in enumerate(columns):
            val_str = row[c_idx].strip() if c_idx < len(row) else ""
            if col.data_type == "INTEGER" and val_str:
                try:
                    num_val: Any = int(val_str.replace(",", ""))
                except ValueError:
                    num_val = None
            elif col.data_type == "REAL" and val_str:
                try:
                    num_val = float(val_str.replace(",", "."))
                except ValueError:
                    num_val = None
            else:
                num_val = val_str if val_str else None

            padded_row.append(num_val)
            row_dict[col.name] = num_val

        rows_to_insert.append(padded_row)
        if r_idx < 5:
            sample_rows.append(row_dict)

    conn.executemany(insert_sql, rows_to_insert)
    conn.commit()

    return TableSchema(
        table_name=table_name,
        columns=columns,
        row_count=len(rows_to_insert),
        sample_rows=sample_rows,
    )


def validate_sql_query(query: str) -> str:
    """Verifica che la query SQL sia rigorosamente in sola lettura e restituisce la query normalizzata."""
    clean = query.strip().rstrip(";").strip()
    if not clean:
        raise TabularQueryError("Query SQL vuota")

    # Controlla multi-statement (punto e virgola multiplo)
    if ";" in clean:
        raise TabularQueryError("Query multi-istruzione non consentite")

    first_word = clean.split()[0].lower()
    if first_word not in _READONLY_KEYWORDS:
        raise TabularQueryError(f"Istruzione '{first_word.upper()}' non consentita: ammesse solo query SELECT")

    tokens = set(re.findall(r"\b[a-zA-Z_]+\b", clean.lower()))
    forbidden_used = tokens.intersection(_FORBIDDEN_KEYWORDS)
    if forbidden_used:
        raise TabularQueryError(f"Parole chiave vietate rilevate nella query: {', '.join(forbidden_used)}")

    return clean


def format_markdown_table(columns: list[str], rows: list[list[Any]], max_rows: int = 50) -> str:
    """Formatta i risultati SQL in una tabella Markdown pulita."""
    if not columns:
        return ""

    header_line = "| " + " | ".join(str(c) for c in columns) + " |"
    separator_line = "| " + " | ".join(["---"] * len(columns)) + " |"
    formatted_rows: list[str] = [header_line, separator_line]

    display_rows = rows[:max_rows]
    for r in display_rows:
        row_cells = [str(cell) if cell is not None else "" for cell in r]
        # Padded to match column length
        if len(row_cells) < len(columns):
            row_cells.extend([""] * (len(columns) - len(row_cells)))
        formatted_rows.append("| " + " | ".join(row_cells[: len(columns)]) + " |")

    if len(rows) > max_rows:
        formatted_rows.append(f"\n*... e altre {len(rows) - max_rows} righe*")

    return "\n".join(formatted_rows)


class TabularEngine:
    """Motore isolato in-memory per il caricamento ed interrogazione di dati tabulari."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        # Timeout per prevenire DoS su query complesse
        self.conn.set_progress_handler(self._check_progress, 10_000)
        self._step_count = 0

    def _check_progress(self) -> int:
        self._step_count += 1
        if self._step_count > 500:  # ~5M instructions max
            return 1  # Interrompe l'esecuzione
        return 0

    def load_document(self, content: bytes, filename: str, table_name: str = "data") -> TableSchema:
        """Carica un file tabulare (CSV o XLSX) nella connessione in-memory."""
        suffix = filename.split(".")[-1].lower() if "." in filename else ""
        if suffix in {"csv", "tsv", "txt"}:
            return load_csv_to_sqlite(self.conn, table_name, content)
        elif suffix in {"xlsx"}:
            return load_xlsx_to_sqlite(self.conn, table_name, content)
        else:
            raise TabularQueryError(f"Estensione '.{suffix}' non supportata per l'analisi tabulare SQL")

    def execute_query(self, query: str) -> QueryResult:
        """Esegue una query SQL validata e restituisce i risultati formattati."""
        validate_sql_query(query)
        self._step_count = 0

        t0 = time.perf_counter()
        try:
            cursor = self.conn.execute(query)
            col_names = [d[0] for d in cursor.description] if cursor.description else []
            raw_rows = cursor.fetchall()
            execution_ms = (time.perf_counter() - t0) * 1000.0

            rows_list = [[r[c] for c in col_names] for r in raw_rows]
            md_table = format_markdown_table(col_names, rows_list)

            return QueryResult(
                columns=col_names,
                rows=rows_list,
                row_count=len(rows_list),
                execution_ms=round(execution_ms, 2),
                markdown_table=md_table,
            )
        except sqlite3.OperationalError as e:
            raise TabularQueryError(f"Errore di esecuzione SQL: {e}") from e
        except Exception as e:
            raise TabularQueryError(f"Errore inatteso nella query: {e}") from e

    def close(self) -> None:
        """Chiude la connessione SQLite."""
        with contextlib.suppress(Exception):
            self.conn.close()


def query_tabular_data(content: bytes, filename: str, query: str, table_name: str = "data") -> QueryResult:
    """Funzione di alto livello per caricare ed eseguire una query tabulare in un unico passaggio isolato."""
    engine = TabularEngine()
    try:
        engine.load_document(content, filename, table_name=table_name)
        return engine.execute_query(query)
    finally:
        engine.close()


def get_tabular_schema(content: bytes, filename: str, table_name: str = "data") -> TableSchema:
    """Restituisce lo schema e il campione delle prime 5 righe per un file tabulare."""
    engine = TabularEngine()
    try:
        return engine.load_document(content, filename, table_name=table_name)
    finally:
        engine.close()
