# PC handoff contract

Save paths relative to the job root where possible, so copying the whole job preserves associations. Also record the source host/root for locating uncopied inputs. Hash the exact retained bytes with SHA-256; never use hashes of path strings. Keep files immutable once referenced by a completed phase, and write a new derivative for corrections.

`handoff.json` is a record of preparation, not a certificate of native success. Use this structure, omitting fields that do not apply and using `null` for observations or usage that were not exposed:

```json
{
  "schemaVersion": 1,
  "workflow": "vps-3d-source-preparation",
  "status": "prepared_source_only",
  "operation": "create",
  "assetId": "stable-job-or-asset-id",
  "tier": "med",
  "preparedAt": "ISO-8601 timestamp",
  "origin": {"host": "mobile-dev", "jobRoot": "/actual/job/root"},
  "brief": {"path": "brief.txt", "sha256": "actual SHA-256"},
  "original": {"path": "original.png", "sha256": "actual SHA-256"},
  "references": {
    "state": "sealed_retained",
    "manifestPath": "references/v1-HASH/manifest.json",
    "manifestSha256": "actual SHA-256",
    "helperPath": "actual installed helper path",
    "helperSha256": "actual SHA-256",
    "viewCount": 20,
    "verificationReceiptPath": "reference-verification.json",
    "consumerState": "pending_pc_native_execution"
  },
  "source": {
    "path": "model.luau",
    "sha256": "actual SHA-256",
    "interface": "module returns function(ctx)",
    "context": ["container", "entryId", "meshPart", "registerEditableMesh", "checkpoint"],
    "inputRevision": null,
    "inputSourceSha256": null
  },
  "imageInspection": {"path": "image-inspection.json", "sha256": "actual SHA-256", "count": 21},
  "workers": [
    {
      "phase": "references",
      "executionMode": "queue_preselected",
      "requested": {"model": "gpt-6.1-sol", "reasoningEffort": "low"},
      "observed": {"model": "gpt-6.1-sol", "reasoningEffort": "low"},
      "receiptPath": "receipts/reference-run.json",
      "usage": null
    },
    {
      "phase": "geometry",
      "executionMode": "queue_preselected",
      "requested": {"model": "gpt-6.1-sol", "reasoningEffort": "ultra"},
      "observed": {"model": "gpt-6.1-sol", "reasoningEffort": "ultra"},
      "receiptPath": "receipts/geometry-run.json",
      "usage": null
    }
  ],
  "staticChecks": [
    {"name": "actual check", "status": "passed", "receiptPath": "checks/actual-check.json", "limitations": "What this check does not establish"}
  ],
  "native": {
    "status": "pending",
    "executedInStudio": false,
    "durableMeshVerified": false,
    "exportVerified": false,
    "uploadedToRoblox": false,
    "actualMetrics": null
  },
  "pending": ["Execute exact Luau source in an owned Studio session", "Inspect front/back and functional openings", "Bake or export actual native mesh and verify durability", "Reimport and verify in client Play"],
  "limitations": ["Synthetic hidden surfaces are interpretations", "Native geometry, appearance and collision have not been verified"]
}
```

Replace all illustrative values with evidence. Observed worker settings must come from actual execution/controller metadata, not the prompt's assertion. Keep available task/run IDs and raw receipt paths; if a receipt is unavailable, record that explicitly and do not invent a file. For reused views, point to their historical receipts and label generation as reused; zero new calls does not imply historical generation was free. `image-inspection.json` contains one path/hash and brief actual observation for each inspected image. A refine handoff records the baseline source revision and references used; it may have fewer than twenty retained views without claiming a newly sealed create set.

An interrupted handoff names the completed phases, missing inputs, last safe checkpoint and next action. Preserve pending references through the controller's consumer registration, with its actual job/consumer identifier and receipt when available. If no registration exists, report `retentionProtection: "manual_preserve_required"` and keep the binaries.

`HANDOFF.md` should tell the PC operator where to find the original, source and manifest; which tier/settings actually ran; which static checks passed or were unavailable; and what remains. Include dimensions/orientation and the expected harness contract. The PC should verify copied hashes and the sealed reference set, execute the exact selected source using the shared M03-T native guide, save actual mesh metrics, review useful angles and openings, and verify a durable bake/export. Record native errors and repairs as new revisions. Until that work finishes, retain the pending consumer and all references. No upload or game publication is implied by this handoff.
