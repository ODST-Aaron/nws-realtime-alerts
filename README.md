# nws-realtime-alerts

A near-real-time NWS weather alert monitor for ISP/MSP NOC environments.  
Monitors multiple customer sites against active NWS alerts and delivers
tiered Discord notifications with ~30 second latency.

---

## How It Works

Instead of fetching the full NWS alert feed on a fixed interval, this monitor
sends a lightweight HTTP `HEAD` request every 30 seconds and inspects the
`Last-Modified` response header. A full fetch and site-matching pass only runs
when the feed has actually changed — significantly reducing API load while
maintaining near-real-time alert detection.

```
Every 30s:  HEAD https://api.weather.gov/alerts/active
                 ↓
         Last-Modified changed?
          YES ──→ GET full feed → match sites → Discord embed
          NO  ──→ sleep 30s
```

---

## Features

- **~30 second alert latency** via `Last-Modified` header optimization
- **Minimal API usage** — full fetch only triggered by actual feed changes
- **Shapely polygon matching** — precise geographic site inclusion using NWS alert polygons
- **Tiered Discord embeds** — color-coded by severity tier
- **Startup & shutdown notifications** — Discord embed on service start and graceful stop
- **Graceful shutdown** — SIGINT/SIGTERM triggers shutdown embed before exiting
- **Active alert summary** — periodic Discord summary of all ongoing alerts
- **Duplicate prevention** — JSON cache prevents re-alerting on already-seen alerts
- **Auto-pruning** — expired alerts are removed from active tracking automatically

---

## Alert Tiers

| Tier | Color | Alert Types |
|---|---|---|
| 🚨 CRITICAL | Red | Tornado Emergency, Tornado Warning, Flash Flood Emergency |
| ⚠️ WARNING | Orange | Severe Thunderstorm Warning, Flash Flood Warning, Blizzard Warning, Ice Storm Warning, Extreme Wind Warning, Winter Storm Warning |
| 👀 WATCH | Yellow | Tornado Watch, Severe Thunderstorm Watch, Winter Storm Watch, High Wind Warning |
| 🔵 ADVISORY | Blue | Wind Advisory, Significant Weather Advisory, Extreme Cold Warning, Dust Storm Warning |

---

## Requirements

- Python 3.10+
- `requests`
- `shapely`

```bash
pip install -r requirements.txt
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/ODST-Aaron/nws-realtime-alerts.git
cd nws-realtime-alerts
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

On Ubuntu/Debian:
```bash
pip install -r requirements.txt --break-system-packages
```

### 3. Create your locations CSV

Copy the example and populate it with your sites:

```bash
cp locations_example.csv locations.csv
```

CSV format — comma or tab separated:

| Column | Required | Description |
|---|---|---|
| Customer | No | Customer or organization name |
| Name | Yes | Site name |
| SiteType | No | Site classification (NOC, Tower, Hub, etc.) |
| Latitude | Yes | Decimal degrees |
| Longitude | Yes | Decimal degrees |
| County | No | County name |
| State | Yes | Two-letter state abbreviation |

Example:
```
Customer,Name,SiteType,Latitude,Longitude,County,State
Example ISP,Main NOC,NOC,35.8423,-90.7043,Craighead,AR
Example ISP,Nashville Tower,Tower,36.1627,-86.7816,Davidson,TN
```

### 4. Configure the script

Edit the configuration block at the top of `weather_alerts.py`:

```python
# ── CONFIGURATION — edit these values ──
CSV_FILE         = r"C:\nws-realtime-alerts\locations.csv"   # Windows
# CSV_FILE       = "/path/to/locations.csv"                  # Linux/macOS

DISCORD_WEBHOOK  = "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"

CACHE_FILE       = r"C:\nws-realtime-alerts\seen_alerts.json"
ACTIVE_FILE      = r"C:\nws-realtime-alerts\active_alerts.json"

HEAD_INTERVAL    = 30    # seconds between feed checks
SUMMARY_INTERVAL = 600   # seconds between active alert summaries (0 to disable)
```

Also update the `USER_AGENT` string with your GitHub URL or contact email.
NWS requires a descriptive User-Agent on all API requests:

```python
USER_AGENT = "NWS-RealTime-Monitor/1.0 (github.com/ODST-Aaron/nws-realtime-alerts)"
```

### 5. Create your Discord webhook

1. Right-click your target Discord channel → **Edit Channel**
2. **Integrations** → **Webhooks** → **New Webhook**
3. Give it a name and copy the webhook URL
4. Paste it into `DISCORD_WEBHOOK` in the config block

### 6. Run

**Windows:**
```powershell
py -3.12 weather_alerts.py
```

**Linux/macOS:**
```bash
python3 weather_alerts.py
```

On startup you should see a green Discord embed confirming the service is online,
your site count, and the list of monitored alert types.  
Press `Ctrl+C` to stop — a grey shutdown embed will appear in Discord.

---

## Running as a Background Service (Linux)

To run continuously as a managed system service on Linux:

### Create the service file

```bash
sudo nano /etc/systemd/system/nws-realtime-alerts.service
```

```ini
[Unit]
Description=NWS Real-Time Weather Alert Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/nws-realtime-alerts
ExecStart=/usr/bin/python3 /path/to/nws-realtime-alerts/weather_alerts.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable nws-realtime-alerts
sudo systemctl start nws-realtime-alerts
```

### Manage the service

```bash
# Check status
sudo systemctl status nws-realtime-alerts

# View live logs
sudo journalctl -u nws-realtime-alerts -f

# Restart after config changes
sudo systemctl restart nws-realtime-alerts

# Stop (triggers Discord shutdown notification)
sudo systemctl stop nws-realtime-alerts
```

---

## File Structure

```
nws-realtime-alerts/
├── weather_alerts.py       # Main monitor script
├── requirements.txt        # Python dependencies
├── locations_example.csv   # Example CSV structure
├── CHANGELOG.md            # Version history
├── LICENSE                 # MIT License
├── .gitignore              # Excludes live data files
└── README.md
```

> `locations.csv`, `seen_alerts.json`, and `active_alerts.json` are excluded
> from version control via `.gitignore` to protect site data and prevent
> alert cache conflicts between environments.

---

## Comparison With Standard Polling

| | Standard Polling | This Monitor |
|---|---|---|
| Check method | Full GET every N minutes | HEAD every 30s, GET only on change |
| Typical latency | 2–5 minutes | ~30 seconds |
| API requests/hour | ~30 full fetches | ~120 HEAD + few full fetches |
| Bandwidth | Constant | Minimal — most checks are ~1KB HEAD responses |

---

## Data Source

Alert data provided by the [National Weather Service API](https://www.weather.gov/documentation/services-web-api).  
Geographic site matching powered by [Shapely](https://shapely.readthedocs.io/).

---

## License

MIT — see [LICENSE](LICENSE) for details.
