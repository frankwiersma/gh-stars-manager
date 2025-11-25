#!/usr/bin/env python3
"""
Fetch READMEs from GitHub starred repositories.

This script fetches starred repos from GitHub API, maintains a CSV cache,
and downloads README files incrementally.
"""

import csv
import os
import subprocess
import sys
import time
import re
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple, Set, List, Dict

# Configuration
CSV_FILE = "starred.csv"
OUTPUT_DIR = "readmes"
MAX_WORKERS = 5  # Concurrent downloads (be nice to GitHub API)
RETRY_ATTEMPTS = 2
RETRY_DELAY = 2  # seconds


def sanitize_filename(name: str) -> str:
    """Convert repo name to safe filename."""
    # Replace / with _ and remove any other problematic characters
    safe_name = name.replace("/", "_")
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', safe_name)
    return safe_name


def fetch_readme_via_gh(repo: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Fetch README content using GitHub CLI.

    Args:
        repo: Repository in format "owner/repo"

    Returns:
        Tuple of (repo_name, content or None, error message or None)
    """
    # Try common README filenames
    readme_variants = [
        "README.md",
        "readme.md",
        "README.MD",
        "Readme.md",
        "README.rst",
        "readme.rst",
        "README.txt",
        "readme.txt",
        "README",
    ]

    for attempt in range(RETRY_ATTEMPTS):
        for readme_name in readme_variants:
            try:
                # Use gh api to fetch file contents
                result = subprocess.run(
                    [
                        "gh", "api",
                        f"/repos/{repo}/contents/{readme_name}",
                        "--jq", ".content"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0 and result.stdout.strip():
                    # Content is base64 encoded
                    import base64
                    try:
                        content = base64.b64decode(result.stdout.strip()).decode('utf-8')
                        return (repo, content, None)
                    except Exception as decode_err:
                        # Try with different encodings
                        try:
                            content = base64.b64decode(result.stdout.strip()).decode('latin-1')
                            return (repo, content, None)
                        except:
                            continue

            except subprocess.TimeoutExpired:
                if attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY)
                continue
            except Exception as e:
                if attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY)
                continue

        if attempt < RETRY_ATTEMPTS - 1:
            time.sleep(RETRY_DELAY)

    return (repo, None, "No README found or fetch failed")


def fetch_readme_raw(repo: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Fetch README using raw GitHub URLs as fallback.

    Args:
        repo: Repository in format "owner/repo"

    Returns:
        Tuple of (repo_name, content or None, error message or None)
    """
    import urllib.request
    import urllib.error

    readme_variants = [
        "README.md",
        "readme.md",
        "README.MD",
        "Readme.md",
        "README.rst",
        "readme.rst",
        "README.txt",
        "readme.txt",
        "README",
    ]

    branches = ["main", "master"]

    for branch in branches:
        for readme_name in readme_variants:
            url = f"https://raw.githubusercontent.com/{repo}/{branch}/{readme_name}"
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'gh-stars-readme-fetcher'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    content = response.read().decode('utf-8', errors='replace')
                    if content:
                        return (repo, content, None)
            except urllib.error.HTTPError:
                continue
            except urllib.error.URLError:
                continue
            except Exception:
                continue

    return (repo, None, "No README found via raw URL")


def fetch_readme(repo: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Fetch README using multiple methods.

    Args:
        repo: Repository in format "owner/repo"

    Returns:
        Tuple of (repo_name, content or None, error message or None)
    """
    # Try gh CLI first
    repo_name, content, error = fetch_readme_via_gh(repo)
    if content:
        return (repo_name, content, None)

    # Fallback to raw URL
    repo_name, content, error = fetch_readme_raw(repo)
    return (repo_name, content, error)


def fetch_starred_repos_from_github() -> List[Dict]:
    """Fetch starred repos directly from GitHub API using gh CLI."""
    print("Fetching starred repos from GitHub...")

    try:
        result = subprocess.run(
            ['gh', 'api', '/user/starred', '--paginate', '--jq',
             '.[] | {full_name: .full_name, stars: .stargazers_count, language: .language}'],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            print(f"Error fetching starred repos: {result.stderr}")
            return []

        # Parse JSON lines
        repos = []
        for line in result.stdout.strip().split('\n'):
            if line:
                try:
                    repo = json.loads(line)
                    repos.append(repo)
                except json.JSONDecodeError:
                    continue

        return repos

    except subprocess.TimeoutExpired:
        print("Timeout fetching starred repos")
        return []
    except FileNotFoundError:
        print("Error: GitHub CLI (gh) not found. Please install it from https://cli.github.com/")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        return []


def load_repos_from_csv(csv_path: str) -> Dict[str, Dict]:
    """Load repository names from CSV file as a dict."""
    repos = {}

    if not os.path.exists(csv_path):
        return repos

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and len(row) >= 1:
                repo_name = row[0].strip().strip('"')
                if repo_name and '/' in repo_name:
                    repos[repo_name] = {
                        'full_name': repo_name,
                        'stars': int(row[1]) if len(row) > 1 and row[1].strip().isdigit() else 0,
                        'language': row[2].strip().strip('"') if len(row) > 2 else ''
                    }

    return repos


def save_repos_to_csv(repos: List[Dict], csv_path: str):
    """Save repositories to CSV file."""
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for repo in repos:
            writer.writerow([
                f'"{repo["full_name"]}"',
                repo.get('stars', 0),
                f'"{repo.get("language", "")}"'
            ])


def get_existing_readmes() -> Set[str]:
    """Get set of repos that already have README files downloaded."""
    existing = set()

    if not os.path.exists(OUTPUT_DIR):
        return existing

    for filename in os.listdir(OUTPUT_DIR):
        if filename.startswith('_') or not filename.endswith('.md'):
            continue
        # Convert filename back to repo name
        repo_name = filename[:-3].replace('_', '/', 1)
        existing.add(repo_name)

    return existing


def save_readme(repo: str, content: str, output_dir: str) -> str:
    """Save README content to file."""
    filename = sanitize_filename(repo) + ".md"
    filepath = os.path.join(output_dir, filename)

    # Add header with repo info
    header = f"# README: {repo}\n\n"
    header += f"**Source:** https://github.com/{repo}\n\n"
    header += "---\n\n"

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(header + content)

    return filepath


def main():
    """Main execution function with incremental updates."""
    print("=" * 60)
    print("GitHub Starred Repos README Fetcher (Incremental)")
    print("=" * 60)

    # Check if gh CLI is available
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: GitHub CLI (gh) not found.")
        print("Please install it from https://cli.github.com/")
        sys.exit(1)

    # Fetch current starred repos from GitHub
    github_repos = fetch_starred_repos_from_github()
    if not github_repos:
        print("Error: Could not fetch starred repos from GitHub")
        sys.exit(1)

    print(f"Found {len(github_repos)} starred repos on GitHub")

    # Load existing CSV
    existing_repos = load_repos_from_csv(CSV_FILE)
    print(f"Found {len(existing_repos)} repos in local cache ({CSV_FILE})")

    # Find new repos
    github_repo_names = {r['full_name'] for r in github_repos}
    existing_repo_names = set(existing_repos.keys())
    new_repo_names = github_repo_names - existing_repo_names

    if new_repo_names:
        print(f"\n✨ Found {len(new_repo_names)} new starred repos!")
    else:
        print("\n✓ No new starred repos")

    # Update CSV with all repos (updates star counts too)
    print(f"\nUpdating {CSV_FILE}...")
    save_repos_to_csv(github_repos, CSV_FILE)

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Check which repos need README downloads
    existing_readmes = get_existing_readmes()
    repos_needing_readmes = [r for r in github_repos if r['full_name'] not in existing_readmes]

    if not repos_needing_readmes:
        print("\n✓ All READMEs already downloaded!")
        print("\nSUMMARY")
        print("=" * 60)
        print(f"Total starred repos: {len(github_repos)}")
        print(f"READMEs on disk:     {len(existing_readmes)}")
        print(f"New repos to fetch:  0")
        return 0

    print(f"\nNeed to fetch READMEs for {len(repos_needing_readmes)} repos")
    print(f"({len(new_repo_names)} newly starred + {len(repos_needing_readmes) - len(new_repo_names)} previously missing)")

    # Fetch READMEs
    print(f"\nFetching READMEs (using {MAX_WORKERS} workers)...")
    print("-" * 60)

    success_count = 0
    failed_count = 0
    failed_repos = []

    repos_to_fetch = [r['full_name'] for r in repos_needing_readmes]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_repo = {executor.submit(fetch_readme, repo): repo for repo in repos_to_fetch}

        for i, future in enumerate(as_completed(future_to_repo), 1):
            repo = future_to_repo[future]
            try:
                repo_name, content, error = future.result()

                is_new = repo_name in new_repo_names
                marker = "NEW" if is_new else "MISSING"

                if content:
                    filepath = save_readme(repo_name, content, OUTPUT_DIR)
                    success_count += 1
                    status = f"OK ({marker})"
                else:
                    failed_count += 1
                    failed_repos.append((repo_name, error))
                    status = f"SKIP ({error})"

                # Progress indicator
                progress = f"[{i}/{len(repos_to_fetch)}]"
                print(f"{progress:12} {status:30} {repo_name}")

            except Exception as e:
                failed_count += 1
                failed_repos.append((repo, str(e)))
                progress = f"[{i}/{len(repos_to_fetch)}]"
                print(f"{progress:12} {'ERROR':30} {repo}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total starred repos:  {len(github_repos)}")
    print(f"New repos found:      {len(new_repo_names)}")
    print(f"READMEs fetched:      {success_count}")
    print(f"Failed/No README:     {failed_count}")
    print(f"Total READMEs on disk: {len(existing_readmes) + success_count}")
    print(f"\nREADME files saved to: {os.path.abspath(OUTPUT_DIR)}/")

    # Save failed repos list
    if failed_repos:
        failed_log = os.path.join(OUTPUT_DIR, "_failed_repos.txt")
        with open(failed_log, 'w', encoding='utf-8') as f:
            f.write("# Repositories without READMEs or fetch failures\n\n")
            for repo, reason in failed_repos:
                f.write(f"{repo}: {reason}\n")
        print(f"Failed repos logged to: {failed_log}")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
