"""GitRepoAdapter —— C6: git_repo runtime source (clone mode)。

跑流程(materialize):
1. lookup source (type=git_repo) by version.runtime_source name
2. git binary preflight (shutil.which)
3. sandbox path 已存在 hard fail (sandbox 是证据链,跟 LocalPathAdapter 一致)
4. git clone url → sandbox_path
5. git checkout ref (branch/tag/commit_sha 统一;detached HEAD 接受)
6. git rev-parse HEAD 拿 commit_sha
7. source_dir_hash = compute_dir_hash(sandbox_path) ← checkout 后 patch 之前
   (compute_dir_hash 已 ignore .git → git metadata 不算入指纹)
8. apply_patch(version.patch, sandbox_path) 覆盖 target

start: 复用 _SandboxCliSession (跟 LocalPathAdapter 一字不差)
teardown: M1 默认 keep (C7 加 cleanup flag 后才 shutil.rmtree)
snapshot_fields: 返 spec §2.1.2 schema (含 commit_sha + source_dir_hash)

git 操作:subprocess.run shell=False + check=True;失败由 _git_run 翻成
RuntimeError 带 stderr;workflow.run materialize 块再翻成 WorkflowError。

clone mode (vs worktree mode 留 M2+ 优化):
- 每 variant full clone,简单,无 cache 状态管理
- sandbox.type = "git_clone"
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

from agent_harness_lab.agentconn import AgentSession, _SandboxCliSession
from agent_harness_lab.hash_utils import compute_dir_hash
from agent_harness_lab.materialize import MaterializeContext, Sandbox
from agent_harness_lab.patch import apply_patch
from agent_harness_lab.runtime_source import RuntimeSource
from agent_harness_lab.version import Version


def _lookup_source(version: Version, ctx: MaterializeContext) -> RuntimeSource:
    """从 ctx.runtime_sources 找 version.runtime_source 对应 source。

    preflight 应已校验 source 存在 + type 匹配,这里 defensive raise。
    """
    for s in ctx.runtime_sources:
        if s.name == version.runtime_source:
            if s.type != "git_repo":
                raise RuntimeError(
                    f"adapter 类型不匹配:期望 git_repo,实际 {s.type} "
                    f"(source {s.name})")
            return s
    raise RuntimeError(
        f"runtime_source '{version.runtime_source}' 不在 runtime-sources.md "
        f"(preflight 应已 hard fail)")


def _resolve_git_binary() -> str:
    """Preflight:git binary 必须在 PATH (avoid cryptic 'exit code 127')。"""
    git_path = shutil.which("git")
    if git_path is None:
        raise RuntimeError(
            "git binary 不在 PATH (GitRepoAdapter 需要 git 命令行)")
    return git_path


def _git_run(git: str, args: list[str], cwd: Path | None = None) -> None:
    """跑 git 命令,失败抛 RuntimeError 带 stderr (workflow catch 翻成 WorkflowError)。"""
    try:
        subprocess.run(
            [git] + args,
            check=True, capture_output=True, text=True,
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()[:300]
        raise RuntimeError(
            f"git {args[0]} 失败 (exit {exc.returncode}): {stderr}") from exc


def _chmod_retry(func, path, exc_info):
    """shutil.rmtree onerror:read-only 文件 chmod 后 retry (Windows git .git/objects)。"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:  # noqa: BLE001
        pass


