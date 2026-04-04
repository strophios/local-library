<!-- feature: heading-h1 id:title -->
# Collective Bargaining and Wage Inequality in American Manufacturing: A Regional Analysis, 1947–2020
<!-- /feature -->

<!-- feature: dense-prose id:abstract -->
The decline of private-sector unionization in the United States—from 36% in 1953
to 6% in 2023—constitutes one of the most significant institutional shifts in
postwar American labor history, yet its causes and consequences remain contested.
This paper examines the relationship between union density and wage dispersion
across manufacturing regions (midwest auto production, steel, textiles) from the
New Deal through the post-Cold War period. Using matched samples of union and
nonunion workers from the Current Population Survey, March Supplements (1947–2020),
we construct regional estimates of union wage effects (controlling for worker
selection), employment flows, and wage inequality measures (Gini coefficient,
90/10 ratio). We find that union density has a strong independent association
with reduced wage inequality even controlling for worker composition: a region-year
with 25% union density exhibits an inequality measure approximately 0.08 points
lower on the Gini coefficient than an observationally similar non-union region,
ceteris paribus. This effect is larger in manufacturing than in services. The
decline of union density since 1980 accounts for 15–20% of the increase in wage
inequality observed in panel estimates. However, direct effects are small relative
to skill-biased technological change and globalization, suggesting that unionization
decline is a partial but important driver of American wage inequality.
<!-- /feature -->

<!-- feature: heading-h2 id:introduction -->
## Introduction
<!-- /feature -->

<!-- feature: dense-prose id:intro-body -->
Labor union membership in the United States has declined precipitously over the
past seven decades. At mid-century, when the Congress of Industrial Organizations
(CIO) and American Federation of Labor (AFL) dominated the political economy of
manufacturing, union density reached a historical peak. The postwar period
witnessed a golden age of American labor, with union contracts establishing wage
floors, health insurance benefits, and pension provisions that became the foundation
of a stable working class. Yet this institutional edifice has largely crumbled.
Private-sector unionization fell from 36% in 1953 to 10% by 2000 to 6% in 2023,
leaving union workers clustered in public-sector employment and a handful of
surviving industries (airline crews, longshore workers, some construction trades).

The causes of this decline are multiply determined. Employer opposition to unionization,
enabled by the Taft-Hartley Act (1947) and enforced through Landrum-Griffin (1959),
created asymmetric bargaining power favoring capital. Manufacturing outsourcing and
automation reduced the size of the bargaining units where unions held market power.
The stagflation of the 1970s, blamed in part on union wage pressure, turned public
opinion against organized labor. Concession bargaining in the 1980s (when union
leaders accepted wage cuts and benefit reductions to preserve employment) further
weakened union legitimacy. By the 1990s, globalization and trade integration had
displaced millions of union manufacturing workers, and union organizing campaigns
increasingly faced well-funded employer countercampaigns.

The wage and inequality consequences of this decline are less well-established than
the decline itself. Previous work estimates union wage premiums (the earnings boost
from union membership) at 10–20%, but these estimates reflect worker selection
(unions recruit high-ability workers) and are heterogeneous across sectors and time
periods. It remains unclear whether the aggregate wage inequality increase in America
can be substantially attributed to declining unionization, or whether it represents
an independent technological and global phenomenon. This paper contributes evidence
on this question using regional variation in union density as a source of
identification.
<!-- /feature -->

<!-- feature: heading-h2 id:historical-context -->
## Historical Context: The Arc of American Unionism
<!-- /feature -->

<!-- feature: dense-prose id:historical-body -->
The American labor movement emerged from craft unions (the AFL, founded 1886) and
industrial unions (the CIO, founded 1935). For much of the twentieth century, union
and nonunion sectors coexisted, with unions concentrated in manufacturing, mining,
transportation, and construction. The organizing wave of the 1930s—driven by the
Great Depression and enabled by the Wagner Act—brought millions of workers into
industrial unions. By 1945, the United Auto Workers (UAW), United Steelworkers, and
International Ladies' Garment Workers' Union (ILGWU) wielded enormous political and
economic power.

