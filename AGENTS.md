# Repository instructions

## Home Assistant dashboard graphs

Jamie confirmed on 10 November 2026 that every newly created dashboard graph must use the existing enhanced Statistics Graph Chart Card, `custom:statistics-graph-chart-card`.

- Apply this requirement to YAML and storage dashboards, chart templates, examples intended for deployment, and scripts or integrations that generate dashboard charts.
- Use the existing installed upstream card and resource registration. Do not add another graph library or create a native `history-graph`, native `statistics-graph`, or native sensor-card sparkline for a new chart.
- When extending or repairing a dashboard, retain enhanced charts and ensure newly generated charts use the same card. Do not rerun an old installer that restores native charts without first updating its chart output.
- Bind direct sensors where sufficient; preserve units, counter aggregation, time ranges, unavailable-data gaps, state timelines and the corrected grid import/export direction.
- Keep consistent sensor colours and readable labels. Use appropriate statistics/resolution for long time ranges and avoid unnecessary animation or frequent background polling.
- Existing test fixtures or migration code may mention native graph types to detect or convert them. Historical backup files should remain unmodified.
- Home Assistant's generated stock Energy/History panels are outside custom dashboard card creation. Do not claim this rule changes those built-in panels.

Read [the graph standard](docs/dashboard-graph-standard.md) before creating or changing dashboard charts. This is an authoring requirement; it does not automatically rewrite charts users manually add through Home Assistant's UI.
