# 0018 — Visibility is declared in the model, not repeated in the data

**Status:** Accepted

## Context

[ADR 0014](0014-typed-profile-store-and-rag-index-replace-bundles.md) replaces
the "private bundle / public bundle" pair with one profile in which every field
has a visibility. The public view has to stay safe when the profile grows, and
the YAML has to stay pleasant to edit by hand.

Considered and rejected:

- **A `visibility:` key on every field in the YAML.** The most explicit, but it
  roughly doubles the size of the files, and a field written without the key is
  an easy slip.
- **A `visibility:` key on every record.** Better, but contact fields (email,
  phone) are not records, and forgetting the key on one record leaks it.

## Decision

- Each Pydantic field declares its visibility once, in `jobomatic.profile.model`
  (`json_schema_extra=PUBLIC` or `PRIVATE`). The marker also appears in the
  generated JSON Schema.
- Each record type has a default (`default_visibility`), and one record may
  override it with a single `visibility:` line, for example a legacy role.
- `jobomatic.profile.visibility.public_view` applies three rules: a record is
  shown only if it is public; a field is shown only if it is marked public; a
  nested value is shown with its parent field. **An unmarked field is private.**
- Two invariants are validated: a legacy role cannot be public, and only
  certifications on the public list can be.
- A test fails when a field has no marker, so adding one is a deliberate act.

## Consequences

- The YAML contains `visibility:` only where a record differs from its type's
  default (today: legacy roles and the public certifications).
- A field added later cannot leak by being forgotten: the public view drops it.
- `presence_view` returns plain data (a dict) rather than a typed model. If
  consumers need attribute access, a typed wrapper can be added later without
  changing the rules.
- Making something public that was never public is a code change to the
  model, which gets reviewed, rather than an edit to a data file.
- `pii_guard` still scans everything generated for public profiles; this ADR
  only decides what goes into it.
