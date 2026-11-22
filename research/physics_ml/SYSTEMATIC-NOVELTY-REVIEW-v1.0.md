# Systematic novelty and prior-art review v1.0

This is the historical design review completed before the v1.0 research stages. Its proposed gates and future-tense requirements describe that earlier plan. The subsequent [confirmatory evaluation](../confirmatory_v1/RESULTS-v1.0.md) is complete, failed its integration gate and consumed the v1.0 holdout. A new method needs new confirmatory evidence.

## Status and scope

**Cut-off:** 14 August 2026.

This review is the novelty gate that must be passed before a final ML method is designed. It covers public-GP/TLE/OMM maneuver screening, orbit/anomaly detection, sequential statistical testing, selective prediction/abstention, physics-informed ML, relevant patents, and public implementations.

The target research idea entering this review was:

> sequential risk-controlled hybrid physics-ML satellite maneuver screening from public GP/TLE/OMM histories with explicit abstention and uncertain-label validation.

The conclusion of this review is that this phrase is too broad and over-claims novelty. Almost every architectural ingredient already exists separately, and several 2025-2026 works combine temporal ML with orbital physics. The defensible contribution is narrower and should center on **catalogue-aware selective event screening and its calibration/evaluation protocol under incomplete public evidence**, not on a neural architecture.

This document is a technical prior-art review, not a legal freedom-to-operate or patent-infringement opinion.

## Review method

The search was organized by technical family rather than by a single keyword string. Searches used combinations of `satellite`, `space object`, `RSO`, `maneuver/manoeuvre`, `TLE`, `OMM`, `GP history`, `SGP4`, `anomaly`, `change point`, and model-family terms. We checked publisher/proceedings pages, preprints, ESA proceedings, patent records and public repositories, then followed citations backward and forward where they materially affected the claim boundary.

Families searched explicitly:

1. classical TLE/element-change and propagation-consistency methods;
2. Kalman, IMM/UKF and particle-filter methods;
3. supervised ML, LSTM/BiLSTM, GRU, TCN and CNN approaches;
4. autoencoders, unsupervised and debris/nominal-reference anomaly models;
5. transformers and foundation/time-series forecasting models;
6. spiking neural networks;
7. physics-informed and hybrid physics-ML methods;
8. conformal prediction, conformal martingales, e-process/sequential testing and anytime-valid risk control;
9. selective classification, reject options and abstention;
10. labelled benchmarks, weak supervision, uncertain labels and public implementations;
11. patents describing maneuver detection from residuals, TLEs, ML, GANs or SGP4-derived synchronized states.

A targeted search did **not** identify, through the cut-off date, a public-GP/TLE maneuver-screening paper whose central method is a GRU or a TCN. This is not evidence that none exists. More importantly, GRUs and TCNs are established temporal architectures and TCN/attention is already used in spacecraft maneuver-intention inference, so substituting one of them for an LSTM/Transformer would not constitute defensible research novelty.

## Findings by technical family

### 1. Classical public-TLE maneuver detection is mature prior art

Kelecy et al. (AMOS 2007) explicitly derive maneuver information from historical TLE data and evaluate against spacecraft with known maneuver histories. Lemmens and Krag (2014) develop both a TLE consistency check and time-series analysis using robust statistics/harmonic analysis. Li, Li and Chen (2018) detect anomalous segments in semi-major-axis and inclination histories with moving windows and propagation-derived references. Li et al. also explicitly discard the first of adjacent TLE pairs separated by less than half an orbit because closely spaced publications may be catalogue updates.

Later work extends these families rather than changing the fundamental problem: clustering/SOM methods detect and classify anomalous TLE segments; Zollo and Weigel compare timeline methods including a discrete linear Kalman filter; Gui et al. (2026) use dual-moving-window curve fitting with probability-derived thresholds for three-dimensional impulsive maneuvers. ESA's AACOS work demonstrates a generic automatic public-TLE maneuver-analysis pipeline and, importantly for our claim boundary, automatically disables analysis when the TLE noise level is too high.

**Implication:** we cannot claim novelty for historical-TLE maneuver detection, moving-window anomaly detection, propagation consistency, adaptive thresholds, generic automation, or abstaining merely because the data are noisy.

### 2. Kalman and particle-filter maneuver/anomaly detection are established

