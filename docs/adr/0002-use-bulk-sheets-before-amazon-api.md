# ADR 0002: Use Bulk Sheets Before Amazon API

## Status
Accepted.

## Decision
The MVP generates Amazon bulk sheet exports instead of executing changes through the Amazon Ads API.

## Consequences
Customers retain control, implementation risk is lower, and the product can validate workflow value before storing Amazon credentials or executing live changes.

