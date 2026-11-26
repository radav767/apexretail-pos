# Advanced catalogue selector boundaries — 26 November 2026

Define these boundaries before expanding the shared selector. POS remains daily selling and stock lookup under the superseding navigation contract; catalogue administration belongs in Backoffice. No selector supplies posting authority or guarantees that a later catalogue write cannot change eligibility.

| Purpose | Current contract | Inactive/deleted products | Authority and limits |
| --- | --- | --- | --- |
| general | Existing active catalogue/stock lookup | Excluded, including exact selected-ID lookup | Current tenant/branch/register context plus existing sales/catalogue/inventory-read policy. No costs. It is not management or recipe acceptance. |
| charge | Eligible profile tip/service associations | Excluded | Existing business-settings permission; active non-stock service/non_stock only; final profile write refreshes/share-locks products. |
| management | Unimplemented, rejected | No implicit inactive visibility | Future explicit Backoffice-only purpose must require current products_edit (not sales/read permission), explicit active/inactive/all filter, deleted exclusion, bounded pagination and independent selected-ID lookup. Inactive rows may be edited/reactivated only through original authorized administration endpoints; never silently selected for selling. No new purpose until API/service/role/tenant/branch/stale-identity acceptance. |
| recipe/component | Unimplemented, rejected | No implicit eligibility | Existing legacy composite metadata in general results does not enable new recipe posting. Future component selection must separately define supported types, variant/unit/quantity precision, active state, cycle/self-reference, version/concurrency and stock ownership before adoption. Unsupported recipe posting remains gated. |

An unavailable saved choice remains evidence for review; search must not erase its ID, invent a replacement or mutate an immutable sale/quotation/document. General exact lookup does not reveal inactive, deleted or foreign records. Unknown purposes fail closed both at the HTTP schema and direct service. Read results never reserve stock or authorize a payment; final transaction services retain their original policy, locks and proofs.

Offset pages retain their existing non-snapshot limitation under concurrent catalogue changes. No advanced-selector expansion, bulk catalogue rewrite, recipe enablement, new financial rounding or posting capability is authorized by this policy. Existing supported catalogue APIs remain in Backoffice, with their permissions/data preserved. Production and Super Admin remain NO-GO.
