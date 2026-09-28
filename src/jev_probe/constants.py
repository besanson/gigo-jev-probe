"""Registered constants of jev-v1. Every value here is fixed by prereg/jev-v1.md."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REGISTRATION_ID = "jev-v1"
PREREG_TAG = "prereg-jev-v1"
PREREG_COMMIT = "306e701e66b12fd197bbc0cc9d645a8d44699435"

# §2 items
BASE_SEED = 20260707
N_ITEMS = 300
N_CLEAN = 100
PER_CLASS = 25
TEST_SPLIT_REMAINDER = 2  # split_of(seed) == "test" iff seed % 3 == 2
METADATA_BORNE = (
    "stale_master_data",
    "superseded_golden_record",
    "silent_unit_change",
    "plausible_outlier",
)
PAYLOAD_VISIBLE = (
    "duplicate_vendor_conflicting_terms",
    "cross_source_contradiction",
    "schema_drift",
    "missing_mandatory_field",
)
CHANNEL_OF = {**{c: "metadata" for c in METADATA_BORNE}, **{c: "payload" for c in PAYLOAD_VISIBLE}}

# §3 conditions and the registered context sentence (verbatim)
CONDITIONS = ("P", "PM")
CONTEXT = (
    "Unit-price evidence retrieved for a replenishment order decision. "
    "You are reviewing it before the decision is made."
)

# §3a API interface
MODEL = "jev-latest"
SDK_VERSION = "0.7.2"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DOCS_URL = "https://docs.typesafe.ai/api"
DOCS_ENDPOINT_STRING = "POST https://api.typesafe.ai/v1/systemone"
HTTP_TIMEOUT_S = 60.0

# §5 repeats
REPEATS = 3

# §6 price: USD 42 per billion input tokens, output free
USD_PER_INPUT_TOKEN = 42.0 / 1e9
USD_PER_OUTPUT_TOKEN = 0.0

# §9 cap and retries
CAP_USD = 40.0
CAP_INPUT_TOKENS = 4_000_000
BACKOFF_INITIAL_S = 1.0
BACKOFF_MAX_S = 60.0
MAX_RETRIES = 8

# §8 analysis
ALPHA = 0.05
BOOTSTRAP_B = 10_000
BOOTSTRAP_SEED = 20260928
FPR_GUARD = 0.10

# §10 cache
RESPONSES_DIR = ROOT / "responses"
CACHE_PATH = RESPONSES_DIR / "jev-v1.jsonl"
MANIFEST_PATH = RESPONSES_DIR / "manifest.json"
TEMPLATE_PATH = ROOT / "results" / "jev-v1.template.md"
RESULTS_PATH = ROOT / "results" / "jev-v1.md"
SLOTS_JSON_PATH = ROOT / "results" / "jev-v1.slots.json"
