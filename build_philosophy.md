# Build Philosophy: Pipeline-First Development with Layer-Complete Implementation

This document describes an approach to building complex software systems that balances rapid iteration toward working functionality with architectural coherence and long-term maintainability.

## The Problem: Two Valid Concerns in Apparent Tension

When building a system with multiple interacting concerns—data storage, content processing, user interaction, etc.—two legitimate priorities compete for attention:

**Architectural coherence:** The system should have consistent patterns, complete APIs, and proper abstractions. Don't write bespoke SQL in five different places. Don't build "create" without "delete." Don't let each component reinvent the same wheel.

**Working functionality:** The system should do something useful as soon as possible. Validate designs against real usage. Get feedback before investing heavily. Deliver incremental value rather than waiting for completeness.

These concerns seem to trade off against each other:

- Prioritizing coherence means building infrastructure before you know how it will be used—risking elegant abstractions that don't fit practical reality.
- Prioritizing functionality means building ad-hoc solutions to get things working—risking architectural debt and gaps that compound over time.

The usual framing presents this as a choice: build infrastructure first ("layer-first") or build features first ("feature-first"). But this framing is misleading. Both concerns are valid. The question is not which to sacrifice, but how to honor both.

## The Two-Axis Model

The resolution comes from recognizing that these concerns operate on **orthogonal axes**. They're not in conflict—they address different dimensions of the same system.

### Pipeline (Vertical Axis)

The **pipeline** represents data flow through the system—the journey of a single unit of work from input to output. For a document processing system, this might be:

```
Input → Acquisition → Extraction → Transformation → Storage → Retrieval → Output
```

Each stage transforms or acts on the data and passes it to the next. The pipeline view answers: *"What happens to a document as it moves through the system?"*

### Layers (Horizontal Axis)

**Layers** represent architectural concerns that cut across the entire system—responsibilities that persist regardless of which pipeline stage is active. Common layers include:

- **Storage:** Data persistence, schema design, CRUD operations, transactions
- **Processing:** Content transformation, parsing, computation
- **Integration:** Communication with external systems, APIs, file formats
- **Interface:** User interaction, queries, commands, output formatting

The layer view answers: *"What subsystems does the application comprise, and what is each responsible for?"*

### The Orthogonal Relationship

```
                            LAYERS (horizontal concerns)
                        ┌───────────┬───────────┬───────────┐
                        │  Storage  │ Processing│ Interface │
    ════════════════════╪═══════════╪═══════════╪═══════════╪════
    Stage 1: Input      │     ●     │           │     ●     │
    ────────────────────┼───────────┼───────────┼───────────┼────
    Stage 2: Transform  │     ●     │     ●     │           │  PIPELINE
    ────────────────────┼───────────┼───────────┼───────────┼────  (vertical
    Stage 3: Store      │     ●     │           │           │   data flow)
    ────────────────────┼───────────┼───────────┼───────────┼────
    Stage 4: Retrieve   │     ●     │     ●     │     ●     │
    ════════════════════╧═══════════╧═══════════╧═══════════╧════
```

Each pipeline stage touches one or more layers. The storage layer might be involved at every stage; processing might only matter during transformation; interface concerns bookend the flow at input and output.

## The Approach: Pipeline-First Building, Layer-Complete Implementation

The core principle combines the strengths of both orientations:

**Build along the pipeline** — Structure development as a sequence of milestones that progressively extend how far data flows through the system. Each milestone delivers testable, working functionality.

**Implement layers completely** — When a pipeline stage requires a layer, implement that layer properly—not just the minimum for the current stage. If Stage 2 needs storage, build the storage layer with full CRUD, proper error handling, and consistent patterns, even if Stage 2 only uses "create."

### Why Pipeline-First?

- **Early feedback:** Working functionality reveals requirement gaps and design flaws faster than specification review
- **Grounded architecture:** Building along the data flow ensures architectural decisions are tested against practical reality—you can't design an elegant abstraction that doesn't fit how data actually moves
- **Maintained motivation:** Visible progress sustains momentum better than invisible infrastructure work
- **Natural test boundaries:** Each pipeline stage is a testable unit with clear inputs and outputs
- **Incremental value:** Partial systems can still be useful (a system that ingests but doesn't yet search is more useful than neither)

### Why Layer-Complete?

- **Avoids the bespoke-code trap:** Without layer discipline, each pipeline stage implements its own ad-hoc version of common concerns. You end up with five places that write SQL, none of which handle deletion.
- **Forces necessary decisions:** Layer completeness prevents indefinite deferral of architectural work. Without this discipline, "we'll handle deletion later" becomes "we never handled deletion."
- **Enables future pipeline stages:** Later stages can rely on layer capabilities being present, not just the subset the earlier stages needed
- **Enforces separation of concerns:** Layers are the unit of abstraction. A pipeline stage should *use* the storage layer, not *contain* storage logic.
- **Provides a completeness lens:** Layers prompt questions that pipeline thinking misses: "We can create and read—can we update? Delete? Handle errors consistently?"

## Testing Strategy

The two-axis model suggests a natural testing structure:

### Substep Unit Tests
Test individual functions within a pipeline stage. Does this parsing function handle malformed input? Does this SQL query return the expected shape?

### Pipeline Stage Tests
Test a complete pipeline stage end-to-end. Given valid input to the extraction stage, do we get correctly extracted output?

### Transition Tests (Contracts)
Test the boundaries between pipeline stages. Does Stage N produce output that Stage N+1 can consume? These are the integration seams.

### Layer Completeness Tests
Test each layer's full API surface. Does the storage layer handle create, read, update, delete? What about concurrent access? Error conditions?

```
┌─────────────────────────────────────────────────────┐
│  Layer completeness tests                           │
├─────────────────────────────────────────────────────┤
│  Pipeline transition tests (contracts)              │
├─────────────────────────────────────────────────────┤
│  Full pipeline stage tests                          │
├─────────────────────────────────────────────────────┤
│  Substep unit tests                                 │
└─────────────────────────────────────────────────────┘
```

The lower levels run fast and catch implementation bugs. The upper levels run slower but catch architectural gaps and integration failures.

## When to Use This Approach

This model is most valuable when:

- The system has **multiple distinct concerns** that interact (storage + processing + external integration + user interface)
- **End-to-end functionality** is the goal, not a library or single-purpose tool
- The project is **large enough** that ad-hoc development would accumulate significant debt
- You want to **iterate based on real usage** rather than specifying everything upfront

For simpler systems (a CLI tool that does one thing, a library with a focused API), this level of structure may be overhead.

## Summary

1. **Identify your pipeline:** What is the data flow? What are the stages from input to output?
2. **Identify your layers:** What are the architectural concerns that cut across stages?
3. **Map the intersections:** Which stages touch which layers?
4. **Build milestone by milestone:** Progress down the pipeline, delivering working functionality at each step
5. **Implement layers properly:** When you touch a layer, build it with completeness in mind—not just the minimum for the current milestone
6. **Test at multiple levels:** Unit tests for substeps, stage tests for pipeline steps, contract tests for transitions, completeness tests for layers

The result is a system that delivers value incrementally while maintaining the architectural coherence needed for long-term maintainability.
