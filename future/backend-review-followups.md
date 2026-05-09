# Backend Review Follow-ups

Deferred issues from backend review. These are intentionally not fixed in the current change set.

## Regenerate and Version Chain

- Issue: Regenerated message versions still default to `version = 1`.
- Impact: Version history can become ambiguous and clients cannot reliably order regenerated branches.
- Suggested next step: Derive the next version from existing sibling/branch history when inserting regenerated messages.
- Affected files: `backend/data.py`, `backend/db.py`.

- Issue: Older regenerated branches are not marked as no longer latest.
- Impact: Multiple branches can appear current at the same time, confusing version selection and display.
- Suggested next step: Update previous latest branches in the same chain when a new version is created.
- Affected files: `backend/data.py`, `backend/db.py`.

- Issue: `parent_msg_id` validation is not scoped to the current session.
- Impact: A regenerate request may attach a message to a parent from another session if IDs are supplied incorrectly or maliciously.
- Suggested next step: Require parent lookup to match both `session_id` and `parent_msg_id` before creating the regenerated message.
- Affected files: `backend/data.py`, `backend/db.py`.

## Retry Handling

- Issue: No `AgentRunResultEvent` path does not increment retries. Intentionally deferred per user request.
- Impact: Failed attempts without a result event may not respect retry accounting, causing inconsistent retry behavior.
- Suggested next step: Increment retry state for all failed attempt exits, including missing-result paths.
- Affected files: `backend/loop.py`, `backend/node.py`.

- Issue: Partial text from failed attempts can pollute frontend output. Intentionally deferred per user request.
- Impact: Users may see streamed text from attempts that are later retried or considered failed.
- Suggested next step: Buffer attempt output until success or emit attempt-scoped events that the frontend can discard on retry.
- Affected files: `backend/loop.py`, `backend/node.py`, `frontend/prototype.html`.

## Tool Registry Wiring

- Issue: Tool registry is not wired into `Agent`.
- Impact: Registered backend tools may not be available to agent execution even though route and registry code exists.
- Suggested next step: Pass the tool registry/tools into agent construction and add coverage for tool availability during a run.
- Affected files: `backend/main.py`, `backend/loop.py`, `backend/tool.py`.

## Switch Version Endpoint

- Issue: The switch-version endpoint ignores the path `msg_id`.
- Impact: Requests can target one message in the URL while switching another message from the request body, which makes authorization and client behavior harder to reason about.
- Suggested next step: Validate that the path `msg_id` matches the body target or remove the duplicate body field and use only the path parameter.
- Affected files: `backend/data.py`.
