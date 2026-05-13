# ADR 0003: Human Approval Before Ad Changes

## Status
Accepted.

## Decision
Every customer-impacting action requires explicit human approval before execution or handoff.

## Consequences
Approval records become core domain objects. AI agents, workers, and scheduled jobs cannot approve or execute dangerous changes on their own.

