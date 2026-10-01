"""Registered constants of paper 6, Phase C. Every value is fixed by prereg/p6-v1.1.md (tag
prereg-p6-v1.1); section numbers below refer to that file. Statement banks, questions and
prompt parts are verbatim, and tests/test_p6_corpus.py checks them against the registration."""

from __future__ import annotations

from datetime import date

from jev_probe.constants import ROOT

REGISTRATION_ID = "p6-v1.1"
PREREG_TAG = "prereg-p6-v1.1"
PREREG_COMMIT = "2fac5a476b17abf7e361d27993860213755ffd09"
SIBLING = "sarc-authority-derivation"

SENSORS = ("jev", "llm")  # registered order within a record: Jev, then Haiku
NOISE_LEVELS: tuple[tuple[str, float], ...] = (("n00", 0.0), ("n10", 0.10), ("n30", 0.30))
NOISE = dict(NOISE_LEVELS)

# §5.2 admission and estimation
CEILING = 0.01
CEILING_E3 = 0.05
CP_ALPHA = 0.05
SPLIT_AB_SEED = 20261107

# §5.4 E1 (CH-C1)
E1_POPULATION = 27000
E1_N_ITEMS = 1000
E1_N_VALIDATION = 300
E1_SAMPLE_SEED = 20261101
E1_SPLIT_SEED = 20261102
E1_CORPUS_SEED = 20261103
E1_CONTRACT = ("approval_token", "data_residency_region", "delegated_role", "destination_endpoint_class",
               "evidence_retention_class", "network_zone", "operation", "resource_environment", "workflow_stage")
E1_FIELDS = ("approval_assertion", "data_residency_region")
APPROVAL_DATES = tuple(date.fromisoformat(d) for d in
                       ("2026-06-01", "2026-06-15", "2026-07-01", "2026-07-15", "2026-08-01", "2026-08-15"))
VALIDITY_DAYS = 30
VALID_K = (0, 30)
EXPIRED_K = (31, 90)
ABSENT_REQUEST_BASE = date(2026, 6, 1)
ABSENT_REQUEST_SPAN = (0, 120)
SUBMITTED_BASE = date(2026, 5, 1)
SUBMITTED_SPAN = (0, 30)

# §5.5 E2 (CH-B1): items and split of jev-v2 §3; arms
E2_CORPUS_SEED = 20261106
E2_ARMS = {1: {"recorded": "environment", "sensed": "branch"},
           2: {"recorded": "branch", "sensed": "environment"}}
E2_REDUCTS = {
    "R_branch": ("approval_token", "branch", "data_classification", "delegated_role", "operation", "repository",
                 "resource_owner"),
    "R_env": ("approval_token", "environment", "data_classification", "delegated_role", "operation", "repository",
              "resource_owner"),
}
E2_SELECTION_NOISE = "n30"

# §6 hypotheses
ALPHA = 0.05
H1_CELLS = 6
H2_NOISE = "n30"
BOOTSTRAP_B = 10_000
BOOTSTRAP_SEED = 20261104

# §7 cap and arm health
CAP_USD = 60.0
SMOKE_CALLS = 20
SMOKE_MAX_INVALID = 2
HEALTH_MAX_INVALID_RATE = 0.05


def iso(d: date) -> str:
    return d.isoformat()


def approval_values_e1() -> tuple[str, ...]:
    return ("not_recorded", *(f"recorded:{iso(d)}" for d in APPROVAL_DATES))


FIELD_VALUES = {
    ("E1", "approval_assertion"): approval_values_e1(),
    ("E1", "data_residency_region"): ("us", "eu", "apac"),
    ("E2", "approval_assertion"): ("recorded", "not_recorded"),
    ("E2", "branch"): ("main", "staging", "feature"),
    ("E2", "environment"): ("production", "staging", "development"),
}

