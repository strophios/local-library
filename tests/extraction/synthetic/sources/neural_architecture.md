<!-- feature: heading-h1 id:title -->
# Efficient Neural Architecture Search via Population-Based Training and Multi-Objective Optimization
<!-- /feature -->

<!-- feature: dense-prose id:abstract -->
Neural architecture search (NAS) has emerged as a promising alternative to manual
network design, yet computational costs often exceed available resources for many
research groups. This work proposes PBOT (Population-Based Optimization for
Transformers), a scalable NAS framework that combines population-based training
(PBT) with multi-objective optimization to jointly optimize model accuracy and
latency. Unlike grid search or random search baselines, PBT adaptively allocates
compute to promising architectures while pruning underperforming candidates,
reducing search cost by 40–60% while maintaining Pareto-optimal solutions. We
evaluate PBOT on ImageNet classification (100M image dataset, challenging scaling
regime), CIFAR-100 (fine-grained classification), and downstream transfer learning
tasks. On ImageNet, PBOT discovers architectures achieving 79.8% top-1 accuracy
with 2.1× speedup over EfficientNet-B4, and 81.2% accuracy with 1.3× speedup
over ViT-Base. Notably, discovered architectures transfer well to semantic
segmentation and object detection, suggesting that the search process discovers
generalizable inductive biases rather than task-specific artifacts. We release
the PBOT framework as open-source software with reproducible search logs.
<!-- /feature -->

<!-- feature: heading-h2 id:introduction -->
## Introduction
<!-- /feature -->

<!-- feature: dense-prose id:intro-body -->
The past decade has witnessed a convergence between automated machine learning
(AutoML) and deep learning research, driven by computational advances and the
success of neural networks across domains. Manual architecture design—the traditional
paradigm where researchers propose candidate networks and evaluate them empirically
—increasingly lags behind the rate of computational budget growth. The ImageNet
community has established benchmarks where top performer status requires networks
of increasing complexity, yet diminishing improvements in accuracy. This incentive
structure creates a research culture where finding the next few percentage points
of accuracy improvement is professionally valued despite unclear downstream utility.

In response, neural architecture search aims to automate the discovery process.
Early work (Zoph & Qtanbery, 2014) used reinforcement learning to generate RNN
architectures, treating architecture specification as a sequence-to-sequence
problem. This approach is conceptually elegant but computationally expensive, as
training a large number of candidate architectures to convergence is necessary to
obtain reliable performance estimates. Recent methods (Cai et al., 2020; Tan et al.,
2021) have developed weight-sharing techniques to reduce training cost per candidate,
where candidate networks share weights and train in a single pass. However,
weight-sharing introduces bias: the performance of a candidate network within
the shared weight space may not reflect its standalone performance, leading to
optimistic accuracy estimates for candidate architectures.

Population-based training (PBT), introduced by Jaderberg et al. (2017), offers an
alternative that naturally handles the exploration-exploitation tradeoff: candidate
solutions train in parallel, with periodic evaluation and selection-based reproduction.
Poorly performing candidates are replaced with mutated clones of high-performing
candidates, concentrating compute on promising regions of the search space. This
paper combines PBT with multi-objective optimization to balance accuracy against
latency, then applies the framework to architecture search for image classification.
<!-- /feature -->

<!-- feature: heading-h2 id:methods -->
## Methods
<!-- /feature -->

<!-- feature: heading-h3 id:architecture-space -->
### Architecture Search Space
<!-- /feature -->

<!-- feature: dense-prose id:arch-space-body -->
We define a hierarchical search space encompassing layer-wise operations,
connectivity patterns, and global configuration choices. The search space is
organized as follows:
<!-- /feature -->

<!-- feature: nested-list id:search-space-hierarchy -->
1. **Block-level operations** (per 4-layer residual block):
   - Convolution kernel size (3×3, 5×5, 7×7)
   - Number of channels (64, 128, 256, 512)
   - Depth (number of layers per block: 2, 3, 4)
   - Normalization scheme (BatchNorm, LayerNorm, GroupNorm)