Kalman-family maneuver detection appears both in observation-based catalog-maintenance work and in TLE/element-timeline comparison studies. Fu (2026) uses an IMM-UKF as one level of a large-scale weak-label cascade. Shorten et al. (2025) develop optimal-proposal particle filters specifically for anomaly and maneuver detection from TLE histories, explicitly model SGP4 uncertainty, and evaluate on a 15-satellite benchmark plus simulation. On the real benchmark, they report that a simple mean-motion baseline can perform equivalently to their best filters, illustrating how strongly benchmark design can affect conclusions.

**Implication:** a Kalman/IMM/particle-filter core, or a residual threshold on top of one, is a baseline choice rather than a novelty claim.

### 3. LSTM/BiLSTM and supervised sequence learning from TLE are established

Cipollone, Frueh and Di Lizia (2025) use LSTM/BiLSTM sequence models on public TLE histories for offline maneuver labeling and online maneuver probability inference. Their paper discusses irregular TLE sampling, interpolation/resampling, object-tailored training and limited generalization to new satellites. Earlier supervised TLE-data-mining work by Cipollone and colleagues already frames maneuver detection as supervised sequence classification.

The open `astro-tools/maneuver-detect` project additionally supplies a reproducible BiLSTM baseline over encoded public TLE histories.

**Implication:** LSTM/BiLSTM architecture, sequence-window classification, irregular-time preprocessing, online/offline variants and object-specific pattern-of-life learning are not new.

### 4. GRU and TCN are not a useful novelty route

The targeted search did not surface a direct public-TLE maneuver detector centered on GRU or TCN through 14 August 2026. However, the architecture family is already routine in aerospace sequence learning. A 2026 spacecraft proximity-maneuver intention study uses cascaded TCN plus self-attention and compares recurrent/Transformer alternatives.

**Implication:** even if a direct TLE-GRU/TCN detector is absent from the indexed material reviewed, using GRU or TCN should be justified by performance, latency or causality, not claimed as the scientific contribution.

### 5. Autoencoder and nominal-only anomaly learning are established and close to our earlier proposal

Wang and Li (2023) use an autoencoder plus decision tree on TLE histories to classify non-maneuver, orbit raising, lowering and maintenance states for Starlink-like constellation satellites, including tests on additional satellites not used for modeling.

More importantly, Cipollone, Raviola and Di Lizia (ESA Space Debris Conference 2025) propose an unsupervised LSTM autoencoder for maneuver detection using public TLE sequences. For each active target, they select debris with similar orbit geometry, train on that ballistic/nominal behavior, and flag the active target when its anomaly score is out-of-distribution; k-means derives the threshold.

The Raytheon patent US11649076B2 is even closer to the broad nominal-reference idea: it trains an unsupervised anomaly model from NORAD TLE data of known debris and uses deviations of active-object TLEs from that debris model to indicate maneuvers.

**Implication:** "learn normal orbital behavior from non-maneuvering/debris objects and detect deviations" is decisively prior art. Our earlier local conditional nominal model cannot be the headline novelty.

### 6. Transformers and time-series foundation models are established

Ré et al. (CVPR Workshops 2024) apply Transformer architectures to orbit-determination anomaly detection/classification, including maneuver and mis-modeled-force cases, using simulated OD data.

Fu (2026) is especially important. It processes 232 million TLE records with a weak-supervision cascade consisting of a physics rule set, IMM-UKF and supplemental-element calibration, produces millions of labeled sequences, and trains a physics-informed orbital Transformer. It explicitly positions the model as high-recall triage rather than final attribution. Its published split is window-level rather than satellite-disjoint, allowing the same NORAD object to occur across train/validation/test; its cascade is explicitly a weak-label mechanism, not ground truth.

The open `astro-tools/maneuver-detect` package has a compact Transformer baseline and a Chronos forecast-residual baseline using a pretrained time-series model.

**Implication:** neither "Transformer for orbital maneuver detection", "physics-informed Transformer", "time-delta encoding", "forecast residual anomaly detection", "foundation model on TLEs", nor "high-recall triage" is novel enough for our paper.

### 7. Spiking neural networks are already applied to orbital maneuver detection

The 2025 MLF-SNN work applies a multi-level-firing spiking neural network to orbital maneuver detection using orbital-element variations and real Space-Track TLE data.

**Implication:** SNN architecture is not a novelty route.

### 8. Generic hybrid physics + ML and runtime physics gates are prior art

