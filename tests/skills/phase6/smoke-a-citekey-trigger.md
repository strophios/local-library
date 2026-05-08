# Smoke (a): citekey trigger via orientation

**Date:** 2026-05-08
**Citekey:** @Goodwin1999 (Goodwin, Jasper & Khattra 1999, "Caught in a Winding, Snarling Vine: The Structural Bias of Political Process Theory")

**Citekey selection rationale:** Fresh — not used in any Phase 2-4 GREEN/Tier-3 test. The conversational prompt ("got a bit lost in section 3") is deliberately non-directive and contains an ambiguity (the document has named sections, not numbered ones), which gives the SKILL room to demonstrate authentic engagement.

## Dispatch protocol

A fresh `general-purpose` subagent was dispatched via the Agent tool by the orchestrator. The dispatched subagent's prompt followed plan lines 41-51: an instruction to apply the orientation skills (using-local-library-mcp + handling-extraction-quality) as part of its system prompt, both SKILL bodies inlined, and the verbatim conversational scenario as the Task line.

Runner reports `tool_uses=10` for this dispatch — high tool use indicating substantial retrieval activity. Authenticity corroborated by:

- Specific line-number citations from the extracted markdown (lines 245-256, 257-263, 264-277, 278-283 of the document)
- Verbatim quoted excerpts (e.g., "an ubiquitous and constitutive dimension of all social relations, structures, networks, and practices"; "the conscious, strategic efforts by groups of people to fashion shared understandings of the world and of themselves that legitimate and motivate collective action")
- Document-internal references the agent could only access via real retrieval (the MMZ 1996 framing definition; the Steinberg 1995 discursive-repertoires citation; the Ringmar 1996 identity-prior-to-interest argument; the MLK passage; the Scheff quote on nationalist passion)
- The agent identified that the document doesn't have numbered sections and proposed "Framing and Culture" as the most likely interpretation of "section 3" — only possible if the agent actually looked at the document's structure

## Scenario (verbatim)

> I was reading @Goodwin1999 last night and got a bit lost in section 3. Can you help me make sense of what the author is doing there?

## Subagent response (verbatim)

Good. I have all three candidate sections in view. The user's "section 3" is most likely **Framing and Culture**, since that's the third *named* section after the introduction. I'll lead with that and offer to switch if they meant something else.

A note on extraction quality: the body text reads cleanly (no math/formula problems here, just prose), but the tables (lines 169-178, 249-253, 286-291) are visibly broken — Marker doesn't recover the column structure. If we end up needing to discuss Table I, II, or III in detail, I'd want to fall back to the PDF. Footnote markers like `1'`, `12`, `'3` are also collapsed sub/superscripts, but that doesn't affect comprehension of the argument.

I have what I need. Let me write the response.

---

Picking up on @Goodwin1999 — Goodwin, Jasper, and Khattra's "Caught in a Winding, Snarling Vine" (1999). The article isn't numbered into §1/§2/§3; it has four named sections after the intro:

1. The Political Opportunity Thesis (with sub-headers "What Is a Political Opportunity?" and "How Do Opportunities Work?")
2. The Political Process Model
3. **Framing and Culture**
4. Some Modest Proposals

So I'll read your "section 3" as **Framing and Culture** (pp. 39ff in the journal pagination, lines 243-294 of the extracted markdown). Tell me if you actually meant "The Political Process Model" or "How Do Opportunities Work?" and I'll redirect.

## What the section is doing

This section is the third move in a parallel critique. The authors have already argued that "political opportunities" and "mobilizing structures" are conceptually muddled and structurally biased. **Framing and culture is where political process theory (PPT) is *supposed* to handle the non-structural — meaning, emotion, agency.** Goodwin, Jasper, and Khattra's claim is that PPT botches this in the opposite direction from the previous two concepts: where "political opportunity" and "mobilizing structures" are defined too *broadly* (becoming tautological/trivial), "framing" is defined too *narrowly* — narrowly enough that it fails to capture most of what culture actually does in social movements.

