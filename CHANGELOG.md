# Changelog

## [1.0.0] — 2026-03-05

### Initial Release

- Near-real-time NWS alert detection via `Last-Modified` HTTP header checking
- Lightweight HEAD request every 30 seconds — full fetch only on feed change
- Shapely polygon-based site matching for precise geographic inclusion
- Tiered Discord embeds: critical / warning / watch / advisory
- Color-coded embeds per severity tier (red / orange / yellow / blue)
- Startup notification on service launch (site count + monitored alert types)
- Graceful shutdown notification on SIGINT / SIGTERM
- Periodic active alert summary embed (configurable interval)
- JSON-based alert cache to prevent duplicate notifications
- Active alert tracking with automatic pruning of expired alerts

---

### Relationship to nws-alert-monitor

This repository is a near-real-time variant of
[nws-alert-monitor](https://github.com/ODST-Aaron/nws-alert-monitor), which uses
a fixed polling interval. The core site-matching logic and Discord embed formatting
are shared between both projects. The key difference is the `Last-Modified` header
optimization which reduces API load and improves alert latency from ~2 minutes to
~30 seconds.