Karunathilake, Abeywardena and Vecchini (2026) explicitly present a hybrid AI/physics architecture for suspicious satellite orbital manipulation. Temporal ML, including LSTM, generates anomaly alerts and a runtime Vis-Viva physics gate filters/validates them. Fu (2026) likewise embeds analytical physics in a weak-supervision/Transformer pipeline. `maneuver-detect` uses learned detectors followed by shared vis-viva/Gauss-style maneuver inversion.

**Implication:** the phrases "hybrid physics-ML", "physics-informed maneuver detector", "physics-validated ML alert", "ML plus an orbital-mechanics gate" and "learned detector with downstream physical inversion" cannot be presented as novel.

Our RTN/element corroboration layer may still be valuable because it is transparent and auditable, but it must be described as an **engineering/interpretability constraint**, not as the novelty.

### 9. Same-epoch SGP4 comparison is not novel in isolation

Historical methods propagate TLE states to common epochs for consistency testing. The CN115016271 patent family explicitly uses SGP4 to propagate two spacecraft's TLE states to the same time before relative-state clustering and maneuver inference.

**Implication:** common-epoch SGP4 propagation or synchronization is not itself novel. The narrower possible contribution is how we treat **catalogue revisions at effectively the same epoch** as data provenance/uncertainty rather than letting them become maneuver evidence.

### 10. Conformal prediction and sequential conformal testing are established

Chen et al. (SPIE 2013) apply conformal prediction to anomaly detection and collision alerting in space surveillance. Therefore conformal prediction in SSA is not new.

Volkhonskiy et al. (2017) develop inductive conformal martingales for quickest change-point detection. Vovk et al. (2021) use conformal test martingales to detect distribution changes. Shaer et al. (2026) go further with **conditional conformal test martingales using a fixed null reference set**, providing anytime-valid type-I error control conditional on that reference under their assumptions and avoiding post-change contamination.

The broader statistical literature also contains anytime-valid risk-control procedures for adaptively collected/sequential data.

**Implication:** empirical conformal-style p-values, betting e-values, a mixture over candidate start times, or fixed-reference sequential evidence cannot be claimed as novel. More importantly, our current v0.3 empirical local p-values over autocorrelated, irregular public GP histories do **not** automatically satisfy the exchangeability/conditional super-uniformity assumptions required for e-process validity.

Therefore the phrase **risk-controlled** must be removed unless the final paper introduces and proves a dependence-aware construction whose assumptions are defensible for this data-generating process. Without such a proof, the correct phrase is **risk-calibrated** or **empirically risk-calibrated**.

### 11. Abstention and reject-option learning are established

Selective classification and reject-option learning explicitly trade error/risk against coverage. Gangrade, Kag and Saligrama (2021), Franc and Prusa (2019), and related work formalize selective risk and abstention. In the space domain, AACOS already disables maneuver analysis in excessive TLE noise.

**Implication:** abstention is not a standalone novelty claim.

A narrower, potentially distinct contribution remains: **abstention because an orbital/sampling context lies outside the satellite-disjoint calibration support**, with coverage/abstention reported as a first-class scientific outcome and catalogue-revision ambiguity as another explicit non-decision state.

### 12. Public benchmarks exist, but the evidence semantics remain a strong differentiator

Shorten et al. release a 15-satellite TLE benchmark with externally obtained maneuver timestamps and some higher-quality DORIS data. `astro-tools/maneuver-detect` expands the open ecosystem with reconstructable public histories, operator-derived labels, learned baselines and a frozen benchmark/leaderboard. Therefore "first open TLE maneuver benchmark" is unavailable.

However, the literature reviewed did not reveal an equivalent evaluation contract to benchmark v1.0 in this repository:

- documented event intervals score TP/FN without asserting the rest of the window is negative;
- unmatched predictions in positive cases are unscored unless they fall in independently verified quiet coverage;
- false positives are measured only on explicit verified-quiet exposure;
- scheduled notices and executed-event evidence retain different confidence tiers;
- all windows are satellite-disjoint across development/calibration/confirmatory partitions;
- a confirmatory satellite set is frozen before method design/tuning;
- confidence intervals are clustered at the satellite, not record/window, level.

Fu's 2026 dataset makes the contrast particularly clear: it uses a very large weak-label cascade and a **window-level split in which the same NORAD object may occur in multiple splits**, whereas our benchmark's confirmatory unit is the satellite and its public evidence is explicitly positive-unlabelled/interval-censored.

