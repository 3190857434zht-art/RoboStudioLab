import sqlite3
import json
from datetime import datetime

# Path to the database file
DATABASE_FILE = "database/history.db"

def init_db():
    """
    Initialize the database and create the history table.
    If the table already exists, this is a no-op.
    """
    # Ensure the database directory exists
    import os
    os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Create table.
    # status: 'success', 'failed', 'unsimulated'
    # params: all runtime parameters such as number of objects, task description, etc.
    # result: run result including generated code, video reference (not stored directly), log, etc.
    # notes: user-provided notes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL,
        experiment_name TEXT,
        status TEXT NOT NULL,
        algorithm TEXT NOT NULL,
        task_description TEXT,
        timestamp TEXT NOT NULL,
        params TEXT,
        result TEXT,
        notes TEXT
    )
    """)

    # Migration: add columns required for branch/tree structure if they do not already exist
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(history)").fetchall()}
    if "parent_id" not in existing_columns:
        cursor.execute("ALTER TABLE history ADD COLUMN parent_id INTEGER")
    if "node_type" not in existing_columns:
        cursor.execute("ALTER TABLE history ADD COLUMN node_type TEXT DEFAULT 'root'")
    if "is_final" not in existing_columns:
        cursor.execute("ALTER TABLE history ADD COLUMN is_final INTEGER DEFAULT 0")

    scrub_sensitive_history_params(cursor)

    conn.commit()
    conn.close()
    print("Database initialized.")


def scrub_sensitive_history_params(cursor):
    """Remove credentials from existing history params during startup migration."""
    sensitive_keys = {"openai_api_key", "openai_base_url", "api_key", "base_url"}
    rows = cursor.execute("SELECT id, params FROM history WHERE params IS NOT NULL AND params != ''").fetchall()
    for row in rows:
        try:
            params = json.loads(row[1] or "{}")
        except Exception:
            continue
        if not isinstance(params, dict) or not any(key in params for key in sensitive_keys):
            continue
        for key in sensitive_keys:
            params.pop(key, None)
        cursor.execute("UPDATE history SET params = ? WHERE id = ?", (json.dumps(params), row[0]))

def get_db_connection():
    """Return a database connection."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Allows column access by name
    return conn

def get_next_experiment_id():
    """Return the numeric part of the next root experiment ID (No.X)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Query only root entries
    cursor.execute("SELECT experiment_id FROM history WHERE experiment_id GLOB 'No.[0-9]*'")
    records = cursor.fetchall()
    conn.close()
  
    if not records:
        return 1
  
    max_id = 0
    for record in records:
        try:
            # Extract the numeric part after 'No.'
            num_str = record['experiment_id'].split('-')[0].replace('No.', '')
            num = int(num_str)
            if num > max_id:
                max_id = num
        except (ValueError, TypeError, IndexError):
            continue
    return max_id + 1


def add_history_record(record_data: dict):
    """
    Insert a new history record into the database.
    record_data is a dict containing all record fields.
    If parent_id / node_type / is_final are provided, the record is stored as a branch node;
    otherwise it is stored as a root entry.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    params_str = json.dumps(record_data.get("params", {}))
    result_str = json.dumps(record_data.get("result", {}))
    parent_id = record_data.get("parent_id")
    node_type = record_data.get("node_type") or ("branch" if parent_id else "root")
    is_final = int(record_data.get("is_final") or 0)

    cursor.execute(
        """
        INSERT INTO history
            (experiment_id, experiment_name, status, algorithm, task_description,
             timestamp, params, result, notes, parent_id, node_type, is_final)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record_data["experiment_id"],
            record_data.get("experiment_name", record_data["experiment_id"]),
            record_data["status"],
            record_data["algorithm"],
            record_data["task_description"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            params_str,
            result_str,
            record_data.get("notes", "") or "",
            parent_id,
            node_type,
            is_final,
        ),
    )

    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id

def update_record_status(record_id: int, new_status: str, result_data: dict):
    """Update the status and result of an existing record."""
    conn = get_db_connection()
    result_str = json.dumps(result_data)
    conn.execute(
        "UPDATE history SET status = ?, result = ?, timestamp = ? WHERE id = ?",
        (
            new_status,
            result_str,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            record_id
        )
    )
    conn.commit()
    conn.close()

def update_notes(record_id: int, notes: str):
    """Update the notes for a given record."""
    conn = get_db_connection()
    conn.execute("UPDATE history SET notes = ? WHERE id = ?", (notes, record_id))
    conn.commit()
    conn.close()

def get_next_draft_num(parent_id=None):
    """Return the next draft number under the specified root entry."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if parent_id is None:
        cursor.execute(
            """
            SELECT experiment_name FROM history
            WHERE experiment_name LIKE 'Draft-%' OR experiment_name LIKE 'New-Draft-%'
            """
        )
    else:
        cursor.execute(
            """
            SELECT experiment_name FROM history
            WHERE parent_id = ?
              AND (experiment_name LIKE 'Draft-%' OR experiment_name LIKE 'New-Draft-%')
            """,
            (parent_id,),
        )
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        return 1
        
    max_num = 0
    for record in records:
        try:
            draft_name = record['experiment_name']
            if draft_name.startswith('New-Draft-'):
                draft_name = draft_name.replace('New-Draft-', 'Draft-', 1)
            num = int(draft_name.replace('Draft-', ''))
            if num > max_num:
                max_num = num
        except (ValueError, TypeError):
            continue
    return max_num + 1


def get_next_apply_code_num(parent_id=None):
    """Return the next Apply-Code-N number.

    When parent_id is None, only root entries are counted;
    when parent_id is provided, only branches under that root are counted.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if parent_id is None:
        cursor.execute(
            """
            SELECT experiment_name FROM history
            WHERE parent_id IS NULL
              AND experiment_name LIKE 'Apply-Code-%'
            """
        )
    else:
        cursor.execute(
            """
            SELECT experiment_name FROM history
            WHERE parent_id = ?
              AND experiment_name LIKE 'Apply-Code-%'
            """,
            (parent_id,),
        )
    records = cursor.fetchall()
    conn.close()

    max_num = 0
    for record in records:
        try:
            num = int(str(record["experiment_name"]).replace("Apply-Code-", "", 1))
            if num > max_num:
                max_num = num
        except (ValueError, TypeError):
            continue
    return max_num + 1