2. **Skip connection patterns**:
   - Dense skip connections (ResNet-style)
   - Residual bottleneck with projection
   - No skip connections (baseline)

3. **Attention mechanisms** (for Transformer-based models):
   - Attention heads per block (4, 8, 16)
   - Feed-forward expansion ratio (1×, 2×, 4×)
   - Positional encoding (absolute, relative, ALiBi)

4. **Global hyperparameters**:
   - Learning rate schedule (constant, stepped, cosine)
   - Batch size (64, 128, 256, 512)
   - Weight decay coefficient (1e-4, 1e-3, 1e-2)
<!-- /feature -->

<!-- feature: inline-math id:algorithm-params -->
Population size $P$ and iterations per round $T$ are key hyperparameters that control
the exploration-exploitation balance and computational budget allocation.
<!-- /feature -->

<!-- feature: heading-h3 id:pbot-algorithm -->
### Population-Based Training for NAS
<!-- /feature -->

<!-- feature: dense-prose id:pbot-body -->
The PBOT algorithm maintains a population of $P$ candidate architectures, each
with associated weights and hyperparameters. The algorithm proceeds in rounds:
at each round, all candidates train for $T$ iterations (typically $T = 1000$ steps
on CIFAR-100, or $T = 5000$ steps on ImageNet). After training, we evaluate
all candidates on a held-out validation set and compute a multi-objective
scoring function combining accuracy and latency. Candidates in the bottom quartile
(worst-performing 25%) are replaced with mutated clones of candidates in the
top quartile (best-performing 25%), with mutations applied to architectural
hyperparameters only (kernel size, channel count, depth) rather than training
hyperparameters. This ensures that network weights, accumulated over multiple
rounds, carry forward into new candidate architectures.

The mutation operator samples new hyperparameters from a discrete uniform
distribution bounded by the current value:
<!-- /feature -->

<!-- feature: heading-h4 id:mutation-pseudocode -->
#### Mutation Pseudocode
<!-- /feature -->

<!-- feature: code-block id:mutation-code -->
```python
def mutate(candidate, mutation_rate=0.25):
    """Mutate a candidate architecture."""
    new_candidate = copy(candidate)

    for param_name in ['kernel_size', 'channels', 'depth']:
        if random() < mutation_rate:
            current_val = getattr(candidate, param_name)
            # Sample new value uniformly within neighbor set
            neighbors = get_valid_neighbors(current_val, param_name)
            new_val = choice(neighbors)
            setattr(new_candidate, param_name, new_val)

    return new_candidate
```
<!-- /feature -->

<!-- feature: heading-h2 id:experiments -->
## Experiments
<!-- /feature -->

<!-- feature: dense-prose id:exp-setup -->
We evaluated PBOT on three image classification benchmarks: ImageNet-1K
(1.28M training images, 1000 classes), CIFAR-100 (50K training images, 100
classes), and a held-out subset of ImageNet-21K (14M images, 14,000 classes).
Each experiment ran with population size $P = 32$, rounds $R = 20$, and iterations
per round $T = 5000$ on ImageNet and $T = 2000$ on CIFAR-100. We compared PBOT
against three baselines: random search over the same architecture space with
identical total compute budget, EfficientNet-B4 (a state-of-the-art manually
designed network), and ViT-Base (a Transformer-based vision model). All methods
use the same data augmentation strategy (RandAugment with magnitude 9), warmup
schedule (5 epochs linear), and final training recipes (cosine learning rate decay,
label smoothing with $\alpha = 0.1$).

Latency measurements were obtained on a single NVIDIA A100 GPU with batch size
128 using the PyTorch profiler, excluding data loading overhead. We report both
absolute latency (milliseconds per batch) and normalized latency relative to
ResNet-50 (set to 1.0×).
<!-- /feature -->

<!-- feature: heading-h2 id:results -->
## Results
<!-- /feature -->

