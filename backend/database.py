import sqlite3
import json
from datetime import datetime

# 数据库文件路径
DATABASE_FILE = "database/history.db"

def init_db():
    """
    初始化数据库，创建 history 表。
    如果表已存在，则不执行任何操作。
    """
    # 确保 database 文件夹存在
    import os
    os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # 创建表
    # status: 'success', 'failed', 'unsimulated'
    # params: 存储运行时的所有参数，如物体数量、任务描述等
    # result: 存储运行结果，如生成的代码、视频的引用（我们不直接存视频）、日志等
    # notes: 存储用户备注
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

    # 迁移：添加分支/树结构所需的新列（如果不存在）
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
    print("数据库初始化完成。")


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
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # 这让我们可以通过列名访问数据
    return conn

def get_next_experiment_id():
    """获取下一个主实验ID的数字部分 (No.X)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 只查找主干记录
    cursor.execute("SELECT experiment_id FROM history WHERE experiment_id GLOB 'No.[0-9]*'")
    records = cursor.fetchall()
    conn.close()
  
    if not records:
        return 1
  
    max_id = 0
    for record in records:
        try:
            # 只提取 'No.' 后面的数字部分
            num_str = record['experiment_id'].split('-')[0].replace('No.', '')
            num = int(num_str)
            if num > max_id:
                max_id = num
        except (ValueError, TypeError, IndexError):
            continue
    return max_id + 1


def add_history_record(record_data: dict):
    """
    向数据库中添加一条新的历史记录。
    record_data 是一个包含所有记录信息的字典。
    若提供 parent_id / node_type / is_final，则按分支节点入库，
    否则按主干（root）入库。
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
    """更新一个已有记录的状态和结果"""
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
    """更新指定记录的备注"""
    conn = get_db_connection()
    conn.execute("UPDATE history SET notes = ? WHERE id = ?", (notes, record_id))
    conn.commit()
    conn.close()

def get_next_draft_num(parent_id=None):
    """获取指定主条目下一个草稿编号。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    if parent_id is None:
        cursor.execute(
            """
            SELECT experiment_name FROM history
            WHERE experiment_name LIKE '草稿-%' OR experiment_name LIKE '新草稿-%'
            """
        )
    else:
        cursor.execute(
            """
            SELECT experiment_name FROM history
            WHERE parent_id = ?
              AND (experiment_name LIKE '草稿-%' OR experiment_name LIKE '新草稿-%')
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
            if draft_name.startswith('新草稿-'):
                draft_name = draft_name.replace('新草稿-', '草稿-', 1)
            num = int(draft_name.replace('草稿-', ''))
            if num > max_num:
                max_num = num
        except (ValueError, TypeError):
            continue
    return max_num + 1


def get_next_apply_code_num(parent_id=None):
    """获取“应用代码-N”的下一个编号。

    parent_id 为空时只统计主条目；有 parent_id 时只统计该主条目下的分支。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if parent_id is None:
        cursor.execute(
            """
            SELECT experiment_name FROM history
            WHERE parent_id IS NULL
              AND experiment_name LIKE '应用代码-%'
            """
        )
    else:
        cursor.execute(
            """
            SELECT experiment_name FROM history
            WHERE parent_id = ?
              AND experiment_name LIKE '应用代码-%'
            """,
            (parent_id,),
        )
    records = cursor.fetchall()
    conn.close()

    max_num = 0
    for record in records:
        try:
            num = int(str(record["experiment_name"]).replace("应用代码-", "", 1))
            if num > max_num:
                max_num = num
        except (ValueError, TypeError):
            continue
    return max_num + 1
