# Quick Start Guide

Get the NWS Real-Time Alert Monitor running in under 5 minutes.

## Prerequisites

- Python 3.12+ installed
- Internet connectivity
- Discord or Slack webhook URL

## Installation (Windows)

### 1. Install Python Dependencies

```bash
pip install requests shapely matplotlib cartopy numpy
```

**Note:** If `cartopy` fails to install, use conda:
```bash
conda install -c conda-forge cartopy
```

### 2. Download the Project

```bash
git clone https://github.com/ODST-Aaron/nws-realtime-alerts.git
cd nws-realtime-alerts
```

### 3. Create Your Locations CSV

Create `locations.csv` with your monitored sites. Minimum required format:

```csv
Customer,Name,SiteType,Latitude,Longitude,City,County,CountyCode,State,Zone
Acme ISP,Tower 1,Tower,35.8423,-90.7043,Jonesboro,Craighead,ARC031,AR,ARZ026
Acme ISP,POP North,POP,35.9123,-90.6543,Jonesboro,Craighead,ARC031,AR,ARZ026
```

**Don't have Zone/CountyCode data?** Use the bulk lookup utility:

```bash
# Edit locations.csv with just Customer,Name,Latitude,Longitude
py -3.12 bulk_zone_lookup.py
# This auto-populates Zone, CountyCode, County, City
```

### 4. Configure Webhooks

Edit `weather_alerts.py`:

```python
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE"
SLACK_WEBHOOK   = None  # or your Slack webhook URL
```

**Getting webhook URLs:**
- **Discord:** Server Settings → Integrations → Webhooks → New Webhook
- **Slack:** Workspace Settings → Manage Apps → Incoming Webhooks

### 5. Run the Monitor

```bash
py -3.12 weather_alerts.py
```

You should see:
```
✓ Startup notification sent  (X sites loaded)
  Checking for alerts already active at startup...
✓ Monitoring active — HEAD check every 30s, full fetch only on feed change
```

Press `Ctrl+C` to stop (sends graceful shutdown notification).

## Installation (Linux)

```bash
# Install system dependencies
sudo apt-get install python3-pip libgeos-dev libproj-dev proj-data proj-bin

# Clone repository
git clone https://github.com/ODST-Aaron/nws-realtime-alerts.git
cd nws-realtime-alerts

# Install Python dependencies
pip3 install -r requirements.txt

# Create locations.csv (see step 3 above)
# Configure webhooks (see step 4 above)

# Run
python3 weather_alerts.py
```

## Troubleshooting

### "No locations loaded"
- Check `locations.csv` exists in the same directory as `weather_alerts.py`
- Verify CSV has `Latitude` and `Longitude` columns
- Make sure coordinates are decimal degrees (not DMS)

### "cartopy install failed"
- Use conda: `conda install -c conda-forge cartopy`
- Or disable maps: Set `ENABLE_MAPS = False` in `weather_alerts.py`

### "Discord error" / "Slack error"
- Verify webhook URL is correct
- Test webhook with curl:
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{"content":"Test"}' YOUR_WEBHOOK_URL
  ```

### Maps not generating
- Verify cartopy installed: `python -c "import cartopy; print(cartopy.__version__)"`
- Check GEOS/PROJ libraries installed
- Disable maps as workaround: `ENABLE_MAPS = False`

## Next Steps

- Customize monitored alert types in `SEVERITY_TIERS`
- Adjust polling intervals (`HEAD_INTERVAL`, `SUMMARY_INTERVAL`)
- Set up as a Windows service (NSSM) or Linux systemd service
- Review full README for advanced configuration

## Getting Help

- Check the full [README.md](README.md)
- Open an issue on GitHub
- Review [CONTRIBUTING.md](CONTRIBUTING.md) for development setup
