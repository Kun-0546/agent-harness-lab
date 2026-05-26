"""Unit tests for harness_package module (parser, hashing, install).

Covers spec docs/harness-package-mvp.md §3-§11 + §15 error cases (parser side).
Integration with workflow/snapshot/evidence lives in
tests/test_harness_package_integration.py.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_harness_lab import harness_package
from agent_harness_lab.harness_package import (
    SUPPORTED_RUNTIME_TYPES,
    Manifest,
    compute_effective_harness_hash,
    compute_manifest_hash,
    compute_payload_hash,
    discover_packages,
    install_package_payload,
    manifest_path_posix,
    merge_env,
    parse_manifest,
    parse_variant_ref,
    resolve_start_command,
)


def _write_pkg(workspace: Path, pkg_id: str, version: str,
               manifest_body: str | None = None,
               payload_files: dict[str, str] | None = None) -> Path:
    """Create harness-packages/<pkg_id>/<version>/{manifest.md, payload/...}."""
    pkg_dir = workspace / "harness-packages" / pkg_id / version
    payload_dir = pkg_dir / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    if payload_files is not None:
        for name, content in payload_files.items():
            (payload_dir / name).write_text(content, encoding="utf-8")
    if manifest_body is None:
        manifest_body = _default_manifest(pkg_id, version)
    (pkg_dir / "manifest.md").write_text(manifest_body, encoding="utf-8")
    return pkg_dir / "manifest.md"


def _default_manifest(pkg_id: str, version: str,
                       runtime_compat: str = "[local_path, git_repo]") -> str:
    return f"""---
id: {pkg_id}
version: {version}
runtime_compatibility: {runtime_compat}
---

## Description
Test package.

## Payload

files:
  - target: prompts/system.md
    source: payload/system.md
env:
  HARNESS_X: "1"
start_command: python -m agent.run
"""


# ===========================================================================
# Group: parse_variant_ref
# ===========================================================================


class TestParseVariantRef(unittest.TestCase):

    def test_valid_basic(self):
        pkg_id, version = parse_variant_ref("foo@0.1.0")
        self.assertEqual(pkg_id, "foo")
        self.assertEqual(version, "0.1.0")

    def test_valid_kebab(self):
        pkg_id, version = parse_variant_ref("minimal-strict-prompt@0.1.0")
        self.assertEqual(pkg_id, "minimal-strict-prompt")
        self.assertEqual(version, "0.1.0")

    def test_valid_semver_prerelease(self):
        pkg_id, version = parse_variant_ref("foo@1.0.0-alpha.1")
        self.assertEqual(version, "1.0.0-alpha.1")

    def test_bare_id_invalid(self):
        with self.assertRaises(ValueError) as ctx:
            parse_variant_ref("foo")
        self.assertIn("<id>@<version>", str(ctx.exception))

    def test_missing_version_after_at(self):
        with self.assertRaises(ValueError):
            parse_variant_ref("foo@")

    def test_uppercase_id_rejected(self):
        with self.assertRaises(ValueError):
            parse_variant_ref("Foo@0.1.0")

    def test_non_semver_version_rejected(self):
        with self.assertRaises(ValueError):
            parse_variant_ref("foo@0.1")

    def test_empty(self):
        with self.assertRaises(ValueError):
            parse_variant_ref("")


# ===========================================================================
# Group: parse_manifest
# ===========================================================================


class TestParseManifest(unittest.TestCase):

    def test_valid_full(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            mp = _write_pkg(tmp, "foo", "0.1.0",
                             payload_files={"system.md": "hello"})
            m = parse_manifest(mp, expected_id="foo",
                                expected_version="0.1.0")
        self.assertEqual(m.id, "foo")
        self.assertEqual(m.version, "0.1.0")
        self.assertEqual(m.ref, "foo@0.1.0")
        self.assertEqual(m.runtime_compatibility,
                         ["local_path", "git_repo"])
        self.assertEqual(m.description, "Test package.")
        self.assertEqual(len(m.payload_files), 1)
        self.assertEqual(m.payload_files[0]["target"], "prompts/system.md")
        self.assertEqual(m.payload_env, {"HARNESS_X": "1"})
        self.assertEqual(m.payload_start_command, "python -m agent.run")

    def test_missing_id_raises(self):
        body = """---
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
x
## Payload
start_command: x
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp, expected_id="foo",
                               expected_version="0.1.0")
            self.assertIn("缺 id", str(ctx.exception))

    def test_missing_version_raises(self):
        body = """---
id: foo
runtime_compatibility: [local_path]
---

## Description
x
## Payload
start_command: x
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp)
            self.assertIn("缺 version", str(ctx.exception))

    def test_missing_runtime_compatibility_raises(self):
        body = """---
