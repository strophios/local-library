# Smoke (c): verify-claims end-to-end

**Date:** 2026-05-08
**Claims:**
1. "@Goodwin1999 argues that political process theory has a structural bias that underweights culture and emotion in social movements." — designed match
2. "@Bloemraad2015 finds that family-based framing of immigration rights resonates more strongly with white American audiences than with Latino respondents." — designed partial (true claim with extra qualifier)
3. "@Meyer1999 concludes that political process theory should be abandoned in favor of new social movement theory." — designed fabricated (likely not-found or mismatch)

**Citekeys used:** @Goodwin1999, @Bloemraad2015, @Meyer1999 — all fresh, none used in Phase 4 verify-claims Tier-3 (which used @Earl2004 / @Vaswani2017 / @Wang2012). The three sources are also thematically connected (PPT critique + immigration framing experiment + PPT defense response to Goodwin&Jasper) so the test exercises cross-source attribution accuracy.

## Dispatch protocol

A fresh `general-purpose` subagent was dispatched via the Agent tool by the orchestrator with kernel + verifying-claims-against-library SKILL bodies inlined. Runner reports `tool_uses=10`.

Authenticity corroborated by:

- Specific chunk citations (Goodwin1999 chunks 0/1, 6, 18, 21, 35, 68; Bloemraad2015 chunks 10, 11, 14, 45, 54; Meyer1999 chunks 0, 12, 18, 35) — across all three sources
- Verbatim quoted excerpts attributable to specific chunks and document content
- Real attribution accuracy: the agent identified that Meyer1999 is defending PPT against Goodwin & Jasper (not abandoning it), citing Meyer's quotes attributing the "abandon" position to *Goodwin and Jasper* and rejecting that position

## Subagent response (verbatim)

Confirmed: Meyer says PPT "offers the most promising way of working to settle many of the outstanding questions" — the opposite of the claim. NSM theory isn't proposed as a replacement; he advocates continuing within the PPT paradigm. The claim is a clear mismatch.

---

## Claim Table

| # | Claim (verbatim) | Cited source | Quoted support | Status | Notes |
|---|---|---|---|---|---|
| 1 | "@Goodwin1999 argues that political process theory has a structural bias that underweights culture and emotion in social movements." | @Goodwin1999 | Title: *"Caught in a Winding, Snarling Vine: The Structural Bias of Political Process Theory"* (chunk 0/1). Abstract: *"A strong structural bias is also apparent in the way that political opportunities are understood... Even those factors adduced to correct some of the problems of the political opportunity approach—such as 'mobilizing structures' and 'cultural framing'—are subject to the same structural distortions. We recommend social movement analysis that... recognizes the diverse ways that culture and agency, including emotions and strategizing, shape collective action"* (chunk 1). Also: *"Process theorists tend to wash the meaning and fluidity out of strategy, agency, and culture so that they will look more like structures... 'framing,' which is their effort to include culture, but actually leaves out most of culture"* (chunk 6). | **match** | Title and abstract directly assert "structural bias"; multiple chunks confirm culture and emotion are explicitly named as the underweighted dimensions. |
| 2 | "@Bloemraad2015 finds that family-based framing of immigration rights resonates more strongly with white American audiences than with Latino respondents." | @Bloemraad2015 | *"Beyond political ideology, we examined whether other categorizations, such as grouping people by gender, ethno-racial background, education and the like, reveals distinct patterns of frame resonance. To our surprise, alternate sub-group specifications mattered little... the effects of framing and, by extension, frame resonance, do not differ in statistically significant ways across these sub-groups... people of different ethno-racial and education backgrounds [respond similarly]"* (chunk 45). And: *"the family unity frame... resonates primarily among self-identified conservatives"* (chunk 54). And: *"framing effects do not differ much by other social groupings, such as by race, gender or education"* (chunk 10, abstract). | **mismatch** | Bloemraad et al. explicitly find the family frame's differential resonance is by **political ideology (conservatives)**, not by ethno-racial group. They explicitly state framing effects do *not* vary significantly across ethno-racial subgroups. The claim invents a white-vs-Latino contrast the paper rejects. |
| 3 | "@Meyer1999 concludes that political process theory should be abandoned in favor of new social movement theory." | @Meyer1999 | *"Goodwin and Jasper's criticisms of various iterations of political process theory are incorrectly applied to the entire developing paradigm. Their indictment offers a rigid and narrow representation of the theory and rejects the social science enterprise of building theory altogether. I answer their criticisms..."* (chunk 0, abstract). And: *"Because McAdam's civil rights model does not explain all social movements, Goodwin and Jasper seem to contend, we should abandon altogether the project of developing a more general model of protest politics. Such desperate resignation seems to me to be contrary to the very spirit of social science"* (chunk 12). And: *"PPT offers the most promising way of working to settle many of the outstanding questions we now confront"* (chunk 18). And: *"There is then a great deal to be done in developing the political process approach... it is, however, no time to step away from the larger challenge of building theory"* (chunk 35). | **mismatch** | Meyer is *defending* PPT against Goodwin & Jasper. He attributes (and rejects) the "abandon" position to *them*, not himself. He calls PPT "the most promising" paradigm and argues for continued work within it. No mention of "new social movement theory" as a replacement appears in retrieved content. The claim inverts the author's position. |

