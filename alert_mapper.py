"""
NWS Alert Mapper
-----------------
Generates a static PNG map for a given NWS alert showing:
  - Alert polygon (for warnings with GeoJSON geometry)
  - County boundaries (for UGC fallback alerts like SPC watches)
  - Affected site pins with labels
  - All monitored site pins (dimmed)
  - State and county boundary lines for geographic context

Called as a module by nws-realtime-alerts. Returns a PNG as bytes
suitable for attaching to a Discord or Slack message.

Dependencies:
    pip install matplotlib cartopy shapely requests
"""

import io
import json
import re
import requests
import numpy as np
from shapely.geometry import shape, Point, MultiPolygon, Polygon

import matplotlib
matplotlib.use("Agg")   # Non-interactive backend — no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import cartopy.crs      as ccrs
import cartopy.feature  as cfeature
from cartopy.io.shapereader import natural_earth, Reader

# ─────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────

# Map appearance
MAP_DPI        = 150
MAP_FIGSIZE    = (10, 7)
PADDING_DEG    = 0.5    # degrees of padding around the alert extent

# Colors
COLOR_POLYGON  = {
    "critical": ("#FF0000", 0.25),   # (fill, alpha)
    "warning":  ("#FF6600", 0.25),
    "watch":    ("#FFCC00", 0.20),
    "advisory": ("#0099FF", 0.20),
}
COLOR_POLYGON_EDGE = {
    "critical": "#CC0000",
    "warning":  "#CC4400",
    "watch":    "#CC9900",
    "advisory": "#0066CC",
}
COLOR_COUNTY_FILL  = (1.0, 0.8, 0.0, 0.15)   # Pale amber for UGC county fill
COLOR_COUNTY_EDGE  = "#CC9900"
COLOR_AFFECTED_PIN = "#FF4444"
COLOR_LABEL_BG     = "white"

# Census Bureau TIGER county shapefile (fetched at runtime, cached in memory)
CENSUS_COUNTY_URL = (
    "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip"
)

# Module-level cache for county geometries so we only fetch once per run
_county_cache: dict | None = None

USER_AGENT = "NWS-AlertMapper/1.0 (github.com/ODST-Aaron/nws-alert-mapper)"
HEADERS    = {"User-Agent": USER_AGENT}


# ─────────────────────────────────────────
#  COUNTY DATA (Census TIGER — runtime fetch)
# ─────────────────────────────────────────

def _load_county_cache() -> dict:
    """
    Fetch the Census Bureau TIGER county shapefile and build a dict
    mapping GEOID (state FIPS + county FIPS, e.g. '05031') to Shapely geometry.

    Result is cached in _county_cache so the file is only fetched once
    per process lifetime.
    """
    global _county_cache
    if _county_cache is not None:
        return _county_cache

    import zipfile
    import tempfile
    import os

    print("  [mapper] Fetching Census county shapefile (one-time)...")
    try:
        resp = requests.get(CENSUS_COUNTY_URL, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  [mapper] ✗ Failed to fetch county shapefile: {e}")
        _county_cache = {}
        return _county_cache

    # Write zip to a temp file and extract
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "counties.zip")
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)

        # Find the .shp file
        shp_path = next(
            (os.path.join(tmpdir, fn) for fn in os.listdir(tmpdir) if fn.endswith(".shp")),
            None,
        )
        if not shp_path:
            print("  [mapper] ✗ No .shp file found in county zip")
            _county_cache = {}
            return _county_cache

        cache = {}
        for record in Reader(shp_path).records():
            # TIGER county records have STATEFP and COUNTYFP attributes
            geoid = record.attributes.get("GEOID", "")
            geom  = shape(record.geometry.__geo_interface__)
            if geoid:
                cache[geoid] = geom

    _county_cache = cache
    print(f"  [mapper] ✓ County shapefile loaded ({len(cache)} counties)")
    return _county_cache


