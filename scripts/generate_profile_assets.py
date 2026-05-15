from __future__ import annotations

import json
import math
import os
import textwrap
import xml.sax.saxutils as xml_utils
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


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
        lines[-1] = lines[-1].rstrip(".") + "…"
    return lines


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(day: date, count: int) -> date:
    year = day.year + (day.month - 1 + count) // 12
    month = (day.month - 1 + count) % 12 + 1
    return date(year, month, 1)


def compute_streaks(contribution_days: list[dict]) -> tuple[int, int]:
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
    today = date.today()
    reversed_days = list(reversed(days))
    if reversed_days and reversed_days[0][0] == today and reversed_days[0][1] == 0:
        reversed_days = reversed_days[1:]
    for _, count in reversed_days:
        if count > 0:
            current += 1
        else:
            break

    return current, longest


def card_shell(width: int, height: int, content: str) -> str:
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Generated GitHub profile card">
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="18" fill="rgba(255,255,255,0.02)" stroke="#d0d7de"/>
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


def generate_stats_svg(user: dict, totals: dict) -> str:
    metrics = [
        ("Public repos", str(totals["public_repo_count"])),
        ("Total stars", str(totals["total_stars"])),
        ("12m contributions", str(totals["total_contributions"])),
        ("12m commits", str(totals["commits"])),
        ("12m PRs", str(totals["pull_requests"])),
        ("12m reviews", str(totals["reviews"])),
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

    subtitle = f"Auto-generated from public GitHub data for {user['login']}"
    content = f"""
  <text x="36" y="42" class="title">Public GitHub Snapshot</text>
  <text x="36" y="64" class="subtitle">{esc(subtitle)}</text>
  {''.join(blocks)}
"""
    return card_shell(800, 240, content)


def generate_activity_svg(monthly_counts: list[tuple[str, int]], current_streak: int, longest_streak: int) -> str:
    max_count = max((count for _, count in monthly_counts), default=1)
    chart_left = 40
    chart_bottom = 210
    bar_width = 42
    gap = 19
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
  <text x="36" y="42" class="title">12-Month Activity</text>
  <text x="36" y="64" class="subtitle">Public contributions grouped by month</text>
  <g transform="translate(572 24)">
    <rect width="188" height="88" rx="16" fill="#f8fafc" stroke="#e5e7eb"/>
    <text x="18" y="28" class="label">Current streak</text>
    <text x="18" y="56" class="value">{current_streak}</text>
    <text x="102" y="28" class="label">Longest streak</text>
    <text x="102" y="56" class="value">{longest_streak}</text>
  </g>
  <line x1="{chart_left}" y1="{chart_bottom}" x2="760" y2="{chart_bottom}" stroke="#d1d5db"/>
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
  <text x="150" y="133" class="small">★ {repo['stargazerCount']}</text>
  <text x="220" y="133" class="small">⑂ {repo['forkCount']}</text>
  <text x="284" y="133" class="small">Updated {esc(updated)}</text>
"""
    return card_shell(390, 150, content)


def build_monthly_counts(contribution_days: list[dict]) -> list[tuple[str, int]]:
    counts_by_month: dict[date, int] = defaultdict(int)
    for item in contribution_days:
        day = datetime.fromisoformat(item["date"]).date()
        counts_by_month[month_start(day)] += item["contributionCount"]

    current = month_start(date.today())
    start = add_months(current, -11)
    months = []
    for index in range(12):
        bucket = add_months(start, index)
        months.append((bucket.strftime("%b"), counts_by_month.get(bucket, 0)))
    return months


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    today = datetime.now(timezone.utc)
    last_year = today - timedelta(days=365)
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
            "from": last_year.isoformat(),
            "to": today.isoformat(),
        },
    )

    user = data["user"]
    repositories = {repo["name"]: repo for repo in user["repositories"]["nodes"]}
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

    current_streak, longest_streak = compute_streaks(contribution_days)
    monthly_counts = build_monthly_counts(contribution_days)

    (OUT_DIR / "stats.svg").write_text(generate_stats_svg(user, totals), encoding="utf-8")
    (OUT_DIR / "activity.svg").write_text(
        generate_activity_svg(monthly_counts, current_streak, longest_streak),
        encoding="utf-8",
    )

    for repo_name in FEATURED_REPOS:
        repo = repositories.get(repo_name)
        if not repo:
            continue
        file_name = f"repo-{repo_name.lower().replace('_', '-').replace('.', '-')}.svg"
        (OUT_DIR / file_name).write_text(generate_repo_card(repo), encoding="utf-8")


if __name__ == "__main__":
    main()
