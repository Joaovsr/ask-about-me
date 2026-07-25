# Domain docs

The repository uses a single domain context.

## Before exploring

- Read `CONTEXT.md` at the repository root for canonical terminology.
- Read the relevant ADRs under `docs/adr/` before changing behavior or architecture.
- If either location is absent, proceed silently; domain-modeling workflows create documents only when decisions crystallize.

## Layout

```text
/
|-- CONTEXT.md
|-- docs/
|   `-- adr/
`-- src/
```

## Vocabulary

Use the terms defined in `CONTEXT.md` in issue titles, plans, tests and code. Do not substitute terms listed under `_Avoid_`.

If a required concept is missing, either reconsider the new terminology or record the gap for a domain-modeling session.

## ADR conflicts

Surface any conflict with an existing ADR explicitly rather than silently overriding it. A changed decision must be recorded by superseding or refining the relevant ADR.
