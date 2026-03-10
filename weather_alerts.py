"""
NWS Real-Time Weather Alert Monitor
------------------------------------
Uses HTTP Last-Modified header checking to minimize API load while achieving
near-real-time alert detection (~30 second latency vs standard polling).

Architecture:
  - HEAD request every HEAD_INTERVAL seconds (lightweight, ~1KB)
  - Full fetch + processing only when Last-Modified header has changed
  - Site matching via Shapely polygon intersection
  - Tiered Discord embeds (critical / warning / watch / advisory)
  - Startup and shutdown notifications via SIGINT/SIGTERM handlers
"""

import requests
import json
import csv
import time
import signal
import sys
from datetime import datetime, timezone
from shapely.geometry import Point, Polygon

# ─────────────────────────────────────────
#  CONFIGURATION  —  edit these values
# ─────────────────────────────────────────
CSV_FILE        = r"C:\nws-realtime-alerts\locations.csv"
DISCORD_WEBHOOK = "YOUR_DISCORD_WEBHOOK_URL_HERE"
CACHE_FILE      = r"C:\nws-realtime-alerts\seen_alerts.json"
ACTIVE_FILE     = r"C:\nws-realtime-alerts\active_alerts.json"

HEAD_INTERVAL   = 30    # seconds between lightweight HEAD checks
SUMMARY_INTERVAL = 600  # seconds between active alert summaries (0 to disable)

NWS_ALERTS_URL  = "https://api.weather.gov/alerts/active"
USER_AGENT      = "NWS-RealTime-Monitor/1.0 (github.com/ODST-Aaron/nws-realtime-alerts)"

# ─────────────────────────────────────────
#  SEVERITY TIERS
# ─────────────────────────────────────────
SEVERITY_TIERS = {
    "critical": [
        "Tornado Emergency",
        "Tornado Warning",
        "Flash Flood Emergency",
    ],
    "warning": [
        "Severe Thunderstorm Warning",
        "Flash Flood Warning",
        "Blizzard Warning",
        "Ice Storm Warning",
        "Extreme Wind Warning",
        "Winter Storm Warning",
    ],
    "watch": [
        "Tornado Watch",
        "Severe Thunderstorm Watch",
        "Winter Storm Watch",
        "High Wind Warning",
    ],
    "advisory": [
        "Wind Advisory",
        "Significant Weather Advisory",
        "Special Weather Statement",
        "Extreme Cold Warning",
        "Dust Storm Warning",
    ],
}

MONITORED_ALERTS = [e for events in SEVERITY_TIERS.values() for e in events]

# ─────────────────────────────────────────
#  EMBED COLORS & EMOJIS
# ─────────────────────────────────────────
TIER_COLORS = {
    "critical": 0xFF0000,
    "warning":  0xFF6600,
    "watch":    0xFFCC00,
    "advisory": 0x0099FF,
    "status":   0x00CC44,
    "shutdown": 0x888888,
}

TIER_EMOJIS = {
    "critical": "🚨",
    "warning":  "⚠️",
    "watch":    "👀",
    "advisory": "🔵",
}

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def get_tier(event: str) -> str:
    for tier, events in SEVERITY_TIERS.items():
        if event in events:
            return tier
    return "advisory"


def load_locations(csv_path: str) -> list:
    locations = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            sample = f.read(1024)
            f.seek(0)
            delimiter = "\t" if "\t" in sample else ","
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                try:
                    locations.append({
                        "customer": row.get("Customer", "").strip(),
                        "name":     row.get("Name", "").strip(),
                        "sitetype": row.get("SiteType", "").strip(),
                        "lat":      float(row["Latitude"]),
                        "lon":      float(row["Longitude"]),
                        "city":        row.get("City", "").strip(),
                        "county":      row.get("County", "").strip(),
                        "county_code": row.get("CountyCode", "").strip().upper(),
                        "state":       row.get("State", "").strip(),
                        "zone":        row.get("Zone", "").strip().upper(),
                    })
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        print(f"✗ CSV not found: {csv_path}")
    return locations


