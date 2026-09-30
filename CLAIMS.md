# Claims (paper 6)

One row per claim, from brief §2. Status is `unregistered` until the author tags `prereg-p6-v1.1`, which supersedes `prereg-p6-v1`; after that it moves only when the evidence named here exists in the repository.

| id | claim | type | evidence pointer | status |
|---|---|---|---|---|
| C1 | A sensed field enters the gate only as an observation record with provenance, score and admission stamp; the model never emits a verdict. | architecture | prereg/p6-v1.1.md §2 (sensed record); Phase B schema and tests | unregistered |
| C2 | Proposition S1 `[F1]`: for a contract with sensed-field set F_s, P(verdict change) ≤ Σ_{i∈F_s} (e_i + u_i), and P(deny→allow) ≤ Σ_{i∈F_s} e_i, where e_i is the probability that field i is admitted with a wrong value and u_i the unknown rate. An instantiation of union-bound reasoning (Barthe et al., ICALP 2016). | instantiation `[F5]` | prereg/p6-v1.1.md §3 (S1); Phase B finite checker | unregistered |
| C3 | Proposition S2 `[F6]`: for sufficient contracts with nested sensed-field sets, the bound does not increase as sensed fields are removed; selection minimises the estimated bound Σ_i (e_i + u_i), a paper 5 cost model. | formal | prereg/p6-v1.1.md §3 (S2); Phase B finite checker | unregistered |
| C4 | On the CH-B1 code/cloud domain and the CH-C1 35-property domain, with two sensor families and three noise levels, the observed unsafe rate never exceeds the bound. | empirical, registered | prereg/p6-v1.1.md §5.4 E1, H1 | unregistered |
| C5 | Deny-to-allow flips were zero in every registered cell. | empirical, registered | prereg/p6-v1.1.md §5.4 E1, §5.5 E2 (unsafe rates, descriptive) | unregistered |
| C6 | Scores from both sensor families are not calibrated (Spiegelhalter rejects), so admission thresholds must be set empirically; this is reported, not assumed. | empirical | prereg/p6-v1.1.md §5.8 E5 | unregistered |
| C7 | Sensing-aware reduct selection changes which reduct is chosen on CH-B1 and reduces measured exposure. | empirical, registered | prereg/p6-v1.1.md §5.5 E2 (substitution test), H2 | unregistered |
| C8 | Everything reproduces from committed caches; no number is hand-entered. | reproducibility | prereg/p6-v1.1.md §7 (cache and slots rules) | unregistered |

## Non-claims

Non-claims, stated in the paper: no prevalence in live systems; no claim that sensing is safe in general; no claim about Jev or Haiku beyond the tested configurations; no claim that the bound is tight.