def ugc_to_geoid(ugc: str) -> str | None:
    """
    Convert a NWS UGC county code (e.g. 'ARC031') to a Census GEOID
    (e.g. '05031').

    UGC county format: {state_abbr}C{county_fips_3digit}
    GEOID format: {state_fips_2digit}{county_fips_3digit}

    State FIPS lookup is required for the conversion.
    """
    STATE_FIPS = {
        "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
        "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
        "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
        "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
        "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
        "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
        "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
        "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
        "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
        "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
        "DC": "11", "PR": "72",
    }
    # UGC county format: e.g. ARC031  (state=AR, type=C, fips=031)
    m = re.match(r"^([A-Z]{2})C(\d{3})$", ugc)
    if not m:
        return None
    state_abbr = m.group(1)
    county_fips = m.group(2)
    state_fips = STATE_FIPS.get(state_abbr)
    if not state_fips:
        return None
    return state_fips + county_fips


def get_county_geometries(ugc_codes: list[str]) -> list:
    """
    Return a list of Shapely geometries for the given UGC county codes.
    Only processes codes in ARC/MSC/TNC format (county codes, not zone codes).
    """
    county_codes = [u for u in ugc_codes if re.match(r"^[A-Z]{2}C\d{3}$", u)]
    if not county_codes:
        return []

    cache = _load_county_cache()
    if not cache:
        return []

    geoms = []
    for ugc in county_codes:
        geoid = ugc_to_geoid(ugc)
        if geoid and geoid in cache:
            geoms.append(cache[geoid])
    return geoms


# ─────────────────────────────────────────
#  MAP EXTENT
# ─────────────────────────────────────────

def compute_extent(
    polygon_geom,
    county_geoms: list,
    affected_sites: list,
    padding: float = PADDING_DEG,
) -> tuple[float, float, float, float]:
    """
    Compute the map extent (west, east, south, north) that fits all
    relevant features — polygon, county boundaries, and affected site pins.
    """
    lons, lats = [], []

    if polygon_geom:
        bounds = shape(polygon_geom).bounds   # (minx, miny, maxx, maxy)
        lons += [bounds[0], bounds[2]]
        lats += [bounds[1], bounds[3]]

    for geom in county_geoms:
        b = geom.bounds
        lons += [b[0], b[2]]
        lats += [b[1], b[3]]

    for site in affected_sites:
        lons.append(float(site["lon"]))
        lats.append(float(site["lat"]))

    if not lons:
        # Fallback — continental US
        return -100.0, -80.0, 25.0, 40.0

    return (
        min(lons) - padding,
        max(lons) + padding,
        min(lats) - padding,
        max(lats) + padding,
    )


# ─────────────────────────────────────────
#  CORE MAP RENDERER
# ─────────────────────────────────────────

