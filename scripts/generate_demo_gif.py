"""
Generates docs/demo.gif — a synthetic terminal recording of `ai-data-clean
demo --which invoice` for the README. Built frame-by-frame with Pillow
(no screen recorder needed) so it's fully reproducible in CI or from a
clean checkout.

Run: python scripts/generate_demo_gif.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "docs" / "demo.gif"

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_SIZE = 16
LINE_HEIGHT = 22
PADDING_X = 22
PADDING_TOP = 52
WIDTH = 860

# GitHub-dark-ish palette
BG = (13, 17, 23)
CHROME = (34, 39, 46)
FG = (201, 209, 217)
GREEN = (63, 185, 80)
YELLOW = (210, 153, 34)
CYAN = (86, 182, 194)
GRAY = (125, 133, 144)
PROMPT_BLUE = (88, 166, 255)
RED_DOT = (255, 95, 86)
YELLOW_DOT = (255, 189, 46)
GREEN_DOT = (39, 201, 63)

font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
font_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE)

# Each line: (text, color, bold, pause_after_ms)
LINES = [
    ("$ ai-data-clean demo --which invoice", PROMPT_BLUE, True, 500),
    ("", FG, False, 0),
    ("[demo mode] Replaying cached AI output for nightmare_invoice.pdf (no API call made)", YELLOW, False, 500),
    ("", FG, False, 0),
    ("Wrote 10 rows to output/demo_invoice.csv", FG, False, 300),
    ("", FG, False, 0),
    ("Summary", FG, True, 150),
    ("  Document type:       invoice", FG, False, 80),
    ("  Line items found:    10", FG, False, 80),
    ("  Overall confidence:  89%", GREEN, False, 300),
    ("  Totals by category:", FG, False, 120),
    ("    Marketing & Advertising      $17,474.33", CYAN, False, 90),
    ("    Professional Services        $1,420.00", CYAN, False, 90),
    ("    Software & Subscriptions     $434.92", CYAN, False, 90),
    ("    Shipping & Freight           $88.40", CYAN, False, 90),
    ("    Meals & Entertainment        $41.16", CYAN, False, 300),
    ("  Issues noted by the AI:", FG, False, 120),
    ("    - Subtotal, tax, and TOTAL DUE rows excluded as document totals, not line items", GRAY, False, 90),
    ("    - Quantity/unit price inferred from context on rows with no aligned columns", GRAY, False, 90),
    ("    - Vendor header block and footer boilerplate ignored as non-line-item content", GRAY, False, 1800),
]

MS_PER_FRAME = 60  # base frame duration for typing animation


def draw_chrome(draw: ImageDraw.ImageDraw, width: int) -> None:
    draw.rectangle([0, 0, width, 40], fill=CHROME)
    for i, color in enumerate((RED_DOT, YELLOW_DOT, GREEN_DOT)):
        cx = 22 + i * 22
        draw.ellipse([cx - 6, 20 - 6, cx + 6, 20 + 6], fill=color)
    title = "suyog@portfolio: ~/ai-data-cleaning-tool"
    draw.text((width / 2, 20), title, font=font, fill=GRAY, anchor="mm")


def render_frame(visible_lines: list[tuple[str, tuple, bool]], height: int) -> Image.Image:
    img = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(img)
    draw_chrome(draw, WIDTH)
    y = PADDING_TOP
    for text, color, bold in visible_lines:
        f = font_bold if bold else font
        draw.text((PADDING_X, y), text, font=f, fill=color)
        y += LINE_HEIGHT
    return img


def build() -> None:
    height = PADDING_TOP + LINE_HEIGHT * (len(LINES) + 1) + 20
    frames: list[Image.Image] = []
    durations: list[int] = []

    revealed: list[tuple[str, tuple, bool]] = []

    # Typing animation for the command line itself.
    command_text, command_color, command_bold, _ = LINES[0]
    for i in range(1, len(command_text) + 1):
        revealed_partial = revealed + [(command_text[:i], command_color, command_bold)]
        frames.append(render_frame(revealed_partial, height))
        durations.append(MS_PER_FRAME)

    revealed.append((command_text, command_color, command_bold))

    # Reveal remaining lines one at a time (output "appearing" as if printed).
    for text, color, bold, pause_ms in LINES[1:]:
        revealed.append((text, color, bold))
        frames.append(render_frame(revealed, height))
        durations.append(max(pause_ms, 60))

    # Hold on the final frame a bit longer, then loop.
    durations[-1] = 2500

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUT_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"Wrote {OUT_PATH} ({len(frames)} frames, {sum(durations) / 1000:.1f}s per loop)")


if __name__ == "__main__":
    build()
