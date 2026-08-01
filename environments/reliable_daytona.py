"""Reliable Daytona DinD environment for high-concurrency Harbor jobs.

This keeps Harbor's Daytona implementation but replaces the DinD daemon startup
path with the command proven by our snapshot builder, allows more time for
startup under burst load, retries dockerd once, and includes daemon diagnostics
in the final error.
"""

from __future__ import annotations

import asyncio
import re

from harbor.environments.daytona.environment import DaytonaEnvironment, _DaytonaDinD


class _ReliableDaytonaDinD(_DaytonaDinD):
    _DOCKER_DAEMON_TIMEOUT_SEC = 180
    _DOCKER_START_COMMAND = (
        "nohup dockerd-entrypoint.sh >/var/log/dockerd.log 2>&1 </dev/null &"
    )
    _HARBOR_DOCKER_START_COMMAND = (
        "dockerd-entrypoint.sh dockerd > /var/log/dockerd.log 2>&1 &"
    )
    _SNAPSHOT_IMAGE_ARCHIVE = "/opt/harbor-images/images.tar.gz"

    async def _vm_exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
    ):
        # Harbor passes an explicit trailing `dockerd`, which can hit a cgroup-v2
        # startup failure on some Daytona runners. The bare entrypoint is the same
        # command used successfully while constructing the warm snapshot.
        if command == self._HARBOR_DOCKER_START_COMMAND:
            command = self._DOCKER_START_COMMAND
        return await super()._vm_exec(
            command,
            cwd=cwd,
            env=env,
            timeout_sec=timeout_sec,
        )

    async def _wait_once_for_docker_daemon(self) -> tuple[bool, str]:
        last_output = ""
        for _ in range(self._DOCKER_DAEMON_TIMEOUT_SEC // 2):
            result = await self._vm_exec(
                "docker version --format '{{.Server.Version}}' 2>/dev/null",
                timeout_sec=10,
            )
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            if result.return_code == 0 and re.fullmatch(r"\d+(?:\.\d+)+", output):
                return True, last_output
            last_output = output
            await asyncio.sleep(2)
        return False, last_output

    async def _load_snapshot_images(self) -> None:
        archive = self._SNAPSHOT_IMAGE_ARCHIVE
        result = await self._vm_exec(
            f"test -s {archive} && gzip -dc {archive} | docker load",
            timeout_sec=900,
        )
        if result.return_code != 0:
            output = (result.stdout or "") + (result.stderr or "")
            raise RuntimeError(
                f"Failed to load snapshot Docker images from {archive}: {output}"
            )
        self._env.logger.debug("Loaded Docker images from %s", archive)

    async def _docker_diagnostics(self) -> str:
        result = await self._vm_exec(
            "printf '%s\\n' '--- processes ---'; "
            "ps aux 2>&1 || true; "
            "printf '%s\\n' '--- first dockerd attempt ---'; "
            "tail -200 /var/log/dockerd.log.first 2>&1 || true; "
            "printf '%s\\n' '--- current dockerd attempt ---'; "
            "tail -200 /var/log/dockerd.log 2>&1 || true",
            timeout_sec=30,
        )
        return (result.stdout or "") + (result.stderr or "")

    async def _wait_for_docker_daemon(self) -> None:
        self._env.logger.debug("Waiting for Docker daemon inside DinD sandbox...")

        ready, last_output = await self._wait_once_for_docker_daemon()
        if ready:
            self._env.logger.debug("Docker daemon is ready")
            await self._load_snapshot_images()
            return

        self._env.logger.warning(
            "Docker daemon was not ready after %ss; restarting it once",
            self._DOCKER_DAEMON_TIMEOUT_SEC,
        )
        await self._vm_exec(
            "cp /var/log/dockerd.log /var/log/dockerd.log.first 2>/dev/null || true; "
            "pkill dockerd 2>/dev/null || true; sleep 2; "
            "rm -f /var/run/docker.pid /var/run/docker.sock; "
            ": > /var/log/dockerd.log; "
            f"{self._DOCKER_START_COMMAND}",
            timeout_sec=15,
        )

        ready, retry_output = await self._wait_once_for_docker_daemon()
        if ready:
            self._env.logger.debug("Docker daemon is ready after one restart")
            await self._load_snapshot_images()
            return

        diagnostics = await self._docker_diagnostics()
        raise RuntimeError(
            "Docker daemon not ready after two "
            f"{self._DOCKER_DAEMON_TIMEOUT_SEC}s attempts. "
            f"Last output: {retry_output or last_output}\n{diagnostics}"
        )


class ReliableDaytonaEnvironment(DaytonaEnvironment):
    """Daytona environment with hardened DinD startup behavior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._compose_mode:
            self._strategy = _ReliableDaytonaDinD(self)
            self.logger.debug(
                "Selected hardened strategy: %s", self._strategy.__class__.__name__
            )
