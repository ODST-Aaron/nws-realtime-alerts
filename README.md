# nws-realtime-alerts

A Python-based NWS weather alert monitor for ISP/NOC environments. Posts tiered Discord embeds when active NWS alerts affect your monitored network sites.

Uses HTTP `Last-Modified` header checking to minimize API load while achieving near-real-time alert detection. Falls back to interval-based polling when the header is absent.

---

## Features

- **Real-time detection** via `Last-Modified` HEAD checks every 30 seconds — full fetch only when the feed changes
- **Fallback polling** every 30 seconds when NWS omits the `Last-Modified` header
- **Two-stage site matching:**
  - Stage 1 — Polygon matching using Shapely for alerts with GeoJSON geometry
  - Stage 2 — UGC zone/county code fallback for SPC watches that use county FIPS lists instead of polygons
- **Tiered Discord embeds** with color coding by severity
- **Adaptive site list formatting** — switches to compact format and truncates with overflow count when site lists are large
- **Startup active alert check** — posts current active alerts on every restart so the team has situational awareness mid-event
- **Periodic active alert summary** every 10 minutes while alerts are ongoing
- **Graceful shutdown** — posts a shutdown notification on Ctrl+C or SIGTERM

---

## Monitored Alert Types

| Tier | Color | Alert Types |
|------|-------|-------------|
| 🚨 CRITICAL | Red | Tornado Emergency, Tornado Warning, Flash Flood Emergency |
| ⚠️ WARNING | Orange | Severe Thunderstorm Warning, Flash Flood Warning, Blizzard Warning, Ice Storm Warning, Extreme Wind Warning, Winter Storm Warning |
| 👀 WATCH | Yellow | Tornado Watch, Severe Thunderstorm Watch, Winter Storm Watch, High Wind Warning |
| 🔵 ADVISORY | Blue | Wind Advisory, Significant Weather Advisory, Special Weather Statement, Extreme Cold Warning, Dust Storm Warning |

---

## Requirements

```
requests>=2.31.0
shapely>=2.0.0
```

Install with:
```powershell
pip install requests shapely
```

---

## Setup

### 1. Clone the repository

```powershell
git clone https://github.com/ODST-Aaron/nws-realtime-alerts.git
cd nws-realtime-alerts
```

### 2. Prepare your locations CSV

Copy `locations_example.csv` to `locations.csv` and populate it with your sites.

**Required columns:**

| Column | Description | Example |
|--------|-------------|---------|
| Customer | Customer or organization name | `ExampleISP` |
| Name | Site name | `Jonesboro NOC` |
| SiteType | Type of site | `Tower`, `Hub`, `Office` |
| Latitude | Decimal latitude | `35.8423` |
| Longitude | Decimal longitude | `-90.7043` |
| City | Nearest city per NWS | `Jonesboro` |
| County | County name | `Craighead` |
| State | Two-letter state code | `AR` |
| Notes | Optional notes | |
| Zone | NWS forecast zone code | `ARZ026` |
| CountyCode | NWS county UGC code | `ARC031` |

> `Zone` and `CountyCode` are required for UGC fallback matching of SPC watches. Use `bulk_zone_lookup.py` to populate these automatically.

### 3. Populate Zone and CountyCode with bulk_zone_lookup.py

```powershell
py -3.12 bulk_zone_lookup.py
```

This queries the NWS `/points/` API for each site (~1 second per site) and writes `locations_with_zones.csv`. Review the output, then rename it to `locations.csv`.

### 4. Configure the script

Edit the configuration block at the top of `weather_alerts.py`:

```python
CSV_FILE        = r"C:\nws-realtime-alerts\locations.csv"
DISCORD_WEBHOOK = "YOUR_DISCORD_WEBHOOK_URL_HERE"
CACHE_FILE      = r"C:\nws-realtime-alerts\seen_alerts.json"
ACTIVE_FILE     = r"C:\nws-realtime-alerts\active_alerts.json"
```

### 5. Run

```powershell
py -3.12 weather_alerts.py
```

---

## File Reference

| File | Description |
|------|-------------|
| `weather_alerts.py` | Main monitor script |
| `bulk_zone_lookup.py` | Populates Zone, CountyCode, County, and City columns in your CSV |
| `locations_example.csv` | Example CSV structure |
| `locations.csv` | Your live site list — **excluded from git** |
| `seen_alerts.json` | Alert ID cache — **excluded from git** |
| `active_alerts.json` | Active alert tracking — **excluded from git** |

---

## Notes

- The NWS alerts API (`api.weather.gov`) does not always return a `Last-Modified` header. When absent, the script falls back to a full fetch every 30 seconds automatically.
- SPC Tornado Watches and Severe Thunderstorm Watches do not include polygon geometry — they are matched via UGC county codes (`ARC031`) rather than coordinates. The `CountyCode` column in your CSV enables this.
- `seen_alerts.json` persists between runs to prevent duplicate notifications. Delete it if you want all currently active alerts to re-fire on next startup.

---

## Related

- [spc-md-monitor](https://github.com/ODST-Aaron/spc-md-monitor) — Companion script for SPC Mesoscale Discussion notifications
