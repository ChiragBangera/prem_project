from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
from pathlib import Path


def slugify_filename(text: str):
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned or "chart"


def _svg_escape(value: str):
    return html.escape(str(value), quote=True)


def _wrap_svg_text(text: str, max_chars: int):
    words = str(text).split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _svg_text_block(lines: list[str], x: int, y: int, line_height: int, fill: str, font_family: str, font_size: int, font_weight: str | int = "400", letter_spacing: str | None = None):
    style_bits = [
        f'fill="{fill}"',
        f'font-family="{font_family}"',
        f'font-size="{font_size}"',
        f'font-weight="{font_weight}"',
    ]
    if letter_spacing is not None:
        style_bits.append(f'letter-spacing="{letter_spacing}"')
    tspans = []
    for index, line in enumerate(lines):
        tspans.append(
            f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{_svg_escape(line)}</tspan>'
        )
    return f'<text x="{x}" y="{y}" {" ".join(style_bits)}>{"".join(tspans)}</text>'


def _team_compare_metric_block(x: int, y: int, width: int, label: str, value: str, ratio: float, accent: str, ink: str, muted: str, track: str):
    bar_width = max(36, int(width * max(0.0, min(ratio, 1.0))))
    label_escaped = _svg_escape(label)
    value_escaped = _svg_escape(value)
    return f"""
    <g transform="translate({x} {y})">
      <text x="0" y="0" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" letter-spacing="0.2">{label_escaped}</text>
      <text x="{width + 38}" y="0" text-anchor="end" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="22" font-weight="700">{value_escaped}</text>
      <rect x="0" y="18" width="{width}" height="12" rx="6" fill="{track}" />
      <rect x="0" y="18" width="{bar_width}" height="12" rx="6" fill="{accent}" />
    </g>
    """.strip()


def _format_pct(value: float):
    return f"{value * 100:.1f}%"


def _truncate_text(text: str, max_chars: int):
    text = str(text)
    return text if len(text) <= max_chars else f"{text[: max_chars - 1]}…"


def _distribution_meter(x: int, y: int, width: int, ratio: float, accent: str, track: str):
    fill_width = max(4, int(width * max(0.0, min(ratio, 1.0))))
    return f"""
    <rect x="{x}" y="{y}" width="{width}" height="10" rx="5" fill="{track}" />
    <rect x="{x}" y="{y}" width="{fill_width}" height="10" rx="5" fill="{accent}" />
    """.strip()


def _distribution_row(row_index: int, player: dict, x: int, y: int, width: int, palette: dict, highlight_names: set[str]):
    ink = "#F6F1E8"
    muted = "#9FA8BC"
    quiet = "#64748B"
    track = "#1E293B"
    border = "#223146"
    accent = palette["accent"]
    player_name = str(player.get("player_name", "Player"))
    highlight = player_name in highlight_names
    background = "#18263A" if highlight else "#111B29"

    xa_share = float(player.get("xA_share", 0))
    xgxa_share = float(player.get("xGxA_share", 0))
    goals = _svg_escape(player.get("goals", 0))
    xa = _svg_escape(player.get("xA", 0))
    xgxa = _svg_escape(player.get("xGxA", 0))
    shots = _svg_escape(player.get("shots", 0))
    minutes = _svg_escape(player.get("minutes", 0))
    rank_label = _svg_escape(str(row_index + 1).zfill(2))
    display_name = _svg_escape(_truncate_text(player_name, 22))

    return f"""
    <g transform="translate({x} {y})">
      <rect x="0" y="0" width="{width}" height="48" rx="14" fill="{background}" stroke="{border}" stroke-width="1" />
      <text x="16" y="29" fill="{quiet}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" font-weight="700">{rank_label}</text>
      <text x="48" y="29" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="17" font-weight="700">{display_name}</text>
      <text x="244" y="16" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="11" letter-spacing="0.6">xA SHARE</text>
      {_distribution_meter(244, 24, 120, xa_share, accent, track)}
      <text x="372" y="31" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700">{_svg_escape(_format_pct(xa_share))}</text>
      <text x="448" y="16" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="11" letter-spacing="0.6">xG+xA SHARE</text>
      <text x="448" y="31" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700">{_svg_escape(_format_pct(xgxa_share))}</text>
      <text x="580" y="16" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="11" letter-spacing="0.6">xA</text>
      <text x="580" y="31" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700">{xa}</text>
      <text x="636" y="16" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="11" letter-spacing="0.6">xG+xA</text>
      <text x="636" y="31" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700">{xgxa}</text>
      <text x="720" y="16" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="11" letter-spacing="0.6">S</text>
      <text x="720" y="31" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700">{shots}</text>
      <text x="764" y="16" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="11" letter-spacing="0.6">MIN</text>
      <text x="764" y="31" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700">{minutes}</text>
      <text x="814" y="16" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="11" letter-spacing="0.6">G</text>
      <text x="814" y="31" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700">{goals}</text>
    </g>
    """.strip()