This evaluation protocol is therefore one of the strongest defensible contributions.

## Patent prior-art map

| Patent / family | Relevant disclosure | Consequence for our claim |
|---|---|---|
| US9617018B2, *Automated detection and characterization of earth-orbiting satellite maneuvers* | residual trends/deviations, temporal sliding windows, OD-based detection/characterization | residual/window maneuver detection and iterative characterization are established |
| US11649076B2 / US20210261276A1, Raytheon, *Space object maneuver detection* | unsupervised model from NORAD TLE data of debris; active-object deviation from debris model indicates maneuver | nominal/debris-reference unsupervised TLE anomaly detection is established |
| US20210342669A1, *Method, system, and medium for processing satellite orbital information using a generative adversarial network* | GAN discriminator for maneuver detection plus generator for maneuver-like orbital evolution | GAN-based maneuver detection is established |
| US11574223B2 / US20210103841A1, *Method and apparatus for rapid discovery of satellite behavior* | ML/data fusion for satellite behavior and maneuver-related analysis | broad ML-based behavior discovery is established |
| CN115016271A/B, *spacecraft relative orbit maneuver detection based on cluster analysis* | historical TLE, SGP4 propagation to a common epoch, relative-state features and clustering | same-time SGP4 synchronization + clustering is established |

No patent reviewed was found to disclose the full combination of catalogue-revision provenance, calibration-support abstention, satellite-level verified-quiet risk calibration and positive-unlabelled interval-censored confirmatory evaluation. That observation is a research novelty finding only, not a legal conclusion.

## Open-source implementation map

| Implementation | Public capability | Relevance |
|---|---|---|
| `dpshorten/TLE_observation_benchmark_dataset` | 15-satellite TLE benchmark, maneuver timestamps, DORIS data for some objects | removes novelty of publishing a TLE maneuver benchmark |
| `astro-tools/maneuver-detect` | reconstructable dataset, classical detector, BiLSTM, Transformer, Chronos residual detector, shared physics inversion, scorer/leaderboard | removes novelty of open learned TLE detector stack and architecture comparisons |
| this repository, detector 0.4 | catalogue-revision resolution, common-epoch SGP4/RTN, event grouping, explicit abstention, PU benchmark semantics | engineering baseline on which the final research method will be tested |

## Novelty matrix

Legend: **No** = established prior art; **Incremental** = useful but too close to known work for a headline claim; **Defensible** = no direct equivalent identified in the reviewed material; **Conditional** = defensible only with an additional theorem/experimental design.

| Candidate contribution | Status | Closest prior art | Final treatment |
|---|---|---|---|
| maneuver detection from public TLE/OMM histories | **No** | Kelecy 2007; Lemmens & Krag 2014; Li et al. 2018; AACOS | baseline problem statement only |
| moving-window/statistical anomaly detector | **No** | Li et al.; DMWCF 2026 | baseline |
| Kalman/IMM/particle-filter anomaly detector | **No** | Zollo & Weigel; Shorten et al.; Fu | baseline |
| LSTM/BiLSTM maneuver detector | **No** | Cipollone et al. 2025; `maneuver-detect` | baseline |
| GRU/TCN temporal backbone | **Incremental** | aerospace sequence models; TCN/attention proximity-intention inference | architecture option only |
| autoencoder / nominal-only anomaly model | **No** | Wang & Li 2023; Cipollone et al. 2025; US11649076B2 | baseline |
| Transformer maneuver/anomaly detector | **No** | Ré et al. 2024; Fu 2026; `maneuver-detect` | baseline |
| time-series foundation forecast residual | **No** | `maneuver-detect` Chronos | baseline |
| SNN maneuver detector | **No** | MLF-SNN 2025 | baseline/reference |
| physics-informed ML | **No** | Fu 2026; Karunathilake et al. 2026 | supporting design only |
| runtime physical corroboration/gate | **No / Incremental** | Karunathilake et al.; learned detectors with physics inversion | auditable constraint, not novelty |
| common-epoch SGP4 residuals | **Incremental** | TLE consistency methods; CN115016271 | useful feature family only |
| conformal anomaly score | **No** | Chen et al. 2013 | mechanism only |
| sequential conformal/e-value accumulation | **No** | Volkhonskiy et al.; Vovk et al.; Shaer et al. | mechanism only |
| formal anytime event risk control on irregular dependent GP histories | **Conditional** | general CTM/e-process/risk-control literature | claim only if a new valid construction/theorem is proved |
| generic abstention | **No** | selective classification; AACOS noise disable | do not claim |
| calibration-support/OOD abstention evaluated as risk-coverage | **Defensible domain combination** | generic selective prediction; nominal/debris OOD models | retain as contribution, describe narrowly |
| handling near-same-epoch catalogue updates | **Incremental alone** | Li et al. 2018 discards close updates | no "first to notice updates" claim |
| deterministic catalogue revision/supersession provenance + audit + abstention | **Defensible domain combination** | no equivalent end-to-end treatment identified | retain as contribution |
| event-level false-alert calibration using only verified-quiet exposure | **Defensible** | no direct equivalent identified | central contribution |
| positive-unlabelled interval-censored event scoring | **Defensible** | existing maneuver timestamp benchmarks do not use this full contract | central contribution |
| scheduled vs executed evidence confidence tiers | **Defensible** | weak-label work generally collapses derived/pseudo labels differently | central contribution |
| satellite-disjoint development/calibration/confirmatory partition | **Defensible in this setting** | Fu uses window-level split; several papers are object-specific or small holdouts | central contribution |
| pre-frozen unseen-satellite confirmatory evaluation | **Defensible in this setting** | no direct equivalent found in reviewed public-TLE maneuver papers | central contribution |
| satellite-cluster bootstrap and object-month false-event burden | **Defensible evaluation combination** | generic clustered inference exists | supporting methodological contribution |

