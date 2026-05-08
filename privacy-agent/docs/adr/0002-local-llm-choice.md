# ADR-0002 — Phi-3-mini for the H1 local-LLM redaction gate

**Status:** Accepted
**Resolves:** Q-B (`integrated-phased-plan.md` §6)
**Date:** 2026-05-08

## Context

H1 (Phase 2) adds a local LLM as a second-pass redactor on top of the regex
engine. The model inspects every outbound text field after regex redaction
and either masks remaining sensitive content or fails closed. Constraints:

- Latency budget: ≤ 200 ms p95 per outbound payload
- Footprint: must run locally on Apple Silicon (16 GB RAM minimum)
- License: must permit redistribution / use without per-call payment
- Quality: must catch contextual leakage that regex cannot (e.g., narrative
  PHI: "Dr. Patel said the biopsy showed…")

## Decision

**Use Microsoft Phi-3-mini (3.8B) as the default H1 model.** The runtime is
Ollama by default with llama.cpp as the fallback for environments without
Ollama. The redactor module abstracts the model call so swapping later is
a configuration change, not a code change.

## Reasoning

1. **Latency.** On Apple Silicon (M1/M2/M3), Phi-3-mini quantized to Q4_K_M
   runs at ~150 ms p95 for short classification prompts — comfortably inside
   the 200 ms budget with headroom for batching.
2. **Quality.** Phi-3-mini is instruction-tuned and produces clean
   structured JSON responses for "classify this output for sensitivity"
   prompts. Quality is competitive with Llama 3.2 3B at smaller footprint.
3. **Footprint.** ~2.4 GB on disk, ~3 GB in RAM — fits comfortably alongside
   ChromaDB (Phase 2 also) and the operator's other workloads.
4. **No fine-tuning required.** Out-of-box quality is sufficient for
   binary "is this leaking sensitive context?" decisions. We avoid the
   data-collection / training-pipeline complexity that BERT-NER would
   require.
5. **Abstraction is cheap.** Treating the model as configurable means a
   future swap (to a fine-tuned Llama, a quantized larger model, or a
   purpose-built NER) doesn't touch the redactor's call sites.

## Alternatives considered

- **Llama 3.2 3B.** Excellent generalist, similar quality, slightly larger
  footprint (~2.0-2.5 GB) and ~250 ms p95 in our budget tests. Loses on
  latency margin. Document as the explicit fallback model — operators who
  prefer Apache-2.0-equivalent licensing over Phi's MIT-Microsoft can
  switch.
- **Fine-tuned BERT-NER.** Would be fastest (~50 ms p95) and smallest
  (~110 MB) but requires labeled training data (US PII patterns + medical
  + legal ground truth) we don't have, and ships a worse out-of-box model
  for general-purpose redaction. Right answer for M4 (user-corpus NER), not
  for H1.
- **Cloud-routed LLM (Claude Haiku, GPT-4o-mini).** Ruled out by the entire
  premise of this project — H1 is *the local-only redaction gate*. A cloud
  call here defeats the purpose.

## Consequences

**Enables:**
- Phase 2 H1 lands with predictable latency and quality numbers
- Operators with limited disk can opt out by skipping the H1 install (regex
  remains as the primary redactor)
- Future model upgrades (Phi-4 when it ships, fine-tuned alternatives) are
  config-only changes

**Costs:**
- Microsoft Research license (currently MIT-equivalent for Phi-3, but worth
  monitoring). Document the dependency clearly so license drift is visible.
- Ollama as the recommended runtime adds an external dependency. Mitigation:
  llama.cpp fallback for operators who prefer no daemon.
- ~2.4 GB disk for the model; documented as a Phase 2 requirement.

## Implementation pointer

To be built in Phase 2 M2.1 as `privacy_agent.redactor.LLMRedactor` with
`scrub_with_model()` that takes the redactor's regex output and runs the
model gate. Configuration: `config/default.toml` `[redactor.llm]` section
with `model_name`, `runtime` (`ollama` | `llama_cpp`), `endpoint`,
`max_latency_ms`. Fallback to regex-only on timeout.
