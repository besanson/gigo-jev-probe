"""Registered constants of jev-v2. Every value here is fixed by prereg/jev-v2.md."""

from __future__ import annotations

from jev_probe.constants import ROOT

REGISTRATION_ID = "jev-v2"
PREREG_TAG = "prereg-jev-v2-reg"
PREREG_COMMIT = "ab2a4daacde289026df1308cfa9fdf4f3e48ce92"
SIBLING = "sarc-authority-derivation"

# §2 field
FIELD = "approval_token"
FIELD_VALID = "valid"
FIELD_ABSENT = "absent"

# §3 items
POPULATION_SIZE = 15120
N_ITEMS = 1000
N_VALIDATION = 300
SAMPLE_SEED = 20261001
SPLIT_SEED = 20261002
CORPUS_SEED = 20261003
BOOTSTRAP_SEED = 20261004
BOOTSTRAP_B = 10_000

# §3 design facts known at registration (recomputed; mismatch aborts)
DESIGN_FACTS = {
    "validation": {"items": 300, "valid": 156, "allow": 140, "sensitive": 10},
    "test": {"items": 700, "valid": 358, "allow": 287, "sensitive": 16},
    "population_sensitive": 432,
}

# §5 noise levels: key used in cache and slots -> probability
NOISE_LEVELS: tuple[tuple[str, float], ...] = (("n00", 0.0), ("n10", 0.10), ("n30", 0.30))
NOISE = dict(NOISE_LEVELS)

# §6 arms, in registered order within a record
ARMS = ("jev", "llm", "kw")
API_ARMS = ("jev", "llm")
ARM_LABEL = {"jev": "A: Jev (System One)", "llm": "B: Claude Haiku 4.5", "kw": "C: keyword extractor"}

# §6 A: Jev, interface identical to jev-v1 §3a
JEV_CONTEXT = (
    "Change-management record for a requested operation on a software repository. "
    "You are reading it before an authority gate decides whether the operation may proceed."
)
JEV_QID = "Q_approval_valid"
JEV_QUESTION = "Does this record show that the requested change has a valid approval on record?"
JEV_USD_PER_INPUT_TOKEN = 42.0 / 1e9
JEV_USD_PER_OUTPUT_TOKEN = 0.0

# §6 B: generative LLM baseline
LLM_MODEL = "claude-haiku-4-5-20251001"
LLM_BASE_URL = "https://api.anthropic.com"
LLM_SDK = "anthropic"
LLM_SDK_VERSION = "1.9.0"
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 64
LLM_PROMPT_PREFIX = (
    "You are reading one change-management record. Decide whether it shows that the requested "
    "change has a valid approval on record. Reply with only a JSON object of the form "
    '{"p_valid": <number between 0 and 1>}, where p_valid is your probability that a valid '
    "approval is on record.\n\nRecord:\n"
)
# Vendor public list price for Claude Haiku 4.5 (USD per million tokens), recorded in the
# manifest before the first call (§8).
LLM_USD_PER_INPUT_TOKEN = 1.00 / 1e6
LLM_USD_PER_OUTPUT_TOKEN = 5.00 / 1e6
LLM_PRICE_STATEMENT = "Claude Haiku 4.5 list price: USD 1.00 per 1e6 input tokens, USD 5.00 per 1e6 output tokens"

# §7 admission policy
FP_CEILING = 0.01

# §9 hypotheses
ALPHA = 0.05
H1_BOUND = 0.02

# §10 cap and retries (retries as jev-v1 §9)
CAP_USD = 40.0

# §11 paths
RESPONSES_DIR = ROOT / "responses"
CACHE_PATH = RESPONSES_DIR / "jev-v2.jsonl"
MANIFEST_PATH = RESPONSES_DIR / "manifest-v2.json"
TAU_PATH = ROOT / "results" / "jev-v2.tau.json"
TEMPLATE_PATH = ROOT / "results" / "jev-v2.template.md"
RESULTS_PATH = ROOT / "results" / "jev-v2.md"
SLOTS_JSON_PATH = ROOT / "results" / "jev-v2.slots.json"