def _render_player_distribution_compare_svg(visualization_payload: dict, output_path: str | Path, width: int = 1900, height: int = 2860):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    left = visualization_payload.get("left_window") or {}
    right = visualization_payload.get("right_window") or {}
    focus_rows = visualization_payload.get("focus_rows") or []
    kicker = _svg_escape(visualization_payload.get("kicker", "PLAYER LOAD MAP"))
    headline_lines = _wrap_svg_text(visualization_payload.get("headline", "Chance creation distribution"), max_chars=42)
    subtitle = _svg_escape(visualization_payload.get("subtitle", "Manchester United by coach window"))
    footer = _svg_escape(visualization_payload.get("footer", "Data source: Understat"))
    title = _svg_escape(visualization_payload.get("title", "Player distribution compare"))
    stat_lines = visualization_payload.get("stat_lines") or []
    highlight_names = set(visualization_payload.get("highlight_names") or [])

    ink = "#F6F1E8"
    muted = "#9FA8BC"
    quiet = "#667085"
    border = "#223146"
    surface = "#0D1522"
    panel = "#121D2D"

    def render_window_card(window: dict, x: int, y: int, palette: dict):
        rows = window.get("rows") or []
        totals = window.get("totals") or {}
        summary_lines = window.get("summary_lines") or []
        label = _svg_escape(window.get("label", "Window"))
        sublabel = _svg_escape(window.get("sublabel", ""))
        top_y = 150

        summary_svg = []
        for index, line in enumerate(summary_lines[:3]):
            summary_svg.append(
                f'<text x="42" y="{top_y + (index * 30)}" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18">{_svg_escape(line)}</text>'
            )

        row_svgs = []
        base_y = 246
        row_gap = 54
        for index, row in enumerate(rows):
            row_svgs.append(_distribution_row(index, row, 32, base_y + (index * row_gap), 806, palette, highlight_names))

        return f"""
        <g transform="translate({x} {y})">
          <rect x="0" y="0" width="870" height="1710" rx="34" fill="{panel}" stroke="{border}" stroke-width="2" />
          <rect x="0" y="0" width="870" height="10" rx="10" fill="{palette['accent']}" />
          <text x="42" y="64" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="36" font-weight="800">{label}</text>
          <text x="42" y="102" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="20">{sublabel}</text>
          <rect x="560" y="38" width="268" height="80" rx="20" fill="{palette['accent_soft']}" fill-opacity="0.18" />
          <text x="586" y="68" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" letter-spacing="0.8">TEAM TOTALS</text>
          <text x="586" y="98" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="20" font-weight="700">xA {totals.get('xA', 0)} | xG {totals.get('xG', 0)} | Shots {totals.get('shots', 0)}</text>
          {''.join(summary_svg)}
          {''.join(row_svgs)}
        </g>
        """.strip()

    def render_focus_row(row: dict, y: int):
        player = _svg_escape(row.get("player_name", "Player"))
        left_metrics = row.get("left") or {}
        right_metrics = row.get("right") or {}
        return f"""
        <g transform="translate(48 {y})">
          <rect x="0" y="0" width="1504" height="70" rx="20" fill="#111B29" stroke="{border}" stroke-width="1" />
          <text x="24" y="43" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="22" font-weight="700">{player}</text>
          <text x="360" y="25" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="12" letter-spacing="0.8">AMORIM</text>
          <text x="360" y="49" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18">xA {left_metrics.get('xA', 0)} | xG+xA {left_metrics.get('xGxA', 0)} | Shots {left_metrics.get('shots', 0)} | Min {left_metrics.get('minutes', 0)}</text>
          <text x="960" y="25" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="12" letter-spacing="0.8">CARRICK</text>
          <text x="960" y="49" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18">xA {right_metrics.get('xA', 0)} | xG+xA {right_metrics.get('xGxA', 0)} | Shots {right_metrics.get('shots', 0)} | Min {right_metrics.get('minutes', 0)}</text>
        </g>
        """.strip()

    annotation_svg = []
    for index, line in enumerate(stat_lines[:4]):
        annotation_svg.append(
            f'<text x="96" y="{88 + (index * 38)}" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="24">{_svg_escape(line)}</text>'
        )

    focus_svg = []
    for index, row in enumerate(focus_rows[:4]):
        focus_svg.append(render_focus_row(row, 76 + (index * 90)))

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#050B14" />
      <stop offset="50%" stop-color="#0A1220" />
      <stop offset="100%" stop-color="#111C2F" />
    </linearGradient>
    <radialGradient id="leftGlow" cx="0.14" cy="0.08" r="0.44">
      <stop offset="0%" stop-color="{left.get('palette', {}).get('accent', '#C8102E')}" stop-opacity="0.22" />
      <stop offset="100%" stop-color="{left.get('palette', {}).get('accent', '#C8102E')}" stop-opacity="0" />
    </radialGradient>
    <radialGradient id="rightGlow" cx="0.86" cy="0.08" r="0.44">
      <stop offset="0%" stop-color="{right.get('palette', {}).get('accent', '#F59E0B')}" stop-opacity="0.18" />
      <stop offset="100%" stop-color="{right.get('palette', {}).get('accent', '#F59E0B')}" stop-opacity="0" />
    </radialGradient>
  </defs>
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#bg)" />
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#leftGlow)" />
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#rightGlow)" />
  <rect x="28" y="28" width="{width - 56}" height="{height - 56}" rx="38" fill="none" stroke="#1D2939" stroke-width="2" />

  <g transform="translate(68 70)">
    <rect x="0" y="0" width="228" height="42" rx="21" fill="#132032" />
    <text x="114" y="28" text-anchor="middle" fill="#E6D5B7" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700" letter-spacing="1.4">{kicker}</text>
    {_svg_text_block(headline_lines, x=0, y=104, line_height=64, fill=ink, font_family="Helvetica Neue, Arial, sans-serif", font_size=58, font_weight="800")}
    <text x="0" y="{128 + ((len(headline_lines) - 1) * 64)}" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="26">{subtitle}</text>
  </g>

  {render_window_card(left, 68, 250, left.get('palette', {'accent': '#C8102E', 'accent_soft': '#F59E0B'}))}
  {render_window_card(right, 962, 250, right.get('palette', {'accent': '#F59E0B', 'accent_soft': '#38BDF8'}))}

  <g transform="translate(68 2010)">
    <rect x="0" y="0" width="1764" height="330" rx="34" fill="{surface}" stroke="{border}" stroke-width="2" />
    <text x="28" y="48" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="24" font-weight="700" letter-spacing="1.1">WHAT CHANGED</text>
    {''.join(annotation_svg)}
  </g>

  <g transform="translate(68 2358)">
    <rect x="0" y="0" width="1764" height="420" rx="34" fill="{surface}" stroke="{border}" stroke-width="2" />
    <text x="28" y="48" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="24" font-weight="700" letter-spacing="1.1">FOCUS PLAYERS</text>
    {''.join(focus_svg)}
  </g>

  <text x="68" y="{height - 36}" fill="{quiet}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18">{footer}</text>
