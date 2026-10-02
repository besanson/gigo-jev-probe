1. **High — C1’s claimed record boundary is bypassed by the experimental pipeline.** **[§§1–3; §9 C1; CLAIMS.md C1]**  
   `analysis_p6.readings()` takes cached scores directly through `admit()` into plain admitted-value dictionaries. `corpus_p6.e1_outcome()` and `e2_outcome()` pass those values to `ContractModel.outcome()`. This path neither constructs `SensedRecord` objects nor invokes `admitted_value()` and its binding checks. The runner and sensor adapters cache model responses, rather than the admission-stamped records claimed in C1’s evidence pointer. Unit tests establish that a separate record-checking component exists; E1/E2 do not demonstrate the architecture’s enforced observation-record boundary. The limitation concerning *mismatched* records does not disclose this broader integration gap.

2. **High — The H2 interpretation asserts verdict dominance that S2 does not prove.** **[§7.8, paragraph after the hypotheses table; §4 S2; Appendix A; §8 closing sentence]**  
   S2 orders sums of error terms. It does **not** imply that every item changed by the smaller sensed-field set must also change under the larger set.

   A counterexample uses reachable tuples with \(z=y\), and allows iff \(x=y\). Both \(\{x,z\}\) and \(\{x,y\}\) are sufficient minimal contracts. The first senses only \(x\), while the second senses \(x,y\). At true tuple `(0,0,0)`, jointly misreading \(x=y=1\) makes the first contract deny incorrectly, while the second still allows correctly. The shared reading is identical, and the sensed sets are nested. I reproduced this counterexample using the committed `ContractModel`.

   Therefore, “S2 … predicts … b should be zero” is false. The observed four zeros remain empirical results. Likewise, §8’s final claim to select contracts to minimise exposure is stronger than minimising its estimated upper bound.

3. **High — “S3 condition held” is computed from zero observed unsafe outcomes, not the global condition.** **[§7.2 table and explanation; §4 S3; Appendix A; registration §§3, 5.4]**  
   `analysis_p6.e1_slots()` sets `s3_held` to `unsafe == 0`. It does not evaluate every reachable deny tuple and every joint admitted-value assignment required by S3. Zero observed failures cannot establish that universal property.

   Moreover, the observed Jev counterexample at 30% noise already disproves the unrestricted global condition for that contract and sensed-field set. Under S3’s definition, the same contract does not become globally deny-ward merely because another sensor/noise cell failed to encounter the witness. Calling zero failures the condition’s “observable form” does not make the two statements equivalent.

4. **High — The estimated bounds’ claimed validity does not follow across the registered phrase-bank shift.** **[§5, especially “The floor”; §§7.2, 10 “Loose bounds”; C4–C5]**  
   Split B uses validation phrasing, while the test split uses a disjoint phrase bank. Clopper–Pearson limits estimate error probabilities for the distribution sampled on split B; they do not automatically bound error under the deliberately different test-document distribution. No invariance or transfer assumption bridges those distributions.

   Separately, the 95% limits are marginal limits for individual error/unknown rates. The manuscript establishes no corresponding simultaneous confidence level for all summed bounds and cells. Repeatedly calling the resulting bounds “valid, not tight” therefore exceeds the statistical guarantee established. The deterministic S1 inequality remains valid; replacing its population rates with these estimates introduces additional assumptions.

5. **Medium — S2’s proof assumes identical admissions, while its statement specifies only identical sensors and documents.** **[§4 S2; Appendix A, proof of S2; C3]**  
   The proof begins by asserting that each shared field’s admitted value is identical under both contracts. That also requires the same admission policy and relevant binding/derivation treatment. Identical sensor scores on identical documents can produce different admitted values or unknown rates under different thresholds. The checker assumes identical admissions by restricting one already-admitted observation vector; it does not establish that the statement’s weaker premises ensure this. E2 does share the policies, so this is a general-statement scope gap rather than a demonstrated failure of its four comparisons.