## Claims that must be rejected

Do not claim any of the following in the final paper:

- first ML-based satellite maneuver detector;
- first deep-learning, LSTM, BiLSTM, GRU, TCN, Transformer, autoencoder or SNN maneuver detector;
- first physics-informed satellite maneuver detector;
- first hybrid physics + ML detector;
- first use of a runtime physics gate for satellite anomalies;
- first use of SGP4/common-epoch propagation for maneuver detection;
- first nominal/debris-reference unsupervised maneuver detector;
- first conformal method for space surveillance;
- first conformal/sequential martingale change detector;
- first detector with abstention;
- first public TLE maneuver dataset or benchmark;
- finite-sample or anytime false-event control from the current v0.3 empirical p/e process;
- "confirmed maneuvers" where the evidence is only a scheduled GPS NANU/Galileo NAGU window.

## Defensible contribution after the review

The strongest defensible contribution is:

> **A catalogue-aware selective event-screening framework for public GP histories that separates catalogue revisions and unsupported operating regimes from maneuver evidence, calibrates event-level false-alert burden on satellite-disjoint verified-quiet exposure, and evaluates interval-censored public maneuver evidence under positive-unlabelled semantics with a pre-frozen unseen-satellite confirmatory set.**

This is intentionally a framework/methodology claim. The temporal learner, sequential accumulator and physical feature extractor are replaceable components whose value must be established experimentally.

A concise paper framing is:

> **Catalogue-aware selective sequential maneuver screening under incomplete public evidence.**

A more statistical alternative is:

> **Selective event screening from public GP histories with satellite-disjoint risk calibration and positive-unlabelled validation.**

## Required adjustment to the proposed final method

### A. Rename the statistical claim

Replace **risk-controlled** with **risk-calibrated** unless the final work includes a formal dependence-aware theorem.

If formal anytime control is pursued, the proof must define the exchangeable/conditionally valid unit at the satellite, event or defensible block level. Individual irregular GP records must not simply be assumed IID. A fixed-reference conditional conformal/e-process construction may be a starting point, but it is prior art and would need a new orbital-data validity argument or construction.

### B. Make architecture secondary

Do not choose a Transformer because it sounds novel. On the development/calibration benchmark, compare at least:

- simple residual/statistical baseline;
- small causal MLP or logistic model on physical residual features;
- GRU or TCN causal sequence model;
- compact Transformer;
- existing detector 0.4.

Select the smallest architecture that materially improves the decision objective. If GRU/TCN wins, present efficiency/generalization as an empirical finding, not novelty.

### C. Retain physics as an auditable support constraint

Common-epoch SGP4 RTN residuals and orbital-element changes remain scientifically useful. Physical corroboration should be framed as:

