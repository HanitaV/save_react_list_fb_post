# Methodology

Observed facts come from operator imported interaction rows and visible profile captures. Automated heuristics include recurrence, bursts, avatar image similarity, and shared-post clusters. These are leads for human review. A dense burst can be caused by normal events; a shared avatar can be benign. Every report distinguishes observations from heuristics.

Extension bundles use collection time in the required timestamp field because Facebook's visible reaction list does not expose individual reaction times. Rows tagged `extension_scan` are excluded from reaction-burst detection. Repeated presence across scanned posts remains an observation, not proof of coordination or a cloned account. The extension's local same-avatar URL and same-name indicators are weaker than backend image hashes and require manual review.

Evidence integrity uses the SHA-256 of the stored screenshot and a per-actor chain. The chain detects changes to records and screenshot bytes, but it is not a cryptographic timestamp authority. An operator should retain exported ZIPs in a controlled archive with independent timestamps when stronger provenance is required.
