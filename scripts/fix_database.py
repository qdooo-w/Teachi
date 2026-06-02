import sqlite3
import logging
import sys
import os
from pathlib import Path

# 自动定位项目根目录 (基于脚本所在位置 scripts/fix_database.py)
BASE_DIR = Path(__file__).resolve().parents[1]

# 核心：将项目根目录加入 sys.path，解决 backend 模块导入问题
if str(BASE_DIR) not in sys.path:
    # 使用 insert(0, ...) 确保项目路径优先级最高，防止与系统库冲突
    sys.path.insert(0, str(BASE_DIR))

# 切换当前工作目录到项目根目录
# 这样无论你在哪个目录下执行，脚本内部的相对路径（如 data/project.db）都能正确解析
os.chdir(str(BASE_DIR))

from backend.config import DATABASE_PATH
from backend.db import DatabaseFacade

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def get_expected_schema():
    """定义期望的表结构和列定义。
    格式: { table_name: { column_name: column_definition, ... }, ... }
    """
    return {
        "users": {
            "uuid": "TEXT PRIMARY KEY",
            "username": "TEXT NOT NULL",
            "email": "TEXT NOT NULL UNIQUE",
            "password_hash": "TEXT NOT NULL",
            "created_at": "REAL NOT NULL"
        },
        "projects": {
            "pid": "TEXT PRIMARY KEY",
            "projectname": "TEXT NOT NULL",
            "user_uuid": "TEXT NOT NULL",
            "timestamp": "REAL NOT NULL",
            "created_at": "REAL NOT NULL"
        },
        "sessions": {
            "sid": "TEXT PRIMARY KEY",
            "pid": "TEXT NOT NULL",
            "sessionname": "TEXT NOT NULL",
            "timestamp": "REAL NOT NULL",
            "created_at": "REAL NOT NULL"
        },
        "messages": {
            "msg_id": "TEXT PRIMARY KEY",
            "sid": "TEXT NOT NULL",
            "kind": "TEXT NOT NULL",
            "raw_json": "TEXT NOT NULL",
            "timestamp": "REAL NOT NULL",
            "anchor_msg_id": "TEXT",
            "version": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "REAL NOT NULL"
        },
        "nonces": {
            "nonce": "TEXT PRIMARY KEY",
            "user_uuid": "TEXT NOT NULL",
            "timestamp": "REAL NOT NULL",
            "created_at": "REAL NOT NULL"
        },
        "community_skills": {
            "id": "TEXT PRIMARY KEY",
            "owner_uuid": "TEXT NOT NULL",
            "name": "TEXT NOT NULL",
            "display_name": "TEXT",
            "description": "TEXT NOT NULL",
            "archive_path": "TEXT NOT NULL",
            "license": "TEXT",
            "compatibility": "TEXT",
            "size_bytes": "INTEGER NOT NULL",
            "downloads": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "REAL NOT NULL",
            "updated_at": "REAL NOT NULL"
        },
        "user_model_configs": {
            "config_id": "TEXT PRIMARY KEY",
            "user_uuid": "TEXT NOT NULL",
            "config_name": "TEXT NOT NULL",
            "api_key": "TEXT NOT NULL DEFAULT ''",
            "base_url": "TEXT NOT NULL DEFAULT ''",
            "model_name": "TEXT NOT NULL DEFAULT ''",
            "user_instruction": "TEXT NOT NULL DEFAULT ''",
            "temperature": "REAL",
            "max_tokens": "INTEGER",
            "is_active": "INTEGER NOT NULL DEFAULT 0",
            "supports_vision": "INTEGER NOT NULL DEFAULT 0",
            "top_p": "REAL",
            "frequency_penalty": "REAL",
            "presence_penalty": "REAL",
            "response_format": "TEXT",
            "created_at": "REAL NOT NULL",
            "updated_at": "REAL NOT NULL"
        },
        "attachments": {
            "attachment_id": "TEXT PRIMARY KEY",
            "sid": "TEXT NOT NULL",
            "user_uuid": "TEXT NOT NULL",
            "anchor_msg_id": "TEXT",
            "original_filename": "TEXT NOT NULL",
            "file_hash": "TEXT NOT NULL DEFAULT ''",
            "file_path": "TEXT NOT NULL",
            "mime_type": "TEXT NOT NULL",
            "file_size": "INTEGER NOT NULL DEFAULT 0",
            "description": "TEXT",
            "description_generated_at": "REAL",
            "created_at": "REAL NOT NULL"
        },
        "user_preferences": {
            "user_uuid": "TEXT PRIMARY KEY",
            "theme": "TEXT NOT NULL DEFAULT 'system'",
            "language": "TEXT NOT NULL DEFAULT 'zh-CN'",
            "font_size": "TEXT NOT NULL DEFAULT 'medium'",
            "code_line_numbers": "INTEGER NOT NULL DEFAULT 0",
            "enter_mode": "TEXT NOT NULL DEFAULT 'enter'",
            "loop_max_retries": "INTEGER",
            "test_connection_timeout": "INTEGER",
            "message_history_limit": "INTEGER",
            "updated_at": "REAL NOT NULL"
        }
    }

