#!/usr/bin/env python3
"""Build / manage a warm Daytona DinD snapshot with task images pre-pulled.

Harbor compose trials otherwise pull task base and emulator images in every
sandbox. Under concurrency that hits registry rate limits. Daytona snapshots do
not retain DinD's /var/lib/docker, so this stores a compressed docker-save
archive in the snapshot filesystem for the runtime environment to load locally.

Usage (use Harbor's Python so the daytona SDK is available):

  set -a && source .env && set +a
  ~/.local/share/uv/tools/harbor/bin/python scripts/build_dind_snapshot.py build
  ~/.local/share/uv/tools/harbor/bin/python scripts/build_dind_snapshot.py status
  ~/.local/share/uv/tools/harbor/bin/python scripts/build_dind_snapshot.py delete

Then run Harbor with:

  harbor run ... -e daytona --ek dind_snapshot=harbor-dind-emulator-1c2g5d-v4 ...

When an emulator or task base image changes: delete + build again, or bump
--name to the next version and flip --ek.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from pathlib import Path
import shlex
import sys
from typing import Sequence

try:
    from daytona import (
        AsyncDaytona,
        CreateSandboxFromImageParams,
        DaytonaConfig,
        Image,
        Resources,
    )
except ImportError:
    sys.stderr.write(
        "daytona SDK not found. Run with Harbor's Python, e.g.\n"
        "  ~/.local/share/uv/tools/harbor/bin/python "
        "scripts/build_dind_snapshot.py build\n"
    )
    raise SystemExit(1)

DEFAULT_NAME = "harbor-dind-emulator-1c2g5d-v4"
DEFAULT_DIND_IMAGE = "docker:28.3.3-dind"
EMULATOR_DIGEST = "sha256:a3dc8a1f0c354e973937d95550bb1e67a0e4cfd810bdddc34191317d60a8b5ab"
EMULATOR_IMAGE = f"public.ecr.aws/f8p0s4x7/taskgen-emulator@{EMULATOR_DIGEST}"
CATEGORY_EMULATOR_IMAGE = (
    "public.ecr.aws/f8p0s4x7/taskgen-emulator:cat-1ab2a6b42823"
)
LOCAL_EMULATOR_IMAGE = "harbor.local/taskgen-emulator:a3dc8a1f0c35"
LOCAL_CATEGORY_EMULATOR_IMAGE = "harbor.local/taskgen-emulator:cat-1ab2a6b42823"
SNAPSHOT_IMAGE_ARCHIVE = "/opt/harbor-images/images.tar.gz"
DEFAULT_PULLS = (
    EMULATOR_IMAGE,
    CATEGORY_EMULATOR_IMAGE,
    "public.ecr.aws/docker/library/ubuntu:24.04",
    "public.ecr.aws/docker/library/node:22-bookworm-slim",
    "public.ecr.aws/docker/library/python:3.13-slim-bookworm",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = PROJECT_ROOT / "tasks"
LOCAL_TASK_IMAGE_REPOSITORY = "harbor.local/task-main"


def _task_images() -> list[tuple[str, Path]]:
    """Return one deterministic local image tag per unique task Dockerfile."""
    unique: dict[str, Path] = {}
    for dockerfile in sorted(TASKS_DIR.glob("*/environment/Dockerfile")):
        digest = hashlib.sha256(dockerfile.read_bytes()).hexdigest()
        unique.setdefault(digest, dockerfile)
    return [
        (f"{LOCAL_TASK_IMAGE_REPOSITORY}:{digest[:12]}", dockerfile)
        for digest, dockerfile in sorted(unique.items())
    ]


async def _build_task_images(sandbox) -> None:
    task_images = _task_images()
    print(f"building {len(task_images)} unique task images…")
    for image, dockerfile in task_images:
        dockerfile_text = dockerfile.read_text()
        if any(
            line.lstrip().upper().startswith(("COPY ", "ADD "))
            for line in dockerfile_text.splitlines()
        ):
            raise RuntimeError(
                f"{dockerfile} uses COPY/ADD; snapshot builder must upload its context"
            )
        digest = image.rsplit(":", 1)[1]
        remote_dir = f"/tmp/harbor-task-images/{digest}"
        await _exec(sandbox, f"mkdir -p {shlex.quote(remote_dir)}", timeout=30)
        await sandbox.fs.upload_file(
            str(dockerfile), f"{remote_dir}/Dockerfile"
        )
        print(f"building {image} from {dockerfile.relative_to(PROJECT_ROOT)}…")
        out = await _exec(
            sandbox,
            "docker build --pull=false "
            f"-t {shlex.quote(image)} {shlex.quote(remote_dir)}",
            timeout=1200,
        )
        if out.strip():
            print(out.rstrip())


async def _write_image_archive(sandbox) -> None:
    """Store runtime images outside /var/lib/docker for snapshot persistence.

    Daytona snapshots do not retain DinD's Docker data directory. A compressed
    docker-save archive in the regular sandbox filesystem survives snapshotting
    and is loaded by ReliableDaytonaEnvironment after dockerd starts.
    """
    await _exec(
        sandbox,
        f"docker tag {shlex.quote(EMULATOR_IMAGE)} "
        f"{shlex.quote(LOCAL_EMULATOR_IMAGE)} && "
        f"docker tag {shlex.quote(CATEGORY_EMULATOR_IMAGE)} "
        f"{shlex.quote(LOCAL_CATEGORY_EMULATOR_IMAGE)}",
        timeout=60,
    )
    images = [
        LOCAL_EMULATOR_IMAGE,
        LOCAL_CATEGORY_EMULATOR_IMAGE,
        *(image for image, _ in _task_images()),
    ]
    image_args = " ".join(shlex.quote(image) for image in images)
    archive = shlex.quote(SNAPSHOT_IMAGE_ARCHIVE)
    await _exec(
        sandbox,
        "mkdir -p /opt/harbor-images && "
        f"docker save {image_args} | gzip -1 > {archive}.tmp && "
        f"mv {archive}.tmp {archive} && gzip -t {archive}",
        timeout=1200,
    )
    print((await _exec(sandbox, f"ls -lh {archive}", timeout=30)).rstrip())


async def _prepare_snapshot_capture(sandbox) -> None:
    """Stop dockerd so the snapshot boots without stale daemon state."""
    print("stopping dockerd cleanly before filesystem capture…")
    await _exec(
        sandbox,
        "pid=''; "
        "[ ! -f /var/run/docker.pid ] || pid=$(cat /var/run/docker.pid); "
        "[ -z \"$pid\" ] || kill \"$pid\" 2>/dev/null || true; "
        "i=0; while [ -n \"$pid\" ] && kill -0 \"$pid\" 2>/dev/null "
        "&& [ $i -lt 60 ]; do sleep 1; i=$((i+1)); done; "
        "sync; rm -f /var/run/docker.pid /var/run/docker.sock",
        timeout=90,
    )


def _exit_code(resp: object) -> int:
    return int(getattr(resp, "exit_code", 0) or 0)


def _exec_text(resp: object) -> str:
    for attr in ("result", "stdout", "output"):
        value = getattr(resp, attr, None)
        if isinstance(value, str):
            return value
    artifacts = getattr(resp, "artifacts", None)
    stdout = getattr(artifacts, "stdout", None) if artifacts is not None else None
    return stdout if isinstance(stdout, str) else ""


async def _exec(sandbox, cmd: str, timeout: int = 600) -> str:
    resp = await sandbox.process.exec(cmd, timeout=timeout)
    out = _exec_text(resp)
    code = _exit_code(resp)
    if code != 0:
        raise RuntimeError(f"exit={code}\ncmd={cmd}\n{out}")
    return out


def _require_api_key() -> str:
    key = os.environ.get("DAYTONA_API_KEY")
    if not key:
        raise SystemExit("DAYTONA_API_KEY is not set (source .env first)")
    return key


async def cmd_status(name: str) -> None:
    async with AsyncDaytona(DaytonaConfig(api_key=_require_api_key())) as daytona:
        try:
            snap = await daytona.snapshot.get(name)
        except Exception as exc:
            print(f"{name}: not found ({exc})")
            raise SystemExit(1) from exc
        print(
            f"{snap.name}  state={snap.state}  "
            f"cpu={snap.cpu}  mem_gib={snap.mem}  disk_gib={snap.disk}"
        )
        if getattr(snap, "error_reason", None):
            print(f"  error_reason={snap.error_reason}")


async def cmd_delete(name: str) -> None:
    async with AsyncDaytona(DaytonaConfig(api_key=_require_api_key())) as daytona:
        try:
            snap = await daytona.snapshot.get(name)
        except Exception as exc:
            print(f"{name}: not found ({exc})")
            raise SystemExit(1) from exc
        await daytona.snapshot.delete(snap)
        print(f"deleted {name}")


async def cmd_build(
    *,
    name: str,
    dind_image: str,
    pulls: Sequence[str],
    cpu: int,
    memory: int,
    disk: int,
    force: bool,
) -> None:
    async with AsyncDaytona(DaytonaConfig(api_key=_require_api_key())) as daytona:
        try:
            existing = await daytona.snapshot.get(name)
        except Exception:
            existing = None

        if existing is not None:
            if not force:
                raise SystemExit(
                    f"snapshot {name!r} already exists "
                    f"(state={existing.state}). Pass --force to replace it."
                )
            print(f"deleting existing snapshot {name} (state={existing.state})…")
            await daytona.snapshot.delete(existing)

        params = CreateSandboxFromImageParams(
            image=Image.base(dind_image),
            resources=Resources(cpu=cpu, memory=memory, disk=disk),
            network_block_all=False,
            auto_stop_interval=0,
            auto_delete_interval=0,
            # Empty TLS dir matches typical dind usage and avoids cert bootstrap races.
            env_vars={"DOCKER_TLS_CERTDIR": ""},
        )
        print(
            f"creating DinD sandbox from {dind_image} "
            f"({cpu}c/{memory}GiB/{disk}GiB)…"
        )
        sandbox = await daytona.create(params, timeout=180)
        print(f"sandbox: {sandbox.id}")

        try:
            # Use the image entrypoint as-is (no trailing "dockerd" arg). Passing
            # "dockerd" makes dockerd-entrypoint.sh hit a cgroup v2 mkdir failure
            # on some Daytona runners; the bare entrypoint comes up reliably.
            print("starting dockerd…")
            await _exec(
                sandbox,
                "nohup dockerd-entrypoint.sh >/var/log/dockerd.log 2>&1 &",
                timeout=20,
            )

            print("waiting for dockerd…")
            for i in range(90):
                resp = await sandbox.process.exec(
                    "docker info --format '{{.ServerVersion}}'", timeout=15
                )
                ver = _exec_text(resp).strip()
                if _exit_code(resp) == 0 and ver:
                    print(f"dockerd ready ({ver})")
                    break
                await asyncio.sleep(2)
            else:
                log = await _exec(
                    sandbox, "tail -80 /var/log/dockerd.log || true", timeout=30
                )
                raise RuntimeError(f"dockerd not ready\n{log}")

            for img in pulls:
                print(f"pulling {img}…")
                out = await _exec(
                    sandbox, f"docker pull {shlex.quote(img)}", timeout=900
                )
                if out.strip():
                    print(out.rstrip())

            await _build_task_images(sandbox)

            await _write_image_archive(sandbox)

            print("docker images:")
            print((await _exec(sandbox, "docker images", timeout=60)).rstrip())
            print("docker disk usage:")
            print((await _exec(sandbox, "docker system df", timeout=60)).rstrip())

            await _prepare_snapshot_capture(sandbox)

            print(f"creating snapshot {name!r} (filesystem capture)…")
            await sandbox._experimental_create_snapshot(name, timeout=0)

            snap = await daytona.snapshot.get(name)
            print(
                f"done: {snap.name}  state={snap.state}  "
                f"cpu={snap.cpu}  mem_gib={snap.mem}  disk_gib={snap.disk}"
            )
            print(f"\nUse with Harbor:\n  --ek dind_snapshot={name}")
        finally:
            print("deleting builder sandbox…")
            try:
                await daytona.delete(sandbox)
            except Exception as exc:
                print(f"cleanup warning: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Warm Daytona DinD snapshot with a local runtime image archive"
    )
    parser.add_argument(
        "--name",
        default=os.environ.get("DIND_SNAPSHOT_NAME", DEFAULT_NAME),
        help=f"snapshot name (default: {DEFAULT_NAME})",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="create warm snapshot (pull + capture)")
    p_build.add_argument(
        "--dind-image",
        default=os.environ.get("DIND_IMAGE", DEFAULT_DIND_IMAGE),
        help=f"DinD base image (default: {DEFAULT_DIND_IMAGE})",
    )
    p_build.add_argument(
        "--pull",
        action="append",
        dest="pulls",
        default=None,
        help="image to pre-pull (repeatable; defaults to emulator + task bases)",
    )
    p_build.add_argument("--cpu", type=int, default=2, help="vCPUs baked into snapshot")
    p_build.add_argument(
        "--memory", type=int, default=8, help="memory GiB baked into snapshot"
    )
    p_build.add_argument(
        "--disk", type=int, default=10, help="disk GiB baked into snapshot"
    )
    p_build.add_argument(
        "--force",
        action="store_true",
        help="delete an existing snapshot with the same name first",
    )

    sub.add_parser("status", help="show snapshot state / resources")
    sub.add_parser("delete", help="delete snapshot")
    sub.add_parser(
        "harbor-flag",
        help="print the --ek flag to pass to harbor run",
    )

    args = parser.parse_args(argv)

    if args.cmd == "harbor-flag":
        print(f"--ek dind_snapshot={args.name}")
        return

    if args.cmd == "status":
        asyncio.run(cmd_status(args.name))
        return

    if args.cmd == "delete":
        asyncio.run(cmd_delete(args.name))
        return

    if args.cmd == "build":
        pulls = tuple(args.pulls) if args.pulls else DEFAULT_PULLS
        asyncio.run(
            cmd_build(
                name=args.name,
                dind_image=args.dind_image,
                pulls=pulls,
                cpu=args.cpu,
                memory=args.memory,
                disk=args.disk,
                force=args.force,
            )
        )
        return

    raise SystemExit(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
