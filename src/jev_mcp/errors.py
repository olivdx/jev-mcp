from __future__ import annotations


class JevMcpError(Exception):
    """Base error carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class NotConfiguredError(JevMcpError):
    def __init__(self) -> None:
        super().__init__(
            "NOT_CONFIGURED",
            "No TypeSafe API key. Run 'jev-mcp key add <API_KEY>' or set TYPESAFE_API_KEY.",
        )


class InvalidKeyError(JevMcpError):
    def __init__(self, message: str = "TypeSafe rejected the API key") -> None:
        super().__init__("INVALID_KEY", message)


class AuthFailedError(JevMcpError):
    def __init__(self, message: str = "TypeSafe authentication failed (401)") -> None:
        super().__init__("AUTH_FAILED", message)


class RateLimitedError(JevMcpError):
    def __init__(self, message: str = "TypeSafe rate limit reached (429)") -> None:
        super().__init__("JEV_RATE_LIMITED", message)


class JevTimeoutError(JevMcpError):
    def __init__(self, message: str = "TypeSafe request timed out") -> None:
        super().__init__("JEV_TIMEOUT", message)


class ApiUnreachableError(JevMcpError):
    def __init__(self, message: str = "Cannot reach the TypeSafe API") -> None:
        super().__init__("API_UNREACHABLE", message)


class JevError(JevMcpError):
    def __init__(self, message: str = "TypeSafe request failed") -> None:
        super().__init__("JEV_ERROR", message)


class PathInvalidError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("PATH_INVALID", message)


class NotARepoError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("NOT_A_REPO", message)


class GitNotFoundError(JevMcpError):
    def __init__(self) -> None:
        super().__init__("GIT_NOT_FOUND", "git was not found on PATH")


class GitFailedError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("GIT_FAILED", message)


class NoTestCommandError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("NO_TEST_COMMAND", message)


class TestRunnerFailedError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("TEST_RUNNER_FAILED", message)


class InvalidProfileError(JevMcpError):
    def __init__(self, message: str) -> None:
        super().__init__("INVALID_PROFILE", message)
