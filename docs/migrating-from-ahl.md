# Migrating from `ahl` (v0.x) to `hlab` (v1)

The retired `ahl` stack and `hlab` are **not** compatible: an `ahl` workspace
cannot be opened by `hlab`, and old `ahl` commands do not map 1:1 onto the v1
surface. There is no automatic converter — migration means re-expressing the
same experiment in the v1 format, not renaming files.

This guide maps each v0.x workspace concept onto its v1 equivalent. The v1
formats themselves are specified in [`v1-spec/`](v1-spec/); the practical
walk-through is [`quickstart.md`](quickstart.md).

## At a glance

| v0.x (`ahl`) | v1 (`hlab`) | Notes |
|---|---|---|
| `program.md` (假设 / 声明 / 对比方式) | `experiment.yaml` | see [Program](#program-programmd--experimentyaml) |
| `cases/*.md` (one Markdown file per case, `## 起始输入` section) | `cases/cases.jsonl` (one JSON object per line, `input` field) | see [Cases](#cases-casesmd--casesjsonl) |
| case-level `max_turns:` frontmatter field | `simulator.max_turns` in `experiment.yaml` | experiment-level, not per-case; see [max_turns](#max_turns-case-level--simulator-level) |
| `simulator.md` (中文三段：人设 / 背景知识 / 追问策略) | `simulator.type: role_play` + `actor` + four-section policy card | see [Simulator](#simulator-simulatormd--role_play-policy-card) |
| `connect.md` (类型 / 配置) | `agent-runtimes/<id>.yaml` `connector:` block | see [Connect](#connect-connectmd--agent-runtimes) |
| `ahl run` | `hlab run` | evidence goes to `evidence/`, not `results/` |
| `ahl score` | evaluation inside `hlab run` (`evaluation.evaluators` + `tracks`) | scoring is no longer a separate verb in the golden path |
| `ahl compare` | `hlab compare` | reads `evidence/scores/`, writes `reports/compare.json` |

## Cases: `cases/*.md` → `cases.jsonl`

v0.x kept one Markdown file per case; the opening input lived in the
`## 起始输入` section and the id in an `id:` frontmatter field (falling back
to the file stem). v1 keeps all cases in one JSONL file (`cases/cases.jsonl`
by default):

```json
{"id":"case-001","input":"<v0.x 起始输入 content>","tags":[]}
```

Mapping per case file:

```text
id: ... frontmatter field (or file stem)  →  "id"
## 起始输入 section body                   →  "input"
free-form prose / other sections          →  "metadata" / "tags" (optional), or drop
```

## max_turns: case level → simulator level

v0.x declared `max_turns:` per case (in the case file's frontmatter), and
**defaulted to 8 turns** when the field was absent. v1 declares the turn
budget once, on the experiment's simulator:

```yaml
simulator:
  type: role_play
  actor: ceo
  max_turns: 8
  policy: cases/simulator.md
```

v1's default is also 8 (see
[`v1-spec/experiment-yaml-schema.md`](v1-spec/experiment-yaml-schema.md) §14a)
— but when migrating, either write `max_turns` explicitly or confirm the v1
default matches what your cases relied on. If your old cases used *different*
`max_turns` values per case, pick the budget the experiment actually needs;
per-case turn budgets have no v1 equivalent.

## Simulator: `simulator.md` → role_play policy card

The v0.x `simulator.md` had three Chinese sections. The v1 `role_play` policy
card has four sections (English or Chinese names both accepted), plus an
`actor:` label in `experiment.yaml`:

| v0.x `simulator.md` | v1 policy card | Notes |
|---|---|---|
| `## 人设` | `## Persona` (or `## 人设`) | unchanged content |
| `## 背景知识` | `## Background` (or `## 背景知识`) | unchanged content |
| `## 追问策略` | `## Strategy` (or `## 追问策略`) | unchanged content |
| — (no equivalent) | `## Stop` (or `## 收尾条件`) | **new**: the "asked enough" criterion. v0.x had only the built-in end token + `max_turns`; without a `Stop` section v1 review WARNs and the conversation ends only on `max_turns` |

The `AHL_SIM_BASE_URL` / `AHL_SIM_MODEL` / `AHL_SIM_API_KEY` environment
variables carry over unchanged. The v0.x `--llm` flag (stub vs. LLM switch) is
retired: without a key, v1 records a `simulator_unconfigured` error and skips
dispatch instead of silently falling back to a stub; deterministic offline runs
are now a designed `scripted` playbook (or `AHL_SIM_STUB=1` for CI). See
[`v1-spec/execution-model.md`](v1-spec/execution-model.md) §14.

## Program: `program.md` → `experiment.yaml`

`program.md`'s prose sections become structured fields:

```text
# <title> / ## 假设          →  question: (the one-line experiment question)
## 声明 - 对话模式            →  simulator: (single_turn, or a multi-turn type)
## 声明 - 对比方式            →  execution.mode: ab (+ hlab compare reads the result)
## 声明 - 评分                →  evaluation.evaluators + evaluation.tracks
harnesses/*.md (per-harness   →  harnesses: list in experiment.yaml
Markdown, formerly versions/)    (id / name / path) + harnesses/<id>/ dirs
## 留/丢规则 / ## 喊人规则     →  objective / optimization (Auto Optimize), or conclusion.md
```

Start from a scaffold (`hlab new <name> --template <name>`) rather than
translating field by field — the v1 schema is documented in
[`v1-spec/experiment-yaml-schema.md`](v1-spec/experiment-yaml-schema.md).

## Connect: `connect.md` → agent-runtimes

The single workspace-level `connect.md` (类型 / 配置) becomes a per-runtime
spec under `agent-runtimes/`:

```yaml
# agent-runtimes/runtime-a.yaml
id: runtime-a
connector:
  type: local_cli             # 外部命令行 → local_cli; per-case script → script
  command: "python run_agent.py"
  working_dir: "./runtime-a"
  input_mode: stdin_json
  timeout: 60
```

```text
类型: 外部命令行   →  connector.type: local_cli (persistent stdin/stdout JSON)
                      or connector.type: script (one process per case)
类型: 进程内库 / HTTP无状态 / HTTP有状态
                   →  no direct v1 equivalent; wrap the agent behind a small
                      CLI (stdin_json) or per-case script
配置: <command>    →  connector.command (+ working_dir)
```

## Scoring: `grader.py` / `rubric.py` → `llm_rubric`

v0.x used `grader.py` and `rubric.py` for dimension-weighted LLM scoring. v1
ports this into the evaluation stack as the `llm_rubric` method.

**Rubric format.** v0.x used a heading-per-dimension style:

```markdown
## Accuracy
权重: 0.5
Is the answer factually correct?

## Conciseness
权重: 0.3
Is the answer concise?
```

v1 uses a single GFM pipe table (Dimension / Weight / Description columns):

```markdown
| Dimension   | Weight | Description                          |
|-------------|--------|--------------------------------------|
| accuracy    | 0.5    | Is the answer factually correct?     |
| conciseness | 0.3    | Is the answer concise?               |
| helpfulness | 0.2    | Is the answer helpful to the user?   |
```

**Scale change.** v0.x grader scored dimensions 1–10; v1 prompts the LLM to
score 0–100 per dimension. Weights work the same (normalised to 1.0 if needed);
the final `score` field is the weighted total on a 0–100 scale.

**Environment variables.** `AHL_JUDGE_BASE_URL`, `AHL_JUDGE_MODEL`, and
`AHL_JUDGE_API_KEY` carry over unchanged — `llm_rubric` reuses the same env
family as `llm_judge`.

**Evaluator config** (`experiment.yaml`):

```yaml
evaluation:
  root: evaluation/
  evaluators:
    - id: quality
      method: llm_rubric
      rubric: rubrics/quality.md
  tracks:
    - id: main
      evaluators: [quality]
      evidence: [traces]
```

**Re-scoring.** After collecting evidence with `hlab run`, recompute scores at
any time (e.g. after updating the rubric file) with `hlab eval <experiment>`.
See [`v1-spec/experiment-yaml-schema.md`](v1-spec/experiment-yaml-schema.md) §14b
and [`v1-spec/execution-model.md`](v1-spec/execution-model.md) §14b.1 for the
full `llm_rubric` specification.

## Commands: `run` / `score` / `compare` → `run` + `compare`

```text
ahl run [--llm]   →  hlab run <experiment>     # runs AND evaluates; --llm retired
ahl score [--llm] →  (no separate verb)        # evaluation runs inside hlab run,
                                               # configured by evaluation.evaluators/tracks
ahl compare       →  hlab compare <experiment> # writes reports/compare.json
```

Around them, the v1 loop adds what v0.x never had: `hlab review` (validate
before running), `hlab status`, `hlab report`, and `hlab conclude`. See the
README's "Command surface" section and
[`v1-spec/cli.md`](v1-spec/cli.md) for the full surface and exit-code
contract.
