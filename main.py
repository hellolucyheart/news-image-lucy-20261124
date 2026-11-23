#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The World in One Day -- poster generator for make.fun news-image-20261124.

This program draws, from scratch, a single editorial poster that sums up
the world news of Tuesday 24 November 2026, and writes it to
``/output/entry.png``. It is the whole entry: no file is read, no network
is touched, no clock is consulted. Every pixel comes from the story data
below and from a fixed seed, so two runs write byte-identical PNGs.

Layout (1024 x 1024, a newspaper front page):
  * masthead with the date the poster sums up,
  * a dusk-globe hero panel drawn with Pillow shapes (sun, meridians,
    continents, sea) carrying the lead story,
  * the lead story in full, four more stories in a two-by-two grid,
    each with a small drawn pictogram,
  * a bottom ticker with four more items of the day.

The five stories were checked against reporting dated 24 November 2026
(see SOURCES.md): the COP31 climate talks ending in deadlock in
Antalya; the factory fire in Banten, Indonesia; the Russian cargo ship
Sparta II ablaze in the Gulf of Finland after a drone strike; Russian
drone and missile attacks on the Kyiv region; and Jensen Huang's return
to Nvidia lifting the company's value by almost a trillion dollars.
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
SEED = 20261124
OUT_DIR = "/output"
OUT_NAME = "entry.png"
W, H = 1024, 1024
LIMIT_BYTES = 1048576
LIMIT_SIDE = 1024

PAPER = (250, 246, 236)
INK = (22, 22, 22)
NAVY = (16, 32, 58)
DUSK = (24, 44, 78)
RED = (176, 30, 30)
GOLD = (214, 164, 65)
TEAL = (46, 120, 110)
GREY = (96, 92, 86)
RULE = (198, 188, 168)
SEA = (28, 68, 96)

LEAD = {
    "kicker": "ANTALYA, TURKIYE",
    "headline": "COP31 ends in deadlock: no deal on fossil fuels",
    "body": (
        "After two weeks of talks and days of overtime, the UN climate "
        "summit in Antalya closes with no agreement on stronger "
        "fossil-fuel language. The EU, the UK and island states refuse "
        "a pact that never mentions fossil fuels at all."
    ),
}

