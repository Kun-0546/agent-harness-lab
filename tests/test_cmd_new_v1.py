"""hlab new creates a valid v1 experiment tree."""
import io
import os
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from agent_harness_lab import cli
from agent_harness_lab.experiment_spec import parse_experiment_yaml


@contextmanager
def workspace():
    tmp = tempfile.TemporaryDirectory()
    saved = os.getcwd()
    os.chdir(tmp.name)
    try:
        cli.main(["init"])  # quiet via redirect below in callers
        yield Path(tmp.name)
    finally:
        os.chdir(saved)
        tmp.cleanup()


class TestNew(unittest.TestCase):
    def test_new_creates_tree(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            rc = cli.main(["new", "skill-ab"])
            self.assertEqual(rc, 0)
            exp = ws / "experiments" / "skill-ab"
            for rel in ("experiment.md", "experiment.yaml", "conclusion.md",
                        "cases/cases.jsonl", "cases/playbook.yaml",
                        "evaluation/evaluation.md",
                        "agent-runtimes/runtime-a.yaml", "harnesses/A/README.md"):
                self.assertTrue((exp / rel).exists(), f"missing {rel}")
            for sub in ("traces", "raw", "artifacts", "snapshots", "scores", "inspections"):
                self.assertTrue((exp / "evidence" / sub).is_dir(), f"missing evidence/{sub}")

    def test_new_yaml_reflects_flags(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "memcmp", "--mode", "auto", "--execution", "longitudinal"])
            spec = parse_experiment_yaml(ws / "experiments" / "memcmp" / "experiment.yaml")
            self.assertEqual(spec.run_mode, "auto")
            self.assertEqual(spec.execution_mode, "longitudinal")
            self.assertEqual(spec.id, "memcmp")

    def test_new_uses_harness_not_variant(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "demo"])
            text = (ws / "experiments" / "demo" / "experiment.yaml").read_text(encoding="utf-8")
            self.assertIn("harnesses:", text)
            self.assertNotIn("variant", text.lower())

    def test_new_duplicate_errors(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "demo"])
            rc = cli.main(["new", "demo"])
            self.assertEqual(rc, 1)

    def test_new_summary_connector_hint_matches_mode(self):
        with workspace() as _ws:
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main(["new", "cop"])                      # copilot default
            self.assertIn("(manual)", out.getvalue())
            self.assertNotIn("(local_cli)", out.getvalue())
            out2 = io.StringIO()
            with redirect_stdout(out2):
                cli.main(["new", "aut", "--mode", "auto"])
            self.assertIn("(local_cli)", out2.getvalue())

    def test_empty_dirs_have_gitkeep(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "demo"])
            exp = ws / "experiments" / "demo"
            # evaluation/graders stays an empty convention dir (rubrics/benchmarks now
            # hold the scaffolded evaluator-referenced files).
            for d in ("reports", "evidence/traces", "evidence/scores", "evaluation/graders", "cases/datasets"):
                self.assertTrue((exp / d / ".gitkeep").exists(), f"{d} missing .gitkeep")

    def test_new_with_experiments_as_file_errors(self):
        tmp = tempfile.TemporaryDirectory()
        saved = os.getcwd()
        os.chdir(tmp.name)
        try:
            (Path(tmp.name) / "experiments").write_text("not a dir", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                rc = cli.main(["new", "x"])
            self.assertEqual(rc, 1)
            self.assertIn("not a directory", err.getvalue())
        finally:
            os.chdir(saved)
            tmp.cleanup()

    def test_new_requires_init(self):
        # a bare dir without experiments/ should refuse
        tmp = tempfile.TemporaryDirectory()
        saved = os.getcwd()
        os.chdir(tmp.name)
        try:
            rc = cli.main(["new", "x"])
            self.assertEqual(rc, 1)
        finally:
            os.chdir(saved)
            tmp.cleanup()


class TestQuestionFlag(unittest.TestCase):
    """hlab new --question fills `question:` so the scaffold needs no placeholder (R4)."""

    def test_question_flag_written_to_yaml_no_placeholder_warn(self):
        from agent_harness_lab.reviewer import review_experiment
        with redirect_stdout(io.StringIO()), workspace() as ws:
            rc = cli.main(["new", "qx", "--question",
                           "Does retrieval filtering reduce leakage?"])
            self.assertEqual(rc, 0)
            spec = parse_experiment_yaml(ws / "experiments" / "qx" / "experiment.yaml")
            self.assertEqual(spec.question, "Does retrieval filtering reduce leakage?")
            rep = review_experiment(ws / "experiments" / "qx")
            self.assertNotIn("question_placeholder", {p.code for p in rep.warnings})

    def test_without_flag_scaffold_keeps_placeholder(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "qless"])
            spec = parse_experiment_yaml(ws / "experiments" / "qless" / "experiment.yaml")
            self.assertTrue(str(spec.question).startswith("<"),
                            f"expected a <placeholder> question, got {spec.question!r}")

    def test_question_with_template_is_ignored_with_note(self):
        # templates define their own question; --question must not corrupt them
        out = io.StringIO()
        with redirect_stdout(out), workspace() as ws:
            rc = cli.main(["new", "tq", "--template", "memory-policy-ab-lite",
                           "--question", "ignored?"])
            self.assertEqual(rc, 0)
            text = (ws / "experiments" / "tq" / "experiment.yaml").read_text(encoding="utf-8")
            self.assertNotIn("ignored?", text)
        self.assertIn("--question is ignored with --template", out.getvalue())


