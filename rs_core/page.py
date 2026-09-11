"""The bookmarks for one body, as a page you can open.

A bookmark is a PNG and a JSON sidecar. The PNG is readable one at a time and
the sidecar is not readable at all, so eleven of them on one body is eleven
files to open and nothing that compares them.

This writes a table instead: one row per bookmark, the card beside it, sorted
by the location it was taken at. Written into the folder the cards already
live in, so the images are one relative path away and the page works from a
file:// URL with nothing serving it.

Regenerated on every open. The bookmarks are the truth and this is a view of
them, so a stale page is a bug waiting rather than a cache.

No tkinter, so it can be checked without EDMC in the way. See
rs_tests/test_page.py.
"""

import html
import os

from rs_core import palette
from rs_core.logging import logger
from rs_core.spotcard import card_dir

BAD = r'<>:"/\|?*'


def filename(body):
    """One page per body, named after it."""
    safe = "".join("_" if ch in BAD else ch for ch in (body or "body")).strip()
    return (safe or "body") + ".html"


def _sort_key(record):
    """By location, then by when it was marked.

    Location first because that is the number on the target panel and the
    order somebody works a body in. A bookmark with no location - marked from
    orbit, or with the destination deselected - sorts last rather than as
    location zero.
    """
    index = record.get("location_index")
    return (index is None, index or 0, str(record.get("marked_at") or ""))


def _cell(value, dash="-"):
    if value is None or value == "":
        return dash
    return html.escape(str(value))


def _coords(record):
    lat, lon = record.get("latitude"), record.get("longitude")
    if lat is None or lon is None:
        return "-"
    return f"{float(lat):.6f} / {float(lon):.6f}"


def render(system, body, records):
    """The page, as a string. `records` are cards.for_system entries."""
    rows = []
    for record in sorted(records, key=_sort_key):
        image = html.escape(os.path.basename(record.get("path") or record.get("card") or ""))
        rows.append(f"""  <tr>
    <td class="num">{_cell(record.get('location_index'))}</td>
    <td class="material">{_cell(record.get('commodity'), 'unknown')}</td>
    <td class="num">{_cell(record.get('rigs'))}</td>
    <td class="num">{_cell(record.get('heading'))}</td>
    <td class="coords">{_coords(record)}</td>
    <td class="when">{_cell(str(record.get('marked_at') or '').split('.')[0])}</td>
    <td class="card"><a href="{image}"><img src="{image}" alt="bookmark"></a></td>
  </tr>""")

    count = len(records)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(body)} - bookmarks</title>
<style>
  body {{ background: {palette.BG}; color: {palette.FG};
         font: 14px/1.5 "Segoe UI", system-ui, sans-serif;
         margin: 0; padding: 28px; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 2px; }}
  .system {{ color: {palette.MUTED}; margin: 0 0 22px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ text-align: left; font-size: .72rem; letter-spacing: .1em;
        text-transform: uppercase; color: {palette.MUTED};
        border-bottom: 1px solid {palette.RULE}; padding: 0 12px 6px 0; }}
  td {{ border-bottom: 1px solid {palette.RULE}; padding: 10px 12px 10px 0;
        vertical-align: middle; }}
  .num, .coords, .when {{ font-family: Consolas, ui-monospace, monospace;
                          font-variant-numeric: tabular-nums; }}
  .num {{ text-align: right; width: 1%; white-space: nowrap; }}
  .coords {{ color: {palette.GOOD}; white-space: nowrap; }}
  .when {{ color: {palette.MUTED}; white-space: nowrap; }}
  .material {{ color: {palette.ACCENT}; font-weight: 600; }}
  .card img {{ display: block; width: 320px; max-width: 40vw;
               border: 1px solid {palette.RULE}; }}
  footer {{ color: {palette.MUTED}; font-size: .78rem; margin-top: 24px; }}
</style>
</head>
<body>
<h1>{html.escape(body)}</h1>
<p class="system">{html.escape(system or '')} &middot;
   {count} bookmark{'' if count == 1 else 's'}</p>
<table>
<thead><tr>
  <th>Loc</th><th>Material</th><th>Rigs</th><th>Hdg</th>
  <th>Coordinates</th><th>Marked</th><th>Card</th>
</tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
<footer>What a mining location holds is in no game feed. These are what you
found and wrote down.</footer>
</body>
</html>
"""


def write(system, body, records, root=None):
    """Write the page beside the cards and return its path, or None.

    Beside them on purpose: the images are then one relative path away, and
    the page opens from a file:// URL with nothing serving it.
    """
    if not records:
        return None
    folder = card_dir(system) if root is None else root
    path = os.path.join(folder, filename(body))
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(render(system, body, records))
    except OSError as err:
        logger.warning(f"could not write {path}: {err}")
        return None
    return path