</svg>"""

    output.write_text(svg, encoding="utf-8")
    return output


def _render_prematch_matchup_svg(visualization_payload: dict, output_path: str | Path, width: int = 1080, height: int = 1350):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    teams = visualization_payload.get("teams") or []
    if len(teams) != 2:
        raise RuntimeError("Prematch matchup renderer requires exactly two teams.")

    kicker = _svg_escape(visualization_payload.get("kicker", "MATCHUP"))
    headline_lines = _wrap_svg_text(visualization_payload.get("headline", "Prematch comparison"), max_chars=28)
    subtitle = _svg_escape(visualization_payload.get("subtitle", "Fixture preview"))
    footer = _svg_escape(visualization_payload.get("footer", "Data source: Understat"))
    title = _svg_escape(visualization_payload.get("title", "Prematch matchup"))
    stat_lines = visualization_payload.get("stat_lines") or []
    focus_players = visualization_payload.get("focus_players") or []

    ink = "#F6F1E8"
    muted = "#9FA8BC"
    quiet = "#667085"
    panel = "#121D2D"
    surface = "#0D1522"
    border = "#223146"
    subtitle_y = 110 + ((len(headline_lines) - 1) * 68) + 42

    def render_stat_row(x: int, y: int, label: str, value: str, accent: str):
        return f"""
        <g transform="translate({x} {y})">
          <text x="0" y="0" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" letter-spacing="1.0">{_svg_escape(label.upper())}</text>
          <text x="0" y="36" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="30" font-weight="800">{_svg_escape(value)}</text>
          <rect x="0" y="52" width="150" height="3" rx="2" fill="{accent}" fill-opacity="0.9" />
        </g>
        """.strip()

    def render_team_card(team: dict, x: int):
        accent = team.get("accent", "#E76F51")
        accent_soft = team.get("accent_soft", "#F4A261")
        name = _svg_escape(team.get("name", "Team"))
        short_name = _svg_escape(team.get("short_name", "TEAM"))
        context_label = _svg_escape(team.get("context_label", ""))
        points = _svg_escape(team.get("points", "0"))
        venue_record = _svg_escape(team.get("venue_record", "-"))
        recent_record = _svg_escape(team.get("recent_record", "-"))
        recent_sequence = team.get("recent_sequence") or []
        metrics = team.get("metrics") or []
        player_note = _svg_escape(team.get("player_note", ""))

        chips = []
        for index, result in enumerate(recent_sequence[:5]):
            result_value = str(result).upper()
            chip_fill = {"W": accent, "D": "#A78BFA", "L": "#475467"}.get(result_value, "#475467")
            chips.append(
                f"""
                <g transform="translate({index * 62} 0)">
                  <rect x="0" y="0" width="50" height="32" rx="16" fill="{chip_fill}" fill-opacity="0.96" />
                  <text x="25" y="21" text-anchor="middle" fill="#F8FAFC" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700">{_svg_escape(result_value)}</text>
                </g>
                """.strip()
            )

        metric_groups = []
        metric_positions = [(0, 0), (190, 0), (0, 112), (190, 112)]
        for index, metric in enumerate(metrics[:4]):
            metric_groups.append(
                render_stat_row(
                    x=metric_positions[index][0],
                    y=metric_positions[index][1],
                    label=metric.get("label", ""),
                    value=metric.get("value", ""),
                    accent=accent,
                )
            )

        return f"""
        <g transform="translate({x} 286)">
          <rect x="0" y="0" width="450" height="670" rx="34" fill="{panel}" stroke="{border}" stroke-width="2" />
          <rect x="0" y="0" width="450" height="10" rx="10" fill="{accent}" />
          <text x="34" y="54" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" letter-spacing="1.6">{context_label}</text>
          <text x="34" y="100" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="40" font-weight="800">{name}</text>

          <text x="34" y="146" fill="{quiet}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="700" letter-spacing="1.0">VENUE POINTS</text>
          <text x="34" y="242" fill="{accent}" font-family="Helvetica Neue, Arial, sans-serif" font-size="118" font-weight="800">{points}</text>

          <rect x="278" y="138" width="138" height="34" rx="17" fill="{accent_soft}" fill-opacity="0.18" />
          <text x="347" y="160" text-anchor="middle" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="700">{short_name}</text>

          <g transform="translate(34 276)">
            <text x="0" y="0" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" letter-spacing="1.2">VENUE W-D-L</text>
            <text x="0" y="34" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="34" font-weight="800">{venue_record}</text>
          </g>

          <g transform="translate(34 350)">
            <text x="0" y="0" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" letter-spacing="1.2">LAST 5 FORM</text>
            <text x="0" y="32" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="30" font-weight="800">{recent_record}</text>
            <g transform="translate(0 52)">{''.join(chips)}</g>
          </g>

          <g transform="translate(34 476)">{''.join(metric_groups)}</g>

          <line x1="34" y1="598" x2="416" y2="598" stroke="{border}" stroke-width="1" />
          <text x="34" y="632" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" letter-spacing="1.0">KEY PLAYER</text>
          <text x="34" y="656" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="700">{player_note}</text>
        </g>
        """.strip()

    focus_rows = []
    for index, player in enumerate(focus_players[:3]):
        y = 92 + (index * 64)
        focus_rows.append(
            f"""
            <g transform="translate(40 {y})">
              <circle cx="8" cy="10" r="4" fill="#C8A96A" />
              <text x="24" y="16" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="22" font-weight="700">{_svg_escape(player.get('name', 'Player'))}</text>
              <text x="250" y="16" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="20">{_svg_escape(player.get('note', ''))}</text>
            </g>
            """.strip()
        )

    highlight_rows = []
    for index, line in enumerate(stat_lines[:2]):
        parts = _wrap_svg_text(line, max_chars=54)
        highlight_rows.append(
            f"""
            <g transform="translate(40 {72 + (index * 86)})">
              <circle cx="8" cy="12" r="5" fill="#C8A96A" />
              {_svg_text_block(parts, x=28, y=18, line_height=30, fill=ink, font_family="Helvetica Neue, Arial, sans-serif", font_size=24, font_weight="700")}
            </g>
            """.strip()
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#040B14" />
      <stop offset="55%" stop-color="#0A1220" />
      <stop offset="100%" stop-color="#101C2E" />
    </linearGradient>
    <radialGradient id="leftGlow" cx="0.14" cy="0.1" r="0.5">
      <stop offset="0%" stop-color="{teams[0].get('accent', '#C8102E')}" stop-opacity="0.2" />
      <stop offset="100%" stop-color="{teams[0].get('accent', '#C8102E')}" stop-opacity="0" />
    </radialGradient>
    <radialGradient id="rightGlow" cx="0.86" cy="0.1" r="0.5">
      <stop offset="0%" stop-color="{teams[1].get('accent', '#1D4ED8')}" stop-opacity="0.18" />
      <stop offset="100%" stop-color="{teams[1].get('accent', '#1D4ED8')}" stop-opacity="0" />
    </radialGradient>
  </defs>
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#bg)" />
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#leftGlow)" />
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#rightGlow)" />
  <rect x="28" y="28" width="{width - 56}" height="{height - 56}" rx="38" fill="none" stroke="#1D2939" stroke-width="2" />

  <g transform="translate(78 74)">
    <rect x="0" y="0" width="150" height="40" rx="20" fill="#132032" />
    <text x="75" y="26" text-anchor="middle" fill="#E6D5B7" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700" letter-spacing="1.4">{kicker}</text>
    {_svg_text_block(headline_lines, x=0, y=110, line_height=68, fill=ink, font_family="Helvetica Neue, Arial, sans-serif", font_size=64, font_weight="800")}
    <text x="0" y="{subtitle_y}" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="24">{subtitle}</text>
  </g>

  {render_team_card(teams[0], 78)}
  {render_team_card(teams[1], 552)}

  <g transform="translate(78 980)">
    <rect x="0" y="0" width="924" height="200" rx="30" fill="{surface}" stroke="{border}" stroke-width="2" />
    <text x="32" y="48" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="24" font-weight="700" letter-spacing="1.2">WHY UNITED ARE FAVORED</text>
    {''.join(highlight_rows)}
  </g>

  <g transform="translate(78 1200)">
    <rect x="0" y="0" width="924" height="108" rx="30" fill="{surface}" stroke="{border}" stroke-width="2" />
    <text x="32" y="42" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="22" font-weight="700" letter-spacing="1.0">PLAYERS TO WATCH</text>
    {''.join(focus_rows[:2])}
  </g>

  <text x="78" y="{height - 42}" fill="{quiet}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18">{footer}</text>
</svg>"""

    output.write_text(svg, encoding="utf-8")
    return output


