from __future__ import annotations

import sqlite3
import uuid
import json
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
                "SELECT uuid, username, email, password_hash, role, created_at FROM users WHERE email = ?",
                (email,),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def get_by_uuid(self, user_uuid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT uuid, username, email, password_hash, role, created_at FROM users WHERE uuid = ?",
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

    def list_latest_by_session_page_for_user(
        self,
        sid: str,
        user_uuid: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """倒序加载会话消息分页（从最新往最旧，内部翻转回升序返回）。"""
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT m.msg_id, m.sid, m.kind, m.raw_json, m.timestamp, m.anchor_msg_id, m.version, m.created_at
                FROM messages AS m
                JOIN sessions AS s ON m.sid = s.sid
                JOIN projects AS p ON s.pid = p.pid
                LEFT JOIN messages AS a ON m.anchor_msg_id = a.msg_id
                WHERE m.sid = ? AND p.user_uuid = ?
                ORDER BY COALESCE(a.timestamp, m.timestamp) DESC, m.timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (sid, user_uuid, limit, offset),
            )
            rows = cursor.fetchall()
        res = [dict(row) for row in rows]
        res.reverse()
        return res


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
    """社区技能广场数据访问层"""

    def create_skill(
        self,
        *,
        skill_id: str,
        owner_uuid: str,
        name: str,
        display_name: str | None = None,
        description: str,
        admin_uuids: str,
    ) -> dict:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO community_skills 
                (id, owner_uuid, name, display_name, description, admin_uuids, likes, downloads, latest_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?)
                """,
                (skill_id, owner_uuid, name, display_name, description, admin_uuids, now_ts, now_ts)
            )
            # 双写：同步 admin_uuids 到专用子表
            try:
                uuids = json.loads(admin_uuids)
            except Exception:
                uuids = []
            for u in uuids:
                if u:
                    cursor.execute(
                        "INSERT OR IGNORE INTO community_skill_admins (skill_id, user_uuid, created_at) VALUES (?, ?, ?)",
                        (skill_id, u, now_ts),
                    )
        record = self.get_skill(skill_id)
        if record is None:
            raise RuntimeError("Skill could not be loaded after insert")
        return record

    def create_version(
        self,
        *,
        version_id: str,
        skill_id: str,
        version: str,
        readme_md: str,
        changelog: str,
        tags: str,
        archive_path: str,
        size_bytes: int,
        source: str | None,
        status: str,
        submitted_by: str,
    ) -> dict:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO community_skill_versions
                (id, skill_id, version, readme_md, changelog, tags, archive_path, size_bytes, downloads, source, status, submitted_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (version_id, skill_id, version, readme_md, changelog, tags, archive_path, size_bytes, source, status, submitted_by, now_ts)
            )
        record = self.get_version(version_id)
        if record is None:
            raise RuntimeError("Version could not be loaded after insert")
        return record

    def get_skill(self, skill_id: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM community_skills WHERE id = ?", (skill_id,))
            return self._row_to_dict(cursor.fetchone())

    def get_skill_by_name(self, name: str) -> dict | None:
        """按技能名称（唯一键）精确查找社区 skill。"""
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM community_skills WHERE name = ?", (name,))
            return self._row_to_dict(cursor.fetchone())

    def get_version(self, version_id: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM community_skill_versions WHERE id = ?", (version_id,))
            return self._row_to_dict(cursor.fetchone())

    def get_latest_approved_version(self, skill_id: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM community_skill_versions WHERE skill_id = ? AND status = 'APPROVED' ORDER BY created_at DESC LIMIT 1",
                (skill_id,)
            )
            return self._row_to_dict(cursor.fetchone())

    def update_latest_version(self, skill_id: str, latest_version: str) -> bool:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE community_skills SET latest_version = ?, updated_at = ? WHERE id = ?",
                (latest_version, now_ts, skill_id)
            )
            return cursor.rowcount > 0

    def list_skills(
        self,
        *,
        keyword: str | None = None,
        tag: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort: str = "popular",
    ) -> list[dict]:
        order_clause = "ORDER BY s.created_at DESC" if sort == "newest" else "ORDER BY s.downloads DESC, s.created_at DESC"
        params: list = []
        where_parts: list = ["v.status = 'APPROVED'"]
        
        if keyword:
            like = f"%{keyword.strip()}%"
            where_parts.append("(s.name LIKE ? OR s.display_name LIKE ? OR s.description LIKE ?)")
            params.extend([like, like, like])
            
        if tag:
            where_parts.append("json_each.value = ?")
            params.append(tag)
            
        where_clause = f"WHERE {' AND '.join(where_parts)}"
        tag_join = ", json_each(v.tags)" if tag else ""
        
        sql = f"""
            SELECT s.*, v.version, v.tags, v.size_bytes 
            FROM community_skills s
            JOIN community_skill_versions v ON s.id = v.skill_id
            {tag_join}
            {where_clause}
            GROUP BY s.id
            {order_clause}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def count_skills(self, *, keyword: str | None = None, tag: str | None = None) -> int:
        params: list = []
        where_parts: list = ["v.status = 'APPROVED'"]
        if keyword:
            like = f"%{keyword.strip()}%"
            where_parts.append("(s.name LIKE ? OR s.display_name LIKE ? OR s.description LIKE ?)")
            params.extend([like, like, like])
        if tag:
            where_parts.append("json_each.value = ?")
            params.append(tag)

        where_clause = f"WHERE {' AND '.join(where_parts)}"
        tag_join = ", json_each(v.tags)" if tag else ""

        sql = f"""
            SELECT COUNT(DISTINCT s.id) AS total
            FROM community_skills s
            JOIN community_skill_versions v ON s.id = v.skill_id
            {tag_join}
            {where_clause}
        """
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        return int(row["total"]) if row else 0

    def delete_skill(self, skill_id: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM community_skills WHERE id = ?", (skill_id,))
            return cursor.rowcount > 0

    def increment_downloads(self, skill_id: str, version_id: str | None = None) -> bool:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE community_skills SET downloads = downloads + 1, updated_at = ? WHERE id = ?",
                (now_ts, skill_id)
            )
            affected = cursor.rowcount
            if version_id:
                cursor.execute(
                    "UPDATE community_skill_versions SET downloads = downloads + 1 WHERE id = ?",
                    (version_id,)
                )
        return affected > 0

    def toggle_like(self, skill_id: str, user_uuid: str) -> bool:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute("SELECT 1 FROM community_skill_likes WHERE skill_id = ? AND user_uuid = ?", (skill_id, user_uuid))
            exists = cursor.fetchone()
            if exists:
                cursor.execute("DELETE FROM community_skill_likes WHERE skill_id = ? AND user_uuid = ?", (skill_id, user_uuid))
                cursor.execute("UPDATE community_skills SET likes = likes - 1 WHERE id = ?", (skill_id,))
                return False
            else:
                cursor.execute("INSERT INTO community_skill_likes (skill_id, user_uuid, created_at) VALUES (?, ?, ?)", (skill_id, user_uuid, now_ts))
                cursor.execute("UPDATE community_skills SET likes = likes + 1 WHERE id = ?", (skill_id,))
                return True

    def create_comment(self, *, comment_id: str, skill_id: str, user_uuid: str, content: str, parent_id: str | None, reply_to_uuid: str | None) -> dict:
        now_ts = self._now_timestamp()
        depth = 0
        with self._cursor() as cursor:
            if parent_id:
                cursor.execute("SELECT depth FROM community_skill_comments WHERE id = ?", (parent_id,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError("Parent comment not found")
                parent_depth = row["depth"]
                if parent_depth >= 1:
                    raise ValueError("Max nesting depth exceeded")
                depth = parent_depth + 1

            cursor.execute(
                """
                INSERT INTO community_skill_comments (id, skill_id, user_uuid, content, parent_id, depth, reply_to_uuid, likes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (comment_id, skill_id, user_uuid, content, parent_id, depth, reply_to_uuid, now_ts, now_ts)
            )
            cursor.execute("SELECT * FROM community_skill_comments WHERE id = ?", (comment_id,))
            return self._row_to_dict(cursor.fetchone())

    def create_report(self, *, report_id: str, comment_id: str, reporter_uuid: str, reason: str, detail: str = "") -> dict:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO community_comment_reports (id, comment_id, reporter_uuid, reason, detail, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (report_id, comment_id, reporter_uuid, reason, detail, now_ts)
            )
            cursor.execute("SELECT * FROM community_comment_reports WHERE id = ?", (report_id,))
            return self._row_to_dict(cursor.fetchone())

    def update_admin_uuids(self, skill_id: str, admin_uuids: str) -> bool:
        """更新 admin_uuids JSON 字段，并同步重建 community_skill_admins 子表记录。"""
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE community_skills SET admin_uuids = ?, updated_at = ? WHERE id = ?",
                (admin_uuids, now_ts, skill_id),
            )
            affected = cursor.rowcount
            if affected:
                cursor.execute("DELETE FROM community_skill_admins WHERE skill_id = ?", (skill_id,))
                try:
                    uuids = json.loads(admin_uuids)
                except Exception:
                    uuids = []
                for u in uuids:
                    if u:
                        cursor.execute(
                            "INSERT OR IGNORE INTO community_skill_admins (skill_id, user_uuid, created_at) VALUES (?, ?, ?)",
                            (skill_id, u, now_ts),
                        )
        return affected > 0

    def add_admin(self, skill_id: str, user_uuid: str) -> bool:
        """将用户加入 skill 管理员（同步双写 JSON 字段与子表）。"""
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute("SELECT admin_uuids FROM community_skills WHERE id = ?", (skill_id,))
            row = cursor.fetchone()
            if not row:
                return False
            try:
                uuids: list = json.loads(row["admin_uuids"])
            except Exception:
                uuids = []
            if user_uuid not in uuids:
                uuids.append(user_uuid)
                cursor.execute(
                    "UPDATE community_skills SET admin_uuids = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(uuids), now_ts, skill_id),
                )
            cursor.execute(
                "INSERT OR IGNORE INTO community_skill_admins (skill_id, user_uuid, created_at) VALUES (?, ?, ?)",
                (skill_id, user_uuid, now_ts),
            )
        return True

    def remove_admin(self, skill_id: str, user_uuid: str) -> bool:
        """将用户从 skill 管理员中移除（同步双写 JSON 字段与子表）。"""
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute("SELECT admin_uuids FROM community_skills WHERE id = ?", (skill_id,))
            row = cursor.fetchone()
            if not row:
                return False
            try:
                uuids: list = json.loads(row["admin_uuids"])
            except Exception:
                uuids = []
            uuids = [u for u in uuids if u != user_uuid]
            cursor.execute(
                "UPDATE community_skills SET admin_uuids = ?, updated_at = ? WHERE id = ?",
                (json.dumps(uuids), now_ts, skill_id),
            )
            cursor.execute(
                "DELETE FROM community_skill_admins WHERE skill_id = ? AND user_uuid = ?",
                (skill_id, user_uuid),
            )
        return True

    def is_skill_admin(self, skill_id: str, user_uuid: str) -> bool:
        """通过有索引的子表校验用户是否为 skill 管理员（O(log n) 查询）。"""
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM community_skill_admins WHERE skill_id = ? AND user_uuid = ?",
                (skill_id, user_uuid),
            )
            return cursor.fetchone() is not None

    def is_liked_by_user(self, skill_id: str, user_uuid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute("SELECT 1 FROM community_skill_likes WHERE skill_id = ? AND user_uuid = ?", (skill_id, user_uuid))
            return cursor.fetchone() is not None

    def list_versions(self, skill_id: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM community_skill_versions WHERE skill_id = ? AND status = 'APPROVED' ORDER BY created_at DESC", (skill_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_contributors(self, skill_id: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM community_skill_contributors WHERE skill_id = ?", (skill_id,))
            return [dict(row) for row in cursor.fetchall()]

    def list_comments(self, skill_id: str, parent_id: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._cursor() as cursor:
            if parent_id:
                cursor.execute("SELECT * FROM community_skill_comments WHERE skill_id = ? AND parent_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?", (skill_id, parent_id, limit, offset))
            else:
                cursor.execute("SELECT * FROM community_skill_comments WHERE skill_id = ? AND parent_id IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?", (skill_id, limit, offset))
            return [dict(row) for row in cursor.fetchall()]

    def delete_comment(self, comment_id: str, user_uuid: str, *, is_admin: bool = False) -> bool:
        """删除评论：本人可删自己的评论，全局 admin 可删任意评论。"""
        with self._cursor() as cursor:
            if is_admin:
                cursor.execute("DELETE FROM community_skill_comments WHERE id = ?", (comment_id,))
            else:
                cursor.execute(
                    "DELETE FROM community_skill_comments WHERE id = ? AND user_uuid = ?",
                    (comment_id, user_uuid),
                )
            return cursor.rowcount > 0

    def toggle_comment_like(self, comment_id: str, user_uuid: str) -> bool:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute("SELECT 1 FROM community_comment_likes WHERE comment_id = ? AND user_uuid = ?", (comment_id, user_uuid))
            exists = cursor.fetchone()
            if exists:
                cursor.execute("DELETE FROM community_comment_likes WHERE comment_id = ? AND user_uuid = ?", (comment_id, user_uuid))
                cursor.execute("UPDATE community_skill_comments SET likes = likes - 1 WHERE id = ?", (comment_id,))
                return False
            else:
                cursor.execute("INSERT INTO community_comment_likes (comment_id, user_uuid, created_at) VALUES (?, ?, ?)", (comment_id, user_uuid, now_ts))
                cursor.execute("UPDATE community_skill_comments SET likes = likes + 1 WHERE id = ?", (comment_id,))
                return True

class UserLibrarySkillsFacade(_DataBase):
    def create(
        self,
        *,
        user_uuid: str,
        name: str,
        display_name: str | None,
        description: str,
        readme_md: str,
        tags: str,
        version: str,
        changelog: str,
        source: str | None,
        community_skill_id: str | None,
        local_path: str,
        size_bytes: int,
        skill_id: str | None = None
    ) -> dict:
        skill_id = skill_id or str(uuid.uuid4())
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_library_skills
                (id, user_uuid, name, display_name, description, readme_md, tags, version, changelog, source, community_skill_id, local_path, size_bytes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (skill_id, user_uuid, name, display_name, description, readme_md, tags, version, changelog, source, community_skill_id, local_path, size_bytes, now_ts, now_ts)
            )
        record = self.get_by_id(skill_id)
        if record is None:
            raise RuntimeError("Library skill could not be loaded after insert")
        return record

    def get_by_id(self, skill_id: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM user_library_skills WHERE id = ?", (skill_id,))
            return self._row_to_dict(cursor.fetchone())

    def get_latest_by_name(self, user_uuid: str, name: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM user_library_skills WHERE user_uuid = ? AND name = ? ORDER BY created_at DESC LIMIT 1",
                (user_uuid, name)
            )
            return self._row_to_dict(cursor.fetchone())

    def list_by_user(self, user_uuid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM user_library_skills WHERE user_uuid = ? ORDER BY created_at DESC", (user_uuid,))
            return [dict(row) for row in cursor.fetchall()]

    def update_community_skill_id(self, library_id: str, community_skill_id: str) -> bool:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE user_library_skills SET community_skill_id = ?, updated_at = ? WHERE id = ?",
                (community_skill_id, now_ts, library_id)
            )
            return cursor.rowcount > 0

class ReviewLogsFacade(_DataBase):
    def create(
        self,
        *,
        version_id: str,
        reviewer_uuid: str,
        action: str,
        from_status: str,
        to_status: str,
        note: str = ""
    ) -> dict:
        log_id = str(uuid.uuid4())
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO skill_review_logs
                (id, version_id, reviewer_uuid, action, from_status, to_status, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (log_id, version_id, reviewer_uuid, action, from_status, to_status, note, now_ts)
            )
            
            cursor.execute(
                "UPDATE community_skill_versions SET status = ? WHERE id = ?",
                (to_status, version_id)
            )
            
            cursor.execute("SELECT * FROM skill_review_logs WHERE id = ?", (log_id,))
            return self._row_to_dict(cursor.fetchone())

    def list_by_version(self, version_id: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM skill_review_logs WHERE version_id = ? ORDER BY created_at ASC", (version_id,))
            return [dict(row) for row in cursor.fetchall()]


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
        self.library = UserLibrarySkillsFacade(self)
        self.reviews = ReviewLogsFacade(self)
        self.attachments = AttachmentsFacade(self)

    @staticmethod
    def _configure_connection(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=OFF;")
        conn.row_factory = sqlite3.Row

    def get_connection(self) -> sqlite3.Connection:
        from pathlib import Path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
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

    @staticmethod
    def _migrate_to_v2_pre(cursor: sqlite3.Cursor) -> None:
        cursor.execute("PRAGMA table_info(users)")
        user_cols = {r["name"] for r in cursor.fetchall()}
        if user_cols and "role" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        
        cursor.execute("PRAGMA table_info(community_skills)")
        cs_cols = {r["name"] for r in cursor.fetchall()}
        if cs_cols and "admin_uuids" not in cs_cols:
            cursor.execute("DROP INDEX IF EXISTS idx_community_skills_created_at")
            cursor.execute("DROP INDEX IF EXISTS idx_community_skills_downloads")
            cursor.execute("DROP INDEX IF EXISTS idx_community_skills_owner")
            cursor.execute("DROP INDEX IF EXISTS idx_community_skills_name")
            cursor.execute("ALTER TABLE community_skills RENAME TO community_skills_old")

    @staticmethod
    def _migrate_to_v2_post(cursor: sqlite3.Cursor) -> None:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='community_skills_old'")
        if not cursor.fetchone():
            return
            
        import json
        import uuid
        cursor.execute("SELECT * FROM community_skills_old")
        for row in cursor.fetchall():
            skill_id = row["id"]
            owner_uuid = row["owner_uuid"]
            admin_uuids = json.dumps([owner_uuid])
            
            cursor.execute(
                """
                INSERT INTO community_skills 
                (id, owner_uuid, name, display_name, description, admin_uuids, likes, downloads, latest_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_id, owner_uuid, row["name"], row.get("display_name"), row["description"],
                    admin_uuids, 0, row.get("downloads", 0), "1.0.0", row["created_at"], row["updated_at"]
                )
            )
            
            version_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO community_skill_versions
                (id, skill_id, version, readme_md, changelog, tags, archive_path, size_bytes, downloads, source, status, submitted_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id, skill_id, "1.0.0", "", "Auto-migrated version", "[]",
                    row.get("archive_path", ""), row.get("size_bytes", 0), row.get("downloads", 0),
                    None, "APPROVED", owner_uuid, row["created_at"]
                )
            )
        
        cursor.execute("DROP TABLE community_skills_old")

    def setup_database(self) -> None:
        with self.db_cursor() as cursor:
            self._migrate_to_v2_pre(cursor)
            schema = """
            CREATE TABLE IF NOT EXISTS users (
                uuid TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
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
                name TEXT NOT NULL UNIQUE,
                display_name TEXT,
                description TEXT NOT NULL,
                admin_uuids TEXT NOT NULL DEFAULT '[]',
                likes INTEGER NOT NULL DEFAULT 0,
                downloads INTEGER NOT NULL DEFAULT 0,
                latest_version TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (owner_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS community_skill_versions (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                version TEXT NOT NULL,
                readme_md TEXT DEFAULT '',
                changelog TEXT DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                archive_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                downloads INTEGER NOT NULL DEFAULT 0,
                source TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING_ADMIN',
                submitted_by TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(skill_id, version),
                FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
                FOREIGN KEY (submitted_by) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS community_skill_likes (
                skill_id TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (skill_id, user_uuid),
                FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS community_skill_comments (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                content TEXT NOT NULL,
                parent_id TEXT,
                depth INTEGER NOT NULL DEFAULT 0,
                reply_to_uuid TEXT,
                likes INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES community_skill_comments(id) ON DELETE CASCADE,
                FOREIGN KEY (reply_to_uuid) REFERENCES users(uuid) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS community_comment_likes (
                comment_id TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (comment_id, user_uuid),
                FOREIGN KEY (comment_id) REFERENCES community_skill_comments(id) ON DELETE CASCADE,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS community_comment_reports (
                id TEXT PRIMARY KEY,
                comment_id TEXT NOT NULL,
                reporter_uuid TEXT NOT NULL,
                reason TEXT NOT NULL,
                detail TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PENDING',
                resolved_by TEXT,
                resolved_at REAL,
                created_at REAL NOT NULL,
                UNIQUE(comment_id, reporter_uuid),
                FOREIGN KEY (comment_id) REFERENCES community_skill_comments(id) ON DELETE CASCADE,
                FOREIGN KEY (reporter_uuid) REFERENCES users(uuid) ON DELETE CASCADE,
                FOREIGN KEY (resolved_by) REFERENCES users(uuid) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS community_skill_contributors (
                skill_id TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'contributor',
                created_at REAL NOT NULL,
                PRIMARY KEY (skill_id, user_uuid),
                FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS community_skill_admins (
                skill_id TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (skill_id, user_uuid),
                FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS user_library_skills (
                id TEXT PRIMARY KEY,
                user_uuid TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                description TEXT NOT NULL,
                readme_md TEXT DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                version TEXT NOT NULL,
                changelog TEXT DEFAULT '',
                source TEXT,
                community_skill_id TEXT,
                local_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS skill_review_logs (
                id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                reviewer_uuid TEXT NOT NULL,
                action TEXT NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                note TEXT DEFAULT '',
                created_at REAL NOT NULL,
                FOREIGN KEY (version_id) REFERENCES community_skill_versions(id) ON DELETE CASCADE,
                FOREIGN KEY (reviewer_uuid) REFERENCES users(uuid) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_community_skills_created_at ON community_skills(created_at);
            CREATE INDEX IF NOT EXISTS idx_community_skills_downloads ON community_skills(downloads);
            CREATE INDEX IF NOT EXISTS idx_community_skills_likes ON community_skills(likes);
            CREATE INDEX IF NOT EXISTS idx_community_skills_owner ON community_skills(owner_uuid);
            CREATE INDEX IF NOT EXISTS idx_community_skills_name ON community_skills(name);
            CREATE INDEX IF NOT EXISTS idx_community_versions_skill ON community_skill_versions(skill_id);
            CREATE INDEX IF NOT EXISTS idx_community_versions_status ON community_skill_versions(status);
            CREATE INDEX IF NOT EXISTS idx_community_versions_submitted ON community_skill_versions(submitted_by);
            CREATE INDEX IF NOT EXISTS idx_community_comments_skill ON community_skill_comments(skill_id);
            CREATE INDEX IF NOT EXISTS idx_community_comments_parent ON community_skill_comments(parent_id);
            CREATE INDEX IF NOT EXISTS idx_community_likes_skill ON community_skill_likes(skill_id);
            CREATE INDEX IF NOT EXISTS idx_comment_likes_comment ON community_comment_likes(comment_id);
            CREATE INDEX IF NOT EXISTS idx_comment_reports_comment ON community_comment_reports(comment_id);
            CREATE INDEX IF NOT EXISTS idx_library_skills_user ON user_library_skills(user_uuid);
            CREATE INDEX IF NOT EXISTS idx_library_skills_community ON user_library_skills(community_skill_id);
            CREATE INDEX IF NOT EXISTS idx_review_logs_version ON skill_review_logs(version_id);
            CREATE INDEX IF NOT EXISTS idx_review_logs_reviewer ON skill_review_logs(reviewer_uuid);
            CREATE INDEX IF NOT EXISTS idx_skill_admins_user ON community_skill_admins(user_uuid);
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
            CREATE INDEX IF NOT EXISTS idx_attachments_hash ON attachments(file_hash, sid, user_uuid);

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
            self._migrate_to_v2_post(cursor)
            # 幂等迁移：将现有 admin_uuids JSON 同步到 community_skill_admins 子表
            cursor.execute(
                """
                INSERT OR IGNORE INTO community_skill_admins (skill_id, user_uuid, created_at)
                SELECT cs.id, je.value, cs.created_at
                FROM community_skills cs, json_each(cs.admin_uuids) je
                WHERE je.value IS NOT NULL AND je.value != ''
                """
            )

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

            # Migrations for v1 (legacy bodies) are now handled and superseded by v2

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
