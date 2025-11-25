#!/usr/bin/env python3
"""
Main Pipeline Runner - Runs the complete GitHub Stars Manager pipeline.

This script orchestrates the entire workflow:
1. Fetch starred repos from GitHub (incremental)
2. Download new READMEs
3. Analyze with LLM (incremental, uses cache)
4. Generate dashboard

Usage: python run.py
"""

import subprocess
import sys
import os
from datetime import datetime


def run_command(command: list, description: str) -> bool:
    """Run a command and return success status."""
    print("\n" + "=" * 70)
    print(f"STEP: {description}")
    print("=" * 70)

    try:
        result = subprocess.run(
            command,
            cwd=os.getcwd(),
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error in step: {description}")
        print(f"Command failed with exit code {e.returncode}")
        return False
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False


def check_prerequisites():
    """Check if all prerequisites are met."""
    print("Checking prerequisites...")

    # Check Python
    print(f"  ✓ Python {sys.version.split()[0]}")

    # Check gh CLI
    try:
        result = subprocess.run(
            ['gh', '--version'],
            capture_output=True,
            text=True
        )
        version = result.stdout.strip().split('\n')[0]
        print(f"  ✓ {version}")
    except FileNotFoundError:
        print("  ❌ GitHub CLI (gh) not found")
        print("     Install from: https://cli.github.com/")
        return False

    # Check if gh is authenticated
    try:
        result = subprocess.run(
            ['gh', 'auth', 'status'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("  ❌ GitHub CLI not authenticated")
            print("     Run: gh auth login")
            return False
        print("  ✓ GitHub CLI authenticated")
    except Exception:
        pass

    # Check Ollama
    try:
        result = subprocess.run(
            ['ollama', 'list'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("  ✓ Ollama is available")
        else:
            print("  ⚠️  Ollama found but may not be running")
            print("     Make sure to start it: ollama serve")
    except FileNotFoundError:
        print("  ⚠️  Ollama not found (optional for analysis)")
        print("     Install from: https://ollama.ai/")
    except subprocess.TimeoutExpired:
        print("  ⚠️  Ollama not responding")
    except Exception:
        pass

    print()
    return True


def main():
    """Run the complete pipeline."""
    start_time = datetime.now()

    print("=" * 70)
    print("GitHub Stars Manager - Full Pipeline")
    print("=" * 70)
    print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Check prerequisites
    if not check_prerequisites():
        print("\n❌ Prerequisites not met. Please fix the issues above.")
        return 1

    # Step 1: Fetch starred repos and READMEs (incremental)
    if not run_command(
        [sys.executable, 'fetch_readmes.py'],
        "Fetch starred repos and download READMEs (incremental)"
    ):
        print("\n⚠️  README fetch failed, but continuing...")
        print("You can run 'python fetch_readmes.py' manually later.")

    # Step 2: Analyze with LLM (incremental, uses cache)
    print("\n" + "=" * 70)
    print("STEP: Analyze READMEs with LLM (incremental, cached)")
    print("=" * 70)
    print("\n⚠️  Note: This step can take a long time on first run.")
    print("Subsequent runs are much faster due to caching.")
    print("You can press Ctrl+C to skip if you want to just update the dashboard.\n")

    user_input = input("Run LLM analysis? [Y/n]: ").strip().lower()

    if user_input in ['', 'y', 'yes']:
        if not run_command(
            [sys.executable, 'analyze_readmes.py'],
            "Analyzing with LLM"
        ):
            print("\n⚠️  Analysis failed or was interrupted.")
            print("You can run 'python analyze_readmes.py' manually later.")
            print("Skipping dashboard generation...")
            return 1
    else:
        print("⏭️  Skipping LLM analysis")
        if not os.path.exists('analyzed_repos.json'):
            print("\n❌ No analysis data found (analyzed_repos.json missing)")
            print("You need to run analysis at least once before generating the dashboard.")
            return 1

    # Step 3: Generate dashboard
    if not run_command(
        [sys.executable, 'generate_dashboard.py'],
        "Generate interactive HTML dashboard"
    ):
        print("\n❌ Dashboard generation failed")
        return 1

    # Success!
    end_time = datetime.now()
    duration = end_time - start_time

    print("\n" + "=" * 70)
    print("✅ PIPELINE COMPLETE!")
    print("=" * 70)
    print(f"Duration: {duration}")
    print(f"\nYour dashboard is ready:")
    print(f"  file://{os.path.abspath('dashboard.html')}")
    print(f"\nOpen it in your browser to explore your starred repos!")

    # Show summary
    if os.path.exists('analyzed_repos.json'):
        import json
        try:
            with open('analyzed_repos.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"\nSummary:")
                print(f"  Total repositories: {data.get('total_repos', 'unknown')}")
                print(f"  Analysis model: {data.get('model_used', 'unknown')}")
        except:
            pass

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        sys.exit(130)