def load_json(path: str, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: str, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def format_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d %I:%M %p UTC")
    except Exception:
        return iso_str or "Unknown"


def format_site_line(site: dict) -> str:
    parts = []
    if site.get("customer"):
        parts.append(site["customer"])
    parts.append(site.get("name", "Unknown"))
    if site.get("sitetype"):
        parts.append(site["sitetype"])
    coord = f"({site['lat']}, {site['lon']})"
    city   = site.get("city", "")
    county = site.get("county", "")
    state  = site.get("state", "")
    if city and county:
        location = f"[{city}, {county} County, {state}]"
    elif county:
        location = f"[{county} County, {state}]"
    elif city:
        location = f"[{city}, {state}]"
    else:
        location = f"[{state}]"
    return "• " + " — ".join(parts) + f"  {coord}  {location}"


def format_site_line_compact(site: dict) -> str:
    """
    Compact site line — omits coordinates to save space when the site list
    is too long to fit in a Discord field at full format.
    Format: • Customer — Name  [City, County County, State]
    """
    parts = []
    if site.get("customer"):
        parts.append(site["customer"])
    parts.append(site.get("name", "Unknown"))
    city   = site.get("city", "")
    county = site.get("county", "")
    state  = site.get("state", "")
    if city and county:
        location = f"[{city}, {county} County, {state}]"
    elif county:
        location = f"[{county} County, {state}]"
    elif city:
        location = f"[{city}, {state}]"
    else:
        location = f"[{state}]"
    return "• " + " — ".join(parts) + f"  {location}"


def build_site_field(sites: list, field_limit: int = 1000) -> str:
    """
    Build the site list string for a Discord embed field.
    Tries full format first. If it exceeds field_limit, switches to compact
    format. If still too long, truncates and appends an overflow note.

    field_limit is set to 1000 (under Discord's 1024 hard limit) for safety.
    """
    # Try full format
    full_lines = [format_site_line(s) for s in sites]
    full_text  = "\n".join(full_lines)
    if len(full_text) <= field_limit:
        return full_text

    # Try compact format
    compact_lines = [format_site_line_compact(s) for s in sites]
    compact_text  = "\n".join(compact_lines)
    if len(compact_text) <= field_limit:
        return compact_text

    # Truncate compact lines and add overflow note
    fitted = []
    overflow_note = ""
    for i, line in enumerate(compact_lines):
        candidate = "\n".join(fitted + [line])
        # Reserve ~40 chars for the overflow note
        if len(candidate) > field_limit - 40:
            remaining = len(compact_lines) - i
            overflow_note = f"\n… and {remaining} more site(s) affected"
            break
        fitted.append(line)
    return "\n".join(fitted) + overflow_note


# ─────────────────────────────────────────
#  NWS API
# ─────────────────────────────────────────
HEADERS = {"User-Agent": USER_AGENT}


# Tracks consecutive HEAD checks without a Last-Modified header so we can
# fall back to a full fetch after FALLBACK_FETCH_INTERVAL seconds.
FALLBACK_FETCH_INTERVAL = 30    # seconds — full fetch if no Last-Modified header

_last_fallback_fetch: float = 0.0   # module-level timestamp


def check_last_modified(last_known: str | None) -> tuple[bool, str | None]:
    """
    Send a HEAD request to the NWS alerts endpoint.
    Returns (changed: bool, new_last_modified: str | None).

    'changed' is True when:
      - The Last-Modified header is present and differs from last_known, OR
      - The Last-Modified header is absent and FALLBACK_FETCH_INTERVAL seconds
        have elapsed since the last fallback fetch (NWS sometimes omits this
        header, which would otherwise prevent any fetches from occurring).
    """
    global _last_fallback_fetch
    try:
        resp = requests.head(NWS_ALERTS_URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        lm = resp.headers.get("Last-Modified")

        if lm:
            # Normal path — header present
            if lm != last_known:
                return True, lm
            return False, last_known
        else:
            # Header absent — fall back to interval-based polling
            now = time.time()
            if now - _last_fallback_fetch >= FALLBACK_FETCH_INTERVAL:
                print(f"  ⚠ Last-Modified header absent — fallback fetch triggered")
                _last_fallback_fetch = now
                return True, last_known
            return False, last_known

    except requests.exceptions.RequestException as e:
        print(f"  ✗ HEAD request failed: {e}")
        return False, last_known


def fetch_alerts() -> list:
    """Full GET fetch of active alerts. Only called when Last-Modified changed."""
    try:
        resp = requests.get(NWS_ALERTS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json().get("features", [])
    except requests.exceptions.RequestException as e:
        print(f"  ✗ GET request failed: {e}")
        return []


def get_affected_sites(alert: dict, locations: list) -> list:
    """
    Match sites against an alert using two methods:

    1. Polygon matching (preferred) — uses the alert's GeoJSON geometry to
       check whether a site's coordinates fall inside the alert area.
       Most Warnings and some Watches include polygon geometry.

    2. UGC zone code fallback — used when NWS omits polygon geometry (common
       for SPC Tornado/Severe Thunderstorm Watches, which are defined by
       county FIPS lists rather than drawn polygons). Matches each site's
       Zone code from the CSV against the UGC codes in the alert's geocode
       field (e.g. ARC019, ARZ026).

    The method used is logged to the console for each alert.
    """
    props = alert.get("properties", {})

    # ── Stage 1: Polygon matching ──────────────────────────────────────────
    geometry = alert.get("geometry")
    if geometry:
        try:
            coords   = geometry["coordinates"]
            geo_type = geometry["type"]

            polygons = []
            if geo_type == "Polygon":
                polygons = [Polygon(coords[0])]
            elif geo_type == "MultiPolygon":
                polygons = [Polygon(ring[0]) for ring in coords]

            if polygons:
                affected = []
                for site in locations:
                    pt = Point(site["lon"], site["lat"])
                    if any(poly.contains(pt) for poly in polygons):
                        affected.append(site)
                if affected:
                    print(f"    matched via polygon ({len(affected)} site(s))")
                return affected
        except Exception as e:
            print(f"  ✗ Polygon error: {e} — falling back to zone matching")

    # ── Stage 2: UGC zone code fallback ───────────────────────────────────
    # NWS SPC watches typically omit polygon geometry and instead list
    # county/zone UGC codes in properties.geocode.UGC (e.g. ["ARC019","ARZ026"])
    ugc_codes = set(props.get("geocode", {}).get("UGC", []))
    if not ugc_codes:
        # Some alerts use affectedZones URLs — extract the code from the end
        zone_urls = props.get("affectedZones", [])
        ugc_codes = {url.split("/")[-1] for url in zone_urls if url}

    if ugc_codes:
        affected = []
        for site in locations:
            site_zone        = site.get("zone", "")
            site_county_code = site.get("county_code", "")
            if (site_zone and site_zone in ugc_codes) or                (site_county_code and site_county_code in ugc_codes):
                affected.append(site)
        if affected:
            print(f"    matched via UGC zone/county fallback ({len(affected)} site(s))")
        return affected

    print(f"  ✗ No geometry or UGC codes found — alert cannot be matched")
    return []


# ─────────────────────────────────────────
#  DISCORD
# ─────────────────────────────────────────
def post_embed(embed: dict) -> bool:
    try:
        resp = requests.post(
            DISCORD_WEBHOOK,
            json={"embeds": [embed]},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  ✗ Discord error: {e}")
        return False


def send_startup(locations: list):
    tier_lines = "\n".join(
        f"**{tier.upper()}**  {TIER_EMOJIS.get(tier, '')}  —  {', '.join(events)}"
        for tier, events in SEVERITY_TIERS.items()
    )
    embed = {
        "title":       "🟢  NWS Real-Time Alert Monitor — Started",
        "description": (
            f"Service is **online**.\n"
            f"Checking for feed updates every **{HEAD_INTERVAL} seconds** via `Last-Modified` header.\n\n"
            f"**Sites loaded:** {len(locations)}\n\n"
            f"**Monitored alert types:**\n{tier_lines}"
        ),
        "color":     TIER_COLORS["status"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer":    {"text": "NWS Real-Time Alert Monitor"},
    }
    post_embed(embed)
    print(f"✓ Startup notification sent  ({len(locations)} sites loaded)")


def send_shutdown():
    embed = {
        "title":       "⛔  NWS Real-Time Alert Monitor — Stopped",
        "description": "Service has been **shut down**. No further alerts will be sent until restarted.",
        "color":       TIER_COLORS["shutdown"],
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "footer":      {"text": "NWS Real-Time Alert Monitor"},
    }
    post_embed(embed)
    print("✓ Shutdown notification sent")


def send_startup_active_summary(locations: list, seen_alerts: list) -> tuple[list, dict]:
    """
    Runs once on startup. Fetches the current NWS feed and checks for any
    monitored alerts already affecting your sites — regardless of seen cache.

    - Alerts NOT in seen cache: posted as normal alert embeds and added to cache
    - Alerts already in seen cache: listed in a single "already active" summary
      embed so the team has situational awareness without duplicate full embeds

    Returns updated (seen_alerts, active_alerts) so main() can use them.
    """
    print("  Checking for alerts already active at startup...")
    alerts = fetch_alerts()
    if not alerts:
        print("  No alerts retrieved at startup.")
        return seen_alerts, {}

    active_alerts  = {}
    already_seen   = []   # active + previously notified
    newly_notified = 0

    current_ids = {a.get("id") for a in alerts}

    for alert in alerts:
        alert_id = alert.get("id", "")
        event    = alert.get("properties", {}).get("event", "")

        if event not in MONITORED_ALERTS:
            continue

        affected = get_affected_sites(alert, locations)
        if not affected:
            continue

        tier  = get_tier(event)
        props = alert["properties"]

        # Track in active_alerts regardless
        active_alerts[alert_id] = {
            "event": event,
            "tier":  tier,
            "sites": [s["name"] for s in affected],
            "sent":  datetime.now(timezone.utc).isoformat(),
        }

        if alert_id in seen_alerts:
            # Already notified in a previous run — collect for summary
            already_seen.append({
                "event":    event,
                "tier":     tier,
                "expires":  format_time(props.get("expires", "")),
                "sites":    affected,
                "headline": props.get("headline", ""),
            })
        else:
            # New alert — post full embed and add to cache
            send_alert(alert, affected)
            seen_alerts.append(alert_id)
            newly_notified += 1
            print(f"  → NEW at startup: {tier.upper()} | {event} | {len(affected)} site(s)")

    # Post a single summary embed for all already-seen active alerts
    if already_seen:
        lines = []
        for item in already_seen:
            emoji    = TIER_EMOJIS.get(item["tier"], "⚠️")
            sitelist = build_site_field(item["sites"])
            lines.append(
                f"{emoji} **{item['event']}** — expires {item['expires']}\n{sitelist}"
            )

        embed = {
            "title":       "📋  Alerts Active at Startup",
            "description": (
                "The following alerts were already active when the monitor started.\n"
                "These were previously notified and will not re-fire as new alerts.\n\n"
                + "\n\n".join(lines)
            ),
            "color":       0xAAAAAA,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "footer":      {"text": "NWS Real-Time Alert Monitor"},
        }
        post_embed(embed)
        print(f"  → {len(already_seen)} already-active alert(s) summarised in Discord")

    if not already_seen and newly_notified == 0:
        print("  No active alerts affecting monitored sites at startup.")

    # Prune seen cache of IDs no longer in the feed
    seen_alerts = [i for i in seen_alerts if i in current_ids]

    return seen_alerts, active_alerts


def send_alert(alert: dict, affected_sites: list):
    props    = alert["properties"]
    event    = props.get("event", "Unknown Event")
    severity = props.get("severity", "Unknown")
    headline = props.get("headline", "No headline available")
    onset    = format_time(props.get("onset", ""))
    expires  = format_time(props.get("expires", ""))
    tier     = get_tier(event)
    emoji    = TIER_EMOJIS.get(tier, "⚠️")

    site_text = build_site_field(affected_sites)

    embed = {
        "title":       f"{emoji}  {event}",
        "description": headline,
        "color":       TIER_COLORS[tier],
        "fields": [
            {"name": "Severity",                                  "value": severity,         "inline": True},
            {"name": "Tier",                                      "value": tier.upper(),     "inline": True},
            {"name": "Onset",                                     "value": onset,            "inline": True},
            {"name": "Expires",                                   "value": expires,          "inline": True},
            {"name": f"Affected Sites ({len(affected_sites)})",   "value": site_text or "None", "inline": False},
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer":    {"text": f"NWS Real-Time Alert Monitor  •  ID: {alert['id'][-12:]}"},
    }
    post_embed(embed)


def send_summary(active_alerts: dict):
    if not active_alerts:
        return
    lines = [
        f"{TIER_EMOJIS.get(data.get('tier', 'advisory'), '⚠️')} "
        f"**{data['event']}** — {len(data['sites'])} site(s) affected"
        for data in active_alerts.values()
    ]
    embed = {
        "title":       "📋  Active Alert Summary",
        "description": "\n".join(lines),
        "color":       0xAAAAAA,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "footer":      {"text": "NWS Real-Time Alert Monitor"},
    }
    post_embed(embed)


# ─────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────
def main():
    locations     = load_locations(CSV_FILE)
    seen_alerts   = load_json(CACHE_FILE, [])
    active_alerts = load_json(ACTIVE_FILE, {})

    if not locations:
        print("✗ No locations loaded — check your CSV path and format.")
        sys.exit(1)

    # ── Graceful shutdown ──────────────────
    def handle_shutdown(sig, frame):
        print("\n⛔ Shutdown signal received...")
        send_shutdown()
        save_json(CACHE_FILE, seen_alerts)
        save_json(ACTIVE_FILE, active_alerts)
        sys.exit(0)

    signal.signal(signal.SIGINT,  handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    send_startup(locations)

    # Check for any alerts already active at startup
    seen_alerts, active_alerts = send_startup_active_summary(locations, seen_alerts)
    save_json(CACHE_FILE, seen_alerts)
    save_json(ACTIVE_FILE, active_alerts)

    last_modified = None
    last_summary  = time.time()

    print(
        f"✓ Monitoring active — HEAD check every {HEAD_INTERVAL}s, "
        f"full fetch only on feed change\n"
    )

    while True:
        now = time.time()
        ts  = datetime.now().strftime("%H:%M:%S")

        # ── Lightweight HEAD check ─────────
        changed, last_modified = check_last_modified(last_modified)

        if changed:
            print(f"[{ts}] Feed updated — fetching alerts...")
            alerts = fetch_alerts()
            current_ids = {a.get("id") for a in alerts}

            for alert in alerts:
                alert_id = alert.get("id", "")
                event    = alert.get("properties", {}).get("event", "")

                if event not in MONITORED_ALERTS:
                    continue
                if alert_id in seen_alerts:
                    continue

                affected = get_affected_sites(alert, locations)
                if not affected:
                    continue

                tier = get_tier(event)
                print(f"  → {tier.upper()} | {event} | {len(affected)} site(s) affected")
                send_alert(alert, affected)

                seen_alerts.append(alert_id)
                active_alerts[alert_id] = {
                    "event": event,
                    "tier":  tier,
                    "sites": [s["name"] for s in affected],
                    "sent":  datetime.now(timezone.utc).isoformat(),
                }

            # Prune expired alerts from active tracking
            active_alerts = {k: v for k, v in active_alerts.items() if k in current_ids}

            save_json(CACHE_FILE, seen_alerts)
            save_json(ACTIVE_FILE, active_alerts)

        else:
            print(f"[{ts}] No feed change")

        # ── Periodic summary ───────────────
        if SUMMARY_INTERVAL > 0 and now - last_summary >= SUMMARY_INTERVAL:
            send_summary(active_alerts)
            last_summary = now

        time.sleep(HEAD_INTERVAL)


if __name__ == "__main__":
    main()
