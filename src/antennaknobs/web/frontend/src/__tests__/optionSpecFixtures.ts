// GENERATED FROM THE LIVE PAYLOAD — do not hand-edit.
//
// Regenerate with:
//   .venv/bin/python -c "import antennaknobs.web.server, json; \
//     from antennaknobs.web.adapter import model_option_specs; \
//     print(json.dumps(model_option_specs(), indent=2))"
//
// Pinned Python-side by tests/test_frontend_option_spec_fixture.py, on the
// same argument as the constraint fixture beside it: a generated file with no
// regeneration gate is a copy, and that one had already gone stale silently.
import type { ModelOptionSpecs } from "../lib/backends";

export const SERVED_OPTION_SPECS: ModelOptionSpecs =
{
  "degree": {
    "kind": "int",
    "label": "degree",
    "default": 2,
    "auto_when_null": false,
    "shown_when": null,
    "gate_label": null,
    "min": 1,
    "max": 2,
    "step": 1,
    "allow_none": false,
    "accepts_min": 1,
    "accepts_max": 2
  },
  "n_qp_const": {
    "kind": "int",
    "label": "n_qp_const (GL pts)",
    "default": 8,
    "auto_when_null": false,
    "shown_when": null,
    "gate_label": null,
    "min": 2,
    "max": 32,
    "step": 1,
    "allow_none": false,
    "accepts_min": 1,
    "accepts_max": 64
  },
  "n_qp_pair": {
    "kind": "int",
    "label": "n_qp_pair (GL pts/axis)",
    "default": null,
    "auto_when_null": true,
    "shown_when": null,
    "gate_label": "n_qp_pair: auto",
    "min": 2,
    "max": 32,
    "step": 1,
    "allow_none": false,
    "accepts_min": 1,
    "accepts_max": 32
  },
  "n_qp_source": {
    "kind": "int",
    "label": "n_qp_source",
    "default": 16,
    "auto_when_null": false,
    "shown_when": "feed_smoothing_factor",
    "gate_label": null,
    "min": 4,
    "max": 64,
    "step": 1,
    "allow_none": false,
    "accepts_min": 1,
    "accepts_max": 64
  },
  "n_qp_sing": {
    "kind": "int",
    "label": "n_qp_sing (GL pts/axis)",
    "default": 32,
    "auto_when_null": false,
    "shown_when": "use_singular_enrichment",
    "gate_label": null,
    "min": 8,
    "max": 128,
    "step": 1,
    "allow_none": false,
    "accepts_min": 1,
    "accepts_max": 128
  },
  "feed_smoothing_factor": {
    "kind": "float",
    "label": "\u03b1 (bump width / h_feed)",
    "default": null,
    "auto_when_null": false,
    "shown_when": null,
    "gate_label": "feed source smoothing",
    "min": 0.5,
    "max": 10.0,
    "step": 0.5,
    "allow_none": true,
    "accepts_min": 0.0,
    "accepts_max": 100.0
  },
  "feed_model": {
    "kind": "enum",
    "label": "feed model",
    "default": "point",
    "auto_when_null": false,
    "shown_when": null,
    "gate_label": null,
    "values": [
      "segment",
      "point"
    ]
  },
  "use_singular_enrichment": {
    "kind": "bool",
    "label": "singular enrichment",
    "default": false,
    "auto_when_null": false,
    "shown_when": null,
    "gate_label": null
  },
  "enrichment_variant": {
    "kind": "enum",
    "label": "enrichment_variant",
    "default": "raw",
    "auto_when_null": false,
    "shown_when": "use_singular_enrichment",
    "gate_label": null,
    "values": [
      "raw",
      "stable",
      "tikhonov",
      "auto"
    ]
  },
  "tikhonov_lambda": {
    "kind": "float",
    "label": "tikhonov_lambda (\u03bb)",
    "default": 0.1,
    "auto_when_null": false,
    "shown_when": "use_singular_enrichment",
    "gate_label": null,
    "min": 0.0,
    "max": 10.0,
    "step": 0.01,
    "allow_none": false,
    "accepts_min": 0.0,
    "accepts_max": 1000.0
  },
  "auto_tap_ratio_threshold": {
    "kind": "float",
    "label": "auto_tap_ratio_threshold",
    "default": 0.3,
    "auto_when_null": false,
    "shown_when": "use_singular_enrichment",
    "gate_label": null,
    "min": 0.0,
    "max": 1.0,
    "step": 0.05,
    "allow_none": false,
    "accepts_min": 0.0,
    "accepts_max": 1.0
  },
  "enrichment_min_k": {
    "kind": "int",
    "label": "enrichment_min_k",
    "default": 3,
    "auto_when_null": false,
    "shown_when": "use_singular_enrichment",
    "gate_label": null,
    "min": 2,
    "max": 8,
    "step": 1,
    "allow_none": false,
    "accepts_min": 2,
    "accepts_max": 64
  },
  "extended_kernel": {
    "kind": "bool",
    "label": "extended kernel (EK)",
    "default": false,
    "auto_when_null": false,
    "shown_when": null,
    "gate_label": null
  }
};
