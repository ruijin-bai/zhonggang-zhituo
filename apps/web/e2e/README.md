# Zhituo Web E2E

Required browser tests live here. Keep them deterministic, tenant-safe, and centered on business-critical cross-layer flows.

The current Pursuit golden test intentionally uses the seeded demo organization and admin membership so CI starts from a known PostgreSQL state. New required-gate cases should reuse stable seed facts or create their own uniquely named records during the test.
