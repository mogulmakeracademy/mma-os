# Entity Drafting Variables - Mogul Maker Academy
# Source: Antonio Cook | Locked: 2026-06-29
# Purpose: Canonical entity strings for use in agreements, contracts, signature blocks, and legal notices.
# Used by: future legal_drafting_agent + all manual agreement drafting until that agent exists

## Primary Operating Entity

**Legal name:** Mogul Maker Academy, LLC

**State of formation:** Wyoming (domestic LLC)

**Qualified to do business in:** Georgia (foreign-filed LLC)

**Standard entity recital (for use in agreement preamble):**
> Mogul Maker Academy, LLC, a Wyoming limited liability company qualified to transact business in the State of Georgia as a foreign limited liability company (the "Company")

**Standard signature block:**
```
MOGUL MAKER ACADEMY, LLC

By:    _________________________
Name:  Antonio Cook
Title: Founder
Date:  _________________________
```

## Governing Law

- **Default governing law:** State of Georgia (principal place of business)
- **Arbitration venue:** State of Georgia, county TBD (typically county where Company maintains its principal office)
- **Reason:** Operations + customers + Antonio's residence are in GA, so jurisdiction follows operations not formation

## Notice Address

- **Principal office:** [TBD - confirm Antonio's preferred notice address for GA operations]
- **Registered agent (Wyoming):** [TBD - confirm WY registered agent on file]
- **Registered agent (Georgia):** [TBD - confirm GA registered agent on file]

## Use in BTF Service Agreement v1

When the legal_drafting_agent renders btf-service-agreement-v1.md into an instance for a client, it MUST:
1. Replace [COMPANY] preamble placeholder with the standard entity recital above
2. Replace [SIGNATURE_BLOCK] placeholder with the standard signature block above
3. Set governing law clause to State of Georgia
4. Set arbitration venue to State of Georgia, with specific county filled from Antonio's notice address

## Open items (need Antonio confirmation)

- [ ] Principal office address for notice provisions
- [ ] Wyoming registered agent name (for cross-reference / notices to WY)
- [ ] Georgia registered agent name (for cross-reference / notices to GA)
- [ ] Specific GA county for arbitration venue

## Related entities (future, not yet active)

- **Mogul Credit, LLC** - separate Florida LLC for credit-related operations (referenced in older doctrines; confirm if still active)
- **Paige Agent AI** - product brand name owned by Mogul Maker Academy, LLC; not a separate legal entity
- **Domain ownership:** paigeagent.ai, portal.mogulmakeracademy.com, mogulmakeracademy.com - all registered to Mogul Maker Academy, LLC

