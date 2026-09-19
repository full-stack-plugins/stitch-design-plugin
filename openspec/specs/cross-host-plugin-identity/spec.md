# cross-host-plugin-identity Specification

## Purpose
TBD - created by archiving change remove-codex-brand-prefixes. Update Purpose after archive.
## Requirements
### Requirement: Current public identities SHALL be host-neutral

Current and future cross-host plugins, skills, producer IDs, and public documentation SHALL use product or role names without a `codex-` prefix.

#### Scenario: A future role plugin is implemented

- **WHEN** the design is converted into manifests and skills
- **THEN** its public IDs use the role name and remain valid for Codex, ZCode, and Kimi

### Requirement: Historical and host-specific names SHALL remain truthful

The repository SHALL retain exact historical repository names and Codex-specific manifest or CLI names where changing them would falsify evidence or break a host contract.

#### Scenario: Documentation records an archived source repository

- **WHEN** the source repository was actually published with a Codex-prefixed name
- **THEN** the historical statement keeps that exact name and labels it as historical