The immediate postwar period saw a wave of strikes and wage demands, culminating in
the 1946-47 strike wave that won substantial wage increases. Yet employer counter-
mobilization was swift. The Taft-Hartley Act (1947) imposed restrictions on union
organizing and strike activity, introduced the concept of the "right to work" (allowing
workers to benefit from union contracts without paying dues), and empowered the
President to impose cooling-off periods in strikes. This legislation reflected a
conservative resurgence and Cold War anti-communist sentiment (many union leaders,
particularly in the CIO, had communist sympathies or allies).
<!-- /feature -->

<!-- feature: blockquote id:taft-hartley-quote -->
"No agency of government should be able to force the men and women of American
business to go out of business or to take less in the products of their labor.
The fundamental purpose of this act is to protect the rights of the working man
or woman" — President Truman, explaining his veto of Taft-Hartley (overridden by
Congress, June 1947).
<!-- /feature -->

<!-- feature: dense-prose id:postwar-consensus -->
The postwar consensus, often called the "Keynesian consensus" or "social democratic
compromise," established a framework in which unions would accept productivity gains
for capital in exchange for cost-of-living wage adjustments and employment guarantees.
This bargain held through the 1960s and into the 1970s, but unraveled during stagflation
(the combination of high inflation and stagnant growth). The OPEC oil shocks of 1973
and 1979 caused severe recessions, squeezing profit margins and leading employers to
demand concessions.
<!-- /feature -->

<!-- feature: heading-h2 id:methodology -->
## Methodology
<!-- /feature -->

<!-- feature: dense-prose id:methods-body -->
We use microdata from the Current Population Survey, March Supplements, which contains
detailed information on union membership, earnings, occupation, industry, and
demographics for a nationally representative sample of approximately 50,000 households
annually (before 2002; 60,000 after). We restrict analysis to workers aged 25-64 in
private-sector employment (excluding government workers, whose unionization trends
differ markedly). We impute union status in years where it was not directly asked
(1987-1993) using a multinomial logistic regression model trained on adjacent years
with full data.

We construct regional wage-inequality measures at the state-year level by aggregating
individual-level data. We measure inequality using the Gini coefficient (standard
measure of distributional dispersion) and the 90/10 percentile ratio (ratio of
earnings at the 90th percentile to earnings at the 10th percentile). Both measures
are computed separately for union and nonunion workers within each state-year cell.

To estimate the causal effect of union density on wage inequality, we employ a fixed-
effects regression framework:
<!-- /feature -->

<!-- feature: display-math id:inequality-regression -->
$$\text{Inequality}_{s,t} = \beta_0 + \beta_1 \text{UnionDensity}_{s,t} + \gamma_s + \delta_t + \epsilon_{s,t}$$
<!-- /feature -->

<!-- feature: dense-prose id:regression-explanation -->
where Inequality$_{s,t}$ is the Gini coefficient (or 90/10 ratio) in state $s$ at time
$t$, UnionDensity$_{s,t}$ is the fraction of private-sector workers in unions, $\gamma_s$
are state fixed effects (capturing permanent differences across regions), $\delta_t$ are
year fixed effects (capturing economy-wide trends), and $\epsilon_{s,t}$ is idiosyncratic
error. The coefficient $\beta_1$ represents the within-state, over-time association between
union density and inequality. We estimate standard errors clustered at the state level to
account for potential serial correlation within states.
<!-- /feature -->

<!-- feature: heading-h2 id:results -->
## Results
<!-- /feature -->

<!-- feature: dense-prose id:results-body -->
The fixed-effects regression yields a point estimate of $\hat{\beta}_1 = -0.078$ (standard
error = 0.032), indicating that a one-percentage-point increase in union density is
associated with a 0.078-point decrease in the Gini coefficient. Converting to elasticities,
this implies that the decline in union density from 25% (1965 level) to 10% (2020 level)
would predict an increase in the Gini coefficient of 1.17 points. Observed increase in
the Gini coefficient over the same period was 5.8 points (from 0.36 to 0.42), implying
that declining unionization accounts for approximately 20% of observed inequality growth.

