#!/usr/bin/env python3
"""Render modern portfolio visual assets.

The architecture source of truth is an SVG file so it remains editable and
portable. PNG assets are rendered with Pillow for Notion uploads and previews.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"

W = 1800
H = 1050
SCALE = 2

COLORS = {
    "bg": "#F8FAFC",
    "panel": "#FFFFFF",
    "panel_alt": "#F1F5F9",
    "ink": "#0F172A",
    "muted": "#64748B",
    "line": "#CBD5E1",
    "blue": "#2563EB",
    "blue_soft": "#DBEAFE",
    "teal": "#0F766E",
    "teal_soft": "#CCFBF1",
    "purple": "#7C3AED",
    "purple_soft": "#EDE9FE",
    "green": "#059669",
    "green_soft": "#D1FAE5",
    "amber": "#D97706",
    "amber_soft": "#FEF3C7",
    "slate": "#475569",
    "slate_soft": "#E2E8F0",
    "red": "#DC2626",
    "red_soft": "#FEE2E2",
}


def rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def font_path(name: str) -> str:
    candidates = {
        "regular": [
            "/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ],
        "bold": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf",
        ],
        "mono": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/ubuntu/UbuntuSansMono[wght].ttf",
        ],
    }
    for path in candidates[name]:
        if Path(path).exists():
            return path
    raise FileNotFoundError(f"No usable font found for {name}")


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(weight), size * SCALE)


def new_canvas(width: int = W, height: int = H, bg: str = COLORS["bg"]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width * SCALE, height * SCALE), rgb(bg))
    return image, ImageDraw.Draw(image)


def sc_rect(rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return tuple(v * SCALE for v in rect)


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int, color: str = COLORS["ink"], weight: str = "regular") -> None:
    draw.text((xy[0] * SCALE, xy[1] * SCALE), value, fill=rgb(color), font=font(size, weight))


def centered_text(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    value: str,
    size: int,
    color: str = COLORS["ink"],
    weight: str = "regular",
) -> None:
    f = font(size, weight)
    bbox = draw.textbbox((0, 0), value, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x1, y1, x2, y2 = sc_rect(rect)
    draw.text((x1 + (x2 - x1 - tw) / 2, y1 + (y2 - y1 - th) / 2 - 2 * SCALE), value, fill=rgb(color), font=f)


def rounded(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    fill: str,
    outline: str | None = None,
    radius: int = 22,
    width: int = 1,
    shadow: bool = False,
) -> None:
    if shadow:
        x1, y1, x2, y2 = rect
        shadow_rect = (x1 + 8, y1 + 12, x2 + 8, y2 + 12)
        draw.rounded_rectangle(sc_rect(shadow_rect), radius=radius * SCALE, fill=rgb("#E2E8F0"))
    draw.rounded_rectangle(
        sc_rect(rect),
        radius=radius * SCALE,
        fill=rgb(fill),
        outline=rgb(outline) if outline else None,
        width=width * SCALE,
    )


def line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str = COLORS["slate"], width: int = 3) -> None:
    draw.line((start[0] * SCALE, start[1] * SCALE, end[0] * SCALE, end[1] * SCALE), fill=rgb(color), width=width * SCALE)


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: str = COLORS["slate"],
    width: int = 3,
) -> None:
    line(draw, start, end, color, width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 16
    points = [(end[0] * SCALE, end[1] * SCALE)]
    for delta in (math.pi - 0.45, math.pi + 0.45):
        points.append(((end[0] + size * math.cos(angle + delta)) * SCALE, (end[1] + size * math.sin(angle + delta)) * SCALE))
    draw.polygon(points, fill=rgb(color))


def polyline_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    color: str = COLORS["slate"],
    width: int = 3,
) -> None:
    for start, end in zip(points, points[1:-1]):
        line(draw, start, end, color, width)
    arrow(draw, points[-2], points[-1], color, width)


def node(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    title: str,
    body: str,
    accent: str,
    soft: str,
    icon: str,
) -> None:
    rounded(draw, rect, COLORS["panel"], COLORS["line"], radius=18, shadow=True)
    x1, y1, _x2, _y2 = rect
    rounded(draw, (x1 + 18, y1 + 20, x1 + 62, y1 + 64), soft, None, radius=12)
    centered_text(draw, (x1 + 18, y1 + 20, x1 + 62, y1 + 64), icon, 20, accent, "bold")
    text(draw, (x1 + 78, y1 + 22), title, 22, COLORS["ink"], "bold")
    text(draw, (x1 + 78, y1 + 55), body, 15, COLORS["muted"])


def group(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], title: str, accent: str) -> None:
    rounded(draw, rect, "#FFFFFF", "#D7DEE8", radius=28, shadow=True)
    x1, y1, _x2, _y2 = rect
    rounded(draw, (x1 + 22, y1 + 20, x1 + 36, y1 + 44), accent, None, radius=7)
    text(draw, (x1 + 48, y1 + 16), title, 18, COLORS["muted"], "bold")


def save_png(image: Image.Image, path: Path) -> None:
    image = image.resize((image.width // SCALE, image.height // SCALE), Image.Resampling.LANCZOS)
    image.save(path)


def render_architecture_svg() -> None:
    svg = """<svg width="1800" height="1050" viewBox="0 0 1800 1050" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="150%">
      <feDropShadow dx="0" dy="10" stdDeviation="10" flood-color="#94A3B8" flood-opacity="0.22"/>
    </filter>
    <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
      <path d="M2 2 L10 6 L2 10" fill="none" stroke="#475569" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
    <style>
      .title{font:700 48px Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill:#0F172A}
      .subtitle{font:400 22px Inter, ui-sans-serif, system-ui, sans-serif; fill:#64748B}
      .group{font:700 16px Inter, ui-sans-serif, system-ui, sans-serif; fill:#64748B; letter-spacing:.04em}
      .node-title{font:700 20px Inter, ui-sans-serif, system-ui, sans-serif; fill:#0F172A}
      .node-body{font:400 14px Inter, ui-sans-serif, system-ui, sans-serif; fill:#64748B}
      .label{font:600 13px Inter, ui-sans-serif, system-ui, sans-serif; fill:#475569}
    </style>
  </defs>
  <rect width="1800" height="1050" fill="#F8FAFC"/>
  <text x="72" y="84" class="title">LLM Agent Routing Control Plane</text>
  <text x="74" y="124" class="subtitle">Agent-first model routing with explainable decisions, safe fallback, and outcome feedback.</text>

  <g filter="url(#shadow)">
    <rect x="72" y="180" width="300" height="318" rx="28" fill="#FFFFFF" stroke="#CBD5E1"/>
    <rect x="432" y="180" width="612" height="548" rx="28" fill="#FFFFFF" stroke="#CBD5E1"/>
    <rect x="1090" y="180" width="320" height="548" rx="28" fill="#FFFFFF" stroke="#CBD5E1"/>
    <rect x="1460" y="180" width="268" height="548" rx="28" fill="#FFFFFF" stroke="#CBD5E1"/>
    <rect x="432" y="780" width="1296" height="160" rx="28" fill="#FFFFFF" stroke="#CBD5E1"/>
  </g>

  <text x="120" y="222" class="group">AGENT LAYER</text>
  <text x="480" y="222" class="group">CONTROL PLANE</text>
  <text x="1138" y="222" class="group">DATA &amp; SIGNALS</text>
  <text x="1508" y="222" class="group">PROVIDER LAYER</text>
  <text x="480" y="822" class="group">OBSERVABILITY</text>

  <g>
    <rect x="108" y="282" width="228" height="118" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <rect x="126" y="304" width="44" height="44" rx="12" fill="#DBEAFE"/>
    <text x="139" y="333" font-size="20" font-weight="700" fill="#2563EB">A</text>
    <text x="184" y="322" class="node-title">AI Agent</text>
    <text x="184" y="354" class="node-body">workflow client</text>

    <rect x="482" y="282" width="230" height="112" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <rect x="500" y="302" width="44" height="44" rx="12" fill="#DBEAFE"/>
    <text x="514" y="331" font-size="20" font-weight="700" fill="#2563EB">D</text>
    <text x="558" y="320" class="node-title">Decision API</text>
    <text x="558" y="352" class="node-body">FastAPI endpoint</text>

    <rect x="760" y="282" width="236" height="112" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <rect x="778" y="302" width="44" height="44" rx="12" fill="#EDE9FE"/>
    <text x="791" y="331" font-size="20" font-weight="700" fill="#7C3AED">S</text>
    <text x="836" y="320" class="node-title">Scoring Engine</text>
    <text x="836" y="352" class="node-body">cost, latency, qps</text>

    <rect x="540" y="454" width="210" height="96" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <text x="568" y="492" class="node-title">Model Catalog</text>
    <text x="568" y="520" class="node-body">price + capability</text>
    <rect x="784" y="454" width="210" height="96" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <text x="812" y="492" class="node-title">Routing Policies</text>
    <text x="812" y="520" class="node-body">balanced, cheap-first</text>
    <rect x="620" y="594" width="282" height="96" rx="18" fill="#ECFDF5" stroke="#A7F3D0"/>
    <text x="650" y="632" class="node-title">Durable Decision</text>
    <text x="650" y="660" class="node-body">recommended + fallback ladder</text>

    <rect x="1130" y="282" width="240" height="96" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <text x="1160" y="320" class="node-title">Redis Signals</text>
    <text x="1160" y="348" class="node-body">fresh probe health</text>
    <rect x="1130" y="432" width="240" height="96" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <text x="1160" y="470" class="node-title">Postgres</text>
    <text x="1160" y="498" class="node-body">decisions + outcomes</text>
    <rect x="1130" y="582" width="240" height="96" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <text x="1160" y="620" class="node-title">Redis Streams</text>
    <text x="1160" y="648" class="node-body">outcomes + probes</text>

    <rect x="1494" y="282" width="200" height="96" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <text x="1522" y="320" class="node-title">LLM Providers</text>
    <text x="1522" y="348" class="node-body">DeepSeek / Moonshot</text>
    <rect x="1494" y="432" width="200" height="96" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <text x="1522" y="470" class="node-title">Probe Worker</text>
    <text x="1522" y="498" class="node-body">provider health</text>
    <rect x="1494" y="582" width="200" height="96" rx="18" fill="#FFFFFF" stroke="#CBD5E1"/>
    <text x="1522" y="620" class="node-title">Event Consumer</text>
    <text x="1522" y="648" class="node-body">persist events</text>

    <rect x="520" y="850" width="250" height="62" rx="16" fill="#F1F5F9" stroke="#CBD5E1"/>
    <text x="548" y="888" class="node-title">Prometheus Metrics</text>
    <rect x="824" y="850" width="250" height="62" rx="16" fill="#F1F5F9" stroke="#CBD5E1"/>
    <text x="852" y="888" class="node-title">Policy Trace</text>
    <rect x="1128" y="850" width="250" height="62" rx="16" fill="#F1F5F9" stroke="#CBD5E1"/>
    <text x="1156" y="888" class="node-title">Outcome Feedback</text>
  </g>

  <path d="M336 340 H482" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <text x="366" y="326" class="label">decision request</text>
  <path d="M712 338 H760" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M876 394 V454" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M645 454 V410 H790" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M889 454 V410 H888" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M902 338 H1130 V330" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M760 594 V550" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M620 642 C470 642 380 580 304 400" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <text x="348" y="620" class="label">fallback candidates</text>
  <path d="M260 400 C530 760 1180 760 1494 330" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <text x="656" y="744" class="label">own vendor key</text>
  <path d="M250 400 C320 505 380 580 482 360" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <text x="318" y="505" class="label">outcome report</text>
  <path d="M1494 480 H1370 V330" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <text x="1386" y="460" class="label">probe signal</text>
  <path d="M1370 630 H1494" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M1494 630 H1370 V480" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M712 394 C650 560 636 690 640 850" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M712 394 C850 620 920 750 949 850" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M712 394 C1000 620 1180 720 1252 850" stroke="#475569" stroke-width="3" marker-end="url(#arrow)"/>
</svg>
"""
    (OUT / "architecture.svg").write_text(svg, encoding="utf-8")


def render_architecture_png() -> None:
    image, draw = new_canvas()
    text(draw, (72, 56), "LLM Agent Routing Control Plane", 46, COLORS["ink"], "bold")
    text(draw, (74, 112), "Agent-first model routing with explainable decisions, safe fallback, and outcome feedback.", 22, COLORS["muted"])

    group(draw, (72, 210, 330, 610), "AGENT LAYER", COLORS["blue"])
    group(draw, (390, 210, 1120, 610), "CONTROL PLANE", COLORS["purple"])
    group(draw, (1180, 210, 1728, 610), "PROVIDER LAYER", COLORS["amber"])
    group(draw, (390, 700, 1460, 955), "DATA & SIGNALS", COLORS["teal"])
    group(draw, (1500, 700, 1728, 955), "OBSERVABILITY", COLORS["slate"])

    node(draw, (108, 360, 294, 480), "AI Agent", "workflow client", COLORS["blue"], COLORS["blue_soft"], "A")
    node(draw, (430, 360, 630, 480), "Decision API", "route + outcome", COLORS["blue"], COLORS["blue_soft"], "D")
    node(draw, (680, 360, 880, 480), "Scoring Engine", "cost, latency, qps", COLORS["purple"], COLORS["purple_soft"], "S")
    node(draw, (920, 360, 1080, 480), "Decision", "fallback ladder", COLORS["green"], COLORS["green_soft"], "R")

    node(draw, (430, 250, 610, 330), "Auth", "quota + scopes", COLORS["slate"], COLORS["slate_soft"], "Q")
    node(draw, (635, 250, 815, 330), "Catalog", "price + capability", COLORS["teal"], COLORS["teal_soft"], "C")
    node(draw, (840, 250, 1050, 330), "Policies", "balanced, cheap-first", COLORS["teal"], COLORS["teal_soft"], "P")

    node(draw, (1225, 332, 1445, 452), "LLM Providers", "DeepSeek / Moonshot", COLORS["amber"], COLORS["amber_soft"], "L")
    node(draw, (1490, 332, 1690, 452), "Probe Worker", "provider health", COLORS["red"], COLORS["red_soft"], "W")

    node(draw, (430, 785, 650, 885), "Redis Signals", "fresh probe health", COLORS["teal"], COLORS["teal_soft"], "R")
    node(draw, (690, 785, 910, 885), "Postgres", "decisions + outcomes", COLORS["slate"], COLORS["slate_soft"], "P")
    node(draw, (950, 785, 1170, 885), "Redis Streams", "outcomes + probes", COLORS["slate"], COLORS["slate_soft"], "S")
    node(draw, (1210, 785, 1420, 885), "Event Consumer", "persist events", COLORS["slate"], COLORS["slate_soft"], "E")

    for rect, title, accent in [
        ((1530, 762, 1698, 812), "Prometheus", COLORS["blue"]),
        ((1530, 832, 1698, 882), "Policy Trace", COLORS["purple"]),
        ((1530, 902, 1698, 952), "Outcomes", COLORS["green"]),
    ]:
        rounded(draw, rect, COLORS["panel_alt"], COLORS["line"], 16)
        rounded(draw, (rect[0] + 16, rect[1] + 17, rect[0] + 28, rect[3] - 17), accent, None, 5)
        text(draw, (rect[0] + 42, rect[1] + 14), title, 16, COLORS["ink"], "bold")

    arrow(draw, (294, 420), (430, 420))
    text(draw, (318, 392), "decision request", 14, COLORS["slate"], "bold")
    arrow(draw, (630, 420), (680, 420))
    arrow(draw, (880, 420), (920, 420))
    text(draw, (890, 392), "ranked route", 14, COLORS["slate"], "bold")

    polyline_arrow(draw, [(1000, 360), (1000, 188), (202, 188), (202, 360)])
    text(draw, (495, 166), "fallback candidates returned to Agent", 14, COLORS["slate"], "bold")

    polyline_arrow(draw, [(202, 480), (202, 638), (1335, 638), (1335, 452)])
    text(draw, (628, 616), "provider call with Agent-owned vendor key", 14, COLORS["slate"], "bold")

    polyline_arrow(draw, [(294, 466), (360, 466), (360, 516), (430, 516), (430, 480)])
    text(draw, (312, 498), "outcome report", 14, COLORS["slate"], "bold")

    arrow(draw, (520, 330), (520, 360))
    arrow(draw, (725, 330), (762, 360))
    arrow(draw, (945, 330), (830, 360))
    polyline_arrow(draw, [(540, 785), (540, 650), (780, 650), (780, 480)])

    polyline_arrow(draw, [(530, 480), (530, 735), (800, 735), (800, 785)])
    polyline_arrow(draw, [(552, 480), (552, 735), (1060, 735), (1060, 785)])
    arrow(draw, (1170, 835), (1210, 835))
    polyline_arrow(draw, [(1315, 885), (1315, 923), (800, 923), (800, 885)])

    arrow(draw, (1490, 392), (1445, 392))
    polyline_arrow(draw, [(1590, 452), (1590, 650), (540, 650), (540, 785)])
    text(draw, (1334, 628), "probe signal", 14, COLORS["teal"], "bold")

    save_png(image, OUT / "architecture.png")


def gradient_rect(image: Image.Image, top: str, bottom: str) -> None:
    draw = ImageDraw.Draw(image)
    t = rgb(top)
    b = rgb(bottom)
    for y in range(image.height):
        ratio = y / max(1, image.height - 1)
        color = tuple(int(t[i] * (1 - ratio) + b[i] * ratio) for i in range(3))
        draw.line((0, y, image.width, y), fill=color)


def render_cover() -> None:
    image = Image.new("RGB", (1800 * SCALE, 950 * SCALE), rgb("#0F172A"))
    gradient_rect(image, "#0F172A", "#172554")
    draw = ImageDraw.Draw(image)
    rounded(draw, (88, 86, 1712, 864), "#0B1220", "#334155", 36)
    text(draw, (150, 158), "LLM Agent Routing", 58, "#F8FAFC", "bold")
    text(draw, (150, 226), "Control Plane", 58, "#F8FAFC", "bold")
    text(draw, (154, 326), "AI infra product case study for model routing, fallback, and governance.", 24, "#CBD5E1")
    for x, y, value, label, color in [
        (154, 470, "17", "tests passed", COLORS["green"]),
        (438, 470, "88.08%", "coverage", COLORS["blue"]),
        (760, 470, "5", "routing policies", COLORS["purple"]),
    ]:
        rounded(draw, (x, y, x + 230, y + 150), "#111827", "#334155", 24)
        text(draw, (x + 28, y + 28), value, 42, color, "bold")
        text(draw, (x + 30, y + 88), label, 18, "#CBD5E1")
    for i, (x1, y1, x2, y2) in enumerate([(1120, 220, 1560, 220), (1180, 360, 1620, 360), (1080, 500, 1580, 500), (1200, 640, 1660, 640)]):
        line(draw, (x1, y1), (x2, y2), ["#60A5FA", "#34D399", "#A78BFA", "#CBD5E1"][i], 4)
        for x in (x1, x2):
            rounded(draw, (x - 22, y1 - 22, x + 22, y1 + 22), "#0F172A", "#475569", 22)
    text(draw, (154, 760), "Product framing + API design + running evidence", 24, "#E2E8F0", "bold")
    save_png(image, OUT / "portfolio-cover.png")


def render_api_demo() -> None:
    image, draw = new_canvas(1600, 900)
    text(draw, (70, 58), "API Demo Flow", 48, COLORS["ink"], "bold")
    text(draw, (74, 118), "A complete route decision, provider call, and outcome feedback loop.", 22, COLORS["muted"])
    steps = [
        ("1", "Decision request", "task + budget + SLO", COLORS["blue"], COLORS["blue_soft"]),
        ("2", "Routing response", "recommended + fallback", COLORS["purple"], COLORS["purple_soft"]),
        ("3", "Provider call", "agent-owned vendor key", COLORS["amber"], COLORS["amber_soft"]),
        ("4", "Outcome report", "recorded or duplicate", COLORS["green"], COLORS["green_soft"]),
    ]
    x = 90
    for number, title, body, accent, soft in steps:
        rounded(draw, (x, 240, x + 310, 470), COLORS["panel"], COLORS["line"], 24, shadow=True)
        rounded(draw, (x + 26, 270, x + 82, 326), soft, None, 16)
        centered_text(draw, (x + 26, 270, x + 82, 326), number, 24, accent, "bold")
        text(draw, (x + 28, 360), title, 24, COLORS["ink"], "bold")
        text(draw, (x + 28, 398), body, 17, COLORS["muted"])
        if x < 1190:
            arrow(draw, (x + 310, 355), (x + 390, 355))
        x += 390
    for y, label in [
        (620, "Selected model: deepseek/deepseek-chat"),
        (680, "Decision id is traceable and idempotent"),
        (740, "Outcome feedback closes the product loop"),
    ]:
        rounded(draw, (100, y - 14, 1500, y + 38), COLORS["panel"], COLORS["line"], 14)
        text(draw, (130, y), label, 22, COLORS["ink"], "bold")
    save_png(image, OUT / "api-demo-card.png")


def render_test_results() -> None:
    image, draw = new_canvas(1500, 850)
    text(draw, (70, 58), "Test Results", 52, COLORS["ink"], "bold")
    cards = [
        (80, 210, 420, 440, "17", "passed", COLORS["green"], COLORS["green_soft"]),
        (540, 210, 880, 440, "88.08%", "coverage", COLORS["blue"], COLORS["blue_soft"]),
        (1000, 210, 1340, 440, "85%", "required", COLORS["purple"], COLORS["purple_soft"]),
    ]
    for x1, y1, x2, y2, value, label, accent, soft in cards:
        rounded(draw, (x1, y1, x2, y2), COLORS["panel"], COLORS["line"], 28, shadow=True)
        rounded(draw, (x1 + 28, y1 + 32, x1 + 92, y1 + 96), soft, None, 18)
        text(draw, (x1 + 32, y1 + 128), value, 50, accent, "bold")
        text(draw, (x1 + 34, y1 + 194), label, 22, COLORS["muted"], "bold")
    for y, value in [
        (580, "Command: ./venv/bin/pytest -q"),
        (640, "Scope: routing, idempotency, outcome, metrics, signals"),
        (700, "Conclusion: automated regression passed"),
    ]:
        text(draw, (100, y), value, 24, COLORS["ink"] if y < 700 else COLORS["green"], "bold")
    save_png(image, OUT / "test-results-card.png")


def render_validation_summary() -> None:
    image, draw = new_canvas(1500, 1000)
    text(draw, (70, 58), "Validation Summary", 50, COLORS["ink"], "bold")
    rows = [
        ("Health ready", "online"),
        ("Catalog / policies", "2 providers / 5 policies"),
        ("Decision API", "passed"),
        ("Outcome idempotency", "recorded then duplicate"),
        ("Prometheus metrics", "routing signals found"),
        ("Redis Streams", "outcomes + probes"),
        ("Postgres", "decisions + attempts"),
        ("Worker integration", "3 processes passed"),
        ("Example Agent E2E", "deepseek-chat selected"),
    ]
    y = 155
    for i, (item, status) in enumerate(rows):
        fill = COLORS["panel"] if i % 2 == 0 else COLORS["panel_alt"]
        rounded(draw, (80, y, 1420, y + 72), fill, COLORS["line"], 14)
        text(draw, (120, y + 22), item, 22, COLORS["ink"], "bold")
        text(draw, (760, y + 22), status, 22, COLORS["green"] if "passed" in status or "online" in status or "selected" in status else COLORS["slate"], "bold")
        y += 78
    text(draw, (95, 885), "Not a static concept: API + persistence + workers + observability", 24, COLORS["blue"], "bold")
    save_png(image, OUT / "validation-summary-card.png")


def render_product_cards() -> None:
    image, draw = new_canvas(1600, 1050)
    text(draw, (70, 58), "Product Framing", 52, COLORS["ink"], "bold")
    cards = [
        (90, 180, "User", "AI Agent teams", COLORS["blue"], COLORS["blue_soft"]),
        (580, 180, "Pain", "Hard-coded model risk", COLORS["red"], COLORS["red_soft"]),
        (1070, 180, "Solution", "Routing control plane", COLORS["green"], COLORS["green_soft"]),
        (90, 535, "Value", "Lower cost + higher reliability", COLORS["purple"], COLORS["purple_soft"]),
        (580, 535, "MVP boundary", "API first before dashboard", COLORS["amber"], COLORS["amber_soft"]),
        (1070, 535, "Next", "Shadow mode + route replay", COLORS["teal"], COLORS["teal_soft"]),
    ]
    for x, y, title, body, accent, soft in cards:
        rounded(draw, (x, y, x + 420, y + 260), COLORS["panel"], COLORS["line"], 28, shadow=True)
        rounded(draw, (x + 30, y + 30, x + 88, y + 88), soft, None, 16)
        text(draw, (x + 30, y + 118), title, 32, COLORS["ink"], "bold")
        text(draw, (x + 32, y + 174), body, 21, COLORS["muted"], "bold")
        rounded(draw, (x + 30, y + 222, x + 390, y + 230), accent, None, 4)
    save_png(image, OUT / "product-cards.png")


def render_technical_highlights() -> None:
    image, draw = new_canvas(1600, 900)
    text(draw, (70, 58), "Technical Highlights", 52, COLORS["ink"], "bold")
    highlights = [
        ("Agent-first", "Control plane does not hold vendor keys"),
        ("Durable decision", "Traceable, retryable, auditable"),
        ("Fallback ladder", "Ordered candidates for recovery"),
        ("Policy routing", "Balanced, cheap-first, latency-first"),
        ("Redis signals", "Fresh probe health for decisions"),
        ("Prometheus", "Metrics for routing and outcomes"),
    ]
    y = 165
    accents = [COLORS["blue"], COLORS["green"], COLORS["purple"], COLORS["amber"], COLORS["teal"], COLORS["slate"]]
    for i, (title, body) in enumerate(highlights):
        rounded(draw, (90, y, 1510, y + 86), COLORS["panel"], COLORS["line"], 16)
        rounded(draw, (110, y + 18, 126, y + 68), accents[i], None, 8)
        text(draw, (150, y + 22), title, 27, COLORS["ink"], "bold")
        text(draw, (590, y + 26), body, 22, COLORS["muted"])
        y += 105
    save_png(image, OUT / "technical-highlights-card.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render_architecture_svg()
    render_cover()
    render_architecture_png()
    render_api_demo()
    render_test_results()
    render_validation_summary()
    render_product_cards()
    render_technical_highlights()
    print(f"Rendered modern portfolio assets into {OUT}")


if __name__ == "__main__":
    main()
