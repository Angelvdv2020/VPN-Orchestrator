from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass
from typing import Iterable

from .errors import CommandError


@dataclass(slots=True)
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class ShellRunner:
    def __init__(
        self,
        logger: logging.Logger,
        timeout: int = 30,
        dry_run: bool = False,
        secrets: Iterable[str] = (),
    ):
        self.logger = logger
        self.timeout = timeout
        self.dry_run = dry_run
        self.secrets = tuple(x for x in secrets if x)

    def _redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "***")
        return text

    def run(
        self,
        argv: list[str],
        *,
        check: bool = True,
        timeout: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        printable = self._redact(shlex.join(argv))
        self.logger.debug("EXEC: %s", printable)

        if self.dry_run:
            self.logger.info("[DRY-RUN] %s", printable)
            return CommandResult(argv, 0, "", "")

        try:
            cp = subprocess.run(
                argv,
                input=input_text,
                text=True,
                capture_output=True,
                timeout=timeout or self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandError(
                f"Команда превысила timeout {timeout or self.timeout}s: {printable}"
            ) from exc
        except OSError as exc:
            raise CommandError(f"Не удалось запустить: {printable}: {exc}") from exc

        stdout = self._redact(cp.stdout or "")
        stderr = self._redact(cp.stderr or "")
        self.logger.debug("RC=%s STDOUT=%r STDERR=%r", cp.returncode, stdout, stderr)

        result = CommandResult(argv, cp.returncode, stdout, stderr)
        if check and cp.returncode != 0:
            msg = stderr.strip() or stdout.strip() or f"код {cp.returncode}"
            raise CommandError(f"{printable}: {msg}")
        return result