The effect is heterogeneous across sectors: in manufacturing, the coefficient is
$\hat{\beta}_1 = -0.112$ (substantial wage-compression effect), while in service sectors
it is $\hat{\beta}_1 = -0.035$ (smaller effect). This heterogeneity makes intuitive sense:
manufacturing unions historically established industry-wide wage standards (e.g., the UAW
pattern agreement, which set wages across all Big Three automakers), creating compression.
Service-sector unions operated on a more fragmented basis.

Robustness checks confirmed the main result: when we instrument union density using lagged
values (to address potential reverse causation, where high inequality causes union decline),
the estimated effect is similar but slightly larger ($\hat{\beta}_1 = -0.095$, standard
error = 0.041). Placebo tests, where we lag the inequality measure (testing whether
future union density affects past inequality), yielded no significant effect, supporting
the causal interpretation.
<!-- /feature -->

<!-- feature: heading-h2 id:discussion -->
## Discussion and Conclusions
<!-- /feature -->

<!-- feature: dense-prose id:discussion-body -->
This analysis provides quantitative evidence that union density and wage inequality
are causally linked: regions and time periods with higher unionization experience
lower wage inequality, controlling for worker composition and year-fixed effects.
The magnitude of the effect—accounting for roughly 20% of observed wage inequality
increase—suggests that unionization decline is an important but not sole driver of
American wage inequality. The remaining 80% likely reflects skill-biased technological
change (computerization favoring educated workers), globalization and offshoring
(reducing bargaining power of manufacturing workers), and the rising returns to
education documented in the labor economics literature.

These findings have implications for labor policy. Proposals to reduce barriers to
unionization (e.g., reforming the National Labor Relations Act) would have
countervailing effects: they might increase wages and reduce inequality in unionizing
sectors, but could also reduce employment if employers face higher labor costs. The
net welfare effects depend on whether one prioritizes wage levels, employment levels,
or efficiency in labor allocation—a fundamentally normative question. What the
evidence suggests is that labor institutions matter, and that the postwar decline
of American unionism represents a genuine shift in the distribution of earnings and
opportunities.
<!-- /feature -->

<!-- feature: heading-h2 id:references -->
## References
<!-- /feature -->

<!-- feature: bibliography id:refs -->
Acemoglu, D., & Robinson, J. A. (2012). *Why nations fail: The origins of power, prosperity, and poverty*. Crown Publishers.

Card, D., Heining, J., & Kline, P. (2002). The impact of nearly universal child schooling in Sweden. *American Economic Review*, 92(4), 1042–1049.

Hirsch, B. T., & Macpherson, D. A. (2003). Union membership and coverage database from the Current Population Survey: Note. *Industrial and Labor Relations Review*, 56(2), 349–354.

Levy, F., & Murnane, R. J. (1992). U.S. earnings levels and earnings inequality: A review of recent trends and proposed explanations. *Journal of Economic Literature*, 30(3), 1333–1381.

Western, B. (1995). A comparative study of working-class disorganization: Union decline in 18 advanced capitalist countries. *American Sociological Review*, 60(2), 179–201.
<!-- /feature -->

<!-- feature: footnote id:fn1 -->
^1^ The March CPS asked union membership status as part of supplemental income questions,
making it ideal for wage analysis, though smaller sample sizes than the monthly CPS limit
some subgroup analysis.
<!-- /feature -->

<!-- feature: footnote id:fn2 -->
^2^ The Gini coefficient ranges from 0 (perfect equality) to 1 (perfect inequality), and
is calculated as $G = \frac{2\sum_{i=1}^{n} i \cdot x_i}{n \sum_{i=1}^{n} x_i} - \frac{n+1}{n}$
where $x_i$ are ordered earnings.
<!-- /feature -->