GRID = [
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

TICKER = (
    "Lisbon marches against the cost of living  \u2022  FIFA picks the hosts "
    "of the 2031 and 2035 Women's World Cups  \u2022  Verstappen wins the "
    "Las Vegas Grand Prix  \u2022  Gukesh defends his chess crown against "
    "Sindarov in Geneva  \u2022  Pant's 128 as India-New Zealand Test ends "
    "in a draw"
)

# The stories on the poster, in reading order, for the fixed run log.
LOG_STORIES = [
    ("Antalya", "COP31 ends in deadlock: no deal on fossil fuels"),
    ("Banten", "Factory fire kills at least 24, around 30 missing"),
    ("Gulf of Finland", "Russian cargo ship Sparta II ablaze after drone strike"),
    ("Kyiv region", "Russian drones and missiles strike homes in Dymer"),
    ("Markets", "Huang returns; Nvidia climbs almost $1tn"),
]


def load_font(kind, size):
    """Pick a DejaVu or Liberation face, falling back to the default."""
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVu%s.ttf" % kind,
        "/usr/share/fonts/truetype/liberation/Liberation%s.ttf" % kind,
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def serif_bold(size):
    return load_font("Serif-Bold", size)


def sans_bold(size):
    return load_font("Sans-Bold", size)


def sans(size):
    return load_font("Sans", size)


def wrap_text(draw, text, font, max_width):
    """Greedy word wrap returning a list of lines that fit max_width."""
    lines, current = [], ""
    for word in text.split():
        trial = (current + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_ticker(draw, text, font, max_width):
    """Trim the ticker word by word until it fits one line, ending in ..."""
    while draw.textlength(text, font=font) > max_width and " " in text:
        if text.endswith(" \u2026"):
            text = text[:-2].rstrip()
        text = text.rsplit(" ", 1)[0].rstrip(" \u2022")
        text += " \u2026"
    return text


def draw_centered(draw, y, text, font, fill, width=W):
    draw.text(((width - draw.textlength(text, font=font)) / 2, y),
              text, font=font, fill=fill)


def paint_hero(draw, box, rng):
    """Draw the dusk-globe hero: banded sky, sun, stars, globe, sea."""
    x0, y0, x1, y1 = box
    # Banded dusk sky.
    bands = 48
    for i in range(bands):
        t = i / max(bands - 1, 1)
        r = int(DUSK[0] + (58 - DUSK[0]) * t)
        g = int(DUSK[1] + (74 - DUSK[1]) * t)
        b = int(DUSK[2] + (112 - DUSK[2]) * t)
        yy = y0 + (y1 - y0) * i // bands
        y_next = y0 + (y1 - y0) * (i + 1) // bands
        draw.rectangle([x0, yy, x1, y_next], fill=(r, g, b))
    # Stars, seeded so the sky is identical on every run.
    for _ in range(70):
        sx = rng.randint(x0 + 8, x1 - 8)
        sy = rng.randint(y0 + 8, y0 + 150)
        s = rng.choice((1, 1, 2))
        draw.ellipse([sx, sy, sx + s, sy + s], fill=(235, 230, 210))
    # Golden sun, low over the sea.
    cx, cy = x0 + 830, y0 + 118
    for rad, col in ((74, (214, 164, 65, 60)), (58, GOLD), (44, (232, 190, 100))):
        draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=col)
    # Globe: deep teal disc, meridian ellipses, abstract continents.
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
    # Sea: three wave lines under the globe.
    for j, wy in enumerate((y1 - 42, y1 - 28, y1 - 14)):
        pts = []
        for x in range(x0, x1 + 1, 16):
            pts.append((x, wy + int(5 * math.sin(x / 55.0 + j * 1.7))))
        draw.line(pts, fill=(150, 190, 205), width=3)


def paint_flame(draw, x, y, s):
    pts = [(x + 0.5 * s, y + 0.05 * s), (x + 0.85 * s, y + 0.45 * s),
           (x + 0.95 * s, y + 0.75 * s), (x + 0.7 * s, y + 0.95 * s),
           (x + 0.3 * s, y + 0.95 * s), (x + 0.05 * s, y + 0.75 * s),
           (x + 0.15 * s, y + 0.45 * s)]
    draw.polygon(pts, fill=(196, 64, 32))
    draw.ellipse([x + 0.32 * s, y + 0.5 * s, x + 0.68 * s, y + 0.88 * s],
                 fill=GOLD)


def paint_ship(draw, x, y, s):
    draw.polygon([(x + 0.05 * s, y + 0.62 * s), (x + 0.95 * s, y + 0.62 * s),
                  (x + 0.8 * s, y + 0.92 * s), (x + 0.2 * s, y + 0.92 * s)],
                 fill=NAVY)
    draw.line([x + 0.5 * s, y + 0.08 * s, x + 0.5 * s, y + 0.62 * s],
              fill=NAVY, width=4)
    draw.polygon([(x + 0.5 * s, y + 0.12 * s), (x + 0.88 * s, y + 0.55 * s),
                  (x + 0.5 * s, y + 0.55 * s)], fill=RED)
    draw.line([x, y + 0.97 * s, x + s, y + 0.97 * s], fill=TEAL, width=3)


def paint_missile(draw, x, y, s):
    draw.polygon([(x + 0.5 * s, y + 0.05 * s), (x + 0.68 * s, y + 0.3 * s),
                  (x + 0.68 * s, y + 0.72 * s), (x + 0.5 * s, y + 0.95 * s),
                  (x + 0.32 * s, y + 0.72 * s), (x + 0.32 * s, y + 0.3 * s)],
                 fill=(96, 92, 86))
    draw.polygon([(x + 0.32 * s, y + 0.3 * s), (x + 0.14 * s, y + 0.55 * s),
                  (x + 0.32 * s, y + 0.5 * s)], fill=RED)
    draw.polygon([(x + 0.68 * s, y + 0.3 * s), (x + 0.86 * s, y + 0.55 * s),
                  (x + 0.68 * s, y + 0.5 * s)], fill=RED)


def paint_chip(draw, x, y, s):
    draw.rectangle([x + 0.22 * s, y + 0.22 * s, x + 0.78 * s, y + 0.78 * s],
                   fill=NAVY)
    draw.rectangle([x + 0.38 * s, y + 0.38 * s, x + 0.62 * s, y + 0.62 * s],
                   fill=GOLD)
    for i in range(3):
        t = 0.3 + 0.2 * i
        draw.line([x + t * s, y + 0.06 * s, x + t * s, y + 0.22 * s],
                  fill=NAVY, width=3)
        draw.line([x + t * s, y + 0.78 * s, x + t * s, y + 0.94 * s],
                  fill=NAVY, width=3)
        draw.line([x + 0.06 * s, y + t * s, x + 0.22 * s, y + t * s],
                  fill=NAVY, width=3)
        draw.line([x + 0.78 * s, y + t * s, x + 0.94 * s, y + t * s],
                  fill=NAVY, width=3)


ICON_PAINT = {"flame": paint_flame, "ship": paint_ship,
              "missile": paint_missile, "chip": paint_chip}


def build_poster():
    """Compose the 1024x1024 front page and return the Pillow image."""
    rng = random.Random(SEED)
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # Masthead.
    d.rectangle([0, 0, W, 10], fill=RED)
    kick = "TUESDAY EDITION  \u2022  ONE DAY  \u2022  FIVE STORIES  \u2022  THE WORLD"
    draw_centered(d, 26, kick, sans_bold(19), RED)
    draw_centered(d, 52, "THE WORLD IN ONE DAY", serif_bold(62), NAVY)
    draw_centered(d, 126, DAY_LABEL, sans_bold(24), INK)
    d.rectangle([0, 162, W, 166], fill=NAVY)

    # Hero panel with the lead kicker overlaid at its foot.
    paint_hero(d, (0, 166, W, 486), rng)
    d.rectangle([0, 446, W, 486], fill=(12, 24, 44))
    draw_centered(d, 456, "LEAD  \u2014  " + LEAD["kicker"], sans_bold(20), GOLD)

    # Lead story.
    lead_font = serif_bold(34)
    for i, line in enumerate(wrap_text(d, LEAD["headline"], lead_font, 940)):
        d.text((42, 502 + i * 42), line, font=lead_font, fill=INK)
    body_font = sans(21)
    lead_lines = wrap_text(d, LEAD["body"], body_font, 940)
    for i, line in enumerate(lead_lines):
        d.text((42, 590 + i * 28), line, font=body_font, fill=(52, 52, 52))
    d.line([42, 672, W - 42, 672], fill=RULE, width=2)

    # Two-by-two grid of the other four stories.
    cell_w, cell_h = 470, 138
    origins = [(42, 692), (512, 692), (42, 844), (512, 844)]
    for story, (ox, oy) in zip(GRID, origins):
        ICON_PAINT[story["icon"]](d, ox, oy + 6, 44)
        tx = ox + 58
        d.text((tx, oy), story["kicker"], font=sans_bold(15), fill=RED)
        for i, line in enumerate(wrap_text(d, story["headline"],
                                           serif_bold(21), cell_w - 58)):
            d.text((tx, oy + 22 + i * 26), line, font=serif_bold(21), fill=INK)
        blines = wrap_text(d, story["body"], sans(16), cell_w - 58)
        for i, line in enumerate(blines[:3]):
            d.text((tx, oy + 78 + i * 21), line, font=sans(16),
                   fill=(52, 52, 52))
    d.line([512, 692, 512, 982], fill=RULE, width=2)

    # Bottom ticker.
    d.rectangle([0, 986, W, H], fill=NAVY)
    tick_font = sans_bold(16)
    d.text((16, 998), "ALSO TODAY", font=tick_font, fill=GOLD)
    ticker = fit_ticker(d, TICKER, sans(16), W - 150 - 16)
    d.text((150, 998), ticker, font=sans(16), fill=(235, 230, 220))
    return img


def check_png_chunks(blob):
    """Walk the PNG chunk list, verifying every chunk's CRC-32.

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
            raise ValueError("truncated chunk %r" % tag)
        stored = struct.unpack(">I", blob[end - 4:end])[0]
        actual = zlib.crc32(tag + blob[offset + 8:offset + 8 + size]) & 0xFFFFFFFF
        if stored != actual:
            raise ValueError("CRC mismatch in chunk %r" % tag)
        tags.append(tag.decode("latin-1"))
        offset = end
    if tags[-1:] != ["IEND"]:
        raise ValueError("missing IEND trailer")
    return tags


def main():
    poster = build_poster()
    if poster.size != (W, H):
        sys.exit("poster is %s, expected %s" % (poster.size, (W, H)))
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, OUT_NAME)
    poster.save(out_path, format="PNG", optimize=True)
    with open(out_path, "rb") as fh:
        blob = fh.read()
    if len(blob) > LIMIT_BYTES:
        sys.exit("entry.png is %d bytes, over the 1 MiB limit" % len(blob))
    tags = check_png_chunks(blob)
    digest = hashlib.sha256(blob).hexdigest()
    print("news-image-20261124: %s" % DAY_LABEL)
    print("wrote %s (%d bytes, %dx%d, sha256 %s)" %
          (out_path, len(blob), W, H, digest))
    print("png chunks: %s" % " ".join(tags))
    for place, headline in LOG_STORIES:
        print("- %s: %s" % (place, headline))
    print("deterministic: seed %d, no network, no clock" % SEED)


if __name__ == "__main__":
    main()
