// GENERATED FROM THE LIVE PAYLOAD — do not hand-edit.
//
// The `ui_defaults` a server with no settings file serves on /capabilities
// (AK#1858): the hosted instance's, which reads no file, so its path is null
// and it offers no save. The page restates none of these defaults, so the
// session tests mount on this payload, the served path, rather than on a
// copy of their own.
//
// Regenerate with:
//   .venv/bin/python -c "import antennaknobs.web.server, json; \
//     from antennaknobs.web import settings as s; \
//     print(json.dumps(s.load(s.catalog(have_pynec=True, have_nec5=True, \
//       have_nec2=True), hosted=True), indent=2))"
//
// Pinned Python-side by tests/test_frontend_ui_defaults_fixture.py.

export const SERVED_UI_DEFAULTS =
{
  "path": null,
  "exists": false,
  "writable": false,
  "switch_labels": [
    {
      "key": "live",
      "label": "Live",
      "default": true
    },
    {
      "key": "freq_sweep",
      "label": "frequency charts re-run by themselves",
      "default": true
    },
    {
      "key": "convergence_sweep",
      "label": "knob and density charts re-run by themselves",
      "default": false
    },
    {
      "key": "pattern_renorm",
      "label": "norm check",
      "default": true
    },
    {
      "key": "refine",
      "label": "adaptive resolution",
      "default": true
    },
    {
      "key": "heatmap_currents",
      "label": "heatmapped currents",
      "default": true
    },
    {
      "key": "current_waveforms",
      "label": "current waveforms",
      "default": false
    },
    {
      "key": "wire_labels",
      "label": "wire labels",
      "default": false
    },
    {
      "key": "feed_labels",
      "label": "feed labels",
      "default": true
    }
  ],
  "switches": {
    "live": true,
    "freq_sweep": true,
    "convergence_sweep": false,
    "pattern_renorm": true,
    "refine": true,
    "heatmap_currents": true,
    "current_waveforms": false,
    "wire_labels": false,
    "feed_labels": true
  },
  "switches_set": [],
  "antenna_view": {
    "orientation": "auto"
  },
  "ground": {
    "enabled": true,
    "type": "finite",
    "method": "sommerfeld",
    "soil": null,
    "terrain_preset": null
  },
  "ground_set": [],
  "grounds": [
    {
      "id": "X",
      "enabled": true,
      "type": "finite",
      "method": "sommerfeld",
      "soil": null,
      "terrain_preset": null
    },
    {
      "id": "Y",
      "enabled": false,
      "type": "finite",
      "method": "sommerfeld",
      "soil": null,
      "terrain_preset": null
    },
    {
      "id": "Z",
      "enabled": true,
      "type": "finite",
      "method": "fast",
      "soil": {
        "eps_r": 13.0,
        "sigma": 0.005
      },
      "terrain_preset": null
    }
  ],
  "slots": {},
  "workbench": {
    "run_on_pick": {
      "frequency": true,
      "pattern": true,
      "knob": false,
      "held": false,
      "convergence": false,
      "map": false
    }
  },
  "problems": []
};