def fix_database():
    expected_schema = get_expected_schema()
    
    logger.info(f"Target database: {DATABASE_PATH}")
    db = DatabaseFacade(DATABASE_PATH)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. 检查并补全缺失的表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        for table_name, columns in expected_schema.items():
            if table_name not in existing_tables:
                logger.info(f"Table '{table_name}' is missing. Creating...")
                col_defs = [f"{name} {definition}" for name, definition in columns.items()]
                
                # 特殊处理外键关联
                extra_clauses = ""
                if table_name == "projects":
                    extra_clauses = ", FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE"
                elif table_name == "sessions":
                    extra_clauses = ", FOREIGN KEY (pid) REFERENCES projects(pid) ON DELETE CASCADE"
                elif table_name == "messages":
                    extra_clauses = (
                        ", FOREIGN KEY (sid) REFERENCES sessions(sid) ON DELETE CASCADE"
                        ", FOREIGN KEY (anchor_msg_id) REFERENCES messages(msg_id) ON DELETE SET NULL"
                    )
                elif table_name == "nonces":
                    extra_clauses = ", FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE"
                elif table_name == "community_skills":
                    extra_clauses = ", FOREIGN KEY (owner_uuid) REFERENCES users(uuid) ON DELETE CASCADE"
                elif table_name == "user_model_configs":
                    extra_clauses = ", FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE"
                elif table_name == "attachments":
                    extra_clauses = (
                        ", FOREIGN KEY (sid) REFERENCES sessions(sid) ON DELETE CASCADE"
                        ", FOREIGN KEY (anchor_msg_id) REFERENCES messages(msg_id) ON DELETE SET NULL"
                        ", FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE"
                    )
                elif table_name == "user_preferences":
                    extra_clauses = ", FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE"
                
                sql = f"CREATE TABLE {table_name} ({', '.join(col_defs)}{extra_clauses})"
                cursor.execute(sql)
                logger.info(f"Created table '{table_name}'.")
            else:
                # 2. 检查并补全现有表中缺失的列
                cursor.execute(f"PRAGMA table_info({table_name})")
                current_columns = {row[1] for row in cursor.fetchall()}
                
                for col_name, col_def in columns.items():
                    if col_name not in current_columns:
                        logger.info(f"Column '{col_name}' is missing in table '{table_name}'. Adding...")
                        # SQLite 只能一次添加一列，且有限制
                        # ALTER TABLE table_name ADD COLUMN column_definition
                        try:
                            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")
                            logger.info(f"Added column '{col_name}' to table '{table_name}'.")
                        except sqlite3.OperationalError as e:
                            logger.error(f"Failed to add column '{col_name}' to table '{table_name}': {e}")
        
        # 3. 检查缺失的索引
        indexes = [
            ("idx_nonces_timestamp", "nonces(timestamp)"),
            ("idx_community_skills_created_at", "community_skills(created_at)"),
            ("idx_community_skills_downloads", "community_skills(downloads)"),
            ("idx_community_skills_owner", "community_skills(owner_uuid)"),
            ("idx_community_skills_name", "community_skills(name)"),
            ("idx_model_configs_user", "user_model_configs(user_uuid)"),
            ("idx_model_configs_active", "user_model_configs(user_uuid, is_active)"),
            ("idx_attachments_sid", "attachments(sid)"),
            ("idx_attachments_user", "attachments(user_uuid)"),
            ("idx_attachments_anchor", "attachments(anchor_msg_id)"),
            ("idx_attachments_hash", "attachments(file_hash, sid, user_uuid)"),
        ]
        
        for idx_name, idx_def in indexes:
            logger.info(f"Applying index '{idx_name}' if missing...")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")

        conn.commit()
    
    logger.info("Database fix completed successfully.")

if __name__ == "__main__":
    fix_database()