6. **Medium — C3’s compiler-cost adapter does not generally encode the stated objective exactly.** **[§4 S2; §9 C3; `selection.py::observation_costs`]**  
   The adapter adds a positive floor to every property, producing
   \[
   \text{compiler cost}(C)=\widehat B(C)+10^{-6}|C|.
   \]
   For unequal-cardinality contracts this can change ties or sufficiently close rankings. The floor being small relative to individual costs does not establish that it is small relative to differences between contract costs.

   There is also an unresolved naming boundary: actual contracts contain `approval_token`, whereas the sensed-field estimates contain `approval_assertion`. Given those registered names, the adapter charges `approval_token` only the floor. E2 selects directly from manually supplied sensed sets, so its successful picks do not verify this compiler integration. Its equal-cardinality comparison also cannot expose the floor issue.

7. **Medium — C4/C5 compare some E2 outcomes with bounds estimated for a different noise condition.** **[§§7.3–7.4; §9 C4–C5; CLAIMS.md evidence pointers]**  
   The cited E2 `estimated_bound.*` slots are selection bounds fitted at **30% noise**, not separate bounds for each noise level. Nevertheless, C4 covers all three noise levels, and C5 describes every flip as lying under its cell’s registered bound. Four E2 flips occur at 10% noise. The named evidence supports a numerical comparison with the 30%-noise selection bound; it does not establish a matching bound for those 10%-noise cells. Nested document corruption does not itself prove monotonicity of model admission-error probabilities.

8. **Medium — E4’s “per-item outcomes equal” claim exceeds the implemented comparison.** **[§7.6; registration §5.7; `E4.check_passes`]**  
   `analysis_p6.e4_slots()` compares only the total unsafe count and total wrong-field count with the checker’s simulation. It does not compare per-item outcome vectors. Different item-level outcomes can produce identical totals. Both paths also reuse the checker’s `ContractModel` evaluator, so their agreement is not an independent validation of contract evaluation. The exact N6 calculations reproduced successfully; the narrower defect is the claimed strength of the pipeline-matching evidence.

9. **Medium — S1’s written proof silently changes the reference verdict unless recorded fields are correct.** **[§2 “Exposure”; Appendix A, proof of S1; C2]**  
   Exposure is defined by comparing sensed versus true sensed values while retaining the same recorded values. Appendix A instead concludes that correct sensing makes the entire observation agree with the true tuple \(t\), then compares against \(g(t)\). That conclusion requires recorded fields to equal their true values, plus truth-preserving deterministic derivation. The checker explicitly supplies recorded fields at truth, and the experiments adopt that assumption. The general proof does not state it. This is a proof/reference mismatch, not a resurrection of the withdrawn directional-bound counterexample.

10. **Medium — C7’s baseline-change component lacks its registered evidence.** **[§7.4; §9 C7; registration §5.5]**  
    The registration requires paper 5’s default CH-B1 choice to be reported alongside the sensing-aware choice. The manuscript reports only the latter, and the cited slots contain no default/baseline comparison. They support the four selected reducts and their lower measured exposure against the alternative reduct. They do not document the separate assertion that sensing awareness *changes* the choice relative to the existing selector.

11. **Medium — The revised fence covers the previously named compositions, but omits directly relevant error-aware reduct selection.** **[§8; NOVELTY.md, narrowed conjunction]**  
    Zhao, Min and Zhu’s **“Test-Cost-Sensitive Attribute Reduction of Data with Normal Distribution Measurement Errors” (2013)** combines measurement-error modelling with cost-sensitive selection of reducts under a decision-information preservation constraint. This is closer to the remaining selection component than a general reference to reduct theory: sensing error already enters a sufficient-subset selection problem. Its objective and semantics differ from SARC’s abstention/exposure construction, so it does **not** establish an exact prior instance of the full conjunction. It does leave a material comparison missing from the narrowed fence. [Wiley Online Library](https://onlinelibrary.wiley.com/doi/10.1155/2013/946070?utm_source=chatgpt.com)

12. **Low — B12’s advertised exhaustive scope includes sufficient contracts the generator omits.** **[§4 proof-status table; Appendix A checker provenance; `checkers/_common.py`]**  
    B12 is documented as enumerating every sufficient contract, but `_sufficient_subsets()` starts at cardinality one. Empty contracts are sufficient for constant verdict functions and are permitted by \(C\subseteq A\). They are not checked. I reran all four checkers and reproduced their reported results; the issue is this specific scope overstatement, not a failing enumerated case. The general-proof tags themselves remain appropriately below `machine-checked`.

Source reviewed: p6-review-r2-pack-5b4fc02.zip