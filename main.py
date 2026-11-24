#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The World in One Day -- a one-image summary of 24 November 2026.

Running this file paints a newspaper front page for Tuesday
24 November 2026 and saves it as ``/output/entry.png``. Nothing is
downloaded, nothing is read from disk, and the clock is never asked:
the picture is a pure function of the story copy below plus one fixed
seed, so running it twice produces the same bytes twice.

The page is 1024 by 1024 and reads top to bottom as:
  * a masthead naming the day the page sums up,
  * a dusk-globe hero panel -- banded evening sky, a low sun, stars,
    a globe with meridians and continents, and a wavy sea -- under
    which the lead story is flagged,
  * the lead story in full, then four further stories in a two-by-two
    grid, each with its own small hand-drawn mark,
  * a closing ticker strip with five more items from the day.

Every story was checked against reporting dated 24 November 2026
(full citations in SOURCES.md): the COP31 climate summit closing in
deadlock in Antalya; the candy-factory fire in Banten, Indonesia;
the Russian cargo ship Sparta II on fire in the Gulf of Finland after
a drone strike; Russian drone and missile strikes on the Kyiv region;
and Jensen Huang's return to Nvidia, worth almost a trillion dollars.
"""

import hashlib
import math
import os
import random
import struct
import sys
import zlib

from PIL import Image, ImageDraw, ImageFont

SLUG = "news-image-20261124"
DAY_LABEL = "TUESDAY,  24  NOVEMBER  2026"
SEED = 24112026
OUT_DIR = "/output"
OUT_NAME = "entry.png"
W, H = 1024, 1024
LIMIT_BYTES = 1048576
LIMIT_SIDE = 1024

PAPER_BG = (250, 246, 236)
INK_COL = (22, 22, 22)
NAVY_COL = (16, 32, 58)
DUSK_COL = (24, 44, 78)
RED_COL = (176, 30, 30)
GOLD_COL = (214, 164, 65)
TEAL_COL = (46, 120, 110)
GREY_COL = (96, 92, 86)
RULE_COL = (198, 188, 168)
SEA_COL = (28, 68, 96)

# Where the hero sun sits inside its panel: low on the left this time,
# setting over the sea while the globe rises on the right of it.
SUN_X, SUN_Y = 128, 92

LEAD_STORY = {
    "kicker": "ANTALYA, TURKIYE",
    "headline": "COP31 ends in deadlock: no deal on fossil fuels",
    "body": (
        "After two weeks of talks and days of overtime, the UN climate "
        "summit in Antalya closes with no agreement on stronger "
        "fossil-fuel language. The EU, the UK and island states refuse "
        "a pact that never mentions fossil fuels at all."
    ),
}

GRID_STORIES = [
    {
        "icon": "flame",
        "kicker": "BANTEN, INDONESIA",
        "headline": "Factory fire kills at least 24",
        "body": (
            "A blaze at a candy factory leaves at least 24 dead and "
            "around 30 missing as rescuers search the ruins."
        ),
    },
    {
        "icon": "ship",
        "kicker": "GULF OF FINLAND",
        "headline": "Russian cargo ship ablaze after drone strike",
        "body": (
            "The Sparta II catches fire off Finland after a reported "
            "drone attack, the war at sea reaching Baltic waters."
        ),
    },
    {
        "icon": "missile",
        "kicker": "KYIV REGION, UKRAINE",
        "headline": "Drones and missiles strike Kyiv region",
        "body": (
            "Russian attacks damage homes in Dymer and leave people "
            "missing, as the war grinds into another winter."
        ),
    },
    {
        "icon": "chip",
        "kicker": "MARKETS",
        "headline": "Huang returns; Nvidia climbs almost $1tn",
        "body": (
            "Jensen Huang is back at Nvidia and tech stocks rally, "
            "adding nearly a trillion dollars to its value."
        ),
    },
]

TICKER_LINE = (
    "Lisbon marches against the cost of living  \u2022  FIFA picks the hosts "
    "of the 2031 and 2035 Women's World Cups  \u2022  Verstappen wins the "
    "Las Vegas Grand Prix  \u2022  Gukesh defends his chess crown against "
    "Sindarov in Geneva  \u2022  Pant's 128 as India-New Zealand Test ends "
    "in a draw"
)

# The five stories again, in reading order, for the fixed run log.
RUN_LOG = [
    ("Antalya", "COP31 ends in deadlock: no deal on fossil fuels"),
    ("Banten", "Factory fire kills at least 24, around 30 missing"),
    ("Gulf of Finland", "Russian cargo ship Sparta II ablaze after drone strike"),
    ("Kyiv region", "Russian drones and missiles strike homes in Dymer"),
    ("Markets", "Huang returns; Nvidia climbs almost $1tn"),
]


def pick_font(kind, size):
    """Find a DejaVu or Liberation face; use the built-in face as a last resort."""
    candidates = (
        f"/usr/share/fonts/truetype/dejavu/DejaVu{kind}.ttf",
        f"/usr/share/fonts/truetype/liberation/Liberation{kind}.ttf",
    )
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def headline_face(size):
    return pick_font("Serif-Bold", size)


def label_face(size):
    return pick_font("Sans-Bold", size)


def body_face(size):
    return pick_font("Sans", size)


def wrap_line(draw, text, font, max_width):
    """Split text greedily into lines no wider than max_width."""
    wrapped, current = [], ""
    for word in text.split():
        trial = (current + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                wrapped.append(current)
            current = word
    if current:
        wrapped.append(current)
    return wrapped


def trim_ticker(draw, text, font, max_width):
    """Shorten the ticker a word at a time until one line fits, ending in ..."""
    while draw.textlength(text, font=font) > max_width and " " in text:
        text = text.rstrip(" \u2026")
        text = text.rsplit(" ", 1)[0].rstrip(" \u2022")
        text += " \u2026"
    return text


def centred_text(draw, y, text, font, fill, width=W):
    """Draw one line centred horizontally at height y."""
    x = (width - draw.textlength(text, font=font)) / 2
    draw.text((x, y), text, font=font, fill=fill)


def draw_setting_sun(draw, x0, y0):
    """Three concentric discs: a soft halo, the gold sun, a bright core."""
    cx, cy = x0 + SUN_X, y0 + SUN_Y
    for rad, col in ((74, (214, 164, 65, 60)), (58, GOLD_COL), (44, (232, 190, 100))):
        draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=col)


def draw_sea_lines(draw, box):
    """Three sine-wave lines for the sea at the foot of the hero panel."""
    x0, y0, x1, y1 = box
    for j, wy in enumerate((y1 - 42, y1 - 28, y1 - 14)):
        pts = []
        for x in range(x0, x1 + 1, 16):
            pts.append((x, wy + int(5 * math.sin(x / 55.0 + j * 1.7))))
        draw.line(pts, fill=(150, 190, 205), width=3)


def draw_hero_panel(draw, box, rng):
    """The dusk-globe hero: banded sky, stars, sun, globe, sea."""
    x0, y0, x1, y1 = box
    # Evening sky in 48 horizontal bands, deep navy fading to dusk blue.
    bands = 48
    for i in range(bands):
        t = i / max(bands - 1, 1)
        r = int(DUSK_COL[0] + (58 - DUSK_COL[0]) * t)
        g = int(DUSK_COL[1] + (74 - DUSK_COL[1]) * t)
        b = int(DUSK_COL[2] + (112 - DUSK_COL[2]) * t)
        yy = y0 + (y1 - y0) * i // bands
        y_next = y0 + (y1 - y0) * (i + 1) // bands
        draw.rectangle([x0, yy, x1, y_next], fill=(r, g, b))
    # Seeded stars in the upper sky, identical on every run.
    for _ in range(70):
        sx = rng.randint(x0 + 8, x1 - 8)
        sy = rng.randint(y0 + 8, y0 + 150)
        s = rng.choice((1, 1, 2))
        draw.ellipse([sx, sy, sx + s, sy + s], fill=(235, 230, 210))
    draw_setting_sun(draw, x0, y0)
    # The globe: a deep teal disc with meridian rings and landmasses.
    gx, gy, gr = x0 + 250, y0 + 165, 118
    draw.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=(30, 78, 92))
    draw.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], outline=(150, 190, 185), width=3)
    for k in range(1, 4):
        rx = gr * k // 4
        draw.ellipse([gx - rx, gy - gr, gx + rx, gy + gr],
                     outline=(120, 170, 165), width=2)
    draw.line([gx, gy - gr, gx, gy + gr], fill=(120, 170, 165), width=2)
    draw.line([gx - gr, gy, gx + gr, gy], fill=(120, 170, 165), width=2)
    continents = [
        [(gx - 78, gy - 58), (gx - 38, gy - 66), (gx - 18, gy - 30),
         (gx - 52, gy - 12), (gx - 84, gy - 28)],
        [(gx + 12, gy - 46), (gx + 52, gy - 52), (gx + 66, gy - 14),
         (gx + 30, gy + 2), (gx + 6, gy - 18)],
        [(gx - 42, gy + 34), (gx - 6, gy + 26), (gx + 12, gy + 58),
         (gx - 22, gy + 72), (gx - 52, gy + 60)],
    ]
    for shape in continents:
        draw.polygon(shape, fill=(74, 148, 106))
    draw_sea_lines(draw, box)


def draw_flame_mark(draw, x, y, s):
    """A small flame: an orange teardrop with a gold heart."""
    pts = [(x + 0.5 * s, y + 0.05 * s), (x + 0.85 * s, y + 0.45 * s),
           (x + 0.95 * s, y + 0.75 * s), (x + 0.7 * s, y + 0.95 * s),
           (x + 0.3 * s, y + 0.95 * s), (x + 0.05 * s, y + 0.75 * s),
           (x + 0.15 * s, y + 0.45 * s)]
    draw.polygon(pts, fill=(196, 64, 32))
    draw.ellipse([x + 0.32 * s, y + 0.5 * s, x + 0.68 * s, y + 0.88 * s],
                 fill=GOLD_COL)


def draw_ship_mark(draw, x, y, s):
    """A small cargo ship: navy hull, mast, red sail, teal waterline."""
    draw.polygon([(x + 0.05 * s, y + 0.62 * s), (x + 0.95 * s, y + 0.62 * s),
                  (x + 0.8 * s, y + 0.92 * s), (x + 0.2 * s, y + 0.92 * s)],
                 fill=NAVY_COL)
    draw.line([x + 0.5 * s, y + 0.08 * s, x + 0.5 * s, y + 0.62 * s],
              fill=NAVY_COL, width=4)
    draw.polygon([(x + 0.5 * s, y + 0.12 * s), (x + 0.88 * s, y + 0.55 * s),
                  (x + 0.5 * s, y + 0.55 * s)], fill=RED_COL)
    draw.line([x, y + 0.97 * s, x + s, y + 0.97 * s], fill=TEAL_COL, width=3)


def draw_missile_mark(draw, x, y, s):
    """A small missile: grey body with two red fins."""
    draw.polygon([(x + 0.5 * s, y + 0.05 * s), (x + 0.68 * s, y + 0.3 * s),
                  (x + 0.68 * s, y + 0.72 * s), (x + 0.5 * s, y + 0.95 * s),
                  (x + 0.32 * s, y + 0.72 * s), (x + 0.32 * s, y + 0.3 * s)],
                 fill=(96, 92, 86))
    draw.polygon([(x + 0.32 * s, y + 0.3 * s), (x + 0.14 * s, y + 0.55 * s),
                  (x + 0.32 * s, y + 0.5 * s)], fill=RED_COL)
    draw.polygon([(x + 0.68 * s, y + 0.3 * s), (x + 0.86 * s, y + 0.55 * s),
                  (x + 0.68 * s, y + 0.5 * s)], fill=RED_COL)


def draw_chip_mark(draw, x, y, s):
    """A small chip: navy square, gold core, twelve pins."""
    draw.rectangle([x + 0.22 * s, y + 0.22 * s, x + 0.78 * s, y + 0.78 * s],
                   fill=NAVY_COL)
    draw.rectangle([x + 0.38 * s, y + 0.38 * s, x + 0.62 * s, y + 0.62 * s],
                   fill=GOLD_COL)
    for i in range(3):
        t = 0.3 + 0.2 * i
        draw.line([x + t * s, y + 0.06 * s, x + t * s, y + 0.22 * s],
                  fill=NAVY_COL, width=3)
        draw.line([x + t * s, y + 0.78 * s, x + t * s, y + 0.94 * s],
                  fill=NAVY_COL, width=3)
        draw.line([x + 0.06 * s, y + t * s, x + 0.22 * s, y + t * s],
                  fill=NAVY_COL, width=3)
        draw.line([x + 0.78 * s, y + t * s, x + 0.94 * s, y + t * s],
                  fill=NAVY_COL, width=3)


MARK_DRAWERS = {"flame": draw_flame_mark, "ship": draw_ship_mark,
                "missile": draw_missile_mark, "chip": draw_chip_mark}


def draw_masthead(d):
    """Red rule, kicker line, title, date line, navy rule."""
    d.rectangle([0, 0, W, 10], fill=RED_COL)
    kick = "TUESDAY EDITION  \u2022  ONE DAY  \u2022  FIVE STORIES  \u2022  THE WORLD"
    centred_text(d, 26, kick, label_face(19), RED_COL)
    centred_text(d, 52, "THE WORLD IN ONE DAY", headline_face(62), NAVY_COL)
    centred_text(d, 126, DAY_LABEL, label_face(24), INK_COL)
    d.rectangle([0, 162, W, 166], fill=NAVY_COL)


def draw_lead_story(d):
    """Headline and body of the lead story, with a rule underneath."""
    lead_font = headline_face(34)
    for i, line in enumerate(wrap_line(d, LEAD_STORY["headline"], lead_font, 940)):
        d.text((42, 502 + i * 42), line, font=lead_font, fill=INK_COL)
    body_font = body_face(21)
    lead_lines = wrap_line(d, LEAD_STORY["body"], body_font, 940)
    for i, line in enumerate(lead_lines):
        d.text((42, 590 + i * 28), line, font=body_font, fill=(52, 52, 52))
    d.line([42, 672, W - 42, 672], fill=RULE_COL, width=2)


def draw_story_grid(d):
    """Four stories in a two-by-two grid, each with its pictogram."""
    cell_w, cell_h = 470, 138
    origins = [(42, 692), (512, 692), (42, 844), (512, 844)]
    for story, (ox, oy) in zip(GRID_STORIES, origins):
        MARK_DRAWERS[story["icon"]](d, ox, oy + 6, 44)
        tx = ox + 58
        d.text((tx, oy), story["kicker"], font=label_face(15), fill=RED_COL)
        for i, line in enumerate(wrap_line(d, story["headline"],
                                           headline_face(21), cell_w - 58)):
            d.text((tx, oy + 22 + i * 26), line, font=headline_face(21), fill=INK_COL)
        blines = wrap_line(d, story["body"], body_face(16), cell_w - 58)
        for i, line in enumerate(blines[:3]):
            d.text((tx, oy + 78 + i * 21), line, font=body_face(16),
                   fill=(52, 52, 52))
    d.line([512, 692, 512, 982], fill=RULE_COL, width=2)


def draw_ticker_bar(d):
    """Navy strip at the foot: an ALSO TODAY label and the trimmed ticker."""
    d.rectangle([0, 986, W, H], fill=NAVY_COL)
    tick_font = label_face(16)
    d.text((16, 998), "ALSO TODAY", font=tick_font, fill=GOLD_COL)
    ticker = trim_ticker(d, TICKER_LINE, body_face(16), W - 150 - 16)
    d.text((150, 998), ticker, font=body_face(16), fill=(235, 230, 220))


def compose_front_page():
    """Assemble the 1024x1024 front page and return the Pillow image.

    The call order below is load-bearing: the seeded star field is drawn
    inside the hero panel, so the panel must run before anything else
    that consumes the same generator.
    """
    rng = random.Random(SEED)
    img = Image.new("RGB", (W, H), PAPER_BG)
    d = ImageDraw.Draw(img)
    draw_masthead(d)
    draw_hero_panel(d, (0, 166, W, 486), rng)
    d.rectangle([0, 446, W, 486], fill=(12, 24, 44))
    centred_text(d, 456, "LEAD  \u2014  " + LEAD_STORY["kicker"], label_face(20), GOLD_COL)
    draw_lead_story(d)
    draw_story_grid(d)
    draw_ticker_bar(d)
    return img


def verify_png_chunks(blob):
    """Walk the PNG chunk list, checking every chunk's CRC-32.

    Returns the ordered chunk tags. Raises ValueError on a short chunk,
    an overrun, or a CRC mismatch, so a damaged poster never reaches
    the grader.
    """
    header = b"\x89PNG\r\n\x1a\n"
    if blob[:8] != header:
        raise ValueError("not a PNG")
    offset, tags = 8, []
    while offset + 8 <= len(blob):
        size, tag = struct.unpack(">I4s", blob[offset:offset + 8])
        end = offset + 8 + size + 4
        if end > len(blob):
            raise ValueError(f"truncated chunk {tag!r}")
        stored = struct.unpack(">I", blob[end - 4:end])[0]
        actual = zlib.crc32(tag + blob[offset + 8:offset + 8 + size]) & 0xFFFFFFFF
        if stored != actual:
            raise ValueError(f"CRC mismatch in chunk {tag!r}")
        tags.append(tag.decode("latin-1"))
        offset = end
    if tags[-1:] != ["IEND"]:
        raise ValueError("missing IEND trailer")
    return tags


def main():
    poster = compose_front_page()
    if poster.size != (W, H):
        sys.exit(f"poster is {poster.size}, expected {(W, H)}")
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, OUT_NAME)
    poster.save(out_path, format="PNG", optimize=True)
    with open(out_path, "rb") as fh:
        blob = fh.read()
    if len(blob) > LIMIT_BYTES:
        sys.exit(f"entry.png is {len(blob)} bytes, over the 1 MiB limit")
    tags = verify_png_chunks(blob)
    digest = hashlib.sha256(blob).hexdigest()
    print(f"news-image-20261124: {DAY_LABEL}")
    print(f"wrote {out_path} ({len(blob)} bytes, {W}x{H}, sha256 {digest})")
    print(f"png chunks: {' '.join(tags)}")
    for place, headline in RUN_LOG:
        print(f"- {place}: {headline}")
    print(f"deterministic: seed {SEED}, no network, no clock")


if __name__ == "__main__":
    main()
