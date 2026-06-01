from __future__ import annotations

import sqlite3
import uuid
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_core import to_json

logger = logging.getLogger(__name__)

class _DataBase:
    """数据对象基类，统一访问根 Facade 的连接与工具能力。"""

    def __init__(self, root: "DatabaseFacade"):
        self._root = root

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._root.db_cursor() as cursor:
            yield cursor

    def _row_to_dict(self, row: sqlite3.Row | None) -> dict | None:
        return self._root._row_to_dict(row)

    def _now_timestamp(self) -> float:
        return self._root._now_timestamp()

class UsersFacade(_DataBase):
    def create(self, username: str, email: str, password_hash: str) -> dict:
        user_uuid = str(uuid.uuid4())
        created_at = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (uuid, username, email, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_uuid, username, email, password_hash, created_at),
            )
        user = self.get_by_uuid(user_uuid)
        if user is None:
            raise RuntimeError("User was inserted but could not be loaded.")
        return user

    def get_by_email(self, email: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT uuid, username, email, password_hash, created_at FROM users WHERE email = ?",
                (email,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def get_by_uuid(self, user_uuid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT uuid, username, email, password_hash, created_at FROM users WHERE uuid = ?",
                (user_uuid,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def delete_by_uuid(self, user_uuid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE uuid = ?", (user_uuid,))
            affected = cursor.rowcount
        return affected > 0

    def update_username(self, user_uuid: str, username: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE users SET username = ? WHERE uuid = ?",
                (username, user_uuid),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_by_uuid(user_uuid)

    def update_password(self, user_uuid: str, password_hash: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE uuid = ?",
                (password_hash, user_uuid),
            )
            affected = cursor.rowcount
        return affected > 0

class ProjectsFacade(_DataBase):
    def create(self, projectname: str, user_uuid: str) -> dict:
        pid = str(uuid.uuid4())
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO projects (pid, projectname, user_uuid, timestamp, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pid, projectname, user_uuid, now_ts, now_ts),
            )
        project = self.get_by_id(pid)
        if project is None:
            raise RuntimeError("Project was inserted but could not be loaded.")
        return project

    def list_by_user(self, user_uuid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT pid, projectname, user_uuid, timestamp, created_at
                FROM projects
                WHERE user_uuid = ?
                ORDER BY timestamp DESC
                """,
                (user_uuid,),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_by_id(self, pid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT pid, projectname, user_uuid, timestamp, created_at FROM projects WHERE pid = ?",
                (pid,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def get_for_user(self, pid: str, user_uuid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT pid, projectname, user_uuid, timestamp, created_at
                FROM projects
                WHERE pid = ? AND user_uuid = ?
                """,
                (pid, user_uuid),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def delete_for_user(self, pid: str, user_uuid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM projects WHERE pid = ? AND user_uuid = ?",
                (pid, user_uuid),
            )
            affected = cursor.rowcount
        return affected > 0

    def update_name_for_user(self, pid: str, user_uuid: str, projectname: str) -> dict | None:
        """改名成功返回最新记录，项目不存在或不属于该用户则返回 None。"""
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE projects
                SET projectname = ?, timestamp = ?
                WHERE pid = ? AND user_uuid = ?
                """,
                (projectname, now_ts, pid, user_uuid),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_for_user(pid=pid, user_uuid=user_uuid)

class SessionsFacade(_DataBase):
    def create(self, pid: str, sessionname: str) -> dict:
        sid = str(uuid.uuid4())
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sessions (sid, pid, sessionname, timestamp, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sid, pid, sessionname, now_ts, now_ts),
            )
        session = self.get_by_id(sid)
        if session is None:
            raise RuntimeError("Session was inserted but could not be loaded.")
        return session

    def touch_timestamp(self, sid: str) -> bool:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE sessions SET timestamp = ? WHERE sid = ?",
                (now_ts, sid),
            )
            affected = cursor.rowcount
        return affected > 0

    def list_by_project(self, pid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT sid, pid, sessionname, timestamp, created_at
                FROM sessions
                WHERE pid = ?
                ORDER BY timestamp DESC
                """,
                (pid,),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_by_id(self, sid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT sid, pid, sessionname, timestamp, created_at FROM sessions WHERE sid = ?",
                (sid,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def get_for_user(self, sid: str, user_uuid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT s.sid, s.pid, s.sessionname, s.timestamp, s.created_at
                FROM sessions AS s
                JOIN projects AS p ON s.pid = p.pid
                WHERE s.sid = ? AND p.user_uuid = ?
                """,
                (sid, user_uuid),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def list_by_user(self, user_uuid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT s.sid, s.pid, s.sessionname, s.timestamp, s.created_at
                FROM sessions AS s
                JOIN projects AS p ON s.pid = p.pid
                WHERE p.user_uuid = ?
                ORDER BY s.timestamp DESC
                """,
                (user_uuid,),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def delete_by_id(self, sid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
            affected = cursor.rowcount
        return affected > 0

    def delete_for_user(self, sid: str, user_uuid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM sessions
                WHERE sid = ?
                  AND pid IN (SELECT pid FROM projects WHERE user_uuid = ?)
                """,
                (sid, user_uuid),
            )
            affected = cursor.rowcount
        return affected > 0

    def update_name_for_user(self, sid: str, user_uuid: str, sessionname: str) -> dict | None:
        """改名成功返回最新记录，会话不存在或不属于该用户则返回 None。"""
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE sessions
                SET sessionname = ?, timestamp = ?
                WHERE sid = ?
                  AND pid IN (SELECT pid FROM projects WHERE user_uuid = ?)
                """,
                (sessionname, now_ts, sid, user_uuid),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_for_user(sid=sid, user_uuid=user_uuid)

class MessagesFacade(_DataBase):
    @staticmethod
    def _serialize_message(message: ModelMessage) -> str:
        return to_json(message).decode("utf-8")

    def create(
        self,
        sid: str,
        kind: str,
        raw_json: str,
        anchor_msg_id: str | None = None,
        version: int = 0,
    ) -> dict:
        """新增消息。

        version 含义：0 表示当前活跃版本；>0 表示已被新一次 regenerate 推到旧版位的历史版本。
        anchor_msg_id 含义：turn anchor，同一回合内 user/tool_call/tool_result/assistant 共享。
        - 第一条 user 消息会被建表后立刻回填为自身的 msg_id（self-reference）。
        - 同一 anchor 下，(anchor_msg_id, version, kind, timestamp) 标识一条具体消息。
        """
        msg_id = str(uuid.uuid4())
        message_timestamp = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO messages (msg_id, sid, kind, raw_json, timestamp, anchor_msg_id, version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg_id,
                    sid,
                    kind,
                    raw_json,
                    message_timestamp,
                    anchor_msg_id,
                    version,
                    message_timestamp,
                ),
            )
        message = self.get_by_id(msg_id)
        if message is None:
            raise RuntimeError("Message was inserted but could not be loaded.")
        return message

    def create_for_user(
        self,
        sid: str,
        user_uuid: str,
        kind: str,
        raw_json: str,
        anchor_msg_id: str | None = None,
        version: int = 0,
    ) -> dict:
        owned_session = self._root.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
        if owned_session is None:
            raise PermissionError("Session does not belong to the current user.")
        return self.create(
            sid=sid,
            kind=kind,
            raw_json=raw_json,
            anchor_msg_id=anchor_msg_id,
            version=version,
        )

    def set_self_anchor(self, msg_id: str) -> None:
        """把消息的 anchor_msg_id 回填为自身（用于 turn 第一条 user 消息）。"""
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE messages SET anchor_msg_id = msg_id WHERE msg_id = ? AND anchor_msg_id IS NULL",
                (msg_id,),
            )

    def get_by_id(self, msg_id: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT msg_id, sid, kind, raw_json, timestamp, anchor_msg_id, version, created_at
                FROM messages
                WHERE msg_id = ?
                """,
                (msg_id,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def get_for_user(self, msg_id: str, user_uuid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT m.msg_id, m.sid, m.kind, m.raw_json, m.timestamp, m.anchor_msg_id, m.version, m.created_at
                FROM messages AS m
                JOIN sessions AS s ON m.sid = s.sid
                JOIN projects AS p ON s.pid = p.pid
                WHERE m.msg_id = ? AND p.user_uuid = ?
                """,
                (msg_id, user_uuid),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def list_by_session(self, sid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT m.msg_id, m.sid, m.kind, m.raw_json, m.timestamp, m.anchor_msg_id, m.version, m.created_at
                FROM messages AS m
                LEFT JOIN messages AS a ON m.anchor_msg_id = a.msg_id
                WHERE m.sid = ?
                ORDER BY COALESCE(a.timestamp, m.timestamp) ASC, m.timestamp ASC
                """,
                (sid,),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def list_by_session_for_user(self, sid: str, user_uuid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT m.msg_id, m.sid, m.kind, m.raw_json, m.timestamp, m.anchor_msg_id, m.version, m.created_at
                FROM messages AS m
                JOIN sessions AS s ON m.sid = s.sid
                JOIN projects AS p ON s.pid = p.pid
                LEFT JOIN messages AS a ON m.anchor_msg_id = a.msg_id
                WHERE m.sid = ? AND p.user_uuid = ?
                ORDER BY COALESCE(a.timestamp, m.timestamp) ASC, m.timestamp ASC
                """,
                (sid, user_uuid),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def list_active_by_session_for_user(self, sid: str, user_uuid: str) -> list[dict]:
        """加载会话内 version=0 的活跃消息，按"回合发起时间，回合内消息时间"双键升序。

        用于 LOAD_HISTORY 节点构造模型上下文与 GET /sessions/{sid}/messages：
        - 排序键用 anchor.timestamp 而非消息自身 timestamp，确保 regenerate 写入的新消息
          回到原回合在历史中的位置，而不是被推到列表末尾。
        """
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT m.msg_id, m.sid, m.kind, m.raw_json, m.timestamp, m.anchor_msg_id, m.version, m.created_at
                FROM messages AS m
                JOIN sessions AS s ON m.sid = s.sid
                JOIN projects AS p ON s.pid = p.pid
                LEFT JOIN messages AS a ON m.anchor_msg_id = a.msg_id
                WHERE m.sid = ? AND p.user_uuid = ? AND m.version = 0
                ORDER BY COALESCE(a.timestamp, m.timestamp) ASC, m.timestamp ASC
                """,
                (sid, user_uuid),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def list_by_session_page(self, sid: str, limit: int = 20, offset: int = 0) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT m.msg_id, m.sid, m.kind, m.raw_json, m.timestamp, m.anchor_msg_id, m.version, m.created_at
                FROM messages AS m
                LEFT JOIN messages AS a ON m.anchor_msg_id = a.msg_id
                WHERE m.sid = ?
                ORDER BY COALESCE(a.timestamp, m.timestamp) ASC, m.timestamp ASC
                LIMIT ? OFFSET ?
                """,
                (sid, limit, offset),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def list_by_session_page_for_user(
        self,
        sid: str,
        user_uuid: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT m.msg_id, m.sid, m.kind, m.raw_json, m.timestamp, m.anchor_msg_id, m.version, m.created_at
                FROM messages AS m
                JOIN sessions AS s ON m.sid = s.sid
                JOIN projects AS p ON s.pid = p.pid
                LEFT JOIN messages AS a ON m.anchor_msg_id = a.msg_id
                WHERE m.sid = ? AND p.user_uuid = ?
                ORDER BY COALESCE(a.timestamp, m.timestamp) ASC, m.timestamp ASC
                LIMIT ? OFFSET ?
                """,
                (sid, user_uuid, limit, offset),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def count_by_session(self, sid: str) -> int:
        with self._cursor() as cursor:
            cursor.execute("SELECT COUNT(1) AS total FROM messages WHERE sid = ?", (sid,))
            row = cursor.fetchone()
        return int(row["total"]) if row else 0

    def count_by_session_for_user(self, sid: str, user_uuid: str) -> int:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(1) AS total
                FROM messages AS m
                JOIN sessions AS s ON m.sid = s.sid
                JOIN projects AS p ON s.pid = p.pid
                WHERE m.sid = ? AND p.user_uuid = ?
                """,
                (sid, user_uuid),
            )
            row = cursor.fetchone()
        return int(row["total"]) if row else 0

    def delete_by_id(self, msg_id: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM messages WHERE msg_id = ?", (msg_id,))
            affected = cursor.rowcount
        return affected > 0

    def delete_for_user(self, msg_id: str, user_uuid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM messages
                WHERE msg_id = ?
                    AND sid IN (
                        SELECT s.sid
                        FROM sessions AS s
                        JOIN projects AS p ON s.pid = p.pid
                        WHERE p.user_uuid = ?
                    )
                """,
                (msg_id, user_uuid),
            )
            affected = cursor.rowcount
        return affected > 0

    def bump_versions_for_anchor(self, anchor_msg_id: str) -> int:
        """把同一 turn anchor 下所有消息的 version 自增 1。

        regenerate 调用前执行：把当前活跃组（version=0）整体推到 version=1，
        随后写入的新消息以 version=0 占据活跃位。
        """
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE messages SET version = version + 1 WHERE anchor_msg_id = ?",
                (anchor_msg_id,),
            )
            affected = cursor.rowcount
        return affected

    def delete_active_turn(self, *, anchor_msg_id: str, user_uuid: str) -> int:
        """删除某 anchor 当前活跃版本（version=0）的整组消息。

        范围：同 anchor + version=0 的所有 kind（user 自引用本条 + tool_call / tool_result /
        assistant / agent_response）。历史版本（version>=1）保留，可通过版本切换访问。

        归属校验：用户必须拥有 sid 所在的项目，否则 0 affected。
        """
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM messages
                WHERE anchor_msg_id = ? AND version = 0
                    AND sid IN (
                        SELECT s.sid
                        FROM sessions AS s
                        JOIN projects AS p ON s.pid = p.pid
                        WHERE p.user_uuid = ?
                    )
                """,
                (anchor_msg_id, user_uuid),
            )
            affected = cursor.rowcount
        return affected

    def list_versions(self, anchor_msg_id: str, user_uuid: str) -> list[dict]:
        """列出同一 anchor 下的所有消息（含历史版本与当前活跃版本）。

        前端可按 (version, kind, timestamp) 自行重组各版本回合。
        """
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT m.msg_id, m.sid, m.kind, m.raw_json, m.timestamp, m.anchor_msg_id, m.version, m.created_at
                FROM messages AS m
                JOIN sessions AS s ON m.sid = s.sid
                JOIN projects AS p ON s.pid = p.pid
                WHERE m.anchor_msg_id = ? AND p.user_uuid = ?
                ORDER BY m.version ASC, m.timestamp ASC
                """,
                (anchor_msg_id, user_uuid),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def swap_version_group(self, msg_id: str, user_uuid: str) -> bool:
        """把 msg_id 所在版本与当前活跃版本（version=0）整组对调。

        语义：找到 msg_id 的 (anchor, version=v)，若 v == 0 直接成功；
        否则把 anchor 下所有 version=0 的记录改为 v，所有 version=v 的记录改为 0。
        整组 swap 保证 (user, tool_call, tool_result, assistant) 在版本切换后仍属于同一回合。
        """
        msg = self.get_for_user(msg_id=msg_id, user_uuid=user_uuid)
        if msg is None:
            return False

        anchor = msg.get("anchor_msg_id")
        target_version = msg.get("version")
        if not anchor or target_version is None:
            return False
        if int(target_version) == 0:
            return True

        sentinel = -1  # 临时占位，避免 UPDATE 顺序导致两组撞车
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE messages SET version = ? WHERE anchor_msg_id = ? AND version = 0",
                (sentinel, anchor),
            )
            cursor.execute(
                "UPDATE messages SET version = 0 WHERE anchor_msg_id = ? AND version = ?",
                (anchor, target_version),
            )
            cursor.execute(
                "UPDATE messages SET version = ? WHERE anchor_msg_id = ? AND version = ?",
                (target_version, anchor, sentinel),
            )
        return True

    def save_agent_messages(
        self,
        *,
        sid: str,
        user_uuid: str,
        new_messages: list[ModelMessage],
        is_final_turn: bool = False,
        anchor_msg_id: str | None = None,
    ) -> tuple[str | None, str | None]:
        """保存 Agent 一个回合产生的消息列表。

        参数:
            anchor_msg_id: 回合锚点。
                - None 表示首次发送：本回合第一条 user 消息会被回填为自身 msg_id 作为新 anchor。
                - 非 None 表示 regenerate：调用方应已对该 anchor 调用过 bump_versions_for_anchor，
                  本次写入的全部消息共享此 anchor 且 version=0。
        返回:
            (final_msg_id, anchor_msg_id)。final_msg_id 仅在 is_final_turn 且有 assistant 消息时返回。
        """
        final_msg_id: str | None = None
        current_anchor = anchor_msg_id

        def _insert(kind: str, raw: str) -> dict:
            row = self.create_for_user(
                sid=sid,
                user_uuid=user_uuid,
                kind=kind,
                raw_json=raw,
                anchor_msg_id=current_anchor,
                version=0,
            )
            return row

        for message in new_messages:
            if isinstance(message, ModelResponse):
                has_tool_call = any(isinstance(part, ToolCallPart) for part in message.parts)
                if has_tool_call:
                    _insert("tool_call", self._serialize_message(message))
                else:
                    if is_final_turn:
                        row = _insert("assistant", self._serialize_message(message))
                        final_msg_id = str(row["msg_id"])
                    else:
                        _insert("agent_response", self._serialize_message(message))
            elif isinstance(message, ModelRequest):
                has_tool_return = any(isinstance(part, ToolReturnPart) for part in message.parts)
                if has_tool_return:
                    _insert("tool_result", self._serialize_message(message))
                elif any(isinstance(part, UserPromptPart) for part in message.parts):
                    row = _insert("user", self._serialize_message(message))
                    if current_anchor is None:
                        # 首次发送：把这条 user 消息作为本回合 anchor
                        new_anchor = str(row["msg_id"])
                        self.set_self_anchor(new_anchor)
                        current_anchor = new_anchor

        return final_msg_id, current_anchor

class AccessFacade(_DataBase):
    """跨领域访问校验聚合。"""

    def validate_project_session(self, *, user_uuid: str, pid: str, sid: str) -> bool:
        project = self._root.projects.get_for_user(pid=pid, user_uuid=user_uuid)
        if project is None:
            return False

        session = self._root.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
        if session is None:
            return False

        return session.get("pid") == pid

class NoncesFacade(_DataBase):
    """
    Nonce 管理（防重放攻击）。
    """

    def is_nonce_used(self, nonce: str) -> bool:
        """检查 nonce 是否已被使用"""
        with self._cursor() as cursor:
            cursor.execute("SELECT 1 FROM nonces WHERE nonce = ?", (nonce,))
            row = cursor.fetchone()
        return row is not None

    def use_nonce(self, nonce: str, user_uuid: str, timestamp: float) -> bool:
        """记录并使用 nonce"""
        created_at = self._now_timestamp()
        try:
            with self._cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO nonces (nonce, user_uuid, timestamp, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (nonce, user_uuid, timestamp, created_at),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def clean_old_nonces(self, before_timestamp: float) -> int:
        """从数据库中删除过期的 nonce"""
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM nonces WHERE timestamp < ?", (before_timestamp,))
            affected = cursor.rowcount
        return affected

class ModelConfigsFacade(_DataBase):
    """用户模型配置管理。

    每个用户可以配置自己的模型参数（API Key、Base URL、模型名称、温度等），
    也可以使用全局默认配置。用户配置优先级高于环境变量默认值。
    """

    _COLUMNS = (
        "config_id, user_uuid, config_name, api_key, base_url, model_name, "
        "user_instruction, temperature, max_tokens, is_active, supports_vision, created_at, updated_at"
    )

    def create(
        self,
        user_uuid: str,
        config_name: str,
        api_key: str = "",
        base_url: str = "",
        model_name: str = "",
        user_instruction: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        is_active: bool = False,
        supports_vision: bool = False,
    ) -> dict:
        config_id = str(uuid.uuid4())
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_model_configs
                    (config_id, user_uuid, config_name, api_key, base_url, model_name,
                     user_instruction, temperature, max_tokens, is_active,
                     supports_vision, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config_id,
                    user_uuid,
                    config_name,
                    api_key,
                    base_url,
                    model_name,
                    user_instruction,
                    temperature,
                    max_tokens,
                    1 if is_active else 0,
                    1 if supports_vision else 0,
                    now_ts,
                    now_ts,
                ),
            )
        config = self.get_by_id(config_id)
        if config is None:
            raise RuntimeError("Model config was inserted but could not be loaded.")
        return config

    def get_by_id(self, config_id: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM user_model_configs WHERE config_id = ?",
                (config_id,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def get_for_user(self, config_id: str, user_uuid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM user_model_configs WHERE config_id = ? AND user_uuid = ?",
                (config_id, user_uuid),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def list_by_user(self, user_uuid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM user_model_configs WHERE user_uuid = ? ORDER BY created_at ASC",
                (user_uuid,),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_active_for_user(self, user_uuid: str) -> dict | None:
        """获取用户当前激活的模型配置。如果没有激活配置则返回 None。"""
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM user_model_configs WHERE user_uuid = ? AND is_active = 1 LIMIT 1",
                (user_uuid,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def update_for_user(
        self,
        config_id: str,
        user_uuid: str,
        *,
        config_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        user_instruction: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        supports_vision: bool | None = None,
    ) -> dict | None:
        """更新模型配置，仅更新非 None 的字段。"""
        updates: list[str] = []
        params: list = []

        if config_name is not None:
            updates.append("config_name = ?")
            params.append(config_name)
        if api_key is not None:
            updates.append("api_key = ?")
            params.append(api_key)
        if base_url is not None:
            updates.append("base_url = ?")
            params.append(base_url)
        if model_name is not None:
            updates.append("model_name = ?")
            params.append(model_name)
        if user_instruction is not None:
            updates.append("user_instruction = ?")
            params.append(user_instruction)
        if temperature is not None:
            updates.append("temperature = ?")
            params.append(temperature)
        if max_tokens is not None:
            updates.append("max_tokens = ?")
            params.append(max_tokens)
        if supports_vision is not None:
            updates.append("supports_vision = ?")
            params.append(1 if supports_vision else 0)

        if not updates:
            return self.get_for_user(config_id, user_uuid)

        updates.append("updated_at = ?")
        params.append(self._now_timestamp())
        params.extend([config_id, user_uuid])

        set_clause = ", ".join(updates)
        with self._cursor() as cursor:
            cursor.execute(
                f"UPDATE user_model_configs SET {set_clause} WHERE config_id = ? AND user_uuid = ?",
                params,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_for_user(config_id, user_uuid)

    def set_active_for_user(self, config_id: str, user_uuid: str) -> dict | None:
        """将指定配置设为激活状态，同时取消该用户其他配置的激活状态。

        使用 CASE WHEN 单条 SQL 原子完成切换，避免两条 UPDATE 之间的并发窗口。
        若目标不存在或不属于该用户，不执行任何写入，直接返回 None。
        """
        # 先验证目标配置存在且属于该用户
        target = self.get_for_user(config_id, user_uuid)
        if target is None:
            return None

        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            # 单条 SQL 原子操作：属于该用户的所有配置，目标设为 1，其余设为 0
            cursor.execute(
                """
                UPDATE user_model_configs
                SET is_active = CASE WHEN config_id = ? THEN 1 ELSE 0 END,
                    updated_at = ?
                WHERE user_uuid = ?
                  AND (is_active = 1 OR config_id = ?)
                """,
                (config_id, now_ts, user_uuid, config_id),
            )
        return self.get_for_user(config_id, user_uuid)

    def deactivate_all_for_user(self, user_uuid: str) -> bool:
        """取消用户所有配置的激活状态（回到全局默认配置）。"""
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE user_model_configs SET is_active = 0, updated_at = ? WHERE user_uuid = ? AND is_active = 1",
                (now_ts, user_uuid),
            )
            affected = cursor.rowcount
        return affected > 0

    def delete_for_user(self, config_id: str, user_uuid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM user_model_configs WHERE config_id = ? AND user_uuid = ?",
                (config_id, user_uuid),
            )
            affected = cursor.rowcount
        return affected > 0

    def user_model_config_supports_vision(self, user_uuid: str) -> bool:
        """检查用户当前激活的配置是否支持视觉。"""
        active_config = self.get_active_for_user(user_uuid)
        if active_config is None:
            return False
        return bool(active_config.get("supports_vision", 0))

class UserPreferencesFacade(_DataBase):
    """用户偏好设置管理。"""

    _COLUMNS = "user_uuid, enter_mode, updated_at"

    def get_for_user(self, user_uuid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM user_preferences WHERE user_uuid = ?",
                (user_uuid,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def upsert_for_user(self, user_uuid: str, *, enter_mode: str | None = None) -> dict:
        existing = self.get_for_user(user_uuid)
        now_ts = self._now_timestamp()

        if existing is None:
            em = enter_mode or "enter"
            with self._cursor() as cursor:
                cursor.execute(
                    "INSERT INTO user_preferences (user_uuid, enter_mode, updated_at) VALUES (?, ?, ?)",
                    (user_uuid, em, now_ts),
                )
        else:
            updates = []
            params = []
            if enter_mode is not None:
                updates.append("enter_mode = ?")
                params.append(enter_mode)
            if updates:
                updates.append("updated_at = ?")
                params.append(now_ts)
                params.append(user_uuid)
                set_clause = ", ".join(updates)
                with self._cursor() as cursor:
                    cursor.execute(
                        f"UPDATE user_preferences SET {set_clause} WHERE user_uuid = ?",
                        params,
                    )
        return self.get_for_user(user_uuid)

class CommunitySkillsFacade(_DataBase):
    """社区技能广场。每条记录指向一份归档 skill 文件夹。

    设计取舍：
    - skill 内容本体存放在 archived_skill/{id}/，数据库只保存路径和展示元信息。
    - 同作者可重复发布同名 skill：每次 publish 都是独立 id；老条目作者可手动删除。
    - 下载时把归档文件夹 copy 到用户私有目录，作者删除后已下载副本不受影响（解耦）。
    """

    _COLUMNS = (
        "id, owner_uuid, name, display_name, description, archive_path, license, compatibility, "
        "size_bytes, downloads, created_at, updated_at"
    )

    def create(
        self,
        *,
        owner_uuid: str,
        name: str,
        display_name: str | None = None,
        description: str,
        archive_path: str,
        size_bytes: int,
        license: str | None = None,
        compatibility: str | None = None,
        skill_id: str | None = None,
    ) -> dict:
        skill_id = skill_id or str(uuid.uuid4())
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute("PRAGMA table_info(community_skills)")
            table_columns = {row["name"] for row in cursor.fetchall()}
            if "body_md" in table_columns:
                insert_columns = (
                    "id, owner_uuid, name, display_name, description, archive_path, body_md, "
                    "license, compatibility, size_bytes, downloads, created_at, updated_at"
                )
                values = (
                    skill_id,
                    owner_uuid,
                    name,
                    display_name,
                    description,
                    archive_path,
                    "",
                    license,
                    compatibility,
                    size_bytes,
                    0,
                    now_ts,
                    now_ts,
                )
            else:
                insert_columns = self._COLUMNS
                values = (
                    skill_id,
                    owner_uuid,
                    name,
                    display_name,
                    description,
                    archive_path,
                    license,
                    compatibility,
                    size_bytes,
                    0,
                    now_ts,
                    now_ts,
                )
            cursor.execute(
                f"INSERT INTO community_skills ({insert_columns}) VALUES ({','.join(['?'] * len(values))})",
                values,
            )
        record = self.get_by_id(skill_id)
        if record is None:
            raise RuntimeError("Community skill was inserted but could not be loaded.")
        return record

    def get_by_id(self, skill_id: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM community_skills WHERE id = ?",
                (skill_id,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def list(
        self,
        *,
        keyword: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort: str = "popular",
    ) -> list[dict]:
        """列表查询。

        sort:
            - "popular"（默认）：downloads DESC, created_at DESC
            - "newest"        ：created_at DESC
        keyword 不为空时，按 name/display_name/description 过滤（大小写不敏感）。
        """
        if sort == "newest":
            order_clause = "ORDER BY created_at DESC"
        else:
            order_clause = "ORDER BY downloads DESC, created_at DESC"

        params: list = []
        where_clause = ""
        if keyword:
            like = f"%{keyword.strip()}%"
            where_clause = "WHERE (name LIKE ? OR display_name LIKE ? OR description LIKE ?)"
            params.extend([like, like, like])
        params.extend([int(limit), int(offset)])

        sql = (
            f"SELECT {self._COLUMNS} FROM community_skills "
            f"{where_clause} {order_clause} LIMIT ? OFFSET ?"
        )
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def count(self, *, keyword: str | None = None) -> int:
        params: list = []
        where_clause = ""
        if keyword:
            like = f"%{keyword.strip()}%"
            where_clause = "WHERE (name LIKE ? OR display_name LIKE ? OR description LIKE ?)"
            params.extend([like, like, like])

        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(1) AS total FROM community_skills {where_clause}",
                params,
            )
            row = cursor.fetchone()
        return int(row["total"]) if row else 0

    def delete_for_owner(self, skill_id: str, owner_uuid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM community_skills WHERE id = ? AND owner_uuid = ?",
                (skill_id, owner_uuid),
            )
            affected = cursor.rowcount
        return affected > 0

    def increment_downloads(self, skill_id: str) -> bool:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE community_skills SET downloads = downloads + 1, updated_at = ? WHERE id = ?",
                (now_ts, skill_id),
            )
            affected = cursor.rowcount
        return affected > 0


class AttachmentsFacade(_DataBase):
    """附件管理门面。

    存储与引用逻辑分离：
    - file_hash (SHA-256 hex) + file_path 标识物理文件，同 sid 内同一文件只写一份。
    - attachment_id (UUID) 是调用标识，多条记录可指向同一 file_path。
    - 删除记录前用 count_by_path 检查引用数，仅最后一条记录删除时才清理物理文件。
    """

    _COLUMNS = (
        "attachment_id, sid, user_uuid, anchor_msg_id, original_filename, "
        "file_hash, file_path, mime_type, file_size, "
        "description, description_generated_at, created_at"
    )

    def create(
        self,
        sid: str,
        user_uuid: str,
        original_filename: str,
        file_hash: str,
        file_path: str,
        mime_type: str,
        file_size: int = 0,
        description: str | None = None,
        description_generated_at: float | None = None,
        attachment_id: str | None = None,
    ) -> dict:
        aid = attachment_id or str(uuid.uuid4())
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO attachments
                    (attachment_id, sid, user_uuid, anchor_msg_id, original_filename,
                     file_hash, file_path, mime_type, file_size,
                     description, description_generated_at, created_at)
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    sid,
                    user_uuid,
                    original_filename,
                    file_hash,
                    file_path,
                    mime_type,
                    file_size,
                    description,
                    description_generated_at,
                    now_ts,
                ),
            )
        record = self.get_for_user(aid, user_uuid)
        if record is None:
            raise RuntimeError("Attachment was inserted but could not be loaded.")
        return record

    def get_for_user(self, attachment_id: str, user_uuid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM attachments WHERE attachment_id = ? AND user_uuid = ?",
                (attachment_id, user_uuid),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def get_by_filename(self, sid: str, original_filename: str, user_uuid: str) -> dict | None:
        """根据会话内友好文件名查找附件。"""
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM attachments WHERE sid = ? AND original_filename = ? AND user_uuid = ? LIMIT 1",
                (sid, original_filename, user_uuid),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def get_by_hash(self, file_hash: str, sid: str, user_uuid: str) -> dict | None:
        """查找同一会话内是否已有相同哈希的附件记录（用于上传去重）。"""
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM attachments WHERE file_hash = ? AND sid = ? AND user_uuid = ? LIMIT 1",
                (file_hash, sid, user_uuid),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def count_by_path(self, file_path: str, user_uuid: str) -> int:
        """统计指向同一物理路径的附件记录数，用于判断是否可以安全删除物理文件。"""
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(1) AS cnt FROM attachments WHERE file_path = ? AND user_uuid = ?",
                (file_path, user_uuid),
            )
            row = cursor.fetchone()
        return int(row["cnt"]) if row else 0

    def list_by_session(self, sid: str, user_uuid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM attachments WHERE sid = ? AND user_uuid = ? ORDER BY created_at ASC",
                (sid, user_uuid),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def count_by_type_in_session(self, sid: str, user_uuid: str, mime_prefix: str) -> int:
        """统计会话内某类 MIME 前缀的附件数（用于生成友好文件名）。"""
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(1) AS cnt FROM attachments WHERE sid = ? AND user_uuid = ? AND mime_type LIKE ?",
                (sid, user_uuid, f"{mime_prefix}%"),
            )
            row = cursor.fetchone()
        return int(row["cnt"]) if row else 0

    def list_by_anchor(self, anchor_msg_id: str, user_uuid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM attachments WHERE anchor_msg_id = ? AND user_uuid = ? ORDER BY created_at ASC",
                (anchor_msg_id, user_uuid),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def bind_anchor(self, *, attachment_ids: list[str], anchor_msg_id: str, user_uuid: str) -> int:
        """把一组附件的 anchor_msg_id 写入指定回合锚点。"""
        if not attachment_ids:
            return 0
        placeholders = ",".join("?" * len(attachment_ids))
        with self._cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE attachments SET anchor_msg_id = ?
                WHERE attachment_id IN ({placeholders}) AND user_uuid = ? AND anchor_msg_id IS NULL
                """,
                [anchor_msg_id, *attachment_ids, user_uuid],
            )
            affected = cursor.rowcount
        return affected

    def update_description(
        self,
        attachment_id: str,
        user_uuid: str,
        description: str,
        description_generated_at: float | None = None,
    ) -> bool:
        now_ts = description_generated_at or self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE attachments
                SET description = ?, description_generated_at = ?
                WHERE attachment_id = ? AND user_uuid = ?
                """,
                (description, now_ts, attachment_id, user_uuid),
            )
            affected = cursor.rowcount
        return affected > 0

    def delete(self, attachment_id: str, user_uuid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM attachments WHERE attachment_id = ? AND user_uuid = ?",
                (attachment_id, user_uuid),
            )
            affected = cursor.rowcount
        return affected > 0

class DatabaseFacade:
    """数据库门面对象：统一提供 users/projects/sessions/messages/access/nonces/community 能力。"""

    def __init__(self, db_path: str = "project.db"):
        self.db_path = db_path
        self.users = UsersFacade(self)
        self.projects = ProjectsFacade(self)
        self.sessions = SessionsFacade(self)
        self.messages = MessagesFacade(self)
        self.access = AccessFacade(self)
        self.nonces = NoncesFacade(self)
        self.model_configs = ModelConfigsFacade(self)
        self.preferences = UserPreferencesFacade(self)
        self.community = CommunitySkillsFacade(self)
        self.attachments = AttachmentsFacade(self)

    @staticmethod
    def _configure_connection(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=OFF;")
        conn.row_factory = sqlite3.Row

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        self._configure_connection(conn)
        return conn

    @contextmanager
    def db_cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _now_timestamp() -> float:
        return datetime.now().timestamp()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _migrate_legacy_community_skill_bodies(cursor: sqlite3.Cursor) -> None:
        """Move old DB-stored SKILL.md text into archived_skill/{id}/SKILL.md."""
        cursor.execute("PRAGMA table_info(community_skills)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "body_md" not in columns or "archive_path" not in columns:
            return

        from backend.config import BASE_DIR

        archive_root = (BASE_DIR / "archived_skill").resolve()
        archive_root.mkdir(parents=True, exist_ok=True)
        cursor.execute(
            """
            SELECT id, body_md, size_bytes
            FROM community_skills
            WHERE body_md != '' AND (archive_path IS NULL OR archive_path = '')
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            skill_id = str(row["id"])
            archive_dir = (archive_root / skill_id).resolve()
            if archive_dir != archive_root and archive_root not in archive_dir.parents:
                continue
            archive_dir.mkdir(parents=True, exist_ok=True)
            skill_file = archive_dir / "SKILL.md"
            skill_file.write_text(str(row["body_md"]), encoding="utf-8")
            size_bytes = skill_file.stat().st_size
            cursor.execute(
                """
                UPDATE community_skills
                SET archive_path = ?, body_md = '', size_bytes = ?
                WHERE id = ?
                """,
                (f"archived_skill/{skill_id}", size_bytes, skill_id),
            )

    def setup_database(self) -> None:
        with self.db_cursor() as cursor:
            schema = """
            CREATE TABLE IF NOT EXISTS users (
                uuid TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                pid TEXT PRIMARY KEY,
                projectname TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                timestamp REAL NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS sessions (
                sid TEXT PRIMARY KEY,
                pid TEXT NOT NULL,
                sessionname TEXT NOT NULL,
                timestamp REAL NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (pid) REFERENCES projects(pid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS messages (
                msg_id TEXT PRIMARY KEY,
                sid TEXT NOT NULL,
                kind TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                timestamp REAL NOT NULL,
                anchor_msg_id TEXT,
                version INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (sid) REFERENCES sessions(sid) ON DELETE CASCADE,
                FOREIGN KEY (anchor_msg_id) REFERENCES messages(msg_id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS nonces (
                nonce TEXT PRIMARY KEY,
                user_uuid TEXT NOT NULL,
                timestamp REAL NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_nonces_timestamp ON nonces(timestamp);
            CREATE TABLE IF NOT EXISTS community_skills (
                id TEXT PRIMARY KEY,
                owner_uuid TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                description TEXT NOT NULL,
                archive_path TEXT NOT NULL,
                license TEXT,
                compatibility TEXT,
                size_bytes INTEGER NOT NULL,
                downloads INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (owner_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_community_skills_created_at ON community_skills(created_at);
            CREATE INDEX IF NOT EXISTS idx_community_skills_downloads ON community_skills(downloads);
            CREATE INDEX IF NOT EXISTS idx_community_skills_owner ON community_skills(owner_uuid);
            CREATE INDEX IF NOT EXISTS idx_community_skills_name ON community_skills(name);
            CREATE TABLE IF NOT EXISTS user_model_configs (
                config_id TEXT PRIMARY KEY,
                user_uuid TEXT NOT NULL,
                config_name TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL DEFAULT '',
                model_name TEXT NOT NULL DEFAULT '',
                user_instruction TEXT NOT NULL DEFAULT '',
                temperature REAL,
                max_tokens INTEGER,
                is_active INTEGER NOT NULL DEFAULT 0,
                supports_vision INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_model_configs_user ON user_model_configs(user_uuid);
            CREATE INDEX IF NOT EXISTS idx_model_configs_active ON user_model_configs(user_uuid, is_active);
            CREATE TABLE IF NOT EXISTS attachments (
                attachment_id TEXT PRIMARY KEY,
                sid TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                anchor_msg_id TEXT,
                original_filename TEXT NOT NULL,
                file_hash TEXT NOT NULL DEFAULT '',
                file_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                description TEXT,
                description_generated_at REAL,
                created_at REAL NOT NULL,
                FOREIGN KEY (sid) REFERENCES sessions(sid) ON DELETE CASCADE,
                FOREIGN KEY (anchor_msg_id) REFERENCES messages(msg_id) ON DELETE SET NULL,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_attachments_sid ON attachments(sid);
            CREATE INDEX IF NOT EXISTS idx_attachments_user ON attachments(user_uuid);
            CREATE INDEX IF NOT EXISTS idx_attachments_anchor ON attachments(anchor_msg_id);
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_uuid TEXT PRIMARY KEY,
                theme TEXT NOT NULL DEFAULT 'system',
                language TEXT NOT NULL DEFAULT 'zh-CN',
                font_size TEXT NOT NULL DEFAULT 'medium',
                code_line_numbers INTEGER NOT NULL DEFAULT 0,
                enter_mode TEXT NOT NULL DEFAULT 'enter',
                loop_max_retries INTEGER,
                test_connection_timeout INTEGER,
                message_history_limit INTEGER,
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            """
            cursor.executescript(schema)

            cursor.execute("PRAGMA table_info(user_model_configs)")
            user_model_configs_columns = {row["name"] for row in cursor.fetchall()}
            if "supports_vision" not in user_model_configs_columns:
                cursor.execute(
                    "ALTER TABLE user_model_configs ADD COLUMN supports_vision INTEGER NOT NULL DEFAULT 0"
                )

            # attachments 表迁移：补充 file_hash / file_size 列
            cursor.execute("PRAGMA table_info(attachments)")
            att_columns = {row["name"] for row in cursor.fetchall()}
            if "file_hash" not in att_columns:
                cursor.execute(
                    "ALTER TABLE attachments ADD COLUMN file_hash TEXT NOT NULL DEFAULT ''"
                )
            if "file_size" not in att_columns:
                cursor.execute(
                    "ALTER TABLE attachments ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0"
                )

            # 确保 file_hash 列存在后再创建对应索引，防止对旧库迁移时报错
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_attachments_hash ON attachments(file_hash, sid, user_uuid)"
            )

            cursor.execute("PRAGMA table_info(community_skills)")
            columns = {row["name"] for row in cursor.fetchall()}
            if "archive_path" not in columns:
                cursor.execute(
                    "ALTER TABLE community_skills ADD COLUMN archive_path TEXT NOT NULL DEFAULT ''"
                )
            if "display_name" not in columns:
                cursor.execute("ALTER TABLE community_skills ADD COLUMN display_name TEXT")
            self._migrate_legacy_community_skill_bodies(cursor)

            # Migrate user_model_configs: add columns if missing
            cursor.execute("PRAGMA table_info(user_model_configs)")
            mc_cols = {row[1] for row in cursor.fetchall()}
            if "top_p" not in mc_cols:
                cursor.execute("ALTER TABLE user_model_configs ADD COLUMN top_p REAL")
            if "frequency_penalty" not in mc_cols:
                cursor.execute("ALTER TABLE user_model_configs ADD COLUMN frequency_penalty REAL")
            if "presence_penalty" not in mc_cols:
                cursor.execute("ALTER TABLE user_model_configs ADD COLUMN presence_penalty REAL")
            if "response_format" not in mc_cols:
                cursor.execute("ALTER TABLE user_model_configs ADD COLUMN response_format TEXT")

        logger.info("Database setup completed")

if __name__ == "__main__":
    DatabaseFacade().setup_database()
