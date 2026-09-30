"""Registered constants of jev-v3. Every value here is fixed by prereg/jev-v3.md; anything not
listed is jev-v2 unchanged (constants_v2)."""

from __future__ import annotations

from jev_probe.constants import ROOT
from jev_probe.constants_v2 import LLM_PROMPT_PREFIX as V2_PROMPT_PREFIX

REGISTRATION_ID = "jev-v3"
PREREG_TAG = "prereg-jev-v3"
PREREG_COMMIT = "37084f8167b9c645217e74edcc09f560b70cc4de"

# §3a request (arm B only)
_V2_REPLY_SENTENCE = "where p_valid is your probability that a valid approval is on record."
assert _V2_REPLY_SENTENCE in V2_PROMPT_PREFIX
LLM_PROMPT_PREFIX = V2_PROMPT_PREFIX.replace(
    _V2_REPLY_SENTENCE, _V2_REPLY_SENTENCE + " No code fences. No text after the object.")
LLM_PREFILL = "{"
LLM_MAX_TOKENS = 32

# §3c arm health rule
SMOKE_N = 20
SMOKE_MAX_INVALID = 2
HEALTH_MAX_INVALID_RATE = 0.05

# §3d cap
CAP_USD = 5.0

# §2 carried arm A values (checked against the jev-v2 cache by the analysis)
CARRIED_JEV_H2_K = 68
CARRIED_JEV_H2_N = 700

# §3e paths
RESPONSES_DIR = ROOT / "responses"
CACHE_PATH = RESPONSES_DIR / "jev-v3.jsonl"
MANIFEST_PATH = RESPONSES_DIR / "manifest-v3.json"
TAU_PATH = ROOT / "results" / "jev-v3.tau.json"
TEMPLATE_PATH = ROOT / "results" / "jev-v3.template.md"
RESULTS_PATH = ROOT / "results" / "jev-v3.md"
SLOTS_JSON_PATH = ROOT / "results" / "jev-v3.slots.json"
