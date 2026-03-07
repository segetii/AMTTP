# TechRxiv v1 (public disclosure) vs Combined-3 (UK) claims — overlap matrix (practical)

This is a *practical* prior-art overlap check using text extracted from the TechRxiv v1 PDF and the current Combined-3 claim set.

- TechRxiv scan output: techrxiv_v1_overlap_terms.md
- TechRxiv term scan: techrxiv_v1_term_scan.txt
- Current claims: ../patent_specification.tex (Claims 1–25)

## Key takeaway

TechRxiv v1 explicitly mentions (among other things) **pre-settlement controls**, a deterministic **decision matrix** with actions including **escrow**/**block**, and **zero-knowledge proofs** for **KYC**, **risk range**, and **sanctions non-membership**, including mentions of **Groth16**.

Note: an earlier scan treated `ttl` as a substring and produced false positives because `ttl` appears inside the word **settl**ement. Treat any TTL/freshness conclusion as **unconfirmed** unless you can locate an explicit TTL/freshness passage in the PDF text.

Those items, **as standalone ideas**, are very likely *not* claimable broadly in a UK filing made after that publication.

The Combined-3 independent claims remain plausibly distinguishable because they *require* features **not found** in the extracted TechRxiv v1 text: **spectrum operators → anomaly tensor**, and **state-dependent friction coefficient $\gamma^*(X)$** used to select enforcement profiles.

## Legend

- **High overlap**: TechRxiv v1 appears to disclose the same feature/idea directly.
- **Partial**: related idea disclosed, but not the same technical mechanism/constraint.
- **Not seen**: term/concept not found in extracted text (note: figures/diagrams may contain text not captured by extraction).

## "Exposed" items (from TechRxiv v1) — patentability reality check

| Exposed item in v1 | Evidence (term hits) | Standalone UK patentability now | Notes / what can still be protected |
| --- | --- | --- | --- |
| Pre-settlement compliance controls | `pre-settlement` (p2) | **Very unlikely** (already public) | Protect *new technical enforcement mechanisms* or *new scoring/control logic* (e.g., friction-driven profile selection; anomaly-tensor scoring), not the general concept.
| Deterministic decision matrix with thresholds | `decision matrix` (p4,5,12) | **Very unlikely** | A threshold table mapping to approve/review/escrow/block is generally straightforward once disclosed.
| Escrow as an enforcement action | `escrow` (multiple pages) | **Very unlikely** | You may still protect *specific on-chain escrow release conditions* tied to new signals (e.g., $\gamma^*(X)$ + attribution-driven proof policy).
| ZK proofs for KYC/risk-range/sanctions non-membership | `kyc`, `risk range`, `non-membership`, `zero-knowledge`, `zk-snark`, `groth16` | **Very unlikely** | What may remain protectable: *how* proofs are selected/combined (e.g., as a deterministic function of $\gamma^*(X)$ and anomaly attribution), or specific on-chain freshness checking / storage patterns if not disclosed.
| TTL / freshness concept | `ttl` hit is unreliable (substring false positive) | **Unknown** | If v1 does not explicitly teach proof-freshness/TTL gates, a specific on-chain timestamp + freshness validation mechanism may still be claimable.
| Sanctions screening | `sanctions` | **Very unlikely** | Protecting a new technical way to do screening (e.g., spectrum/anomaly tensor + proof gating) is the angle.

## Claims 1–25 (Combined-3) — overlap risk summary

This section is *not legal advice*; it is a technical overlap assessment to help you understand risk.

| Claim(s) | What it mainly covers | TechRxiv v1 overlap | Why |
| --- | --- | --- | --- |
| 1–2 | Pre-settlement enforcement + **anomaly tensor via spectrum operators** + **$\gamma^*(X)$** profile selection + on-chain proof gating | **Partial** | v1 discloses pre-settlement controls/decision matrix/escrow/ZK proofs; v1 does **not** show anomaly tensor/spectrum operators or adaptive friction $\gamma^*(X)$ in extracted text.
| 3–6 | Spectrum operators → anomaly tensor + decomposition + attribution + deviation-separating condition | **Not seen** | Those UDL-style elements are not found in extracted v1 text.
| 7 | Boundary-centred dimension magnifier | **Not seen** | Not found in extracted v1 text.
| 8–11 | MFLS/failure-mode correction without retraining | **Unknown / likely low** | Not checked in v1 beyond term scan; needs targeted search for MFLS/C,G,A,T/blind-spot terms.
| 12 | Discrete profile selection driven by $\gamma^*(X)$ thresholds | **Partial** | v1 uses a decision matrix; $\gamma^*(X)$-driven switching is not found.
| 13–14 | Proof types incl. sanctions non-membership / risk-range / KYC; Groth16 + TTL | **High (except TTL)** | v1 explicitly lists these proof types and mentions Groth16; TTL is not confirmed by the extracted text.
| 15 | Proof policy as function of $\gamma^*(X)$ *and* per-law-domain attribution | **Not seen** | The coupling of (friction + attribution) to proof requirements is not found.
| 16–17 | Closed-form $\gamma^*(X)$ expression; gravitational interaction engine | **Not seen (by term scan)** | v1 term scan did not find gamma/friction; gravitational terms not evaluated.
| 18 | Profile also sets rate limits/delays/escrow duration/value limits | **Unknown / partial** | v1 implies operational controls; specifics unclear.
| 19 | Cross-chain bridge requiring verification on both chains | **Not seen** | Not found in v1 scan.
| 20 | Instability metrics from graph spectral radius/centrality/bursts | **Unknown / partial** | v1 says graph analysis exists; these specific metrics not checked.
| 21 | Navier–Stokes style flow metrics | **Not seen** | Not found in v1 scan.
| 22 | Minsky regime classification | **Not seen** | Not found in v1 scan.
| 23 | On-chain storage of profiles mapping to thresholds+policy | **Not seen** | Not found in v1 scan.
| 24 | Verifier stores timestamped results; core checks TTL freshness | **Partial** | v1 clearly mentions proof verification; TTL/freshness is not confirmed by the extracted text.
| 25 | On-chain event log for audit trail | **Partial** | v1 mentions audit logs/infrastructure; exact event structure unknown.

## Practical answer to “are the exposed items still patentable?”

- **As broad standalone claims (e.g., “a pre-settlement compliance decision matrix with escrow and ZK KYC proofs”)**: very likely **no**, because TechRxiv v1 already made those ideas public.
- **As parts of a new, narrower combination claim** anchored on features *not disclosed* in TechRxiv v1 (e.g., spectrum/anomaly-tensor scoring + $\gamma^*(X)$ adaptive profile selection + attribution-driven proof policy): **potentially yes**, subject to inventive-step and sufficiency.

## Limits of this method

PDF text extraction can miss text inside images/figures. For high-stakes decisions, the safest step is a manual read-through of TechRxiv v1 (especially figures/tables) and then updating this matrix.