class TestAutoScaffoldRunnable(unittest.TestCase):
    """--mode auto scaffolds a runnable PLACEHOLDER echo agent (R4)."""

    def test_auto_new_writes_echo_agents_and_harness_working_dirs(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "autox", "--mode", "auto"])
            exp = ws / "experiments" / "autox"
            for hid, rtid in (("A", "runtime-a"), ("B", "runtime-b")):
                agent = exp / "harnesses" / hid / "agent.py"
                self.assertTrue(agent.is_file(), f"missing harnesses/{hid}/agent.py")
                self.assertIn("PLACEHOLDER", agent.read_text(encoding="utf-8"))
                rt = (exp / "agent-runtimes" / f"{rtid}.yaml").read_text(encoding="utf-8")
                self.assertIn(f'working_dir: "./harnesses/{hid}"', rt)
                self.assertIn("agent.py", rt)

    def test_auto_runtime_command_uses_probed_interpreter(self):
        from agent_harness_lab.experiment_templates import detect_python_command
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "autoy", "--mode", "auto"])
            rt = (ws / "experiments" / "autoy" / "agent-runtimes" / "runtime-b.yaml") \
                .read_text(encoding="utf-8")
            self.assertIn(f"command: '{detect_python_command()} agent.py'", rt)

    def test_copilot_new_has_no_echo_agent(self):
        # the copilot path is unchanged: manual connector, no scaffolded agent.py
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "cop"])
            exp = ws / "experiments" / "cop"
            self.assertFalse((exp / "harnesses" / "A" / "agent.py").exists())
            rt = (exp / "agent-runtimes" / "runtime-a.yaml").read_text(encoding="utf-8")
            self.assertIn("type: manual", rt)
            self.assertIn('working_dir: "./runtime-a"', rt)


class TestYamlTemplateContent(unittest.TestCase):
    """Scaffolded experiment.yaml content pinned: R7 html + E2 engine key names."""

    def test_default_report_formats_include_html(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "demo"])
            spec = parse_experiment_yaml(ws / "experiments" / "demo" / "experiment.yaml")
            self.assertEqual(spec.report_formats, ["md", "html"])

    def test_optimization_comment_names_engine_keys(self):
        # E2 drift: the commented promotion_policy must use keys the engine
        # actually parses (auto_optimize._parse_promotion), not invented ones.
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "demo"])
            text = (ws / "experiments" / "demo" / "experiment.yaml").read_text(encoding="utf-8")
            self.assertIn("require_primary_track_passed", text)
            self.assertIn("block_on_issues", text)
            self.assertNotIn("promote_if_track", text)
            self.assertNotIn("reject_if_issue", text)


class TestNameHandling(unittest.TestCase):
    def test_name_normalized_to_kebab_id_used_as_dir(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            rc = cli.main(["new", "My Cool Exp"])
            self.assertEqual(rc, 0)
            self.assertTrue((ws / "experiments" / "my-cool-exp").is_dir())
            spec = parse_experiment_yaml(ws / "experiments" / "my-cool-exp" / "experiment.yaml")
            self.assertEqual(spec.id, "my-cool-exp")  # dir name == id, no divergence

    def test_digit_only_and_reserved_names_review_clean(self):
        from agent_harness_lab.reviewer import review_experiment
        for nm in ("007", "yes", "null"):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), workspace() as ws:
                rc = cli.main(["new", nm])
                self.assertEqual(rc, 0, f"new {nm} should succeed")
                rep = review_experiment(ws / "experiments" / nm)
                # no ERROR; the only acceptable finding is the scaffold's own
                # placeholder-question WARN (R4)
                self.assertEqual(rep.errors, [],
                                 f"new {nm} must review with no ERROR: "
                                 f"{[str(p) for p in rep.errors]}")
                self.assertEqual({p.code for p in rep.warnings}, {"question_placeholder"},
                                 f"unexpected warnings for {nm}: "
                                 f"{[str(p) for p in rep.warnings]}")

    def test_unusable_name_rejected(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), workspace() as _ws:
            rc = cli.main(["new", "..."])  # no [a-z0-9] -> empty id -> rejected
            self.assertEqual(rc, 1)

    def test_scaffold_playbook_is_parseable_by_user_sim(self):
        # SIM-5: the scaffolded playbook.yaml must be parseable and its default
        # sequence must be content-equal to the built-in fallback (the retired stub).
        from agent_harness_lab import user_sim
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "pbtest"])
            pb_path = ws / "experiments" / "pbtest" / "cases" / "playbook.yaml"
            self.assertTrue(pb_path.exists(), "cases/playbook.yaml not scaffolded")
            pb = user_sim.load_playbook(pb_path)
            self.assertEqual(pb.default, user_sim.DEFAULT_PLAYBOOK_FOLLOWUPS,
                             "scaffolded playbook default must equal the built-in stub sequence")

    def test_scaffold_yaml_comment_mentions_scripted_and_playbook_path(self):
        # SIM-5: the simulator comment in the scaffolded YAML must mention the
        # scripted type and the playbook path so users can find it.
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "pbcomment"])
            text = (ws / "experiments" / "pbcomment" / "experiment.yaml").read_text(encoding="utf-8")
            self.assertIn("scripted", text)
            self.assertIn("cases/playbook.yaml", text)

    def test_longitudinal_sets_cumulative_state_policy(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            cli.main(["new", "longexp", "--execution", "longitudinal"])
            spec = parse_experiment_yaml(ws / "experiments" / "longexp" / "experiment.yaml")
            self.assertEqual(spec.execution_mode, "longitudinal")
            self.assertEqual(spec.state_policy, "cumulative")

    def test_path_separators_do_not_escape_experiments(self):
        with redirect_stdout(io.StringIO()), workspace() as ws:
            rc = cli.main(["new", "../evil"])
            self.assertEqual(rc, 0)
            self.assertFalse((ws / "evil").exists())  # did not escape
            self.assertTrue((ws / "experiments" / "evil").is_dir())


if __name__ == "__main__":
    unittest.main()
