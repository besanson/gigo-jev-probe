# Novelty fence (paper 6)

Brief §4, verbatim. Written before `prereg/p6-v1.md` is tagged.

Not claimed as new: score thresholds with reject option (Chow 1970; Geifman and El-Yaniv 2017); conformal prediction and risk control (Vovk; Angelopoulos and Bates); learning to defer (Madras et al. 2018; Mozannar and Sontag 2020); calibration measurement (Guo et al. 2017; Spiegelhalter 1986; Brier); confidence-scored information extraction; human-in-the-loop escalation; runtime enforcement and shields (already fenced in paper 4); reduct theory and cost-sensitive reduction (already fenced in paper 5).

Claimed: the composition. An abstaining admission policy placed between a sensor and a sufficiency-checked authority contract; an exposure bound stated in terms of the contract's sensed fields; sensing-aware reduct selection as a paper 5 cost model; the sensed record as a SARC-DQ-governable evidence record. The sentence for Section 9: "This paper does not introduce abstention, calibration, conformal control or reducts. It shows how an abstaining sensor composes with a sufficiency-checked contract, bounds the resulting exposure by the contract's sensed fields, and selects contracts to minimise it."

External reviewer to run the fence before the prereg is public. Same as paper 5.

## Prior compositions `[F4]` (added with `prereg/p6-v1.1.md`)

Composing an uncertain perception or sensing component with a symbolic check that decides has
been done before. Zhu and Zhang (CAV 2024), Astorga et al. (OOPSLA 2023) and Artikis et al.
(DEBS 2012) each place probabilistic or learned outputs under a deterministic or symbolic
decision layer. The composition of a sensor with a deciding check is therefore not claimed as
new. Zhu and Zhang appears in the CAV 2024 accepted-papers list. Astorga et al. and Artikis
et al. remain as named in the review, verification pending the citation gate.

**Claim, narrowed.** What is claimed is the conjunction of: an abstaining admission policy
between a sensor and a **sufficiency-checked** authority contract; an exposure bound stated
over that contract's sensed fields (an instantiation of union-bound reasoning, `[F5]`); and
**sensing-aware selection** among sufficient contracts, as a paper 5 cost model, for nested
sensed-field sets (`[F6]`). Neither the admission policy alone, nor the bound alone, nor the
composition with a symbolic decision layer alone is claimed.