def render_map(
    alert: dict,
    affected_sites: list,
    tier: str,
) -> bytes | None:
    """
    Generate a PNG map for the given alert.

    Parameters
    ----------
    alert          : NWS alert feature dict (GeoJSON feature)
    affected_sites : list of site dicts that fall within the alert area
    tier           : alert tier string ('critical', 'warning', 'watch', 'advisory')

    Returns
    -------
    PNG image as bytes, or None if rendering failed.
    """
    props      = alert.get("properties", {})
    event      = props.get("event", "Alert")
    geometry   = alert.get("geometry")
    ugc_codes  = props.get("geocode", {}).get("UGC", [])

    # ── Geometry sources ──────────────────
    polygon_geom   = geometry   # May be None
    county_geoms   = []

    if not polygon_geom:
        county_geoms = get_county_geometries(ugc_codes)
        if not county_geoms:
            print(f"  [mapper] ✗ No polygon or county geometry available for {event}")
            return None

    # ── Map extent ────────────────────────
    west, east, south, north = compute_extent(polygon_geom, county_geoms, affected_sites)

    # ── Figure setup ──────────────────────
    proj = ccrs.PlateCarree()
    fig  = plt.figure(figsize=MAP_FIGSIZE, dpi=MAP_DPI, facecolor="#1a1a2e")
    ax   = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent([west, east, south, north], crs=proj)
    ax.set_facecolor("#16213e")

    # ── Base map features ─────────────────
    ax.add_feature(cfeature.OCEAN.with_scale("50m"),      facecolor="#0d1b2a", zorder=1)
    ax.add_feature(cfeature.LAND.with_scale("50m"),       facecolor="#1e2d40", zorder=2)
    ax.add_feature(cfeature.LAKES.with_scale("50m"),      facecolor="#0d1b2a", alpha=0.8, zorder=3)
    ax.add_feature(cfeature.RIVERS.with_scale("50m"),     edgecolor="#0d1b2a", linewidth=0.5, zorder=4)
    ax.add_feature(cfeature.STATES.with_scale("50m"),     edgecolor="#ffffff", linewidth=0.8, alpha=0.6, zorder=5)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"),    edgecolor="#ffffff", linewidth=1.0, zorder=5)

    # County lines (Natural Earth admin-2)
    counties_shp = natural_earth(resolution="10m", category="cultural", name="admin_2_counties")
    ax.add_geometries(
        [r.geometry for r in Reader(counties_shp).records()],
        crs=proj,
        facecolor="none",
        edgecolor="#ffffff",
        linewidth=0.3,
        alpha=0.3,
        zorder=6,
    )

    # ── Alert polygon ─────────────────────
    fill_color, fill_alpha = COLOR_POLYGON.get(tier, ("#FFCC00", 0.20))
    edge_color             = COLOR_POLYGON_EDGE.get(tier, "#CC9900")

    if polygon_geom:
        ax.add_geometries(
            [shape(polygon_geom)],
            crs=proj,
            facecolor=fill_color,
            edgecolor=edge_color,
            linewidth=2.0,
            alpha=fill_alpha,
            zorder=7,
        )
        # Solid edge outline on top
        ax.add_geometries(
            [shape(polygon_geom)],
            crs=proj,
            facecolor="none",
            edgecolor=edge_color,
            linewidth=2.0,
            zorder=8,
        )

    # ── County fills (UGC fallback) ───────
    if county_geoms:
        ax.add_geometries(
            county_geoms,
            crs=proj,
            facecolor=COLOR_COUNTY_FILL,
            edgecolor=COLOR_COUNTY_EDGE,
            linewidth=1.5,
            zorder=7,
        )

    # ── Affected site pins ────────────────
    affected_lons = [float(s["lon"]) for s in affected_sites]
    affected_lats = [float(s["lat"]) for s in affected_sites]

    ax.scatter(
        affected_lons,
        affected_lats,
        s=60,
        color=COLOR_AFFECTED_PIN,
        edgecolors="white",
        linewidths=0.8,
        zorder=11,
        transform=proj,
    )

    # Labels for affected sites
    for site in affected_sites:
        lat  = float(site["lat"])
        lon  = float(site["lon"])
        name = site.get("name", "")
        ax.annotate(
            name,
            xy=(lon, lat),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=6,
            color="white",
            transform=proj,
            zorder=12,
            path_effects=[
                pe.withStroke(linewidth=2, foreground="black")
            ],
        )

    # ── Title ─────────────────────────────
    headline = props.get("headline", event)
    if len(headline) > 80:
        headline = headline[:77] + "..."
    ax.set_title(
        headline,
        fontsize=9,
        color="white",
        pad=8,
        loc="left",
    )

    # ── Legend ────────────────────────────
    legend_elements = [
        mpatches.Patch(facecolor=fill_color, edgecolor=edge_color,
                       alpha=0.6, label="Alert Area"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=COLOR_AFFECTED_PIN,
                   markersize=7, linewidth=0, label=f"Affected Sites ({len(affected_sites)})"),
    ]
    legend = ax.legend(
        handles=legend_elements,
        loc="lower left",
        fontsize=7,
        facecolor="#1a1a2e",
        edgecolor="#444444",
        labelcolor="white",
        framealpha=0.9,
    )

    # ── Render to bytes ───────────────────
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=MAP_DPI, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────
#  PUBLIC INTERFACE
# ─────────────────────────────────────────

def generate_alert_map(
    alert: dict,
    affected_sites: list,
    tier: str,
) -> bytes | None:
    """
    Public entry point. Wraps render_map with error handling so a map
    failure never crashes the calling script.

    Returns PNG bytes on success, None on failure.
    """
    try:
        return render_map(alert, affected_sites, tier)
    except Exception as e:
        print(f"  [mapper] ✗ Map generation failed: {e}")
        return None
