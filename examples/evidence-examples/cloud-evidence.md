# cloud-evidence

> **Template** — copy to `experiments/<your-experiment>/materials/cloud-evidence.md`
> and edit. The file's *existence* upgrades a legacy `connect.md` variant from
> `weak` to `medium` evidence. AHL never parses this content.
>
> **Critical disclosure**: this file is **NOT cloud attestation**. It is a
> note from you, recording what you observed about a cloud deployment at the
> time of capture. AHL has no programmatic channel to verify any of these
> claims with the cloud provider. See
> [`docs/evidence-guide.md`](../../docs/evidence-guide.md) §6 for the full
> reasoning.

## What was checked

The remote agent reachable via the documented HTTP endpoint was
confirmed to be the deployment intended for this experiment:

- **Deployment id**: `prod-coding-agent-v2026-05-30-build42`
- **Endpoint**: `https://coding-agent.internal.example.com/v1/chat`
- **Region**: `us-west-2`
- **Active configuration version** (per console export downloaded at
  capture time): `harness-config-v2.4.1`
- **System prompt excerpt** (first 200 chars, from console-displayed
  active config): `You are a senior software engineer ...`
- **Plugin list** (per the agent's HTTP `/diagnostics` endpoint at
  capture): `["code-search", "git-helper", "repl", "doc-search"]`
- **Console screenshot description**: deployment dashboard showed
  status "Healthy", uptime "14d 2h", request rate "~12 rpm",
  no recent restarts or config-push events.

## Who / what supplied this

- **Supplier**: Kun (manually, via the cloud provider's web console +
  HTTP probes against the deployment's diagnostic endpoint).
- The deployment id and config version were copied from the console;
  the plugin list was captured from the agent's own `/diagnostics`
  HTTP response.
- No third-party signed attestation, deployment manifest, or cryptographic
  trust chain was used.

## When was it captured

- **Captured at**: 2026-06-01 14:20:00 PDT.
- **AHL run timestamp**: 2026-06-01 14:35:18 PDT (≈15 minutes after
  capture; replace with your actual run id, e.g. `run-20260601-213518`).
- Cloud deployments can change between capture and run without your
  knowledge (auto-redeploy, config push, blue/green switch). The closer
  the capture is to the actual `ahl run`, the more weight this
  attestation carries.

## What this evidence can support

- Upgrading the variant from `weak → medium` in v0.4 inference
  (existence triggers).
- A reviewer's question two months later: "what deployment id was V1
  pointing at?" — the field above answers it for the *captured* state.
- Distinguishing two variants both backed by cloud deployments
  (e.g., V1 = prod deployment, V2 = staging deployment with experimental
  harness) — different `materials/cloud-evidence.md` per experiment,
  describing different deployments.

## What this evidence cannot prove

- **That the deployment was unchanged between capture and the AHL run.**
  This is the central limitation. Cloud platforms routinely auto-redeploy,
  hot-swap configs, fall back to a previous version on health-check
  failure, or fan out requests across multiple shards with subtly
  different state. None of that is captured by a static markdown file.
- **That the agent processing AHL's requests was actually the deployment
  named above.** Load balancers, regional failover, A/B routing can
  send your traffic to a different backend than the dashboard implies.
- **That the configuration excerpt is the complete active configuration.**
  Excerpts are excerpts — there may be settings, env vars, secrets,
  inherited defaults you didn't see.
- **Anything cryptographic.** No signature, no deployment manifest hash,
  no provider-side attestation.

## Limitations

- **Existence-only**: AHL reads this file's filename but never its
  content. Adding more fields above doesn't change what AHL infers.
- **Ceiling at medium**: cloud / external runtime + supplied evidence
  cannot reach `strong`. `strong` is reserved for runtimes AHL itself
  materialized (`local_path` / `git_repo`). Cloud deployments are
  intrinsically opaque to AHL.
- **Cloud-side drift is invisible**: an auto-redeploy two minutes after
  capture would not invalidate this file from AHL's perspective — but
  the run would be measuring a different harness than what's documented
  here. Mitigation: re-capture and re-author before every iteration.
- **Honor system**: AHL trusts that what you wrote above is what you
  actually saw. The cloud-evidence channel is for your future self
  and reviewers, not for automated verification.
- **Not a substitute for real attestation**: if your environment
  requires cryptographic chain-of-custody from a deployment manifest
  to the running agent, this file does **not** provide it. That is
  out of scope for AHL through v0.8.