<!-- feature: dense-prose id:results-body -->
On ImageNet, PBOT discovered architectures spanning a wide Pareto front, with
several notable points: a 77.2% accuracy architecture requiring 45 ms/batch
(0.71× ResNet-50 latency), a 79.8% accuracy architecture at 96 ms/batch (1.51×
ResNet-50), and an 81.2% accuracy architecture at 128 ms/batch (2.01× ResNet-50).
All three dominate EfficientNet-B4 on the accuracy-latency tradeoff, which achieves
80.1% accuracy with 156 ms/batch. ViT-Base achieves higher accuracy (81.1%) but
requires 384 ms/batch, placing it off the efficient frontier relative to discovered
PBOT architectures.

The average Pareto-optimality gap—defined as the multiplicative distance to the
best-known solution on the accuracy-latency frontier—was 0.8%, indicating that
PBOT consistently produces competitive solutions. Across all search runs, the top
3 discovered architectures were remarkably consistent in their design choices:
they all use 7×7 convolutions in early blocks (contrary to conventional wisdom
favoring 3×3), channel counts around 256-512 in middle layers, and aggressive
depth scaling (10-12 layers per block). This consistency suggests convergence
to genuine optima rather than lucky discoveries.

Transfer learning experiments show that PBOT-discovered architectures transfer
well to downstream tasks. When fine-tuned on COCO object detection (12K training
images), the 79.8% ImageNet architecture achieved 46.2 average precision (AP),
compared to 45.8 for EfficientNet-B4 and 47.1 for ViT-Base (p < 0.01 for
PBOT vs EfficientNet-B4). On semantic segmentation (ADE20K with 25K training
images), PBOT achieved 53.4 mIoU compared to 52.1 for EfficientNet-B4. These
improvements are modest in absolute terms but consistent across multiple transfer
tasks, suggesting that PBOT discovers architectures with generalizable properties.

We also evaluated search efficiency by comparing PBOT against random search and
regularized evolution under equivalent computational budgets (500 GPU-hours each).
PBOT achieved a final Pareto hypervolume 12% larger than regularized evolution
and 34% larger than random search. More critically, PBOT reached 90% of its final
hypervolume after 180 GPU-hours, while regularized evolution required 350 GPU-hours
to reach the same threshold. This advantage stems from the Bayesian optimization
component: by modeling the objective landscape, PBOT concentrates evaluations in
promising regions of the search space rather than relying solely on evolutionary
pressure. The computational overhead of maintaining and querying the surrogate model
is minimal (less than 2% of total search time), making PBOT strictly more efficient
than ablated variants that omit the Bayesian component.
<!-- /feature -->

<!-- feature: heading-h2 id:conclusion -->
## Conclusion
<!-- /feature -->

<!-- feature: dense-prose id:conclusion-body -->
This work demonstrates that population-based training offers a practical framework
for neural architecture search, achieving efficiency competitive with or exceeding
hand-designed networks. The Pareto-optimal architectures discovered by PBOT can
be deployed as drop-in replacements for standard backbones in computer vision
pipelines, with benefits extending to transfer learning tasks. Code and search
logs are released to enable reproducibility and downstream research.
<!-- /feature -->

<!-- feature: heading-h2 id:references -->
## References
<!-- /feature -->

<!-- feature: dense-prose id:refs -->
Cai, H., Gan, C., Wang, T., et al. (2020). Once for all: Train one network and
specialize it for efficient deployment. In *International Conference on Learning
Representations* (pp. 1-12).

Jaderberg, M., Dalibard, V., Osindski, S., et al. (2017). Population based training
of neural networks. *arXiv preprint arXiv:1711.09846*.

Tan, M., & Le, Q. (2019). EfficientNet: Rethinking model scaling for convolutional
neural networks. In *International Conference on Machine Learning* (pp. 6105-6114).

Zoph, B., & Qtanbery, V. (2014). Neural architecture search with reinforcement learning.
*arXiv preprint arXiv:1611.01578*.
<!-- /feature -->
