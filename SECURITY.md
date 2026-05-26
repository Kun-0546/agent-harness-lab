# Security Policy

## Reporting a Vulnerability

If you discover a security issue in Agent Harness Lab, **please do not open a
public GitHub issue**. Public disclosure before a fix is available puts users
at risk.

Report privately by opening a GitHub security advisory:

https://github.com/Kun-0546/agent-harness-lab/security/advisories/new

You will receive acknowledgement within 7 days. Remediation timeline depends
on severity:

| Severity | Target |
|---|---|
| Critical / High | Patch within 30 days |
| Medium | Patch in the next minor release |
| Low | Patch when convenient, no specific commitment |

## Scope

In-scope security issues include:

- Path traversal in `materialize/` adapters or `patch.py` (current defenses:
  `_safe_target_path` + `_safe_source_path`; see
  `docs/runtime-materialization-m1-spec.md`).
- Command injection in `agentconn.py` subprocess invocation
  (`_SandboxCliSession` uses `shell=False`; legacy `_CliSession` is documented).
- Secrets leakage through logs, snapshots, or sandbox dirs.
- Insecure default file modes on materialized sandboxes.

Out of scope:

- User agents launched through `connect.md` or `runtime-sources.md`. Their
  security is the user's responsibility; AHL is the harness, not the agent.
- Third-party LLM API keys. AHL reads them from environment variables
  (`AHL_JUDGE_API_KEY` / `AHL_SIM_API_KEY`) and never writes them to disk.

## Supported Versions

Only the latest minor release receives security fixes. Older minor versions
should upgrade.

| Version | Supported |
|---|---|
| 0.9.x (current) | Yes |
| 0.8.x and earlier | No (upgrade to the latest minor) |

## Disclosure

After a fix is released, the security advisory will be published with
attribution to the reporter (unless they prefer to remain anonymous). The
release notes / `CHANGELOG.md` will reference the advisory ID without
exposing exploit details before users have had a reasonable window to upgrade.