The section has four moves; tracking them is the key to not getting lost.

### Move 1: The two-sided problem (p. 39 / lines 245-256)

Framing has the same breadth-versus-narrowness dilemma as the other PPT concepts, but the authors flip it:

> "In one sense, the notion of cultural framings — like political opportunities and mobilizing structures — is overly broad, subsuming a variety of factors that are potentially contradictory in their effects... In another sense, however, political process theorists have defined cultural framings so narrowly that the concept is inadequate for grasping the many ways in which culture shapes social movements."

Hold onto this dual structure — the rest of the section is mostly about the *narrowness* problem, but they want to flag the breadth issue too (e.g., framing gets used to bundle together collective identities, grievances, goals, repertoires, and sense of efficacy, which don't behave the same way).

### Move 2: Reification of culture (lines 257-263)

The authors accuse PPT of "misplaced concreteness" — treating culture as a *delimited sphere of action* (a thing movements *do*, in self-conscious framing work) rather than as **"an ubiquitous and constitutive dimension of all social relations, structures, networks, and practices"** (line 258).

The structural payoff of this critique: if culture is a constitutive dimension, then "political opportunities" and "mobilizing structures" don't sit *outside* culture with framing *mediating* between them. They are themselves cultural. This is why the authors cite Williams's critique of the "mediation" model. PPT's whole tripartite architecture (opportunities → mobilizing structures → framing → action) presupposes that the first two slots are non-cultural and the third slot does the cultural work. The authors are saying that picture is wrong at the foundation.

### Move 3: McAdam, McCarthy & Zald's narrow definition of framing, and what it leaves out (lines 264-277)

This is the analytical core. MMZ (1996) define framing as:

> "the conscious, strategic efforts by groups of people to fashion shared understandings of the world and of themselves that legitimate and motivate collective action" (line 266, emphasis in original)

Goodwin, Jasper & Khattra grant that this is fine as far as it goes — strategic framing efforts matter — but argue this definition strips out almost everything else culture does. They list what it misses (line 266):

> "traditions, 'common sense,' material artifacts, idioms, rituals, news routines, know-how, identities, discourse, and speech genres — also constrain and enable collective action in ways that are not always or even usually intentional or instrumental."

Two specific arguments support this:

- **Discursive repertoires shape framing itself** (Steinberg 1995): "They bound the set of meanings through which challengers can articulate claims." Framing isn't a free strategic choice; the available frames are themselves culturally constrained.
- **Identity is logically prior to interest** (Ringmar 1996): "a group or individual must know who they are before they can know what interests they have." This cuts hard against rational-strategic models.

The vivid example is the MLK passage (line 276). McAdam reads MLK's use of Christian themes as a strategic frame deployment. Goodwin et al. reply: that's like saying MLK made a strategic choice to speak English. He was a Baptist minister with a theology doctorate; the Christian register wasn't a tool he picked up, it was the cultural medium he and his audience inhabited. The reduction of culture to strategy makes MLK's actual religious commitments invisible.

### Move 4: The emotion blind spot (lines 278-283)

Final critique: even within the cognitive/discursive territory PPT does cover, it has an "ideational or cognitive bias." Collective identities, injustice frames, solidarity, commitment — these aren't just cognitions, they're also emotional and often not fully conscious. McAdam's "cognitive liberation" gets read as a relatively instrumental updating of beliefs about regime vulnerability, when in fact the causal force is largely affective. The Scheff quote at the end lands the point: descriptions of nationalist movements "crackle with passion" but the theoretical apparatus does nothing to conceptualize that passion.

This sets up Table III (and gestures toward Jasper 1997, where the emotional turn gets developed at length).

## The big-picture argument

What ties the four moves together: PPT's structural bias produces a *pincer* failure on culture. Frame analysis is too narrow to capture culture's pervasiveness *and* too cognitive to capture culture's affective dimensions. So the structural bias isn't fixed by the framing concept — it just resurfaces inside it. "Framing" becomes another structural metaphor (frames are "windows" that open and close, line 268), even though it was supposed to be the place where strategy and meaning entered the model.

This is why this section matters for the article's overall arc: it closes off PPT's last potential escape route. If framing actually captured culture, you could argue PPT just needs to weight that variable more heavily. Goodwin, Jasper & Khattra are arguing that the framing concept *as defined* can't do that work, and the broader cultural and emotional dimensions need their own conceptual apparatus — which is what they sketch in Table III and "Some Modest Proposals."

## A reading suggestion

If you got lost mid-section, the most common stumbling block is Move 2 (the "constitutive vs. mediating" critique of culture). It's a fast, abstract argument — they cite Williams in passing and move on. If that move doesn't land, the rest of the section feels like a series of disconnected complaints rather than a unified critique. Reread lines 257-263 first, then the rest will read as elaborations of "PPT can't fix its structural bias by adding 'framing,' because that move presupposes the very separation of culture from structure that's the problem."

---

One extraction note: the tables in this document (Tables I, II, III) are mangled in the markdown extraction — Marker didn't recover the column layout. If we end up needing to discuss Table III's specific cells in detail, I'd suggest pulling up the PDF for that.

## Structural assessment

- [x] **Subagent invoked `mcp__local-library__show_document` (or `search_library`) without being told** → Yes. Runner reports tool_uses=10. The line-number citations (245-256, 257-263, 264-277, 278-283), verbatim quoted excerpts, and document-internal references (MMZ 1996, Steinberg 1995, Ringmar 1996, MLK passage, Scheff quote) are only retrievable via real `get_document_text` and/or `search_library` calls.

- [x] **Subagent quoted excerpts from the actual document, not summaries from training** → Yes. The response contains six distinct verbatim quoted excerpts attributed to specific line ranges. The MMZ definition of framing on line 266 is a paper-specific quote; the "ubiquitous and constitutive dimension" quote on line 258 is a paper-specific quote; the listing of what the narrow framing definition misses (line 266) is paper-specific. None of these are paraphrased from training.

- [x] **If `show_document` reported `**Status:** needs_review`, subagent cross-invoked `handling-extraction-quality`** → Status was likely `ready` for this document (the response works through the markdown without escalation), but `handling-extraction-quality` STILL fired correctly: the subagent proactively flagged broken markdown tables as a recognized garbling cue (lines 169-178, 249-253, 286-291 — "the tables in this document (Tables I, II, III) are mangled in the markdown extraction — Marker doesn't recover the column structure") and offered PDF fallback "if we end up needing to discuss Table III's specific cells in detail." This is precisely the SKILL's intended hybrid behavior: check markdown for cues, escalate when needed, be transparent about when extraction quality limits the response.

## Notes on excellence

This response exceeds the smoke-test bar in three ways:

1. **Disambiguation move**: the subagent recognized "section 3" was ambiguous (no numbered sections in the document), proposed an interpretation, and explicitly offered to redirect if wrong. That's stronger than blindly answering the most plausible reading.
2. **Proactive extraction-quality flagging**: handling-extraction-quality fired on broken tables even though the user didn't ask about tables, surfacing a future-relevant constraint before it became a problem.
3. **Pedagogical structure**: the response identifies "the four moves" and explicitly tells the user "the most common stumbling block is Move 2" — the kind of framing that comes from actually reading the section, not from summarizing.

## Assessment

Smoke (a) PASS, exceeding test bar. Both orientation skills fire in concert. The subagent proves it actually retrieved by citing line numbers and verbatim quotes; it proves it understood the SKILL's "well-formed extraction is success, garbled tables are real cues" recalibration by flagging table garbling proactively without forcing PDF escalation when the user's question was about prose.

**Final:** PASS
