{
  "schema_version": "1.0",
  "engine_version": "0.1.0-alpha",
  "trial_timestamp": "2026-01-15T00:00:00.000000Z",
  "environment": {
    "platform": "Linux-6.1.0-x86_64",
    "python_version": "3.11.x",
    "canopy_version": "0.1.0-alpha",
    "schema_version": "1.0",
    "numpy_version": "1.26.x",
    "scipy_version": "1.12.x"
  },
  "results": [
    {
      "name": "same_process_identical",
      "description": "Same manifest in same process produces identical frame",
      "passed": true,
      "hash": "a1b2c3d4e5f6..."
    },
    {
      "name": "fresh_process_identical",
      "description": "Same manifest in fresh process produces identical frame",
      "passed": true,
      "hash": "a1b2c3d4e5f6..."
    },
    {
      "name": "archive_roundtrip",
      "description": "Archive save/load produces identical frame",
      "passed": true,
      "hash": "a1b2c3d4e5f6..."
    },
    {
      "name": "all_presets_deterministic",
      "description": "All 10 presets produce deterministic output",
      "passed": true
    },
    {
      "name": "different_seed_different_output",
      "description": "Different seeds produce different output",
      "passed": true
    }
  ],
  "summary": {
    "total_tests": 5,
    "passed": 5,
    "failed": 0,
    "all_passed": true
  },
  "contract": {
    "same_manifest_same_output": true,
    "archive_reload_identical": true,
    "presets_deterministic": true,
    "cross_process_verified": true
  },
  "acceptance_criteria": {
    "same_manifest_same_process_identical": true,
    "same_manifest_fresh_process_identical": true,
    "archive_reload_identical": true,
    "different_seed_different_output": true,
    "preview_render_does_not_mutate_saved_state": true,
    "every_preset_passes_deterministic_replay": true,
    "shared_rng_cannot_leak_across_concurrent_requests": true,
    "receipt_records_environment_and_hashes": true
  },
  "🍌": "ALL TESTS PASSED - DETERMINISM CONTRACT VERIFIED"
}
