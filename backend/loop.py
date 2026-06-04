"""loop.py - 状态机图声明、引擎、SSE 流式响应与 FastAPI 路由。

架构：
- _graph (LoopGraph): 声明节点间的有向边与条件，模块加载时静态构建
- run_loop: 引擎核心 —— 取节点 → 执行 → 查图 → 路由 → 循环
- router (FastAPI APIRouter): POST /loop/{sid} 协议驱动入口
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends
from backend.db import DatabaseFacade
from backend.db_dep import get_db
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.auth import get_current_user, verify_nonce
from backend.config import LOOP_MAX_RETRIES
from backend.context import (
    ActionKind,
    LoopContext,
    LoopGraph,
    NodeName,
    _registry,
)

# 导入 node 会触发所有 @register_node 装饰器，填充 _registry
import backend.node as node  # noqa: F401

logger = logging.getLogger(__name__)

# ── 用户锁 & 运行中任务 ──

_user_locks: dict[str, asyncio.Lock] = {}
_user_locks_lock = asyncio.Lock()
TaskKey = tuple[str, str]

_running_tasks: dict[TaskKey, asyncio.Task] = {}


def task_key(user_uuid: str, sid: str) -> TaskKey:
    return (user_uuid, sid)


async def get_user_lock(user_uuid: str) -> asyncio.Lock:
    """获取用户的互斥锁（不存在则创建，线程安全）。"""
    if user_uuid not in _user_locks:
        async with _user_locks_lock:
            if user_uuid not in _user_locks:
                _user_locks[user_uuid] = asyncio.Lock()
    return _user_locks[user_uuid]


# ── 条件函数 ──
# 签名: (ctx: LoopContext) -> bool
# 由图引擎在每步查询时调用，依据 LoopContext 状态判断边是否可选。


def _no_error(ctx: LoopContext) -> bool:
    return ctx.error is None


def _can_retry(ctx: LoopContext) -> bool:
    return ctx.error is not None and ctx.retries < LOOP_MAX_RETRIES


def _has_error(ctx: LoopContext) -> bool:
    return ctx.error is not None and ctx.retries >= LOOP_MAX_RETRIES


def _action_is(*actions: str):
    """返回闭包: 当前 action 在指定集合中时返回 True。"""

    def check(ctx: LoopContext) -> bool:
        return ctx.action.value in actions

    return check


# ── 图声明 ──
# 静态结构，模块加载时构建一次。节点在执行时才查询图决定下一跳。这一部分只是声明，不涉及真正的执行和调度。

_graph = LoopGraph()

# 入口: 所有 action 统一从 VALIDATE 进入
_graph.set_entry(ActionKind.SEND, NodeName.VALIDATE)
_graph.set_entry(ActionKind.REGENERATE, NodeName.VALIDATE)
_graph.set_entry(ActionKind.STOP, NodeName.VALIDATE)

# VALIDATE 分支
_graph.add_edge(NodeName.VALIDATE, NodeName.LOAD_HISTORY, condition=_action_is("send", "regenerate"))
_graph.add_edge(NodeName.VALIDATE, NodeName.STOP, condition=_action_is("stop"))

# 线形流水 (VALIDATE 通过后 → LOAD → BUILD → BUILD_MODEL → CALL)
_graph.add_edge(NodeName.LOAD_HISTORY, NodeName.BUILD_MESSAGES)
_graph.add_edge(NodeName.BUILD_MESSAGES, NodeName.BUILD_MODEL)
_graph.add_edge(NodeName.BUILD_MODEL, NodeName.CALL_MODEL)

# CALL_MODEL 三向分支 (按优先级排列: 正常 / 重试 / 失败)
_graph.add_edge(NodeName.CALL_MODEL, NodeName.SAVE, condition=_no_error)
_graph.add_edge(NodeName.CALL_MODEL, NodeName.CALL_MODEL, condition=_can_retry)
_graph.add_edge(NodeName.CALL_MODEL, NodeName.STREAM_ERROR, condition=_has_error)

# 收束
_graph.add_edge(NodeName.SAVE, NodeName.STREAM_COMPLETE)

# 所有出口 → RELEASE_LOCK（确保锁释放）
_graph.add_edge(NodeName.STREAM_COMPLETE, NodeName.RELEASE_LOCK)
_graph.add_edge(NodeName.STREAM_ERROR, NodeName.RELEASE_LOCK)
_graph.add_edge(NodeName.STOP, NodeName.RELEASE_LOCK)


# ── 引擎 ──


async def run_loop(ctx: LoopContext, entry: NodeName) -> None:
    """状态机引擎核心。

    循环: 取当前节点函数 → 执行 → NodeOutput 带主动跳转则跳 → 查图决定下一跳。
    节点无出边时退出；终态节点也会先执行自身逻辑。
    """
    current = entry
    logger.info("loop_start action=%s user=%s sid=%s", ctx.action.value, ctx.user_uuid, ctx.sid)

    try:
        while True:
            node_fn = _registry.get(current)#获取当前节点的执行函数实例
            if node_fn is None:
                ctx.error = f"Node not registered: {current}"
                ctx.error_code = "LOOP_CONFIG_ERROR"
                logger.error("loop_config_error node=%s user=%s sid=%s", current, ctx.user_uuid, ctx.sid)
                current = NodeName.STREAM_ERROR
                continue

            try:
                output = await node_fn(ctx)
            except Exception as exc:
                ctx.error = str(exc)
                ctx.error_code = "LOOP_EXECUTION_ERROR"
                logger.exception("loop_execution_error node=%s user=%s sid=%s", current, ctx.user_uuid, ctx.sid)
                current = NodeName.STREAM_ERROR
                continue

            # 节点主动跳转（优先级高于图查询）
            if output.transition:
                current = NodeName(output.transition)
                continue

            # 查图: 取满足条件的候选边
            candidates = _graph.next_nodes(current, ctx)
            if not candidates:
                logger.info(
                    "loop_end action=%s user=%s sid=%s error_code=%s",
                    ctx.action.value,
                    ctx.user_uuid,
                    ctx.sid,
                    ctx.error_code,
                )
                break  # 无候选，自然终止

            # 路由: 当前取第一条候选（后期替换为路由 Agent）
            current = await _graph.route(ctx, candidates)
    finally:
        # 收底落库：如果未曾保存，且有新产生的新消息
        if ctx.action in (ActionKind.SEND, ActionKind.REGENERATE) and not getattr(ctx, "saved", False):
            new_messages = [m for m in ctx.messages if m not in ctx.history_messages]
            if new_messages:
                logger.info("loop_emergency_save action=%s user=%s sid=%s", ctx.action.value, ctx.user_uuid, ctx.sid)
                db = ctx.db
                if ctx.action == ActionKind.REGENERATE and ctx.anchor_msg_id:
                    db.messages.bump_versions_for_anchor(anchor_msg_id=ctx.anchor_msg_id)
                    anchor_for_save: str | None = ctx.anchor_msg_id
                else:
                    anchor_for_save = None

                try:
                    response_msg_id, anchor_msg_id = db.messages.save_agent_messages(
                        sid=ctx.sid,
                        user_uuid=ctx.user_uuid,
                        new_messages=new_messages,
                        is_final_turn=True,
                        anchor_msg_id=anchor_for_save,
                    )
                    ctx.response_msg_id = response_msg_id
                    if ctx.action == ActionKind.SEND:
                        ctx.anchor_msg_id = anchor_msg_id

                    if ctx.attachment_ids and ctx.anchor_msg_id:
                        db.attachments.bind_anchor(
                            attachment_ids=ctx.attachment_ids,
                            anchor_msg_id=ctx.anchor_msg_id,
                            user_uuid=ctx.user_uuid,
                        )
                    ctx.saved = True
                    db.sessions.touch_timestamp(sid=ctx.sid)
                except Exception as e:
                    logger.exception("emergency_save_failed error=%s", str(e))


# ── SSE 流式响应 ──


async def stream_response(ctx: LoopContext) -> AsyncGenerator[str, None]:
    """SSE 生成器: 启动引擎并逐帧消费事件队列。"""
    queue: asyncio.Queue = asyncio.Queue()
    ctx.sse_queue = queue

    entry = _graph.entry_node(ctx.action)
    run_task = asyncio.create_task(run_loop(ctx, entry))

    # 存储运行中任务（用于 STOP 取消），STOP 请求自身不存储
    if ctx.action != ActionKind.STOP:
        _running_tasks[task_key(ctx.user_uuid, ctx.sid)] = run_task

    try:
        while True:
            queue_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                {queue_task, run_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if queue_task in done:
                event = queue_task.result()
                yield f"data: {json.dumps(event, default=str)}\n\n"
                continue

            if run_task in done:
                if queue_task in pending:
                    queue_task.cancel()
                break

        # 传播引擎异常（如有）
        await run_task
    except asyncio.CancelledError:
        pass
    finally:
        _running_tasks.pop(task_key(ctx.user_uuid, ctx.sid), None)

    # 发送结束帧
    done_event: dict[str, Any] = {"type": "done"}
    if ctx.response_msg_id:
        done_event["msg_id"] = ctx.response_msg_id
    if ctx.anchor_msg_id:
        done_event["anchor_msg_id"] = ctx.anchor_msg_id
    if ctx.error:
        done_event["error"] = ctx.error
        done_event["error_code"] = ctx.error_code
    yield f"data: {json.dumps(done_event, default=str)}\n\n"


# ── FastAPI 路由 ──

router = APIRouter(prefix="/loop", tags=["chat"])


class ChatRequest(BaseModel):
    """POST /loop/{sid} 请求体。action 字段驱动状态机入口选择。"""

    pid: str = Field(..., description="项目 ID")
    action: ActionKind = Field(default=ActionKind.SEND, description="send | regenerate | stop")
    message: str = Field(default="", description="用户输入文本（regenerate 时可为空表示沿用原 PROMPT）")
    anchor_msg_id: str | None = Field(
        default=None,
        description="regenerate 必填：要重放回合的 anchor msg_id（即原回合首条 user 消息 ID）",
    )
    allowed_tools: list[str] | None = Field(default=None, description="前端请求允许的工具列表")
    attachment_ids: list[str] | None = Field(default=None, description="本轮附件 ID 列表，save_node 执行后写入 anchor_msg_id")


@router.post("/{sid}")
async def chat_loop(
    sid: str,
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user),
    _nonce: None = Depends(verify_nonce),
    db: DatabaseFacade = Depends(get_db),
) -> StreamingResponse:
    """协议驱动入口: POST /loop/{sid}

    body.action 区分 send / regenerate / stop，统一进入状态机引擎。
    """
    user_uuid: str = current_user["uuid"]

    db = get_db()

    ctx = LoopContext(
        user_uuid=user_uuid,
        pid=payload.pid,
        sid=sid,
        action=payload.action,
        user_input=payload.message,
        anchor_msg_id=payload.anchor_msg_id,
        allowed_tools=payload.allowed_tools,
        attachment_ids=payload.attachment_ids,
        db=db,
    )

    return StreamingResponse(
        stream_response(ctx),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
