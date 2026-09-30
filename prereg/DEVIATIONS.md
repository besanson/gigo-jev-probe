# Deviations

jev-v1: no deviations. Run segment 1 paused after a 6-call smoke test and resumed in registered order under §9; cached calls were not repeated.

jev-v2: no procedural deviation. Known issue KI-1: the LLM arm (claude-haiku-4-5-20251001) returned 2,100 of 2,100 test records and 900 of 900 validation records (6,000 of 6,000 replies, including the one registered re-request) wrapped in a Markdown code fence; the registered parser (§6 B, bare JSON only) scored all of them invalid, thresholds fell back to ±inf, and every LLM reading mapped to unknown. H2 therefore compares Jev with a sensor that always denies and is uninformative about Haiku. H3 cost is real but bought no usable verdict. H1 is unaffected. Root cause: the registration had no per-arm health check before the test split.

jev-v3: no deviations.
