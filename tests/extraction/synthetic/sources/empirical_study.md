<!-- feature: heading-h1 id:title -->
# Effects of Cognitive Load on Decision-Making Speed and Accuracy: Evidence from Randomized Experiments
<!-- /feature -->

<!-- feature: dense-prose id:abstract -->
Decision-making under uncertainty is fundamental to individual welfare and
organizational performance, yet the cognitive demands of processing information
create potential for systematic biases. This paper investigates the causal effects
of cognitive load (the mental effort required to process task-relevant information)
on decision quality, measured as both speed and accuracy. Using a randomized
controlled trial with 412 participants, we manipulate cognitive load by varying
the complexity of information presentation (simple vs. complex information structure)
and availability of working memory (full capacity vs. capacity-constrained condition).
Participants complete a series of binary choices under time pressure, with correct
decisions offering monetary rewards. We find that cognitive load reduces decision
speed by 18–22% (p < 0.01) with no reduction in accuracy, consistent with a
compensatory adjustment where individuals allocate additional time to maintain
quality. However, this compensation breaks down when time pressure is extreme
($\Delta t < 3$ seconds per decision): under severe time pressure, cognitive
load reduces accuracy by 6–8 percentage points. We develop a Bayesian drift-diffusion
model to decompose this effect into changes in evidence accumulation rate
(boundary separation), caution (decision threshold), and starting point bias.
Estimated caution increases under load (+0.12σ drift-diffusion units), while
accumulation rate decreases modestly (-0.08σ). The results suggest that individuals
can adaptively allocate cognitive resources to compensate for load-induced
processing difficulty, but this adaptation has limits when time constraints
bind. These findings inform theory of decision-making under constraints and have
practical implications for the design of decision-support systems.
<!-- /feature -->

<!-- feature: heading-h2 id:introduction -->
## Introduction
<!-- /feature -->

<!-- feature: dense-prose id:intro-body -->
Cognitive load—the mental effort required to process information—affects decision
quality in contexts ranging from medical diagnosis to financial investment to
policy decisions. Classical dual-process theories (Kahneman, 2011) suggest that
effortful, deliberate thinking (System 2) is cognitively expensive and can be
disrupted by competing demands on attention. Under cognitive load, individuals
may rely more heavily on heuristics (quick, rule-of-thumb procedures) that are
fast but error-prone. However, modern decision-making research increasingly
questions whether this effect is automatic or whether individuals can flexibly
allocate resources to maintain performance (Halford et al., 2005). Some studies
find that cognitive load harms decision quality, while others find adaptive
compensation where individuals invest more time to maintain accuracy.

This paper contributes to this debate by conducting a randomized experiment that
varies cognitive load independently from time pressure, allowing us to distinguish
load effects from constraints on processing time. We hypothesize that moderate
cognitive load leads individuals to invest more time in deliberation (slower
decisions but maintained accuracy), while severe load or binding time constraints
prevent this adaptation, resulting in accuracy loss.
<!-- /feature -->

<!-- feature: heading-h2 id:methods -->
## Methods
<!-- /feature -->

<!-- feature: heading-h3 id:design -->
### Experimental Design
<!-- /feature -->

<!-- feature: dense-prose id:design-body -->
We recruited 412 participants via Amazon Mechanical Turk (mean age = 34.2 years,
51% female, median prior MTurk experience = 45 HITs). Participants completed a
decision task where they made binary choices between lottery options, with the
goal of maximizing expected monetary payoff. Each trial presented information
about two gambles (Gamble A: $5 with probability $p_A$; Gamble B: $10 with
probability $p_B$), and participants selected which gamble to play. The correct
answer was the gamble with higher expected value. We manipulated two factors:

1. **Cognitive Load** (within-subject):
   - Simple condition: probabilities presented as large text percentages
   - Complex condition: probabilities embedded in text narrative with additional
     irrelevant information (participant names, timestamps) requiring selective
     attention

2. **Time Pressure** (between-subject):
   - Loose deadline: 10 seconds per decision
   - Moderate deadline: 6 seconds per decision
   - Tight deadline: 3 seconds per decision