def _git_capture(git: str, args: list[str], cwd: Path | None = None) -> str:
    """跑 git 命令并返 stdout (用于 rev-parse 等);失败同 _git_run。"""
    try:
        result = subprocess.run(
            [git] + args,
            check=True, capture_output=True, text=True,
            cwd=str(cwd) if cwd else None,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()[:300]
        raise RuntimeError(
            f"git {args[0]} 失败 (exit {exc.returncode}): {stderr}") from exc


class GitRepoAdapter:
    """git_repo runtime source (C6) —— clone + checkout + patch + subprocess。"""

    def materialize(self, version: Version, ctx: MaterializeContext) -> Sandbox:
        if not version.patch:
            raise RuntimeError(
                f"版本 {version.version_id}:runtime_source 写了但无 patch 段 "
                f"(M1 patch 必填,含 start_command)")
        if not version.patch.start_command:
            raise RuntimeError(
                f"版本 {version.version_id}:patch.start_command 缺 "
                f"(M1 不假设默认命令)")

        source = _lookup_source(version, ctx)
        url = source.config["url"]
        ref = source.config["ref"]

        # Preflight: git binary
        git = _resolve_git_binary()

        # Step 1: sandbox path 已存在 hard fail (sandbox 是证据链一部分)
        sandbox_path = (ctx.experiment_dir / "sandbox" / ctx.run_id
                        / version.version_id)
        if sandbox_path.exists():
            raise RuntimeError(
                f"sandbox 路径已存在，拒绝覆盖: {sandbox_path}")
        sandbox_path.parent.mkdir(parents=True, exist_ok=True)

        # Step 2: clone url → sandbox
        _git_run(git, ["clone", url, str(sandbox_path)])

        # Step 3: checkout ref (branch/tag/commit_sha 统一;detached HEAD OK)
        _git_run(git, ["checkout", ref], cwd=sandbox_path)

        # Step 4: 拿 commit_sha (HEAD,40 字符 hex)
        commit_sha = _git_capture(
            git, ["rev-parse", "HEAD"], cwd=sandbox_path).strip()

        # Step 5: source_dir_hash —— checkout 后 patch 之前 (跟 local_path 时机一致)
        source_dir_hash = compute_dir_hash(sandbox_path)

        # Step 6: apply patch (覆盖 target;_safe_target_path 防 traversal)
        apply_patch(version.patch, sandbox_path)

        return Sandbox(
            type="git_clone",
            path=sandbox_path,
            start_command=version.patch.start_command,
            metadata={
                "source_dir_hash": source_dir_hash,
                "source_name": source.name,
                "url": url,
                "ref": ref,
                "commit_sha": commit_sha,
                "env": dict(version.patch.env),
            },
        )

    def start(self, sandbox: Sandbox) -> AgentSession:
        if sandbox.start_command is None:
            raise RuntimeError(f"sandbox 无 start_command:{sandbox.path}")
        env = sandbox.metadata.get("env") or {}
        return _SandboxCliSession(
            sandbox.start_command,
            cwd=sandbox.path,
            env_override=env or None,
        )

    def teardown(self, sandbox: Sandbox, cleanup: bool = False) -> None:
        # 默认 keep (sandbox 是证据链);cleanup=True 才 shutil.rmtree。
        # clone mode 下 shutil.rmtree 即可清整个 sandbox (含 .git);worktree mode
        # 留 M2+ 时再加 git worktree remove 分支。
        # Windows: git clone 的 .git/objects 文件可能 read-only,shutil.rmtree
        # PermissionError → onerror chmod retry。
        if cleanup and sandbox.path is not None and sandbox.path.exists():
            shutil.rmtree(sandbox.path, onerror=_chmod_retry)

    def snapshot_fields(self, version: Version, ctx: MaterializeContext,
                        sandbox: Sandbox | None) -> dict:
        """spec §2.1.2 git_repo runtime_source schema (含 commit_sha + source_dir_hash)。

        sandbox=None (materialize 失败时 → 还没 checkout)→ commit_sha 和
        source_dir_hash 都空串(诚实表达 "材料化失败,没拿到指纹")。
        """
        source = _lookup_source(version, ctx)
        if sandbox and "commit_sha" in sandbox.metadata:
            commit_sha = sandbox.metadata["commit_sha"]
            source_dir_hash = sandbox.metadata.get("source_dir_hash", "")
        else:
            commit_sha = ""
            source_dir_hash = ""
        return {
            "type": "git_repo",
            "name": source.name,
            "url": source.config["url"],
            "ref": source.config["ref"],
            "commit_sha": commit_sha,
            "source_dir_hash": source_dir_hash,
        }