def _render_team_compare_svg(visualization_payload: dict, output_path: str | Path, width: int = 1080, height: int = 1350):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    teams = visualization_payload.get("teams") or []
    if len(teams) != 2:
        raise RuntimeError("Custom team comparison renderer requires exactly two teams.")

    subtitle = _svg_escape(visualization_payload.get("subtitle", "Last 5 league matches"))
    footer = _svg_escape(visualization_payload.get("footer", "Data source: Understat"))
    title = _svg_escape(visualization_payload.get("title", "Team comparison"))
    kicker = _svg_escape(visualization_payload.get("kicker", "FORM CHECK"))
    stat_lines = visualization_payload.get("stat_lines") or []
    headline_lines = _wrap_svg_text(visualization_payload.get("headline", "Recent form comparison"), max_chars=28)
    wrapped_stat_lines = [_wrap_svg_text(line, max_chars=56) for line in stat_lines[:3]]
    subtitle_y = 108 + ((len(headline_lines) - 1) * 64) + 48

    ink = "#F6F1E8"
    muted = "#9FA8BC"
    quiet = "#667085"
    surface = "#0D1522"
    panel = "#121D2D"
    panel_border = "#223146"
    track = "#1E293B"

    card_width = 462
    card_height = 700
    left_x = 78
    right_x = 540
    card_y = 260

    def render_team_card(team: dict, x: int):
        accent = team.get("accent", "#E76F51")
        accent_soft = team.get("accent_soft", "#2A9D8F")
        name = _svg_escape(team.get("name", "Team"))
        short_name = _svg_escape(team.get("short_name", team.get("name", "TEAM")))
        points = _svg_escape(team.get("points", "0"))
        record = _svg_escape(team.get("record", "-"))
        results = team.get("results") or []
        metrics = team.get("metrics") or []
        summary = _svg_escape(team.get("summary", ""))

        result_chips = []
        for index, result in enumerate(results):
            result_value = str(result).upper()
            chip_fill = {"W": accent, "D": "#A78BFA", "L": "#475467"}.get(result_value, "#475467")
            result_chips.append(
                f"""
                <g transform="translate({index * 70} 0)">
                  <rect x="0" y="0" width="58" height="36" rx="18" fill="{chip_fill}" fill-opacity="0.96" />
                  <text x="29" y="24" text-anchor="middle" fill="#F8FAFC" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="700">{_svg_escape(result_value)}</text>
                </g>
                """.strip()
            )

        metric_groups = []
        for index, metric in enumerate(metrics):
            metric_groups.append(
                _team_compare_metric_block(
                    x=0,
                    y=index * 94,
                    width=314,
                    label=metric.get("label", ""),
                    value=metric.get("value", ""),
                    ratio=float(metric.get("ratio", 0)),
                    accent=accent,
                    ink=ink,
                    muted=muted,
                    track=track,
                )
            )

        return f"""
        <g transform="translate({x} {card_y})">
          <rect x="0" y="0" width="{card_width}" height="{card_height}" rx="34" fill="{panel}" stroke="{panel_border}" stroke-width="2" />
          <rect x="0" y="0" width="{card_width}" height="10" rx="10" fill="{accent}" />
          <circle cx="52" cy="58" r="14" fill="{accent}" />
          <text x="78" y="66" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="34" font-weight="700">{name}</text>
          <text x="40" y="112" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" letter-spacing="2.2">LAST 5 LEAGUE MATCHES</text>

          <text x="40" y="194" fill="{quiet}" font-family="Georgia, Times New Roman, serif" font-size="24" font-style="italic">Points</text>
          <text x="40" y="282" fill="{accent}" font-family="Helvetica Neue, Arial, sans-serif" font-size="110" font-weight="800">{points}</text>
          <rect x="196" y="172" width="180" height="44" rx="22" fill="{accent_soft}" fill-opacity="0.22" />
          <text x="286" y="200" text-anchor="middle" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="20" font-weight="700">W-D-L {record}</text>

          <text x="40" y="334" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" letter-spacing="1.8">FORM STRIP</text>
          <g transform="translate(40 356)">
            {''.join(result_chips)}
          </g>

          <g transform="translate(40 464)">
            {''.join(metric_groups)}
          </g>

          <line x1="40" y1="642" x2="{card_width - 40}" y2="642" stroke="{panel_border}" stroke-width="1" />
          <text x="40" y="678" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="600">{short_name}</text>
          <text x="{card_width - 40}" y="678" text-anchor="end" fill="{quiet}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16">{summary}</text>
        </g>
        """.strip()

    highlight_lines = []
    for index, line_parts in enumerate(wrapped_stat_lines):
        baseline_y = 88 + (index * 72)
        highlight_lines.append(
            f"""
            <g transform="translate(48 {baseline_y})">
              <circle cx="9" cy="12" r="4.5" fill="#C8A96A" />
              {_svg_text_block(line_parts, x=28, y=18, line_height=28, fill=ink, font_family="Helvetica Neue, Arial, sans-serif", font_size=26)}
            </g>
            """.strip()
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#050B14" />
      <stop offset="55%" stop-color="#0A1220" />
      <stop offset="100%" stop-color="#101C2E" />
    </linearGradient>
    <radialGradient id="glowLeft" cx="0.18" cy="0.12" r="0.54">
      <stop offset="0%" stop-color="{teams[0].get('accent', '#E76F51')}" stop-opacity="0.22" />
      <stop offset="100%" stop-color="{teams[0].get('accent', '#E76F51')}" stop-opacity="0" />
    </radialGradient>
    <radialGradient id="glowRight" cx="0.84" cy="0.1" r="0.52">
      <stop offset="0%" stop-color="{teams[1].get('accent', '#2A9D8F')}" stop-opacity="0.18" />
      <stop offset="100%" stop-color="{teams[1].get('accent', '#2A9D8F')}" stop-opacity="0" />
    </radialGradient>
  </defs>

  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#bg)" />
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#glowLeft)" />
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#glowRight)" />
  <rect x="28" y="28" width="{width - 56}" height="{height - 56}" rx="38" fill="none" stroke="#1D2939" stroke-width="2" />

  <g transform="translate(78 78)">
    <rect x="0" y="0" width="164" height="40" rx="20" fill="#132032" />
    <text x="82" y="26" text-anchor="middle" fill="#E6D5B7" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700" letter-spacing="1.4">{kicker}</text>
    {_svg_text_block(headline_lines, x=0, y=108, line_height=64, fill=ink, font_family="Helvetica Neue, Arial, sans-serif", font_size=62, font_weight="800")}
    <text x="0" y="{subtitle_y}" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="26">{subtitle}</text>
  </g>

  {render_team_card(teams[0], left_x)}
  {render_team_card(teams[1], right_x)}

  <g transform="translate(78 986)">
    <rect x="0" y="0" width="924" height="276" rx="30" fill="{surface}" stroke="#1E2A3B" stroke-width="2" />
    <text x="42" y="58" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="24" font-weight="700" letter-spacing="1.3">WHY THE EDGE LOOKS THIS WAY</text>
    {''.join(highlight_lines)}
  </g>

  <text x="78" y="{height - 48}" fill="{quiet}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18">{footer}</text>
</svg>
"""
    output.write_text(svg, encoding="utf-8")
    return output


def _chart_scale(value: float, min_value: float, max_value: float, top: int, height: int):
    if max_value <= min_value:
        return top + height
    ratio = (value - min_value) / (max_value - min_value)
    return top + height - (ratio * height)


def _render_coach_trend_insight_svg(visualization_payload: dict, output_path: str | Path, width: int = 1080, height: int = 1350):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    windows = visualization_payload.get("windows") or []
    if len(windows) != 2:
        raise RuntimeError("Coach trend insight renderer requires exactly two windows.")

    title = _svg_escape(visualization_payload.get("title", "Coach trend insight"))
    kicker = _svg_escape(visualization_payload.get("kicker", "TACTICAL TREND"))
    headline_lines = _wrap_svg_text(visualization_payload.get("headline", "Open-play xG is trending down"), max_chars=26)
    subtitle = _svg_escape(visualization_payload.get("subtitle", "Manchester United | EPL 2025/26"))
    footer = _svg_escape(visualization_payload.get("footer", "Data source: Understat"))
    verdict = _wrap_svg_text(visualization_payload.get("verdict", ""), max_chars=46)
    annotations = visualization_payload.get("annotations") or []
    latest_match = visualization_payload.get("latest_match") or {}
    max_value = float(visualization_payload.get("max_value", 3.2))
    min_value = float(visualization_payload.get("min_value", 0.0))

    paper = "#F2EDE3"
    ink = "#111318"
    muted = "#6B665F"
    faint = "#D7CFC1"
    panel = "#FFF8EC"
    red = "#C8102E"
    gold = "#B9852B"
    coal = "#1A1D21"

    chart_left = 104
    chart_top = 475
    chart_width = 872
    chart_height = 440
    all_points = [point for window in windows for point in window.get("points", [])]
    max_index = max([int(point.get("match_index", 1)) for point in all_points] or [1])
    min_index = min([int(point.get("match_index", 1)) for point in all_points] or [1])
    x_span = max(1, max_index - min_index)

    def x_for(match_index: int):
        return chart_left + ((match_index - min_index) / x_span) * chart_width

    def y_for(value: float):
        return _chart_scale(value, min_value, max_value, chart_top, chart_height)

    def point_path(points: list[dict]):
        if not points:
            return ""
        commands = []
        for index, point in enumerate(points):
            prefix = "M" if index == 0 else "L"
            commands.append(f"{prefix} {x_for(int(point.get('match_index', 1))):.1f} {y_for(float(point.get('value', 0))):.1f}")
        return " ".join(commands)

    def slope_path(window: dict):
        points = window.get("slope_points") or []
        return point_path(points)

    def render_dots(window: dict, accent: str):
        dots = []
        for point in window.get("points", []):
            cx = x_for(int(point.get("match_index", 1)))
            cy = y_for(float(point.get("value", 0)))
            dots.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="{accent}" stroke="{paper}" stroke-width="3" />'
            )
        return "".join(dots)

    def render_window_summary(window: dict, x: int, accent: str):
        label = _svg_escape(window.get("label", "Coach"))
        matches = _svg_escape(window.get("matches", "-"))
        average = _svg_escape(window.get("average", "-"))
        slope = _svg_escape(window.get("slope_label", "-"))
        note = _svg_escape(window.get("note", ""))
        return f"""
        <g transform="translate({x} 1030)">
          <rect x="0" y="0" width="420" height="174" rx="22" fill="{panel}" stroke="{faint}" stroke-width="2" />
          <rect x="0" y="0" width="420" height="8" rx="8" fill="{accent}" />
          <text x="28" y="50" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="29" font-weight="800">{label}</text>
          <text x="28" y="84" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="17">{matches} league matches</text>
          <text x="28" y="126" fill="{accent}" font-family="Helvetica Neue, Arial, sans-serif" font-size="36" font-weight="800">{average}</text>
          <text x="176" y="126" fill="{coal}" font-family="Helvetica Neue, Arial, sans-serif" font-size="24" font-weight="800">{slope}</text>
          <text x="28" y="154" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15">{note}</text>
        </g>
        """.strip()

    def render_annotation(annotation: dict):
        match_index = int(annotation.get("match_index", 1))
        value = float(annotation.get("value", 0))
        label = _svg_escape(annotation.get("label", "Match"))
        sublabel = _svg_escape(annotation.get("sublabel", ""))
        accent = annotation.get("accent", coal)
        dx = float(annotation.get("dx", 0))
        dy = float(annotation.get("dy", -64))
        box_width = int(annotation.get("width", 152))
        box_height = 58 if sublabel else 38
        point_x = x_for(match_index)
        point_y = y_for(value)
        box_x = max(chart_left + 8, min(chart_left + chart_width - box_width - 8, point_x + dx))
        box_y = max(chart_top + 42, min(chart_top + chart_height - box_height - 24, point_y + dy))
        text_y = box_y + 25
        sublabel_svg = ""
        if sublabel:
            sublabel_svg = f'<text x="{box_x + 13:.1f}" y="{box_y + 47:.1f}" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" font-weight="700">{sublabel}</text>'
        return f"""
        <g>
          <line x1="{point_x:.1f}" y1="{point_y:.1f}" x2="{box_x + 14:.1f}" y2="{box_y + box_height / 2:.1f}" stroke="{accent}" stroke-width="2" stroke-opacity="0.72" />
          <circle cx="{point_x:.1f}" cy="{point_y:.1f}" r="9" fill="{paper}" stroke="{accent}" stroke-width="4" />
          <rect x="{box_x:.1f}" y="{box_y:.1f}" width="{box_width}" height="{box_height}" rx="14" fill="{paper}" stroke="{accent}" stroke-width="2" />
          <text x="{box_x + 13:.1f}" y="{text_y:.1f}" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="17" font-weight="900">{label}</text>
          {sublabel_svg}
        </g>
        """.strip()

    def era_band(window: dict, accent: str):
        points = window.get("points") or []
        if not points:
            return ""
        start = x_for(int(points[0].get("match_index", 1)))
        end = x_for(int(points[-1].get("match_index", 1)))
        label = _svg_escape(window.get("label", "Coach").upper())
        return f"""
        <rect x="{start:.1f}" y="{chart_top}" width="{max(1, end - start):.1f}" height="{chart_height}" fill="{accent}" fill-opacity="0.055" />
        <text x="{start + 12:.1f}" y="{chart_top + 28}" fill="{accent}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="800">{label}</text>
        """.strip()

    grid_lines = []
    for value in [0, 1, 2, 3]:
        y = y_for(value)
        grid_lines.append(
            f'<line x1="{chart_left}" y1="{y:.1f}" x2="{chart_left + chart_width}" y2="{y:.1f}" stroke="{faint}" stroke-width="1" />'
        )
        grid_lines.append(
            f'<text x="{chart_left - 20}" y="{y + 5:.1f}" text-anchor="end" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16">{value}</text>'
        )

    left_window, right_window = windows
    left_path = point_path(left_window.get("points", []))
    right_path = point_path(right_window.get("points", []))
    left_slope = slope_path(left_window)
    right_slope = slope_path(right_window)
    annotation_svg = "".join(render_annotation(annotation) for annotation in annotations[:6])
    latest_label = _svg_escape(latest_match.get("label", "Latest match"))
    latest_value = _svg_escape(latest_match.get("value", ""))
    latest_note = _svg_escape(latest_match.get("note", ""))

    verdict_svg = ""
    for index, line in enumerate(verdict[:3]):
        verdict_svg += f'<tspan x="220" dy="{0 if index == 0 else 34}">{_svg_escape(line)}</tspan>'

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
  <defs>
    <linearGradient id="paper" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#F7F1E7" />
      <stop offset="100%" stop-color="#E8DFD1" />
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#5B4234" flood-opacity="0.18" />
    </filter>
  </defs>
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#paper)" />
  <rect x="32" y="32" width="{width - 64}" height="{height - 64}" rx="28" fill="none" stroke="#CFC3B3" stroke-width="2" />

  <g transform="translate(70 72)">
    <rect x="0" y="0" width="190" height="38" rx="19" fill="{coal}" />
    <text x="95" y="25" text-anchor="middle" fill="#F8F1E6" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="800">{kicker}</text>
    {_svg_text_block(headline_lines, x=0, y=102, line_height=68, fill=ink, font_family="Helvetica Neue, Arial, sans-serif", font_size=64, font_weight="900")}
    <text x="0" y="{128 + ((len(headline_lines) - 1) * 68)}" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="24">{subtitle}</text>
  </g>

  <g transform="translate(70 292)" filter="url(#shadow)">
    <rect x="0" y="0" width="940" height="122" rx="24" fill="{coal}" />
    <text x="28" y="45" fill="#F8F1E6" font-family="Helvetica Neue, Arial, sans-serif" font-size="24" font-weight="800">THE READ</text>
    <text x="220" y="48" fill="#F8F1E6" font-family="Helvetica Neue, Arial, sans-serif" font-size="25" font-weight="700">{verdict_svg}</text>
  </g>

  <g>
    <rect x="70" y="440" width="940" height="520" rx="28" fill="{panel}" stroke="{faint}" stroke-width="2" />
    <text x="104" y="458" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="800">OPEN-PLAY xG PER MATCH</text>
    {''.join(grid_lines)}
    {era_band(left_window, red)}
    {era_band(right_window, gold)}
    <path d="{left_path}" fill="none" stroke="{red}" stroke-width="4" stroke-linejoin="round" />
    <path d="{right_path}" fill="none" stroke="{gold}" stroke-width="4" stroke-linejoin="round" />
    <path d="{left_slope}" fill="none" stroke="{coal}" stroke-width="5" stroke-dasharray="13 10" opacity="0.72" />
    <path d="{right_slope}" fill="none" stroke="{coal}" stroke-width="5" stroke-dasharray="13 10" opacity="0.72" />
    {render_dots(left_window, red)}
    {render_dots(right_window, gold)}
    {annotation_svg}
    <line x1="{chart_left}" y1="{chart_top + chart_height}" x2="{chart_left + chart_width}" y2="{chart_top + chart_height}" stroke="{coal}" stroke-width="2" />
    <text x="{chart_left}" y="940" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15">Match 1</text>
    <text x="{chart_left + chart_width}" y="940" text-anchor="end" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15">Match {max_index}</text>
  </g>

  {render_window_summary(left_window, 70, red)}
  {render_window_summary(right_window, 590, gold)}

  <g transform="translate(70 1212)">
    <rect x="0" y="0" width="940" height="54" rx="18" fill="{coal}" />
    <text x="22" y="35" fill="#F8F1E6" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="900">{latest_label}</text>
    <text x="380" y="35" fill="#F8F1E6" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="700">{latest_value}</text>
    <text x="690" y="35" fill="#CFC3B3" font-family="Helvetica Neue, Arial, sans-serif" font-size="16" font-weight="700">{latest_note}</text>
  </g>

  <g transform="translate(70 1284)">
    <line x1="0" y1="0" x2="940" y2="0" stroke="#CFC3B3" stroke-width="2" />
    <text x="0" y="38" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="17">{footer}</text>
  </g>
</svg>"""

    output.write_text(svg, encoding="utf-8")
    return output


def _render_process_vs_results_lens_svg(visualization_payload: dict, output_path: str | Path, width: int = 1080, height: int = 1350):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    view_width = 1080
    view_height = 1350
    title = _svg_escape(visualization_payload.get("title", "Process vs results"))
    kicker = _svg_escape(visualization_payload.get("kicker", "PROCESS VS RESULTS"))
    headline_lines = _wrap_svg_text(visualization_payload.get("headline", "Results are not always process"), max_chars=31)
    subtitle = _svg_escape(visualization_payload.get("subtitle", "Points vs xPTS, finishing, defensive variance"))
    footer = _svg_escape(visualization_payload.get("footer", "Data source: Understat"))
    metric_series = visualization_payload.get("metric_series") or {}
    categories = visualization_payload.get("categories") or []
    rankings = visualization_payload.get("rankings") or {}

    rows = []
    def series_value(name: str, index: int):
        values = metric_series.get(name) or []
        if index >= len(values):
            return 0
        return values[index]

    for index, team in enumerate(categories):
        rows.append(
            {
                "team": team,
                "points_gap": float(series_value("points_minus_xpts", index)),
                "finishing_gap": float(series_value("goals_minus_xg", index)),
                "defensive_gap": float(series_value("xga_minus_goals_against", index)),
            }
        )

    ink = "#162033"
    cream = "#6F5E45"
    muted = "#6B7280"
    green = "#168A4A"
    red = "#C73A32"
    amber = "#C77A10"
    blue = "#147AA6"
    paper = "#F7F0E4"
    panel = "#FFFDF8"
    panel_2 = "#FFFFFF"
    border = "#DACDBA"

    def signed(value: float):
        return f"{value:+.2f}"

    def cell_fill(value: float):
        return green if value >= 0 else red

    def heat_cell(x: int, y: int, width_px: int, value: float):
        opacity = min(0.92, 0.34 + (abs(value) / 18))
        return f"""
        <rect x="{x}" y="{y}" width="{width_px}" height="27" rx="10" fill="{cell_fill(value)}" fill-opacity="{opacity:.2f}" />
        <text x="{x + width_px / 2:.0f}" y="{y + 19}" text-anchor="middle" fill="#FFFFFF" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="900">{_svg_escape(signed(value))}</text>
        """.strip()

    def ranking_value(key: str, field: str):
        row = rankings.get(key) or {}
        return row.get(field, 0)

    def ranking_team(key: str, max_chars: int = 20):
        return _truncate_text((rankings.get(key) or {}).get("team", "Team"), max_chars)

    def spotlight_card(x: int, y: int, width_px: int, accent: str, label: str, main_key: str, main_field: str, counter_key: str, counter_field: str, note: str):
        main_value = ranking_value(main_key, main_field)
        counter_value = ranking_value(counter_key, counter_field)
        return f"""
        <g transform="translate({x} {y})">
          <rect x="0" y="0" width="{width_px}" height="154" rx="24" fill="{panel_2}" stroke="{border}" stroke-width="1.5" />
          <rect x="0" y="0" width="{width_px}" height="7" rx="7" fill="{accent}" />
          <text x="24" y="38" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.8">{_svg_escape(label)}</text>
          <text x="24" y="76" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="25" font-weight="900">{_svg_escape(ranking_team(main_key, 14))}</text>
          <text x="{width_px - 24}" y="76" text-anchor="end" fill="{accent}" font-family="Helvetica Neue, Arial, sans-serif" font-size="25" font-weight="900">{_svg_escape(signed(float(main_value)))}</text>
          <text x="24" y="110" fill="{cream}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="800">Lowest: {_svg_escape(ranking_team(counter_key, 13))}</text>
          <text x="{width_px - 24}" y="110" text-anchor="end" fill="{cream}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="900">{_svg_escape(signed(float(counter_value)))}</text>
          <text x="24" y="137" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13">{_svg_escape(note)}</text>
        </g>
        """.strip()

    row_svgs = []
    for index, row in enumerate(rows[:20]):
        y = 616 + (index * 31)
        stripe = "#F1E7D7" if index % 2 == 0 else "#FFF9EF"
        row_svgs.append(
            f"""
            <g>
              <rect x="68" y="{y - 21}" width="944" height="31" rx="12" fill="{stripe}" />
              <text x="90" y="{y}" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="17" font-weight="800">{_svg_escape(_truncate_text(row['team'], 27))}</text>
              {heat_cell(398, y - 22, 172, row["points_gap"])}
              {heat_cell(598, y - 22, 172, row["finishing_gap"])}
              {heat_cell(798, y - 22, 172, row["defensive_gap"])}
            </g>
            """.strip()
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {view_width} {view_height}" role="img" aria-label="{title}">
  <defs>
    <linearGradient id="lensBg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FFF9EF" />
      <stop offset="58%" stop-color="#F7F0E4" />
      <stop offset="100%" stop-color="#EEE0CB" />
    </linearGradient>
    <radialGradient id="greenGlow" cx="0.16" cy="0.12" r="0.52">
      <stop offset="0%" stop-color="{green}" stop-opacity="0.11" />
      <stop offset="100%" stop-color="{green}" stop-opacity="0" />
    </radialGradient>
    <radialGradient id="redGlow" cx="0.92" cy="0.10" r="0.50">
      <stop offset="0%" stop-color="{red}" stop-opacity="0.08" />
      <stop offset="100%" stop-color="{red}" stop-opacity="0" />
    </radialGradient>
    <filter id="lensShadow">
      <feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#B89F79" flood-opacity="0.18" />
    </filter>
  </defs>
  <rect x="0" y="0" width="{view_width}" height="{view_height}" fill="url(#lensBg)" />
  <rect x="0" y="0" width="{view_width}" height="{view_height}" fill="url(#greenGlow)" />
  <rect x="0" y="0" width="{view_width}" height="{view_height}" fill="url(#redGlow)" />
  <rect x="32" y="32" width="1016" height="1286" rx="34" fill="none" stroke="#D6C7B1" stroke-width="2" />

  <g transform="translate(68 70)">
    <rect x="0" y="0" width="236" height="40" rx="20" fill="#162033" />
    <text x="118" y="27" text-anchor="middle" fill="#FFF9EF" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="900" letter-spacing="1.2">{kicker}</text>
    {_svg_text_block(headline_lines, x=0, y=108, line_height=58, fill=ink, font_family="Helvetica Neue, Arial, sans-serif", font_size=56, font_weight="900")}
    <text x="0" y="{138 + ((len(headline_lines) - 1) * 64)}" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="23">{subtitle}</text>
  </g>

  <g filter="url(#lensShadow)">
    {spotlight_card(68, 284, 296, green, "POINTS VS PROCESS", "points_overperformer", "points_gap", "points_underperformer", "points_gap", "Points minus xPTS")}
    {spotlight_card(392, 284, 296, amber, "FINISHING QUALITY", "finishing_overperformer", "finishing_gap", "finishing_underperformer", "finishing_gap", "Goals minus xG")}
    {spotlight_card(716, 284, 296, blue, "DEFENSIVE PREVENTION", "defensive_overperformer", "defensive_prevention_gap", "defensive_underperformer", "defensive_prevention_gap", "xGA minus goals against")}
  </g>

  <g transform="translate(68 494)">
    <rect x="0" y="0" width="944" height="744" rx="28" fill="{panel}" stroke="{border}" stroke-width="2" />
    <text x="22" y="42" fill="{cream}" font-family="Helvetica Neue, Arial, sans-serif" font-size="21" font-weight="900">FULL LEAGUE VARIANCE TABLE</text>
    <text x="330" y="80" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.8">POINTS - xPTS</text>
    <text x="536" y="80" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.8">GOALS - xG</text>
    <text x="728" y="80" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.8">xGA - GA</text>
    <text x="22" y="80" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.8">TEAM</text>
  </g>

  {''.join(row_svgs)}

  <g transform="translate(68 1268)">
    <rect x="0" y="0" width="448" height="36" rx="18" fill="{green}" fill-opacity="0.14" />
    <text x="24" y="24" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="800">Positive = above model expectation</text>
    <rect x="496" y="0" width="448" height="36" rx="18" fill="{red}" fill-opacity="0.14" />
    <text x="520" y="24" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="800">Negative = below model expectation</text>
    <text x="0" y="62" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14">{footer}</text>
  </g>
</svg>"""

    output.write_text(svg, encoding="utf-8")
    return output


def _render_goalkeeper_variance_svg(visualization_payload: dict, output_path: str | Path, width: int = 1080, height: int = 1350):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    view_width = 1080
    view_height = 1350
    title = _svg_escape(visualization_payload.get("title", "Goalkeeper variance"))
    kicker = _svg_escape(visualization_payload.get("kicker", "KEEPER VARIANCE"))
    headline_lines = _wrap_svg_text(visualization_payload.get("headline", "Who is beating xGA?"), max_chars=34)
    subtitle = _svg_escape(visualization_payload.get("subtitle", "Premier League goalkeeper starts"))
    footer = _svg_escape(visualization_payload.get("footer", "Data source: Understat"))
    rows = visualization_payload.get("rows") or []
    focus = visualization_payload.get("focus") or {}

    ink = "#142033"
    muted = "#667085"
    brown = "#6F5E45"
    paper = "#F8F0E4"
    panel = "#FFFDF8"
    line = "#D8C9B5"
    green = "#168A4A"
    red = "#C73A32"
    blue = "#147AA6"

    max_abs = max([abs(float(row.get("xga_minus_ga", 0))) for row in rows] + [1])
    max_starts = max([float(row.get("starts", 0)) for row in rows] + [1])
    max_xpts_gap = max([abs(float(row.get("pts_minus_xpts", 0))) for row in rows] + [1])

    def signed(value: float):
        return f"{value:+.2f}"

    def ratio_bar(x: int, y: int, width_px: int, value: float, max_value: float, positive_color: str = green):
        center = x + (width_px / 2)
        half = width_px / 2
        bar_width = min(half, half * abs(value) / max_value)
        fill = positive_color if value >= 0 else red
        bar_x = center if value >= 0 else center - bar_width
        return f"""
        <line x1="{x}" y1="{y + 10}" x2="{x + width_px}" y2="{y + 10}" stroke="#E6D9C8" stroke-width="8" stroke-linecap="round" />
        <line x1="{center}" y1="{y + 10}" x2="{center}" y2="{y + 10}" stroke="{brown}" stroke-width="16" stroke-linecap="round" />
        <rect x="{bar_x:.1f}" y="{y + 3}" width="{bar_width:.1f}" height="14" rx="7" fill="{fill}" />
        """.strip()

    def starts_pill(x: int, y: int, starts: float):
        fill_width = max(10, 74 * starts / max_starts)
        return f"""
        <rect x="{x}" y="{y}" width="74" height="12" rx="6" fill="#E6D9C8" />
        <rect x="{x}" y="{y}" width="{fill_width:.1f}" height="12" rx="6" fill="{blue}" fill-opacity="0.78" />
        """.strip()

    def focus_card(x: int, y: int):
        if not focus:
            return ""
        return f"""
        <g transform="translate({x} {y})">
          <rect x="0" y="0" width="944" height="138" rx="26" fill="{panel}" stroke="{line}" stroke-width="2" />
          <text x="28" y="39" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" font-weight="900" letter-spacing="0.9">FOCUS PLAYER</text>
          <text x="28" y="86" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="36" font-weight="900">{_svg_escape(focus.get('player', 'Player'))}</text>
          <text x="28" y="116" fill="{brown}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="800">{_svg_escape(focus.get('team', 'Team'))} | {_svg_escape(focus.get('record', ''))} | {_svg_escape(str(focus.get('starts', '')))} starts</text>
          <text x="462" y="43" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900">xGA - GA</text>
          <text x="462" y="88" fill="{green if float(focus.get('xga_minus_ga', 0)) >= 0 else red}" font-family="Helvetica Neue, Arial, sans-serif" font-size="42" font-weight="900">{_svg_escape(signed(float(focus.get('xga_minus_ga', 0))))}</text>
          <text x="650" y="43" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900">PTS - xPTS</text>
          <text x="650" y="88" fill="{green if float(focus.get('pts_minus_xpts', 0)) >= 0 else red}" font-family="Helvetica Neue, Arial, sans-serif" font-size="42" font-weight="900">{_svg_escape(signed(float(focus.get('pts_minus_xpts', 0))))}</text>
          <text x="824" y="43" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900">GA / xGA</text>
          <text x="824" y="88" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="31" font-weight="900">{_svg_escape(str(focus.get('ga', 0)))} / {_svg_escape(str(focus.get('xga', 0)))}</text>
        </g>
        """.strip()

    row_svgs = []
    for index, row in enumerate(rows[:28]):
        y = 604 + (index * 22)
        bg = "#F0E4D3" if index % 2 == 0 else "#FFF9EF"
        is_focus = row.get("player") == focus.get("player") and row.get("team") == focus.get("team")
        stroke = blue if is_focus else "none"
        stroke_width = 2 if is_focus else 0
        xga_gap = float(row.get("xga_minus_ga", 0))
        xpts_gap = float(row.get("pts_minus_xpts", 0))
        row_svgs.append(
            f"""
            <g>
              <rect x="68" y="{y - 17}" width="944" height="20" rx="9" fill="{bg}" stroke="{stroke}" stroke-width="{stroke_width}" />
              <text x="88" y="{y}" fill="{brown}" font-family="Helvetica Neue, Arial, sans-serif" font-size="12" font-weight="900">{_svg_escape(str(row.get('rank', index + 1)).zfill(2))}</text>
              <text x="126" y="{y}" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900">{_svg_escape(_truncate_text(row.get('player', 'Player'), 22))}</text>
              <text x="340" y="{y}" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="12" font-weight="800">{_svg_escape(_truncate_text(row.get('team', 'Team'), 13))}</text>
              <text x="492" y="{y}" text-anchor="end" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900">{_svg_escape(str(row.get('starts', 0)))}</text>
              {starts_pill(506, y - 10, float(row.get('starts', 0)))}
              <text x="660" y="{y}" text-anchor="end" fill="{green if xga_gap >= 0 else red}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900">{_svg_escape(signed(xga_gap))}</text>
              {ratio_bar(678, y - 10, 138, xga_gap, max_abs)}
              <text x="878" y="{y}" text-anchor="end" fill="{green if xpts_gap >= 0 else red}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900">{_svg_escape(signed(xpts_gap))}</text>
              <text x="966" y="{y}" text-anchor="end" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900">{_svg_escape(str(row.get('ga', 0)))} / {_svg_escape(str(row.get('xga', 0)))}</text>
            </g>
            """.strip()
        )

    top_three = rows[:3]
    top_labels = []
    for index, row in enumerate(top_three):
        top_labels.append(
            f'<text x="{68 + (index * 310)}" y="470" fill="{ink}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="900">{index + 1}. {_svg_escape(_truncate_text(row.get("player", "Player"), 18))}</text>'
            f'<text x="{68 + (index * 310)}" y="494" fill="{green if float(row.get("xga_minus_ga", 0)) >= 0 else red}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="900">{_svg_escape(signed(float(row.get("xga_minus_ga", 0))))} xGA-GA</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {view_width} {view_height}" role="img" aria-label="{title}">
  <defs>
    <linearGradient id="gkBg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FFF9EF" />
      <stop offset="65%" stop-color="{paper}" />
      <stop offset="100%" stop-color="#ECDFC9" />
    </linearGradient>
    <radialGradient id="gkGlow" cx="0.16" cy="0.05" r="0.48">
      <stop offset="0%" stop-color="{green}" stop-opacity="0.10" />
      <stop offset="100%" stop-color="{green}" stop-opacity="0" />
    </radialGradient>
    <filter id="softShadow">
      <feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#B89F79" flood-opacity="0.16" />
    </filter>
  </defs>
  <rect x="0" y="0" width="{view_width}" height="{view_height}" fill="url(#gkBg)" />
  <rect x="0" y="0" width="{view_width}" height="{view_height}" fill="url(#gkGlow)" />
  <rect x="32" y="32" width="1016" height="1286" rx="34" fill="none" stroke="{line}" stroke-width="2" />

  <g transform="translate(68 70)">
    <rect x="0" y="0" width="220" height="40" rx="20" fill="{ink}" />
    <text x="110" y="27" text-anchor="middle" fill="#FFF9EF" font-family="Helvetica Neue, Arial, sans-serif" font-size="15" font-weight="900" letter-spacing="1.1">{kicker}</text>
    {_svg_text_block(headline_lines, x=0, y=108, line_height=50, fill=ink, font_family="Helvetica Neue, Arial, sans-serif", font_size=48, font_weight="900")}
    <text x="0" y="{132 + ((len(headline_lines) - 1) * 50)}" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18">{subtitle}</text>
  </g>

  <g filter="url(#softShadow)">
    {focus_card(68, 258)}
  </g>

  <g>
    <text x="68" y="438" fill="{brown}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18" font-weight="900">TOP xGA-GA OVERPERFORMERS</text>
    {''.join(top_labels)}
  </g>

  <g transform="translate(68 512)">
    <rect x="0" y="0" width="944" height="758" rx="28" fill="{panel}" stroke="{line}" stroke-width="2" />
    <text x="20" y="38" fill="{brown}" font-family="Helvetica Neue, Arial, sans-serif" font-size="20" font-weight="900">QUALIFYING PREMIER LEAGUE STARTING KEEPERS</text>
    <text x="20" y="72" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.7">RK</text>
    <text x="58" y="72" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.7">KEEPER</text>
    <text x="272" y="72" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.7">TEAM</text>
    <text x="424" y="72" text-anchor="end" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.7">STARTS</text>
    <text x="592" y="72" text-anchor="end" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.7">xGA - GA</text>
    <text x="810" y="72" text-anchor="end" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.7">PTS - xPTS</text>
    <text x="898" y="72" text-anchor="end" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" font-weight="900" letter-spacing="0.7">GA / xGA</text>
  </g>

  {''.join(row_svgs)}

  <g transform="translate(68 1292)">
    <text x="0" y="0" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14">{footer}</text>
    <text x="0" y="22" fill="{muted}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14">Positive xGA-GA = team conceded fewer than expected in that keeper's starts. Understat does not provide post-shot xG/saves.</text>
  </g>
</svg>"""

    output.write_text(svg, encoding="utf-8")
    return output


def render_echarts_svg(visualization_payload: dict, output_path: str | Path, width: int = 1200, height: int = 675):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    script_path = Path(__file__).resolve().parents[2] / "scripts" / "render_echarts.mjs"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as temp_file:
        json.dump(visualization_payload, temp_file, ensure_ascii=False)
        temp_file_path = temp_file.name

    try:
        subprocess.run(
            [
                "node",
                str(script_path),
                "--input",
                temp_file_path,
                "--output",
                str(output),
                "--width",
                str(width),
                "--height",
                str(height),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip() or "ECharts rendering failed.") from exc

    return output


def render_svg_to_png(svg_path: str | Path, png_path: str | Path | None = None, density: int = 144):
    svg_output = Path(svg_path)
    if png_path is None:
        png_output = svg_output.with_suffix(".png")
    else:
        png_output = Path(png_path)
    png_output.parent.mkdir(parents=True, exist_ok=True)

    script_path = Path(__file__).resolve().parents[2] / "scripts" / "render_svg_to_png.mjs"
    try:
        subprocess.run(
            [
                "node",
                str(script_path),
                "--input",
                str(svg_output),
                "--output",
                str(png_output),
                "--density",
                str(density),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip() or "SVG to PNG rendering failed.") from exc

    return png_output


def render_visualization_asset(visualization_payload: dict, output_path: str | Path, width: int = 1080, height: int = 1350):
    render_mode = visualization_payload.get("render_mode")
    template = visualization_payload.get("template")

    if render_mode == "custom_svg" and template == "premium_team_compare_v1":
        return _render_team_compare_svg(visualization_payload, output_path, width=width, height=height)
    if render_mode == "custom_svg" and template == "player_distribution_compare_v1":
        return _render_player_distribution_compare_svg(visualization_payload, output_path, width=width, height=height)
    if render_mode == "custom_svg" and template == "prematch_matchup_v1":
        return _render_prematch_matchup_svg(visualization_payload, output_path, width=width, height=height)
    if render_mode == "custom_svg" and template == "coach_trend_insight_v1":
        return _render_coach_trend_insight_svg(visualization_payload, output_path, width=width, height=height)
    if render_mode == "custom_svg" and template == "process_vs_results_lens_v1":
        return _render_process_vs_results_lens_svg(visualization_payload, output_path, width=width, height=height)
    if render_mode == "custom_svg" and template == "goalkeeper_variance_v1":
        return _render_goalkeeper_variance_svg(visualization_payload, output_path, width=width, height=height)

    return render_echarts_svg(visualization_payload, output_path, width=width, height=height)


def render_visualization_asset_with_png(visualization_payload: dict, output_path: str | Path, width: int = 1080, height: int = 1350, density: int = 144):
    svg_output = render_visualization_asset(visualization_payload, output_path, width=width, height=height)
    png_output = render_svg_to_png(svg_output, density=density)
    return {"svg": svg_output, "png": png_output}
