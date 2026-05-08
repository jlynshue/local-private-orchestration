# calgary — privacy-agent workspace

Conductor workspace for the privacy-preserving local orchestration project.

## Layout

```
calgary/
├── run.sh                ← Conductor "run script" entry point (modes below)
├── setup.sh              ← Conductor "setup script" entry point (idempotent)
├── privacy-agent/        ← the actual project (148 + 25 + 5 tests, all green)
└── .context/             ← design artifacts (architecture, plan, proposals)
```

## Wiring it into Conductor

Conductor's Run tab takes a shell command. Pick whichever mode fits the moment:

| Conductor "Add run script" value | What it does |
|---|---|
| `bash run.sh` | default — fast unit + integration tests (~5 s) |
| `bash run.sh watch` | long-lived; re-runs unit tests on save (`run_script_mode = concurrent`) |
| `bash run.sh server` | start the MCP stdio server for manual poking |
| `bash run.sh redteam` | the M1.9 invariant gate (~1 s) |
| `bash run.sh full` | everything: lint + tests + redteam + perf + smoke |

For first-time setup (Conductor's Setup tab), use:

```
bash setup.sh
```

`setup.sh` is idempotent — safe to re-run. `run.sh` auto-bootstraps the venv if it's missing, so you can also skip the setup step and just hit Run.

## All `run.sh` modes

```
test       (default) unit + integration suite
watch      poll src/ + tests/, re-run on save
redteam    M1.9 invariant gate
perf       NFR-PERF-1 baselines + comparison
all        every test in the project
lint       ruff check
smoke      privacy-cli audit verify + canary seed/list
server     start the MCP stdio server
ci         scripts/ci.sh fast
full       scripts/ci.sh full
help       full mode list
```

## Project docs

For project-level documentation (threat model, compliance mapping, runbook,
acceptance checklist) see inside `privacy-agent/`:

- `privacy-agent/README.md`
- `privacy-agent/ACCEPTANCE.md`
- `privacy-agent/THREAT_MODEL.md`
- `privacy-agent/COMPLIANCE.md`
- `privacy-agent/RUNBOOK.md`

For the design backstory:

- `.context/architecture-impact-analysis.md`
- `.context/enhancement-proposals.md`
- `.context/integrated-phased-plan.md`
