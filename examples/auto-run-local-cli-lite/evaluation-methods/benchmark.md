# Evaluation method: benchmark

A `benchmark` evaluator runs a deterministic script over the collected evidence and
prints a JSON verdict to stdout. This experiment's benchmark
(`experiments/demo/evaluation/benchmarks/concise_faq.py`) scores **correctness AND
conciseness** for every (harness, case):

```text
passed = required key term present
         AND response length <= 120 characters
         AND filler-phrase count <= 1
```

It emits one record per (harness, case), tagged with `harness_id`, so the report can
compare the harnesses side by side. A correct-but-bloated answer fails (too long /
too much filler); a correct-and-direct answer passes. No network, no human, no LLM.

`human_annotation` and `llm_judge` are available as evaluator methods but stay
**pending** unless you supply an annotation file; `llm_judge` is an offline stub that
never calls an external LLM.
