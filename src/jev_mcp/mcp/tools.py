from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass

from jev_mcp.collectors.detect import detect_test_command
from jev_mcp.collectors.runner import run_tests
from jev_mcp.config import AppConfig, load_config
from jev_mcp.credentials import mask, resolve_api_key, verify_api_key
from jev_mcp.decision.envelope import build_decide_payload
from jev_mcp.decision.policy import POLICY_ID, PROFILES, facts_from_payloads, route_decision
from jev_mcp.errors import InvalidProfileError, JevMcpError, NotConfiguredError
from jev_mcp.jev.client import evaluate_state
from jev_mcp.jev.questions import QUESTIONSET_ID, RISK_LEVELS, build_questions
from jev_mcp.jev.state_builder import build_state
from jev_mcp.logger import new_request_id, trace
from jev_mcp.util.paths import config_path, jev_home, resolve_project_root
from jev_mcp.util.responses import tool_response


@dataclass
class AppState:
    config: AppConfig


def create_app_state(config: AppConfig | None = None) -> AppState:
    return AppState(config=config or load_config())


class _Timer:
    def __init__(self, tool: str, mcp_session_id: str | None) -> None:
        self.tool = tool
        self.request_id = new_request_id()
        self.mcp_session_id = mcp_session_id
        self._started = time.monotonic()

    def __enter__(self) -> _Timer:
        trace(
            "tool_start",
            tool=self.tool,
            request_id=self.request_id,
            mcp_session_id=self.mcp_session_id,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        trace(
            "tool_end",
            tool=self.tool,
            request_id=self.request_id,
            duration_ms=self.duration_ms,
            error_code=exc.code if isinstance(exc, JevMcpError) else None,
        )
        return False

    @property
    def duration_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)


async def handle_run_tests(
    state: AppState,
    *,
    project_root: str,
    command: list[str] | None = None,
    timeout_s: float | None = None,
    env: dict[str, str] | None = None,
    mcp_session_id: str | None = None,
) -> dict:
    with _Timer("run_tests", mcp_session_id) as timer:
        root = resolve_project_root(project_root)
        payload = await run_tests(
            root, state.config.tests, command=command, timeout_s=timeout_s, env=env
        )
        trace(
            "tests_ran",
            request_id=timer.request_id,
            runner_id=payload["runner_id"],
            exit_code=payload["exit_code"],
            duration_s=payload["duration_s"],
            timed_out=payload["timed_out"],
        )
        return tool_response(payload, request_id=timer.request_id, duration_ms=timer.duration_ms)


async def handle_decide(
    state: AppState,
    *,
    goal: str,
    tests: dict | None = None,
    project_root: str | None = None,
    profile: str | None = None,
    extra: dict | None = None,
    mcp_session_id: str | None = None,
) -> dict:
    with _Timer("decide", mcp_session_id) as timer:
        chosen = profile or state.config.decision.default_profile
        if chosen not in PROFILES:
            raise InvalidProfileError(
                f"Unknown profile '{chosen}'. Use one of: {', '.join(PROFILES)}"
            )

        api_key, _ = resolve_api_key()
        if not api_key:
            raise NotConfiguredError()

        jev_state, missing = build_state(goal=goal, tests=tests, extra=extra)
        answers = await evaluate_state(jev_state, state.config, api_key)
        result = route_decision(
            answers,
            facts=facts_from_payloads(None, tests if "tests" not in missing else None),
            profile=chosen,
            cfg=state.config.decision,
            missing_signals=missing,
        )
        trace(
            "policy_route",
            request_id=timer.request_id,
            profile=chosen,
            action=result.action,
            confidence=result.confidence,
            project_root=project_root,
        )
        payload = build_decide_payload(
            result, answers, model=state.config.jev.model, missing_signals=missing
        )
        return tool_response(payload, request_id=timer.request_id, duration_ms=timer.duration_ms)


async def handle_health(
    state: AppState,
    *,
    project_root: str | None = None,
    probe: bool = False,
    mcp_session_id: str | None = None,
) -> dict:
    with _Timer("health", mcp_session_id) as timer:
        errors: list[dict] = []
        api_key, source = resolve_api_key()

        reachable = None
        if probe and api_key:
            try:
                await asyncio.to_thread(verify_api_key, api_key)
                reachable = True
            except JevMcpError as exc:
                reachable = False
                errors.append({"code": exc.code, "message": exc.message})

        git_available = shutil.which("git") is not None

        test_command = None
        if project_root:
            detected = detect_test_command(resolve_project_root(project_root), state.config.tests)
            test_command = list(detected[1]) if detected else None

        body = {
            "ok": bool(api_key) and reachable is not False,
            "key_source": source,
            "key_hint": mask(api_key) if api_key else None,
            "typesafe_reachable": reachable,
            "git_available": git_available,
            "home": str(jev_home()),
            "config_path": str(config_path()),
            "test_command": test_command,
        }
        return tool_response(
            body, request_id=timer.request_id, duration_ms=timer.duration_ms, errors=errors
        )


async def handle_describe(state: AppState, *, mcp_session_id: str | None = None) -> dict:
    with _Timer("describe", mcp_session_id) as timer:
        questions = build_questions()
        body = {
            "tools": ["run_tests", "decide", "health", "describe"],
            "questionset_id": QUESTIONSET_ID,
            "policy_id": POLICY_ID,
            "profiles": list(PROFILES),
            "questions": {
                key: {
                    "type": type(question).__name__.lower(),
                    "instructions": getattr(question, "instructions", ""),
                }
                for key, question in questions.items()
            },
            "risk_levels": list(RISK_LEVELS),
            "workflow": [
                "agent summarizes the work in decide.extra (plan, changes, open questions)",
                "call decide with goal and extra; optionally pass run_tests payload in tests",
                "obey the action: fix keeps working, ask goes to the user, done may finish",
            ],
            "notes": [
                "there is no collect_git tool; context is agent-authored in extra",
                "next_action is a cross-check; the action comes from policy in code",
                "nouls carry no confidence; decide.confidence describes the rule that fired",
            ],
        }
        return tool_response(body, request_id=timer.request_id, duration_ms=timer.duration_ms)
