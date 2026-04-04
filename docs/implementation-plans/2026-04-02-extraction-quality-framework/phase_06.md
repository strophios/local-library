## Phase 6: Source Document Authoring

**Goal:** Complete the synthetic document set with realistic composite papers and establish initial baseline.

**Nature of this phase:** Primarily content creation, not code. The infrastructure from Phases 1-5 is exercised end-to-end. The "test" is that the smoke test passes and a baseline is established.

---

<!-- START_TASK_1 -->
### Task 1: Design feature coverage matrix

**Files:**
- Create: `tests/extraction/synthetic/sources/COVERAGE.md`

**Step 1: Create coverage matrix**

Document the planned feature coverage across all source documents:

| Feature Type | Doc 1: Urban Transit | Doc 2: Climate Stats | Doc 3: NAS Survey | Doc 4: Labor History | Doc 5: Empirical Study | Doc 6: Engineering |
|---|---|---|---|---|---|---|
| heading-h1 | x | x | x | x | x | x |
| heading-h2 | x | x | x | x | x | x |
| heading-h3 | | | x | | x | |
| heading-h4 | | | x | | | |
| table-simple | x | | | | | |
| table-complex | | | | | x | |
| footnote | x | | | x | | |
| bibliography | x | | | x | | |
| display-math | | x | | | x | |
| inline-math | | x | | | x | |
| blockquote | | | | x | | |
| code-block | | | x | | | x |
| nested-list | | | x | | | |
| dense-prose | x | x | x | x | x | x |

Each document exercises 5-8 features in context. Every feature type is covered by at least 2 documents.

**Step 2: Commit**

```bash
git add tests/extraction/synthetic/sources/COVERAGE.md
git commit -m "docs: add feature coverage matrix for synthetic extraction tests"
```

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Author synthetic source documents

**Files:**
- Create: `tests/extraction/synthetic/sources/urban_transit.md`
- Create: `tests/extraction/synthetic/sources/climate_modeling.md`
- Create: `tests/extraction/synthetic/sources/neural_architecture.md`
- Create: `tests/extraction/synthetic/sources/labor_history.md`
- Create: `tests/extraction/synthetic/sources/empirical_study.md`
- Create: `tests/extraction/synthetic/sources/engineering_report.md`

Each document should:
- Read like a real academic paper (plausible topic, realistic prose, proper structure)
- Be 1500-3000 words (enough for 2-4 PDF pages)
- Exercise the features assigned in the coverage matrix
- Annotate all feature regions with `<!-- feature: TYPE id:NAME -->` / `<!-- /feature -->` tags
- Have annotations as a measurement overlay, not as the organizing principle

**Authoring guidance for the implementer:**

- **Don't** write placeholder text ("Lorem ipsum" or "This section tests headings"). Write realistic academic prose.
- **Don't** isolate features. A heading should introduce real content, not sit alone.
- **Do** make documents internally coherent — the prose should make sense as a paper.
- **Do** vary complexity within feature types (e.g., one simple 3-column table, one complex table with merged headers).
- **Do** include enough prose between features to stress the reflow and alignment pipelines.

Example structure for one document (urban_transit.md):

```markdown
<!-- feature: heading-h1 id:title -->
# Comparative Analysis of Urban Transit Systems in the Eastern Seaboard
<!-- /feature -->

<!-- feature: dense-prose id:abstract -->
Urban mass transit systems in the eastern United States have undergone
significant transformation over the past three decades. This analysis
examines ridership patterns, infrastructure investment, and service
reliability across five metropolitan transit authorities...
<!-- /feature -->

<!-- feature: heading-h2 id:methodology -->
## Methodology
<!-- /feature -->

<!-- feature: dense-prose id:methods-body -->
We collected ridership data from the National Transit Database (NTD)
spanning fiscal years 2010 through 2023. Our dataset includes...
<!-- /feature -->

<!-- feature: table-simple id:ridership-data -->
| System | 2015 Ridership (M) | 2023 Ridership (M) | Change |
|--------|--------------------|--------------------|--------|
| WMATA  | 217.2              | 148.3              | -31.7% |
| SEPTA  | 113.8              | 95.4               | -16.2% |
| MBTA   | 178.1              | 142.6              | -19.9% |
<!-- /feature -->

...continues with footnotes, bibliography, more prose...
```

**Step 1: Write all 6 source documents**

Write each document following the coverage matrix. Prioritize realistic content over perfect coverage — a document that reads naturally with 5 well-placed features is better than one with 8 awkwardly inserted features.

**Step 2: Verify annotations parse correctly**

Run:
```bash
uv run python -c "
from pathlib import Path
from tests.extraction.synthetic.annotations import parse_annotations

for md in sorted(Path('tests/extraction/synthetic/sources').glob('*.md')):
    if md.name == 'COVERAGE.md':
        continue
    regions = parse_annotations(md.read_text())
    types = [r.feature_type for r in regions]
    print(f'{md.stem}: {len(regions)} regions — {types}')
"
```

Expected: Each document shows its annotated regions with correct feature types.

**Step 3: Generate fixture PDFs and verify**

Run:
```bash
uv run python -c "
from pathlib import Path
from tests.extraction.synthetic.generate import generate_all_tiers

sources = Path('tests/extraction/synthetic/sources')
fixtures = Path('tests/extraction/synthetic/fixtures')

for md in sorted(sources.glob('*.md')):
    if md.name == 'COVERAGE.md':
        continue
    result = generate_all_tiers(md, fixtures / md.stem)
    print(f'{md.stem}: {len(result)} tiers generated')
"
```

Expected: Each document generates 4 tier PDFs.

**Step 4: Commit source documents**

```bash
git add tests/extraction/synthetic/sources/
git commit -m "feat: add 6 annotated synthetic source documents for extraction quality"
```

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Run full benchmark and establish baseline

**Step 1: Run the smoke test end-to-end**

Run: `uv run pytest tests/extraction/synthetic/ -v --run-extraction-quality`
Expected: All smoke tests pass

**Step 2: Run the full benchmark and write results**

Run:
```bash
uv run python -c "
from pathlib import Path
from tests.extraction.synthetic.runner import ExtractionQualityRunner
from tests.extraction.synthetic.reporting import print_summary

runner = ExtractionQualityRunner(
    sources_dir=Path('tests/extraction/synthetic/sources'),
    fixtures_dir=Path('tests/extraction/synthetic/fixtures'),
    results_dir=Path('tests/extraction/synthetic/results'),
)
report = runner.run()
output = runner.write_results(report)
print_summary(report.to_dict())
print(f'\nResults written to {output}')
"
```

Expected: Rich-formatted summary table for each document x tier.

**Step 3: Promote to baseline**

Copy the results file to `baseline.json`:

```bash
cp tests/extraction/synthetic/results/<latest>.json tests/extraction/synthetic/results/baseline.json
```

**Step 4: Commit baseline**

```bash
git add tests/extraction/synthetic/results/baseline.json
git commit -m "feat: establish initial extraction quality baseline"
```

<!-- END_TASK_3 -->