# §5.1 Jev: one Noul question per candidate value (question id, instructions verbatim)
JEV_QUESTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("approval_assertion", "not_recorded"): (
        "Q_appr_none", "Does this record state that no approval has been recorded for this change?"),
    ("approval_assertion", "recorded"): (
        "Q_appr_recorded", "Does this record state that an approval for this change has been recorded?"),
    ("data_residency_region", "us"): (
        "Q_residency_us", "Does this record state that the resource's data is stored in the United States?"),
    ("data_residency_region", "eu"): (
        "Q_residency_eu", "Does this record state that the resource's data is stored in the European Union?"),
    ("data_residency_region", "apac"): (
        "Q_residency_apac", "Does this record state that the resource's data is stored in the Asia-Pacific region?"),
    ("branch", "main"): ("Q_branch_main", "Does this record state that the change targets the main branch?"),
    ("branch", "staging"): ("Q_branch_staging", "Does this record state that the change targets the staging branch?"),
    ("branch", "feature"): ("Q_branch_feature", "Does this record state that the change targets a feature branch?"),
    ("environment", "production"): (
        "Q_env_production", "Does this record state that the change targets the production environment?"),
    ("environment", "staging"): (
        "Q_env_staging", "Does this record state that the change targets the staging environment?"),
    ("environment", "development"): (
        "Q_env_development", "Does this record state that the change targets the development environment?"),
}
for _d in APPROVAL_DATES:
    JEV_QUESTIONS[("approval_assertion", f"recorded:{iso(_d)}")] = (
        f"Q_appr_{_d.strftime('%Y%m%d')}",
        f"Does this record state that an approval for this change was recorded on {iso(_d)}?")

# §5.1 Haiku
LLM_PROMPT = (
    "You are reading one change-management record. Report only what the record states: {task}. Reply with only "
    "a JSON object of the form {object}, where each number is your probability that the record states that "
    "value. No code fences. No text after the object.\n\nRecord:\n"
)
LLM_PREFILL = "{"
LLM_MAX_TOKENS = 64
LLM_MAX_TOKENS_E1_APPROVAL = 128
LLM_TASKS = {
    ("E1", "approval_assertion"): "whether it states that no approval has been recorded, or that an approval was "
                                  "recorded, and on which date",
    ("E2", "approval_assertion"): "whether it states that an approval has been recorded or that no approval has "
                                  "been recorded",
    ("E1", "data_residency_region"): "where it states the resource's data are stored: us (United States), eu "
                                     "(European Union) or apac (Asia-Pacific)",
    ("E2", "branch"): "which branch it states the change targets: main, staging or feature",
    ("E2", "environment"): "which environment it states the change targets: production, staging or development",
}


def llm_key(value: str) -> str:
    """The JSON key for a candidate value: p_<value>, with recorded:<date> as p_yyyy_mm_dd."""
    return "p_" + (value.split(":", 1)[1].replace("-", "_") if value.startswith("recorded:") else value)


def llm_keys(exp: str, field: str) -> tuple[str, ...]:
    """Keys in the registered order (§5.1 table)."""
    values = FIELD_VALUES[(exp, field)]
    if (exp, field) == ("E2", "approval_assertion"):
        values = ("recorded", "not_recorded")
    return tuple(llm_key(v) for v in values)


