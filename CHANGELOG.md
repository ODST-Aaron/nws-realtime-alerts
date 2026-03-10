# Changelog

All notable changes to nws-realtime-alerts are documented here.

---

## [1.2.0] - 2026-03-07

### Added
- **Special Weather Statement** added to advisory tier (blue embed)
- **`CountyCode` column** support in `locations.csv` — stores NWS county UGC code (e.g. `ARC031`) separately from forecast zone code (e.g. `ARZ026`)
- **`bulk_zone_lookup.py`** updated to populate `CountyCode` column automatically; output path updated to `C:\nws-realtime-alerts\` to match main script
- **Adaptive site list formatting** in Discord embeds — switches from full format (with coordinates) to compact format (without coordinates) when field length approaches Discord's 1024-character field limit, then truncates with overflow count if still too long
- **Startup active alert summary** — on every restart, fetches the current feed and posts full alert embeds for any active alerts affecting monitored sites, regardless of seen cache; previously notified alerts are listed in a grey summary embed for situational awareness

### Fixed
- **UGC county code fallback** now correctly matches SPC Tornado Watches and Severe Thunderstorm Watches — these use county FIPS codes (`ARC031`) in their UGC lists, not forecast zone codes (`ARZ026`). Previously, all SPC watch UGC matching failed silently because only zone codes were checked
- **`Last-Modified` header absence handling** — NWS API does not always return this header; script now falls back to a full fetch every 30 seconds when the header is absent, rather than printing `No feed change` indefinitely
- **Discord 400 errors** caused by oversized embed field values when large numbers of sites were affected by a single alert (e.g. 63-site Tornado Watch)

---

## [1.1.0] - 2026-02-XX

### Added
- **UGC zone code fallback** for alerts without polygon geometry — matches site `Zone` column against `properties.geocode.UGC` list in alert
- **City column** added to site line format in embeds: `Customer — Name — SiteType  (lat, lon)  [City, County County, State]`
- **`bulk_zone_lookup.py`** updated to populate `City` column from NWS `relativeLocation` field
- **Shutdown notification** embed on SIGINT/SIGTERM

### Fixed
- Zone-only UGC fallback missed SPC watches that use county codes — partially addressed (fully resolved in v1.2.0 with CountyCode column)

---

## [1.0.0] - 2026-01-XX

### Initial release
- Real-time NWS alert monitoring via HTTP `Last-Modified` HEAD checks
- Polygon-based site matching using Shapely
- Tiered Discord embeds (CRITICAL / WARNING / WATCH / ADVISORY)
- Startup and shutdown notifications
- `seen_alerts.json` cache to prevent duplicate notifications
- `active_alerts.json` for active alert tracking and periodic summary embeds
- `bulk_zone_lookup.py` for populating Zone and County columns