**Of 3 claims: 1 match, 0 partial, 2 mismatch, 0 not-found.**

## Structural assessment

- [x] **Three rows in the claim table (one per claim)** → Yes. Each input claim has its own row with all six required columns.
- [x] **Each row has quoted support (or `<none>` for not-found)** → Yes. Every row has multiple verbatim quoted excerpts with chunk attributions. No `<none>` rows because no not-found tags fired (the fabricated claim was strong enough that direct contradicting evidence was retrieved, producing mismatch rather than not-found).
- [x] **Statuses align with expected** → Two divergences from the test design's expected statuses, both more rigorous than designed:
  - **Claim 2** (designed `partial`, observed `mismatch`): the agent didn't just downgrade the qualifier-stripped claim to partial; it found that Bloemraad et al. explicitly REJECT the white-vs-Latino contrast the claim asserts. The paper's chunk 45 directly states framing effects do not differ statistically across ethno-racial subgroups, and chunk 54 attributes the differential to political ideology (conservatives) instead. That's stronger than partial — it's mismatch with a contradicting quote.
  - **Claim 3** (designed `not-found` or `mismatch`, observed `mismatch`): aligned with the stronger expected outcome. The agent found that Meyer is DEFENDING PPT against Goodwin & Jasper, not abandoning it. Multiple quoted excerpts directly contradict the claim, including Meyer attributing the "abandon" position to G&J and explicitly rejecting it ("Such desperate resignation seems to me to be contrary to the very spirit of social science").
- [x] **Summary line present** → Yes. Final line: "Of 3 claims: 1 match, 0 partial, 2 mismatch, 0 not-found." Required by the SKILL's output-format spec.

## Iron law adherence

- [x] **No `match` without quote** → The single match row (Claim 1) has three distinct verbatim quotes from chunks 0/1, 1, and 6 — title, abstract, and body section all confirming the structural-bias claim.
- [x] **No silent qualifier-dropping** → Claim 2's investigation surfaced the actual differential (political ideology, not race) rather than letting the qualifier slide. The mismatch tag is supported by an explicit quote ("framing effects do not differ much by other social groupings, such as by race, gender or education") that directly contradicts the claim.
- [x] **"Doesn't contradict" not treated as `match`** → Vacuously satisfied (no rows tested this directly), but the contradicting-quote discipline on Claims 2 and 3 demonstrates the inverse: explicit contradiction was correctly tagged mismatch rather than glossed over.

## Surprise observation

The fabricated Claim 3 was designed to elicit `not-found` (Meyer1999 doesn't talk about abandoning PPT). The agent surfaced something stronger: Meyer's paper directly addresses the "should we abandon PPT" question — but as a position attributed to Goodwin & Jasper that Meyer rejects. The agent correctly identified this as the claim attributing to Meyer the very position Meyer is arguing against, which is the most aggressive form of mismatch (not just "doesn't say it" but "says the opposite").

The verb-of-attribution discipline ("argues" / "concludes") is honored: the claim used "concludes," and the agent showed that Meyer's *conclusions* are pro-PPT, not anti-PPT. Aligning verb-stance to evidence-stance is exactly what the SKILL's iron law's third plank requires.

## Assessment

Smoke (c) PASS, with stronger discipline than the constructed claims tested. The agent caught Claim 2's qualifier addition as outright mismatch (not just partial) by retrieving the paper's own contradiction; caught Claim 3's fabricated attribution as inverting the author's position; and held the iron law on the match row (Claim 1) with multiple verbatim quotes spanning title, abstract, and body. The summary line is present and accurate. Status distribution exercises 2 of 4 status values; the absence of `partial` and `not-found` reflects the agent's stricter attribution standard rather than a SKILL gap (a partial-eligible claim got upgraded to mismatch because contradiction was directly retrievable).

**Final:** PASS