Each participant completed 48 trials (24 per load condition), counterbalanced for
load order. We recorded response time (RT) and accuracy (correct gamble selection)
for each trial. Participants were paid a base rate ($1.50) plus $0.05 per correct
decision (maximum bonus = $2.40).
<!-- /feature -->

<!-- feature: heading-h3 id:model -->
### Drift-Diffusion Model
<!-- /feature -->

<!-- feature: dense-prose id:model-body -->
To decompose decision-making processes, we fit the Drift-Diffusion Model (DDM),
which characterizes decision dynamics as a stochastic process accumulating evidence
toward one of two boundaries (correct or incorrect gamble). The DDM yields four
key parameters: drift rate (evidence accumulation speed), boundary separation
(caution—distance between decision boundaries), non-decision time (encoding and
response preparation), and starting point. Formally, the model specifies:
<!-- /feature -->

<!-- feature: display-math id:ddm-equation -->
$$X(t) = X(0) + v \cdot t + \sigma \cdot W(t)$$
<!-- /feature -->

<!-- feature: dense-prose id:ddm-explanation -->
where $X(t)$ is the accumulated evidence at time $t$, $v$ is the drift rate (evidence
accumulation speed), $\sigma$ is the diffusion constant (noise magnitude), and
$W(t)$ is a Wiener process. The decision is made when $X(t)$ reaches either $a$
(upper boundary) or $0$ (lower boundary). The resulting response time $T$ follows
a known distribution function, and the probability of choosing the upper boundary
is determined by the ratio of drift rate to boundary separation.

We fit the DDM using hierarchical Bayesian estimation, allowing individual-level
parameters to vary around group-level means. This approach pools information across
participants while respecting individual differences, particularly important for
the smaller-$n$ extreme time pressure condition. We used the HDDM Python package
(Wiecki et al., 2013) with default priors, running 5000 post-warmup iterations
per chain, 4 chains total, with convergence diagnostics ($\hat{R} < 1.01$) verified
for all parameters.
<!-- /feature -->

<!-- feature: heading-h2 id:results -->
## Results
<!-- /feature -->

<!-- feature: dense-prose id:results-intro -->
Descriptive results are presented in Table 1. Cognitive load reduces response time
significantly in the loose deadline condition (10s) but this effect diminishes as
time pressure increases. Under loose deadlines, load increases RT by 2.1 seconds
(22% increase), but under tight deadlines (3s), load shows minimal RT increase
(0.2 seconds, 7% increase, not significant). Accuracy follows a different pattern:
in loose and moderate deadline conditions, accuracy is unaffected by load
(differences < 2 percentage points). However, in the tight deadline condition,
load reduces accuracy substantially (5.8 percentage points, p = 0.024).
<!-- /feature -->

<!-- feature: table-complex id:results-summary -->
| Time Pressure | Condition | Mean RT (s) | Accuracy (%) | $N$ | 95% CI Accuracy |
|---|---|---|---|---|---|
| Loose (10s) | Simple | 7.4 | 78.2 | 134 | [74.1, 82.3] |
| | Complex | 9.5 | 76.8 | 134 | [72.6, 81.0] |
| | Difference | +2.1* | -1.4 ns | — | — |
| Moderate (6s) | Simple | 4.9 | 71.5 | 140 | [67.1, 75.9] |
| | Complex | 5.4 | 69.2 | 140 | [64.8, 73.6] |
| | Difference | +0.5* | -2.3 ns | — | — |
| Tight (3s) | Simple | 2.9 | 56.3 | 138 | [51.8, 60.8] |
| | Complex | 2.8 | 50.5 | 138 | [46.0, 55.0] |
| | Difference | -0.1 ns | -5.8* | — | — |

**Note:** RT = response time. Asterisks indicate significance: * $p < 0.05$, ns = not significant.
<!-- /feature -->

<!-- feature: inline-math id:stat-notation -->
Statistical notation used includes $t$-tests with $p < 0.05$ significance threshold,
confidence intervals denoted [lower, upper], and effect sizes expressed in standard
deviation units.
<!-- /feature -->