id: foo
version: 0.1.0
---

## Description
x
## Payload
start_command: x
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp)
            self.assertIn("runtime_compatibility", str(ctx.exception))

    def test_runtime_compatibility_with_legacy_connect_rejected(self):
        body = _default_manifest(
            "foo", "0.1.0",
            runtime_compat="[local_path, legacy_connect]",
        )
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={"system.md": "x"})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp)
            self.assertIn("legacy_connect", str(ctx.exception))

    def test_runtime_compatibility_unknown_type_accepted(self):
        # Forward-compat: docker_image etc. accepted at parse time;
        # only rejected at use time (workflow preflight).
        body = _default_manifest(
            "foo", "0.1.0",
            runtime_compat="[local_path, docker_image]",
        )
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={"system.md": "x"})
            m = parse_manifest(mp)
        self.assertIn("docker_image", m.runtime_compatibility)

    def test_id_path_mismatch_raises(self):
        body = _default_manifest("bar", "0.1.0")
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={"system.md": "x"})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp, expected_id="foo",
                                expected_version="0.1.0")
            self.assertIn("不一致", str(ctx.exception))

    def test_version_path_mismatch_raises(self):
        body = _default_manifest("foo", "0.2.0")
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={"system.md": "x"})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp, expected_id="foo",
                                expected_version="0.1.0")
            self.assertIn("不一致", str(ctx.exception))

    def test_unknown_frontmatter_field_rejected(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
unknown_field: x
---

## Description
x
## Payload
start_command: x
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp)
            self.assertIn("unknown_field", str(ctx.exception))

    def test_description_section_missing(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Payload
start_command: x
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp)
            self.assertIn("Description", str(ctx.exception))

    def test_payload_section_missing(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
x
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp)
            self.assertIn("Payload", str(ctx.exception))

    def test_all_empty_payload_rejected(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
empty
## Payload

"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp)
            self.assertIn("三段全空", str(ctx.exception))

    def test_payload_empty_files_but_has_env_ok(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
env-only package
## Payload
env:
  HARNESS_X: "1"
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            m = parse_manifest(mp)
        self.assertEqual(m.payload_files, [])
        self.assertEqual(m.payload_env, {"HARNESS_X": "1"})
        self.assertIsNone(m.payload_start_command)

    def test_payload_empty_files_but_has_start_command_ok(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
start-only package
## Payload
start_command: python -m agent.run
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            m = parse_manifest(mp)
        self.assertEqual(m.payload_files, [])
        self.assertEqual(m.payload_start_command, "python -m agent.run")

    def test_payload_source_path_traversal_rejected(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
traversal attempt
## Payload
files:
  - target: prompts/system.md
    source: ../../etc/passwd
start_command: x
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            with self.assertRaises(ValueError) as ctx:
                parse_manifest(mp)
            self.assertIn("越出 payload/", str(ctx.exception))

    def test_description_empty_body_ok(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description

## Payload
start_command: x
"""
        with TemporaryDirectory() as t:
            mp = _write_pkg(Path(t), "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            m = parse_manifest(mp)
        self.assertEqual(m.description, "")  # empty body OK


# ===========================================================================
# Group: discover_packages
# ===========================================================================


class TestDiscoverPackages(unittest.TestCase):

    def test_empty_workspace(self):
        with TemporaryDirectory() as t:
            result = discover_packages(Path(t))
        self.assertEqual(result, {})

    def test_single_package(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            _write_pkg(tmp, "foo", "0.1.0",
                        payload_files={"system.md": "x"})
            result = discover_packages(tmp)
        self.assertEqual(set(result.keys()), {("foo", "0.1.0")})
        self.assertEqual(result[("foo", "0.1.0")].ref, "foo@0.1.0")

    def test_multiple_versions_same_id(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            _write_pkg(tmp, "foo", "0.1.0", payload_files={"a.md": "x"})
            _write_pkg(tmp, "foo", "0.2.0", payload_files={"a.md": "y"})
            result = discover_packages(tmp)
        self.assertEqual(set(result.keys()),
                         {("foo", "0.1.0"), ("foo", "0.2.0")})

    def test_multiple_packages(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            _write_pkg(tmp, "foo", "0.1.0", payload_files={"a.md": "x"})
            _write_pkg(tmp, "bar", "0.1.0", payload_files={"a.md": "y"})
            result = discover_packages(tmp)
        self.assertEqual(set(result.keys()),
                         {("foo", "0.1.0"), ("bar", "0.1.0")})

    def test_directory_without_manifest_skipped(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            # Create empty package dir (no manifest)
            (tmp / "harness-packages" / "wip" / "0.0.1").mkdir(parents=True)
            _write_pkg(tmp, "foo", "0.1.0", payload_files={"a.md": "x"})
            result = discover_packages(tmp)
        self.assertEqual(set(result.keys()), {("foo", "0.1.0")})

    def test_path_id_mismatch_raises(self):
        # Write manifest with id="bar" but place at harness-packages/foo/0.1.0/
        body = _default_manifest("bar", "0.1.0")
        with TemporaryDirectory() as t:
            tmp = Path(t)
            _write_pkg(tmp, "foo", "0.1.0", manifest_body=body,
                        payload_files={"system.md": "x"})
            with self.assertRaises(ValueError):
                discover_packages(tmp)


# ===========================================================================
# Group: hashing
# ===========================================================================


def _make_manifest_for_hash_tests(tmp: Path, env: dict = None,
                                    start_cmd: str = "python -m a.b",
                                    file_content: str = "hello"):
    payload_files = {"system.md": file_content}
    env_str = ""
    if env:
        env_str = "\nenv:\n" + "\n".join(
            f'  {k}: "{v}"' for k, v in env.items())
    body = f"""---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
hash test
## Payload

files:
  - target: prompts/system.md
    source: payload/system.md{env_str}
start_command: {start_cmd}
"""
    mp = _write_pkg(tmp, "foo", "0.1.0", manifest_body=body,
                     payload_files=payload_files)
    return parse_manifest(mp)


class TestManifestHash(unittest.TestCase):

    def test_stable(self):
        with TemporaryDirectory() as t:
            m = _make_manifest_for_hash_tests(Path(t))
            h1 = compute_manifest_hash(m.manifest_path)
            h2 = compute_manifest_hash(m.manifest_path)
        self.assertEqual(h1, h2)
        self.assertTrue(h1.startswith("sha256:"))

    def test_changes_with_content(self):
        with TemporaryDirectory() as t1:
            m1 = _make_manifest_for_hash_tests(Path(t1))
            h1 = compute_manifest_hash(m1.manifest_path)
        with TemporaryDirectory() as t2:
            m2 = _make_manifest_for_hash_tests(
                Path(t2), start_cmd="python -m other")
            h2 = compute_manifest_hash(m2.manifest_path)
        self.assertNotEqual(h1, h2)


class TestPayloadHash(unittest.TestCase):

    def test_stable(self):
        with TemporaryDirectory() as t:
            m = _make_manifest_for_hash_tests(Path(t),
                                                env={"A": "1", "B": "2"})
            h1 = compute_payload_hash(m)
            h2 = compute_payload_hash(m)
        self.assertEqual(h1, h2)

    def test_changes_with_file_content(self):
        with TemporaryDirectory() as t1:
            m1 = _make_manifest_for_hash_tests(Path(t1),
                                                 file_content="hello")
            h1 = compute_payload_hash(m1)
        with TemporaryDirectory() as t2:
            m2 = _make_manifest_for_hash_tests(Path(t2),
                                                 file_content="world")
            h2 = compute_payload_hash(m2)
        self.assertNotEqual(h1, h2)

    def test_changes_with_env(self):
        with TemporaryDirectory() as t1:
            m1 = _make_manifest_for_hash_tests(Path(t1), env={"A": "1"})
            h1 = compute_payload_hash(m1)
        with TemporaryDirectory() as t2:
            m2 = _make_manifest_for_hash_tests(Path(t2), env={"A": "2"})
            h2 = compute_payload_hash(m2)
        self.assertNotEqual(h1, h2)

    def test_changes_with_start_command(self):
        with TemporaryDirectory() as t1:
            m1 = _make_manifest_for_hash_tests(Path(t1),
                                                 start_cmd="a")
            h1 = compute_payload_hash(m1)
        with TemporaryDirectory() as t2:
            m2 = _make_manifest_for_hash_tests(Path(t2),
                                                 start_cmd="b")
            h2 = compute_payload_hash(m2)
        self.assertNotEqual(h1, h2)

    def test_file_order_does_not_affect(self):
        # Build two manifests with same files but different declared order
        def _m(tmp, files_decl):
            body = f"""---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
order test
## Payload

files:
{files_decl}
start_command: x
"""
            payload = {"a.md": "AAA", "b.md": "BBB"}
            mp = _write_pkg(tmp, "foo", "0.1.0", manifest_body=body,
                             payload_files=payload)
            return parse_manifest(mp)

        files_order_1 = (
            "  - target: prompts/a.md\n    source: payload/a.md\n"
            "  - target: prompts/b.md\n    source: payload/b.md"
        )
        files_order_2 = (
            "  - target: prompts/b.md\n    source: payload/b.md\n"
            "  - target: prompts/a.md\n    source: payload/a.md"
        )
        with TemporaryDirectory() as t1:
            m1 = _m(Path(t1), files_order_1)
            h1 = compute_payload_hash(m1)
        with TemporaryDirectory() as t2:
            m2 = _m(Path(t2), files_order_2)
            h2 = compute_payload_hash(m2)
        self.assertEqual(h1, h2)


class TestEffectiveHarnessHash(unittest.TestCase):

    def test_stable(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            sandbox = tmp / "sb"
            (sandbox / "prompts").mkdir(parents=True)
            (sandbox / "prompts" / "system.md").write_text("x",
                                                            encoding="utf-8")
            h1 = compute_effective_harness_hash(
                sandbox, ["prompts/system.md"], [],
                {"A": "1"}, "cmd")
            h2 = compute_effective_harness_hash(
                sandbox, ["prompts/system.md"], [],
                {"A": "1"}, "cmd")
        self.assertEqual(h1, h2)

    def test_includes_union_of_targets(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            sandbox = tmp / "sb"
            (sandbox / "prompts").mkdir(parents=True)
            (sandbox / "prompts" / "system.md").write_text("x",
                                                            encoding="utf-8")
            (sandbox / "prompts" / "other.md").write_text("y",
                                                           encoding="utf-8")
            h_only_package = compute_effective_harness_hash(
                sandbox, ["prompts/system.md"], [],
                {}, "cmd")
            h_with_patch_target = compute_effective_harness_hash(
                sandbox, ["prompts/system.md"], ["prompts/other.md"],
                {}, "cmd")
        self.assertNotEqual(h_only_package, h_with_patch_target)

    def test_changes_with_file_content(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            sandbox = tmp / "sb"
            (sandbox / "prompts").mkdir(parents=True)
            p = sandbox / "prompts" / "system.md"
            p.write_text("x", encoding="utf-8")
            h1 = compute_effective_harness_hash(
                sandbox, ["prompts/system.md"], [], {}, "cmd")
            p.write_text("y", encoding="utf-8")
            h2 = compute_effective_harness_hash(
                sandbox, ["prompts/system.md"], [], {}, "cmd")
        self.assertNotEqual(h1, h2)

    def test_changes_with_env_or_start(self):
        with TemporaryDirectory() as t:
            sandbox = Path(t) / "sb"
            sandbox.mkdir()
            h1 = compute_effective_harness_hash(sandbox, [], [],
                                                  {"A": "1"}, "cmd")
            h2 = compute_effective_harness_hash(sandbox, [], [],
                                                  {"A": "2"}, "cmd")
            h3 = compute_effective_harness_hash(sandbox, [], [],
                                                  {"A": "1"}, "cmd2")
        self.assertNotEqual(h1, h2)
        self.assertNotEqual(h1, h3)


# ===========================================================================
# Group: merge_env / resolve_start_command
# ===========================================================================


class TestMergeEnv(unittest.TestCase):

    def test_patch_overrides_package(self):
        out = merge_env({"A": "1", "B": "2"}, {"B": "20", "C": "3"})
        self.assertEqual(out, {"A": "1", "B": "20", "C": "3"})

    def test_disjoint_keys(self):
        out = merge_env({"A": "1"}, {"B": "2"})
        self.assertEqual(out, {"A": "1", "B": "2"})

    def test_empty_inputs(self):
        self.assertEqual(merge_env({}, {}), {})
        self.assertEqual(merge_env({"A": "1"}, {}), {"A": "1"})
        self.assertEqual(merge_env({}, {"A": "1"}), {"A": "1"})


class TestResolveStartCommand(unittest.TestCase):

    def test_patch_wins(self):
        self.assertEqual(resolve_start_command("patch-cmd", "mfst-cmd"),
                         "patch-cmd")

    def test_fallback_to_manifest(self):
        self.assertEqual(resolve_start_command(None, "mfst-cmd"),
                         "mfst-cmd")
        self.assertEqual(resolve_start_command("", "mfst-cmd"), "mfst-cmd")

    def test_both_none(self):
        self.assertIsNone(resolve_start_command(None, None))
        self.assertIsNone(resolve_start_command("", None))


# ===========================================================================
# Group: install_package_payload
# ===========================================================================


class TestInstallPackagePayload(unittest.TestCase):

    def test_installs_files(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            mp = _write_pkg(tmp, "foo", "0.1.0",
                             payload_files={"system.md": "HELLO"})
            m = parse_manifest(mp)
            sandbox = tmp / "sb"
            sandbox.mkdir()
            install_package_payload(m, sandbox)
            installed = sandbox / "prompts" / "system.md"
            self.assertTrue(installed.exists())
            self.assertEqual(installed.read_text(encoding="utf-8"), "HELLO")

    def test_creates_parent_dirs(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
nested
## Payload

files:
  - target: a/b/c/system.md
    source: payload/system.md
start_command: x
"""
        with TemporaryDirectory() as t:
            tmp = Path(t)
            mp = _write_pkg(tmp, "foo", "0.1.0", manifest_body=body,
                             payload_files={"system.md": "HI"})
            m = parse_manifest(mp)
            sandbox = tmp / "sb"
            sandbox.mkdir()
            install_package_payload(m, sandbox)
            self.assertTrue((sandbox / "a/b/c/system.md").exists())

    def test_target_path_traversal_rejected(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
traversal
## Payload

files:
  - target: ../escape.md
    source: payload/system.md
start_command: x
"""
        with TemporaryDirectory() as t:
            tmp = Path(t)
            mp = _write_pkg(tmp, "foo", "0.1.0", manifest_body=body,
                             payload_files={"system.md": "x"})
            m = parse_manifest(mp)
            sandbox = tmp / "sb"
            sandbox.mkdir()
            with self.assertRaises(RuntimeError) as ctx:
                install_package_payload(m, sandbox)
            self.assertIn("越出 sandbox", str(ctx.exception))

    def test_missing_source_raises(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            mp = _write_pkg(tmp, "foo", "0.1.0",
                             payload_files={"system.md": "x"})
            m = parse_manifest(mp)
            # Remove the source file after parse
            (tmp / "harness-packages" / "foo" / "0.1.0" / "payload"
             / "system.md").unlink()
            sandbox = tmp / "sb"
            sandbox.mkdir()
            with self.assertRaises(FileNotFoundError):
                install_package_payload(m, sandbox)

    def test_empty_payload_files_noop(self):
        body = """---
id: foo
version: 0.1.0
runtime_compatibility: [local_path]
---

## Description
env only
## Payload

env:
  X: "1"
start_command: cmd
"""
        with TemporaryDirectory() as t:
            tmp = Path(t)
            mp = _write_pkg(tmp, "foo", "0.1.0", manifest_body=body,
                             payload_files={})
            m = parse_manifest(mp)
            sandbox = tmp / "sb"
            sandbox.mkdir()
            install_package_payload(m, sandbox)  # no-op
            # Sandbox stays empty
            self.assertEqual(list(sandbox.iterdir()), [])


# ===========================================================================
# Group: manifest_path_posix
# ===========================================================================


class TestManifestPathPosix(unittest.TestCase):

    def test_returns_forward_slash(self):
        with TemporaryDirectory() as t:
            tmp = Path(t)
            mp = _write_pkg(tmp, "foo", "0.1.0",
                             payload_files={"system.md": "x"})
            posix = manifest_path_posix(tmp, mp)
        self.assertEqual(
            posix, "harness-packages/foo/0.1.0/manifest.md")
        self.assertNotIn("\\", posix)


# ===========================================================================
# Group: Redlines / sanity
# ===========================================================================


class TestRedlines(unittest.TestCase):

    def test_supported_types_only_two_in_v05(self):
        self.assertEqual(SUPPORTED_RUNTIME_TYPES, ("local_path", "git_repo"))

    def test_harness_package_module_has_no_third_party_imports(self):
        import sys
        before = set(sys.modules.keys())
        import importlib

        importlib.reload(harness_package)
        added = set(sys.modules.keys()) - before
        third_party = [
            m for m in added
            if "." not in m
            and m not in sys.stdlib_module_names
            and not m.startswith("agent_harness_lab")
            and not m.startswith("_")
        ]
        self.assertEqual(third_party, [],
                         f"harness_package pulled third-party imports: "
                         f"{third_party}")


if __name__ == "__main__":
    unittest.main()
