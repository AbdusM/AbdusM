from __future__ import annotations

import json
import os
import textwrap
import xml.sax.saxutils as xml_utils
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "AbdusM")
TOKEN = os.environ.get("GITHUB_TOKEN")
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "profile"
FEATURED_REPOS = [
    "cloudflare-bot-blocker",
    "park-vintage-data-lab",
    "lux-story",
    "uForage",
]


def require_token() -> str:
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN is required")
    return TOKEN


def graphql(query: str, variables: dict) -> dict:
    token = require_token()
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "abdusm-profile-assets",
        },
        method="POST",
    )
    try:
        with urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SystemExit(f"GraphQL request failed: {exc.code}") from exc

    if payload.get("errors"):
        raise SystemExit(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


def esc(text: str) -> str:
    return xml_utils.escape(text or "")


def wrap_text(text: str, width: int, max_lines: int) -> list[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    lines = textwrap.wrap(cleaned, width=width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "..."
    return lines


def repo_asset_name(repo_name: str) -> str:
    return f"repo-{repo_name.lower().replace('_', '-').replace('.', '-')}.svg"


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(day: date, count: int) -> date:
    year = day.year + (day.month - 1 + count) // 12
    month = (day.month - 1 + count) % 12 + 1
    return date(year, month, 1)


def june_cycle_start(reference_date: date) -> date:
    if reference_date.month > 6:
        return date(reference_date.year, 6, 1)
    return date(reference_date.year - 1, 6, 1)


def period_label(start: date, end: date) -> str:
    return f"{start.strftime('%b')} {start.day}, {start.year} to {end.strftime('%b')} {end.day}, {end.year}"


def compute_streaks(contribution_days: list[dict], reference_date: date) -> tuple[int, int]:
    days = sorted(
        [(datetime.fromisoformat(item["date"]).date(), item["contributionCount"]) for item in contribution_days],
        key=lambda item: item[0],
    )

    longest = 0
    current_run = 0
    for _, count in days:
        if count > 0:
            current_run += 1
            longest = max(longest, current_run)
        else:
            current_run = 0

    current = 0
    reversed_days = list(reversed(days))
    if reversed_days and reversed_days[0][0] == reference_date and reversed_days[0][1] == 0:
        reversed_days = reversed_days[1:]
    for _, count in reversed_days:
        if count > 0:
            current += 1
        else:
            break

    return current, longest


def card_shell(width: int, height: int, content: str) -> str:
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Generated GitHub profile card">
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="18" fill="#ffffff" fill-opacity="0.02" stroke="#d0d7de"/>
  <style>
    .title {{ font: 700 24px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #111827; }}
    .subtitle {{ font: 500 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #6b7280; }}
    .label {{ font: 600 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #6b7280; text-transform: uppercase; letter-spacing: 0.12em; }}
    .value {{ font: 700 28px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #111827; }}
    .small {{ font: 600 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #374151; }}
    .body {{ font: 500 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #374151; }}
  </style>
  {content}
</svg>
"""


def generate_stats_svg(user: dict, totals: dict, start: date, end: date) -> str:
    metrics = [
        ("Public repos", str(totals["public_repo_count"])),
        ("Total stars", str(totals["total_stars"])),
        ("Cycle contributions", str(totals["total_contributions"])),
        ("Cycle commits", str(totals["commits"])),
        ("Cycle PRs", str(totals["pull_requests"])),
        ("Cycle reviews", str(totals["reviews"])),
    ]

    blocks = []
    start_x = 36
    start_y = 88
    width = 230
    height = 64
    for index, (label, value) in enumerate(metrics):
        column = index % 3
        row = index // 3
        x = start_x + column * 248
        y = start_y + row * 84
        blocks.append(
            f"""
  <g transform="translate({x} {y})">
    <rect width="{width}" height="{height}" rx="14" fill="#f8fafc" stroke="#e5e7eb"/>
    <text x="16" y="24" class="label">{esc(label)}</text>
    <text x="16" y="50" class="value">{esc(value)}</text>
  </g>"""
        )

    subtitle = f"June cycle: {period_label(start, end)}"
    content = f"""
  <text x="36" y="42" class="title">GitHub Visual Snapshot</text>
  <text x="36" y="64" class="subtitle">{esc(subtitle)}</text>
  {''.join(blocks)}
"""
    return card_shell(800, 240, content)


def generate_activity_svg(
    monthly_counts: list[tuple[str, int]],
    current_streak: int,
    longest_streak: int,
    start: date,
    end: date,
) -> str:
    max_count = max((count for _, count in monthly_counts), default=1)
    chart_left = 40
    chart_bottom = 210
    chart_right = 760
    chart_width = chart_right - chart_left
    slot_count = max(len(monthly_counts), 1)
    gap = 14 if slot_count > 12 else 19
    bar_width = min(42, (chart_width - gap * (slot_count - 1)) / slot_count)
    bars = []
    labels = []
    for index, (label, count) in enumerate(monthly_counts):
        height = 0 if max_count == 0 else max(10, round((count / max_count) * 108)) if count else 4
        x = chart_left + index * (bar_width + gap)
        y = chart_bottom - height
        bars.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{height}" rx="10" fill="#2563eb"/>')
        labels.append(f'<text x="{x + bar_width / 2}" y="230" text-anchor="middle" class="subtitle">{esc(label)}</text>')
        labels.append(f'<text x="{x + bar_width / 2}" y="{y - 8}" text-anchor="middle" class="small">{count}</text>')

    content = f"""
  <text x="36" y="42" class="title">June Cycle Activity</text>
  <text x="36" y="64" class="subtitle">{esc(period_label(start, end))}</text>
  <g transform="translate(572 24)">
    <rect width="188" height="88" rx="16" fill="#f8fafc" stroke="#e5e7eb"/>
    <text x="18" y="28" class="label">Current streak</text>
    <text x="18" y="56" class="value">{current_streak}</text>
    <text x="102" y="28" class="label">Longest streak</text>
    <text x="102" y="56" class="value">{longest_streak}</text>
  </g>
  <line x1="{chart_left}" y1="{chart_bottom}" x2="{chart_right}" y2="{chart_bottom}" stroke="#d1d5db"/>
  {''.join(bars)}
  {''.join(labels)}
"""
    return card_shell(800, 260, content)


def generate_repo_card(repo: dict) -> str:
    description_lines = wrap_text(repo.get("description") or "No description provided.", width=36, max_lines=3)
    description_svg = []
    for index, line in enumerate(description_lines):
        description_svg.append(f'<text x="28" y="{70 + index * 20}" class="body">{esc(line)}</text>')

    language_name = repo.get("primaryLanguage", {}).get("name") or "Unknown"
    language_color = repo.get("primaryLanguage", {}).get("color") or "#9ca3af"
    updated = datetime.fromisoformat(repo["updatedAt"].replace("Z", "+00:00")).strftime("%b %Y")

    content = f"""
  <text x="28" y="36" class="title">{esc(repo['name'])}</text>
  {''.join(description_svg)}
  <circle cx="34" cy="128" r="6" fill="{language_color}"/>
  <text x="48" y="133" class="small">{esc(language_name)}</text>
  <text x="176" y="133" class="small">Stars {repo['stargazerCount']}</text>
  <text x="246" y="133" class="small">Forks {repo['forkCount']}</text>
  <text x="318" y="133" class="small">{esc(updated)}</text>
"""
    return card_shell(390, 150, content)


def build_monthly_counts(contribution_days: list[dict], start: date, end: date) -> list[tuple[str, int]]:
    counts_by_month: dict[date, int] = defaultdict(int)
    for item in contribution_days:
        day = datetime.fromisoformat(item["date"]).date()
        if day < start or day > end:
            continue
        counts_by_month[month_start(day)] += item["contributionCount"]

    months = []
    month_count = (end.year - start.year) * 12 + end.month - start.month + 1
    for index in range(month_count):
        bucket = add_months(start, index)
        months.append((bucket.strftime("%b '%y"), counts_by_month.get(bucket, 0)))
    return months


def validate_generated_assets(expected_files: list[Path]) -> None:
    missing = [path for path in expected_files if not path.exists()]
    if missing:
        names = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        raise SystemExit(f"Missing generated assets: {names}")

    for path in expected_files:
        try:
            ElementTree.parse(path)
        except ElementTree.ParseError as exc:
            raise SystemExit(f"Invalid SVG XML in {path.relative_to(ROOT)}: {exc}") from exc

        content = path.read_text(encoding="utf-8")
        try:
            content.encode("ascii")
        except UnicodeEncodeError as exc:
            raise SystemExit(f"Non-ASCII SVG content in {path.relative_to(ROOT)}: {exc}") from exc


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    now = datetime.now(timezone.utc)
    today = now.date()
    cycle_start = june_cycle_start(today)
    cycle_start_datetime = datetime(cycle_start.year, cycle_start.month, cycle_start.day, tzinfo=timezone.utc)
    query = """
    query ProfileData($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        login
        followers {
          totalCount
        }
        repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
          totalCount
          nodes {
            name
            description
            url
            stargazerCount
            forkCount
            updatedAt
            primaryLanguage {
              name
              color
            }
          }
        }
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalPullRequestReviewContributions
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    data = graphql(
        query,
        {
            "login": OWNER,
            "from": cycle_start_datetime.isoformat(),
            "to": now.isoformat(),
        },
    )

    user = data["user"]
    repositories = {repo["name"]: repo for repo in user["repositories"]["nodes"]}
    missing_featured = [repo_name for repo_name in FEATURED_REPOS if repo_name not in repositories]
    if missing_featured:
        raise SystemExit(f"Missing featured public repositories: {', '.join(missing_featured)}")

    contribution_days = [
        day
        for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]

    totals = {
        "public_repo_count": user["repositories"]["totalCount"],
        "total_stars": sum(repo["stargazerCount"] for repo in repositories.values()),
        "total_contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "commits": user["contributionsCollection"]["totalCommitContributions"],
        "pull_requests": user["contributionsCollection"]["totalPullRequestContributions"],
        "issues": user["contributionsCollection"]["totalIssueContributions"],
        "reviews": user["contributionsCollection"]["totalPullRequestReviewContributions"],
        "followers": user["followers"]["totalCount"],
    }

    current_streak, longest_streak = compute_streaks(contribution_days, today)
    monthly_counts = build_monthly_counts(contribution_days, cycle_start, today)

    (OUT_DIR / "stats.svg").write_text(generate_stats_svg(user, totals, cycle_start, today), encoding="utf-8")
    (OUT_DIR / "activity.svg").write_text(
        generate_activity_svg(monthly_counts, current_streak, longest_streak, cycle_start, today),
        encoding="utf-8",
    )

    for repo_name in FEATURED_REPOS:
        repo = repositories[repo_name]
        file_name = repo_asset_name(repo_name)
        (OUT_DIR / file_name).write_text(generate_repo_card(repo), encoding="utf-8")

    expected_files = [
        OUT_DIR / "stats.svg",
        OUT_DIR / "activity.svg",
        *(OUT_DIR / repo_asset_name(repo_name) for repo_name in FEATURED_REPOS),
    ]
    validate_generated_assets(expected_files)


if __name__ == "__main__":
    main()
