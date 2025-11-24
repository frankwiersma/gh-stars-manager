#!/usr/bin/env python3
"""
Fetch READMEs from GitHub starred repositories.

This script reads a CSV file containing starred GitHub repositories and downloads
their README files into a local folder for later analysis.
"""

import csv
import os
import subprocess
import sys
import time
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple

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


def load_repos_from_csv(csv_path: str) -> list:
    """Load repository names from CSV file."""
    repos = []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and len(row) >= 1:
                repo_name = row[0].strip().strip('"')
                if repo_name and '/' in repo_name:
                    repos.append(repo_name)

    return repos


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
    """Main execution function."""
    print("=" * 60)
    print("GitHub Starred Repos README Fetcher")
    print("=" * 60)

    # Check if gh CLI is available
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Warning: GitHub CLI (gh) not found. Will use raw URL method only.")

    # Load repos from CSV
    if not os.path.exists(CSV_FILE):
        print(f"Error: CSV file '{CSV_FILE}' not found.")
        print("Please run: gh api '/user/starred' --paginate --jq '.[] | [.full_name, .stargazers_count, .language] | @csv' > starred.csv")
        sys.exit(1)

    repos = load_repos_from_csv(CSV_FILE)
    total_repos = len(repos)
    print(f"\nFound {total_repos} starred repositories in {CSV_FILE}")

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}/")

    # Fetch READMEs
    print(f"\nFetching READMEs (using {MAX_WORKERS} workers)...")
    print("-" * 60)

    success_count = 0
    failed_count = 0
    failed_repos = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_repo = {executor.submit(fetch_readme, repo): repo for repo in repos}

        for i, future in enumerate(as_completed(future_to_repo), 1):
            repo = future_to_repo[future]
            try:
                repo_name, content, error = future.result()

                if content:
                    filepath = save_readme(repo_name, content, OUTPUT_DIR)
                    success_count += 1
                    status = "OK"
                else:
                    failed_count += 1
                    failed_repos.append((repo_name, error))
                    status = f"SKIP ({error})"

                # Progress indicator
                progress = f"[{i}/{total_repos}]"
                print(f"{progress:12} {status:30} {repo_name}")

            except Exception as e:
                failed_count += 1
                failed_repos.append((repo, str(e)))
                progress = f"[{i}/{total_repos}]"
                print(f"{progress:12} {'ERROR':30} {repo}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total repositories:  {total_repos}")
    print(f"Successfully fetched: {success_count}")
    print(f"Failed/No README:     {failed_count}")
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