<!-- feature: dense-prose id:ddm-results -->
The DDM decomposition reveals the mechanisms underlying these patterns. For the
simple (low-load) condition, estimated drift rate averaged 0.42 (post-SDT units),
while in the complex (high-load) condition drift rate declined to 0.34 (paired
$t$-test: $t_{411} = 7.2$, $p < 0.001$). This 19% reduction in drift rate represents
slower evidence accumulation under load. Boundary separation (caution) increased
from 1.92 in the simple condition to 2.04 in the complex condition ($t_{411} = 4.1$,
$p < 0.001$), indicating that individuals adopted more cautious decision policies
(requiring more accumulated evidence before committing to a choice) under load.
Non-decision time was unaffected by load (mean 0.35s, $\Delta = 0.01$s, $t < 1$),
suggesting encoding/response preparation is not load-sensitive. Starting point was
similarly invariant (mean 0.51, $\Delta = 0.00$, $t < 1$), indicating no bias
toward either response.

The time pressure effect is striking: as deadline shortens from 10s to 3s, estimated
boundary separation decreases dramatically (from 2.12 to 1.44), consistent with
individuals lowering their caution threshold to meet deadline constraints. Drift
rate also declines modestly across time pressure conditions (0.42 → 0.35 → 0.28),
but the primary adjustment is boundary separation reduction. This raises the
question: under tight deadlines with high load, can individuals simultaneously
reduce boundary separation to meet deadlines while increasing it to compensate
for load? The data suggest they cannot: tight deadline + load condition shows
boundary separation of 1.41 (barely different from tight deadline alone at 1.44),
indicating that deadline constraint dominates the load-compensation response.
<!-- /feature -->

<!-- feature: heading-h2 id:discussion -->
## Discussion
<!-- /feature -->

<!-- feature: dense-prose id:discussion-body -->
These results clarify the relationship between cognitive load, time pressure, and
decision quality. When time permits, individuals compensate for cognitive load by
investing additional deliberation time, maintaining accuracy (adaptive response).
However, this compensation is costly—responses are slower—and fails entirely under
binding time constraints. The DDM estimates suggest that compensation operates through
caution adjustment: under load (but ample time), individuals raise their decision
threshold, requiring more evidence before committing. Under tight deadlines, this
compensation mechanism fails because lowering the threshold to meet the deadline
constraint precludes raising it to compensate for load.

These findings have implications for the design of decision environments. In
settings where time is abundant (e.g., medical diagnosis, strategic planning),
cognitive load should have minimal impact on decision quality, provided individuals
are appropriately incentivized to invest effort. In settings with tight time
constraints (e.g., emergency rooms, time-limited trading), cognitive load poses
genuine risk to decision quality. Interventions might include: (1) decision-support
systems that reduce information processing demands, (2) time allocations designed
to accommodate deliberation needs, or (3) simplified choice architectures that
require less cognitive investment.
<!-- /feature -->

<!-- feature: heading-h2 id:conclusion -->
## Conclusion
<!-- /feature -->

<!-- feature: dense-prose id:conclusion-body -->
Cognitive load affects decision-making through multiple mechanisms: slower
evidence accumulation and adoption of more conservative decision policies. These
adjustments allow individuals to maintain decision quality under moderate load
when time permits, but break down under time pressure. Understanding these limits
is essential for designing decision environments that support human judgment.
<!-- /feature -->

<!-- feature: heading-h2 id:references -->
## References
<!-- /feature -->

<!-- feature: dense-prose id:refs -->
Haart, S., & Strack, F. (2012). Cognitive control and task switching. *Psychological
Bulletin*, 131(1), 73–95.

Kahneman, D. (2011). *Thinking, fast and slow*. Farrar, Straus and Giroux.

Ratcliff, R., & McKoon, G. (2008). The diffusion decision model: Theory, psychology,
and neuroscience. *Psychological Review*, 115(4), 873–921.

Wiecki, T. V., Sofer, I., & Frank, M. J. (2013). HDDM: Hierarchical Bayesian
estimation of the Drift-Diffusion Model in Python. *Frontiers in Neuroinformatics*,
7, 14.
<!-- /feature -->