- a transparent support/consistency requirement;
- an interpretability aid;
- an ablation-tested safeguard.

It must not be sold as the first physics-informed or physics-gated maneuver detector.

### D. Put selective decision-making at the center

The final method should have explicit outcomes:

1. candidate maneuver event;
2. no alert within **verified support**;
3. abstain because calibration/orbit/sampling support is insufficient;
4. abstain because catalogue-revision/data-quality ambiguity is unresolved.

Risk/coverage curves and abstention reasons should be reported, rather than hiding abstentions inside accuracy.

### E. Calibrate event-level false-alert burden, not pointwise scores

The operating point should be selected on the satellite-disjoint calibration partition using event-level burden on verified-quiet exposure, e.g. false candidate events per verified-quiet object-month, subject to a target recall/coverage criterion. Pointwise probability calibration can be auxiliary but must not be the main safety claim.

### F. Preserve positive-unlabelled benchmark semantics

The benchmark v1.0 contract is part of the research method:

- documented intervals score TP/FN;
- unmatched alerts elsewhere in positive cases remain unscored;
- only verified-quiet intervals contribute FP exposure;
- scheduled and executed evidence retain separate confidence tiers;
- uncertainty is never converted silently into a negative class.

### G. Keep confirmatory satellites untouched

All architecture selection, threshold selection, feature selection, support-distance rules and ablation decisions must use development/calibration objects only. The v1.0 confirmatory objects are inspected once, after the method and integration gate are frozen. If that boundary is broken, benchmark v1.1 must freeze a new confirmatory set.

## Mandatory baselines for the final study

At minimum, compare against representatives of the established families:

1. detector method 0.4;
2. moving-window / TLE-consistency statistical baseline;
3. linear Kalman timeline baseline;
4. Shorten-style particle-filter comparator where reproducible;
5. `astro-tools/maneuver-detect` classical baseline;
6. its BiLSTM baseline;
7. its Transformer baseline;
8. its Chronos forecast-residual baseline.

Fu's PIOT and Karunathilake's hybrid physics-ML should be discussed as literature comparators even if exact code/checkpoints are unavailable.

## Mandatory ablations

The final method should include the following ablations because they directly test the claimed contribution:

| Ablation | Question answered |
|---|---|
| no catalogue-revision resolution | does catalogue provenance actually prevent false maneuver evidence? |
| no support/OOD abstention | does selective screening improve risk at useful coverage? |
| no physical corroboration | is the physics layer useful beyond the temporal learner? |
| pointwise threshold vs event-level calibration | is event-level risk calibration materially better aligned with operational burden? |
| random-window split vs satellite-disjoint split | how much optimistic leakage arises from same-satellite windows? |
| unlabeled-as-negative vs PU/verified-quiet semantics | how badly does conventional binary scoring bias conclusions? |
| backbone swap: MLP/GRU-or-TCN/Transformer | is the contribution robust to architecture choice rather than being one network trick? |
| scheduled-only evidence excluded | are conclusions robust when only executed/high-confidence evidence is scored? |

## Historical method-design gate

The final ML method may now be designed, but it must satisfy these constraints:

- the **novelty claim is the selective decision/calibration/evidence framework**, not the backbone;
- no formal `risk-controlled` wording without a proof valid for dependent irregular GP histories;
- no physics-informed-first claim;
- no generic abstention-first claim;
- confirmatory satellites remain untouched;
- the method must be demonstrably better than simple and open learned baselines on the frozen v1.0 benchmark without relying on mislabeled negatives.

If the eventual results show that catalogue-aware abstention and PU event-level calibration do not materially change performance or risk estimates, the paper's algorithmic novelty would be too thin and the work should be reframed primarily as a benchmark/evaluation-methodology paper rather than overstating a detector contribution.

## Core references

The complete machine-readable bibliography is in `REFERENCES-v1.0.bib`. Key sources include Kelecy et al. (2007); Lemmens and Krag (2014); Li, Li and Chen (2018); Zollo and Weigel (2024); Shorten et al. (2025); Cipollone, Frueh and Di Lizia (2025); Cipollone, Raviola and Di Lizia (2025); Wang and Li (2023); Ré et al. (2024); Fu (2026); Gui et al. (2026); Karunathilake et al. (2026); Volkhonskiy et al. (2017); Vovk et al. (2021); Shaer et al. (2026); and the patent families listed above.
