"""hlab init creates the v1 workspace structure."""
import io
import os
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from agent_harness_lab import cli


@contextmanager
def workspace():
    tmp = tempfile.TemporaryDirectory()
    saved = os.getcwd()
    os.chdir(tmp.name)
    try:
        yield Path(tmp.name)
    finally:
        os.chdir(saved)
        tmp.cleanup()


class TestInit(unittest.TestCase):
    def test_init_creates_structure(self):
        with workspace() as ws:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cli.main(["init"])
            self.assertEqual(rc, 0)
            self.assertTrue((ws / "goal.md").is_file())
            self.assertTrue((ws / "experiments").is_dir())
            self.assertTrue((ws / ".hlab").is_dir())
            for m in ("human_annotation", "llm_judge", "benchmark"):
                self.assertTrue((ws / "evaluation-methods" / f"{m}.md").is_file())

    def test_no_inert_config_yaml_but_hlab_marker_kept(self):
        with workspace() as ws:
            with redirect_stdout(io.StringIO()):
                cli.main(["init"])
            self.assertFalse((ws / ".hlab" / "config.yaml").exists())  # inert content removed
            self.assertTrue((ws / ".hlab").is_dir())                   # marker dir kept
            self.assertTrue((ws / ".hlab" / ".gitkeep").exists())      # tracked empty marker

    def test_workspace_methods_do_not_mention_experiment_local_tracks(self):
        # tracks are an experiment-local concept; workspace-level Evaluation Methods
        # must not introduce "track" as a method-layer concept.
        with workspace() as ws:
            with redirect_stdout(io.StringIO()):
                cli.main(["init"])
            for m in ("human_annotation", "llm_judge", "benchmark"):
                txt = (ws / "evaluation-methods" / f"{m}.md").read_text(encoding="utf-8").lower()
                self.assertNotIn("track", txt, f"evaluation-methods/{m}.md must not mention tracks")
                self.assertNotIn("evolution method", txt)  # never "Evolution Method"

    def test_init_idempotent(self):
        with workspace() as ws:
            with redirect_stdout(io.StringIO()):
                cli.main(["init"])
                rc = cli.main(["init"])  # second run must not fail or clobber
            self.assertEqual(rc, 0)
            self.assertTrue((ws / "goal.md").is_file())

    def test_init_fails_honestly_when_experiments_is_a_file(self):
        # If a layout dir cannot be created (a plain file already occupies the
        # name), init must NOT report success for a workspace it cannot complete.
        with workspace() as ws:
            (ws / "experiments").write_text("not a dir", encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = cli.main(["init"])
            self.assertEqual(rc, 1)                                 # honest failure
            self.assertNotIn("Initialized", out.getvalue())         # no success banner
            self.assertIn("experiments", err.getvalue())            # names the blocker
            self.assertFalse((ws / "experiments").is_dir())         # left untouched, still a file
            self.assertFalse((ws / "goal.md").exists())             # no partial scaffold


if __name__ == "__main__":
    unittest.main()