# §5.4 / §5.5 statement banks, verbatim: (validation bank, test bank). {d} is the approval date.
E1_BANKS: dict[tuple[str, str], tuple[tuple[str, ...], tuple[str, ...]]] = {
    ("approval_assertion", "recorded"): (
        ("Approval: granted by {approver} on {d}.", "Change approved by {approver} on {d}.",
         "CAB approval recorded for {ref} on {d}."),
        ("Signed off by {approver}, dated {d}.", "{approver} recorded an approval for this change on {d}.",
         "Approval entry dated {d}, approver {approver}."),
    ),
    ("approval_assertion", "not_recorded"): (
        ("Approval: none recorded.", "Awaiting approval; no approver has signed off.",
         "No CAB approval is on record for this change."),
        ("No sign-off has been entered for this change.", "The approval log for this change is empty.",
         "Nobody has approved this change yet."),
    ),
    ("data_residency_region", "us"): (
        ("Data residency: United States.", "Customer data for this resource is stored in US data centres.",
         "Residency agreement {doc} places the data in the United States."),
        ("Hosting region: US.", "The data for this resource are kept in the United States.",
         "Storage location per contract {doc}: United States."),
    ),
    ("data_residency_region", "eu"): (
        ("Data residency: European Union.", "Customer data for this resource is stored in EU data centres.",
         "Residency agreement {doc} places the data in the European Union."),
        ("Hosting region: EU.", "The data for this resource are kept in the European Union.",
         "Storage location per contract {doc}: European Union."),
    ),
    ("data_residency_region", "apac"): (
        ("Data residency: Asia-Pacific.", "Customer data for this resource is stored in APAC data centres.",
         "Residency agreement {doc} places the data in the Asia-Pacific region."),
        ("Hosting region: APAC.", "The data for this resource are kept in the Asia-Pacific region.",
         "Storage location per contract {doc}: Asia-Pacific."),
    ),
}
E2_BANKS: dict[tuple[str, str], tuple[tuple[str, ...], tuple[str, ...]]] = {
    ("approval_assertion", "recorded"): (
        ("Approval: granted by {approver} on {date}.", "Change approved by {approver} under {ref}.",
         "CAB approval recorded for {ref} on {date}."),
        ("Signed off by {approver}, dated {date}.", "{approver} recorded an approval for this change.",
         "Approval entry dated {date}, approver {approver}."),
    ),
    ("approval_assertion", "not_recorded"): E1_BANKS[("approval_assertion", "not_recorded")],
    ("branch", "main"): (
        ("Target branch: main.", "The change merges into the main branch.", "Branch under change: main (trunk)."),
        ("Merge target: main.", "This patch goes onto main.", "Destination branch is main."),
    ),
    ("branch", "staging"): (
        ("Target branch: staging.", "The change merges into the staging branch.", "Branch under change: staging."),
        ("Merge target: staging.", "This patch goes onto the staging branch.", "Destination branch is staging."),
    ),
    ("branch", "feature"): (
        ("Target branch: a feature branch.", "The change lands on a feature branch.",
         "Branch under change: feature/{slug}."),
        ("Merge target: feature/{slug}.", "This patch goes onto a feature branch.",
         "Destination branch is a feature branch."),
    ),
    ("environment", "production"): (
        ("Target environment: production.", "This change deploys to the production environment.",
         "Environment: prod (customer-facing)."),
        ("Deploys to: production.", "Rollout target is the production environment.", "Runs against prod."),
    ),
    ("environment", "staging"): (
        ("Target environment: staging.", "This change deploys to the staging environment.",
         "Environment: pre-production staging."),
        ("Deploys to: staging.", "Rollout target is the staging environment.", "Runs against staging."),
    ),
    ("environment", "development"): (
        ("Target environment: development.", "This change deploys to the development environment.",
         "Environment: dev sandbox."),
        ("Deploys to: development.", "Rollout target is the development environment.", "Runs against dev."),
    ),
}

# Per-item draws not fixed verbatim by the registration ("drawn per item"); fixed here, before any call.
DOC_PREFIX = "DPA-"
SLUGS = ("retry-backoff", "metrics-export", "dependency-bump", "auth-refactor", "cache-tuning", "log-format")

# Paths
RESPONSES_DIR = ROOT / "responses"
RESULTS_DIR = ROOT / "results"


def cache_path(exp: str):
    return RESPONSES_DIR / f"p6-{exp}.jsonl"


def manifest_path(exp: str):
    return RESPONSES_DIR / f"manifest-p6-{exp}.json"


def tau_path(exp: str):
    return RESULTS_DIR / f"p6-{exp}.tau.json"


TEMPLATE_PATH = RESULTS_DIR / "p6.template.md"
RESULTS_PATH = RESULTS_DIR / "p6.md"
SLOTS_JSON_PATH = RESULTS_DIR / "p6.slots.json"
