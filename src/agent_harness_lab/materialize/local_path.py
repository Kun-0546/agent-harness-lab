"""LocalPathAdapter —— C5: local_path runtime source。

跑流程(materialize):
1. lookup source (type=local_path) by version.runtime_source name
2. source_dir_hash = compute_dir_hash(source.path) ← pre-patch 的可复现指纹
3. shutil.copytree(source.path, sandbox/<run_id>/<variant_id>/)
4. apply_patch(version.patch, sandbox_path) 覆盖 target
5. 返 Sandbox(type="copy_dir", path=sandbox_path, start_command=patch.start_command,
            metadata={source_dir_hash, source_name, source_path, env})

start: _SandboxCliSession 跑 patch.start_command in sandbox cwd + patch.env (shell=False)
teardown: M1 默认 keep (no-op);C7 加 --cleanup-sandboxes flag 后改 shutil.rmtree
snapshot_fields: 返 spec §2.1 runtime_source schema (含 source_dir_hash)
"""
from __future__ import annotations

import shutil
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
            if s.type != "local_path":
                raise RuntimeError(
                    f"adapter 类型不匹配:期望 local_path,实际 {s.type} "
                    f"(source {s.name})")
            return s
    raise RuntimeError(
        f"runtime_source '{version.runtime_source}' 不在 runtime-sources.md "
        f"(preflight 应已 hard fail)")


class LocalPathAdapter:
    """local_path runtime source —— copy_dir + apply patch + subprocess (shell=False)。"""

    def materialize(self, version: Version, ctx: MaterializeContext) -> Sandbox:
        if not version.patch:
            raise RuntimeError(
                f"版本 {version.version_id}:runtime_source 写了但无 patch 段 "
                f"(M1 patch 必填,含 start_command)")

        # v0.5: 查 variant 引用的 harness package (None = 无 package)
        from agent_harness_lab.harness_package import (
            install_package_payload,
            merge_env,
            resolve_start_command,
        )
        manifest = (ctx.variant_packages or {}).get(version.version_id)

        # v0.5: 解析 effective start_command —— patch 胜出,可 fallback 到 manifest
        # v0.4 行为(无 package):等价 patch.start_command 必填,否则同样 raise
        patch_start = version.patch.start_command
        manifest_start = manifest.payload_start_command if manifest else None
        effective_start = resolve_start_command(patch_start, manifest_start)
        if not effective_start:
            raise RuntimeError(
                f"版本 {version.version_id}:必须由 package manifest 或 "
                f"variant ## Patch 至少一方提供 start_command "
                f"(M1 不假设默认命令)")

        source = _lookup_source(version, ctx)
        source_path = Path(source.config["path"])
        if not source_path.exists():
            raise RuntimeError(
                f"source path 不存在:{source_path} (source {source.name})")

        # Step 1: source_dir_hash —— pre-patch raw source 的指纹
        source_dir_hash = compute_dir_hash(source_path)

        # Step 2: copy source → sandbox
        # sandbox path 是证据链的一部分,已存在 hard fail —— 拒绝静默覆盖。
        sandbox_path = (ctx.experiment_dir / "sandbox" / ctx.run_id
                        / version.version_id)
        if sandbox_path.exists():
            raise RuntimeError(
                f"sandbox 路径已存在，拒绝覆盖: {sandbox_path}")
        sandbox_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_path, sandbox_path)

        # Step 3 (NEW v0.5): install harness package payload —— 在 patch 之前
        # spec docs/harness-package-mvp.md §9 固定 install order:
        # materialize → package → patch → snapshot。patch 之后覆盖 package
        # 同名文件,实现 "variant patch wins on file conflicts"。
        if manifest is not None:
            install_package_payload(manifest, sandbox_path)

        # Step 4: apply variant ## Patch (覆盖 target;包括覆盖 package 同名文件)
        apply_patch(version.patch, sandbox_path)

        # Merged env (package + patch, patch 胜出 per-key)
        package_env = manifest.payload_env if manifest else {}
        merged_env = merge_env(package_env, dict(version.patch.env))

        return Sandbox(
            type="copy_dir",
            path=sandbox_path,
            start_command=effective_start,
            metadata={
                "source_dir_hash": source_dir_hash,
                "source_name": source.name,
                "source_path": str(source_path),
                "env": merged_env,
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
        # 失败抛 OSError —— workflow 在 finally 块吞掉(teardown 失败不该 fail run)。
        if cleanup and sandbox.path is not None and sandbox.path.exists():
            import shutil
            shutil.rmtree(sandbox.path)

    def snapshot_fields(self, version: Version, ctx: MaterializeContext,
                        sandbox: Sandbox | None) -> dict:
        """spec §2.1 materialized runtime_source schema —— 含 source_dir_hash。

        source_dir_hash 从 sandbox.metadata 读(materialize 已算);sandbox=None
        (materialize 失败时仍尝试写 snapshot)→ 重算 source dir。
        """
        source = _lookup_source(version, ctx)
        source_path = Path(source.config["path"])
        if sandbox and "source_dir_hash" in sandbox.metadata:
            source_dir_hash = sandbox.metadata["source_dir_hash"]
        else:
            try:
                source_dir_hash = compute_dir_hash(source_path)
            except FileNotFoundError:
                source_dir_hash = ""
        return {
            "type": "local_path",
            "name": source.name,
            "path": str(source_path),
            "source_dir_hash": source_dir_hash,
        }
