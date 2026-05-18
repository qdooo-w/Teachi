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


class CommunitySkillsFacade(_DataBase):
    """社区技能广场。每条记录指向一份归档 skill 文件夹。

    设计取舍：
    - skill 内容本体存放在 archived_skill/{id}/，数据库只保存路径和展示元信息。
    - 同作者可重复发布同名 skill：每次 publish 都是独立 id；老条目作者可手动删除。
    - 下载时把归档文件夹 copy 到用户私有目录，作者删除后已下载副本不受影响（解耦）。
    """

    _COLUMNS = (
        "id, owner_uuid, name, description, archive_path, license, compatibility, "
        "size_bytes, downloads, created_at, updated_at"
    )

    def create(
        self,
        *,
        owner_uuid: str,
        name: str,
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
                    "id, owner_uuid, name, description, archive_path, body_md, "
                    "license, compatibility, size_bytes, downloads, created_at, updated_at"
                )
                values = (
                    skill_id,
                    owner_uuid,
                    name,
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
        keyword 不为空时，按 name LIKE OR description LIKE 过滤（大小写不敏感）。
        """
        if sort == "newest":
            order_clause = "ORDER BY created_at DESC"
        else:
            order_clause = "ORDER BY downloads DESC, created_at DESC"

        params: list = []
        where_clause = ""
        if keyword:
            like = f"%{keyword.strip()}%"
            where_clause = "WHERE (name LIKE ? OR description LIKE ?)"
            params.extend([like, like])
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
            where_clause = "WHERE (name LIKE ? OR description LIKE ?)"
            params.extend([like, like])

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
        self.community = CommunitySkillsFacade(self)

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
        columns = {row[1] for row in cursor.fetchall()}
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
            """
            cursor.executescript(schema)
            cursor.execute("PRAGMA table_info(community_skills)")
            columns = {row[1] for row in cursor.fetchall()}
            if "archive_path" not in columns:
                cursor.execute(
                    "ALTER TABLE community_skills ADD COLUMN archive_path TEXT NOT NULL DEFAULT ''"
                )
            self._migrate_legacy_community_skill_bodies(cursor)

        logger.info("Database setup completed")


if __name__ == "__main__":
    DatabaseFacade().setup_database()
