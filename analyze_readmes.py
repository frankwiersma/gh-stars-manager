#!/usr/bin/env python3
"""
README Analyzer - LLM-powered analysis of GitHub starred repositories.

Uses Ollama with qwen3:8b to extract rich metadata, hierarchical tags,
and insights from README files for intelligent categorization and discovery.
"""

import json
import os
import re
import sys
import time
import csv
import hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
import urllib.request
import urllib.error

# Configuration
READMES_DIR = "readmes"
OUTPUT_FILE = "analyzed_repos.json"
CSV_FILE = "starred.csv"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:8b"  # Changed from qwen2.5:14b - use what you have installed
MAX_README_LENGTH = 12000  # Truncate very long READMEs
CACHE_FILE = "analysis_cache.json"


@dataclass
class RepoAnalysis:
    """Structured analysis of a repository."""
    # Basic info
    repo: str
    name: str
    owner: str
    github_url: str

    # From CSV
    stars: int = 0
    language: str = ""

    # LLM-extracted
    summary: str = ""
    purpose: str = ""  # What problem does it solve?
    target_audience: str = ""  # Who is this for?

    # HIERARCHICAL TAXONOMY (depth trees)
    # Format: "Level1 > Level2 > Level3"
    # Examples: "AI > GenAI > LLM", "Security > Offensive > Web"
    taxonomy: List[str] = field(default_factory=list)  # Multiple paths possible

    # Smart tags (flat tags for filtering)
    tags: List[str] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    use_cases: List[str] = field(default_factory=list)

    # Quality signals
    maturity: str = ""  # alpha, beta, stable, mature, archived
    complexity: str = ""  # beginner, intermediate, advanced, expert
    documentation_quality: str = ""  # poor, basic, good, excellent
    activity_status: str = ""  # active, maintained, stale, abandoned

    # Discovery helpers
    similar_to: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    # Insights
    standout_features: List[str] = field(default_factory=list)
    potential_value: str = ""  # Why might this be useful?

    # Metadata
    analyzed_at: str = ""
    analysis_version: str = "2.0"
    readme_hash: str = ""
    has_readme: bool = True
    error: str = ""


def load_csv_metadata(csv_path: str) -> Dict[str, Dict[str, Any]]:
    """Load stars and language from CSV."""
    metadata = {}
    if not os.path.exists(csv_path):
        return metadata

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and len(row) >= 1:
                repo = row[0].strip().strip('"')
                if repo and '/' in repo:
                    metadata[repo] = {
                        'stars': int(row[1]) if len(row) > 1 and row[1].strip() else 0,
                        'language': row[2].strip().strip('"') if len(row) > 2 else ""
                    }
    return metadata


def load_cache() -> Dict[str, Any]:
    """Load analysis cache."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def save_cache(cache: Dict[str, Any]):
    """Save analysis cache."""
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def compute_hash(content: str) -> str:
    """Compute hash of content for cache invalidation."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:12]


def call_ollama(prompt: str, max_retries: int = 3) -> Optional[str]:
    """Call Ollama API with the given prompt."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 2500,
        }
    }

    data = json.dumps(payload).encode('utf-8')

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                OLLAMA_URL,
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=180) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get('response', '')
        except urllib.error.HTTPError as e:
            # HTTP error from Ollama (404, 500, etc)
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            else:
                print(f"\n    Ollama HTTP Error {e.code}: {e.reason}")
                return None
        except urllib.error.URLError as e:
            # Connection error
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            else:
                print(f"\n    Ollama connection error: {e.reason}")
                return None
        except KeyboardInterrupt:
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            else:
                print(f"\n    Ollama error: {str(e)[:50]}")
                return None

    return None


def extract_json_from_response(response: str) -> Optional[Dict]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to find JSON in code blocks
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', response)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    json_match = re.search(r'\{[\s\S]*\}', response)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try the whole response
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    return None


TAXONOMY_EXAMPLES = """
TAXONOMY EXAMPLES (use ">" for hierarchy, be specific):
- "AI > GenAI > LLM > Chatbot"
- "AI > GenAI > LLM > Code Assistant"
- "AI > GenAI > Voice > TTS"
- "AI > GenAI > Voice > STT"
- "AI > GenAI > Image > Generation"
- "AI > GenAI > Image > Editing"
- "AI > Computer Vision > Object Detection"
- "AI > Computer Vision > OCR"
- "AI > ML > Training"
- "AI > ML > Inference"
- "Security > Offensive > Web > Scanner"
- "Security > Offensive > Web > Exploitation"
- "Security > Offensive > Active Directory"
- "Security > Offensive > Cloud > Azure"
- "Security > Offensive > Cloud > AWS"
- "Security > Offensive > Phishing"
- "Security > Offensive > Red Team"
- "Security > Defensive > SIEM"
- "Security > Defensive > Hardening"
- "Security > Defensive > Forensics"
- "DevOps > CI/CD > Pipelines"
- "DevOps > Containers > Docker"
- "DevOps > Containers > Kubernetes"
- "DevOps > IaC > Terraform"
- "DevOps > IaC > Bicep"
- "DevOps > Monitoring > Metrics"
- "DevOps > Monitoring > Logging"
- "Development > Web > Frontend > React"
- "Development > Web > Backend > API"
- "Development > CLI > Productivity"
- "Development > Libraries > Python"
- "Development > Testing > Unit"
- "Development > Testing > E2E"
- "Data > Processing > ETL"
- "Data > Visualization"
- "Data > Databases > SQL"
- "Data > Scraping"
- "Automation > Workflow > n8n"
- "Automation > Bots > Discord"
- "Automation > Bots > Telegram"
- "Self-Hosted > Media"
- "Self-Hosted > Productivity"
- "Self-Hosted > Finance"
- "Documentation > Knowledge Base"
- "Documentation > Note Taking"
- "Learning > Tutorials"
- "Learning > Courses"
- "Learning > Cheatsheets"
"""


def analyze_readme(repo: str, readme_content: str, csv_meta: Dict) -> RepoAnalysis:
    """Analyze a README using the LLM."""
    owner, name = repo.split('/', 1)

    analysis = RepoAnalysis(
        repo=repo,
        name=name,
        owner=owner,
        github_url=f"https://github.com/{repo}",
        stars=csv_meta.get('stars', 0),
        language=csv_meta.get('language', ''),
        analyzed_at=datetime.now().isoformat(),
        readme_hash=compute_hash(readme_content)
    )

    # Truncate very long READMEs
    if len(readme_content) > MAX_README_LENGTH:
        readme_content = readme_content[:MAX_README_LENGTH] + "\n\n[... truncated ...]"

    prompt = f"""Analyze this GitHub repository and provide structured metadata for a starred repos manager.

Repository: {repo}
Primary Language: {csv_meta.get('language', 'Unknown')}
Stars: {csv_meta.get('stars', 0)}

README Content:
---
{readme_content}
---

{TAXONOMY_EXAMPLES}

Respond with this JSON structure:
{{
    "summary": "2-3 sentence description of what this project does",
    "purpose": "What specific problem does it solve?",
    "target_audience": "Who is this for? (e.g., 'Python developers', 'Security researchers', 'DevOps engineers')",

    "taxonomy": [
        "Primary > Category > Subcategory > Specific",
        "Secondary > Path > If > Applicable"
    ],

    "tags": ["flat", "searchable", "tags", "15-20 tags"],
    "tech_stack": ["python", "docker", "react", "etc"],
    "use_cases": ["specific use case 1", "specific use case 2"],

    "maturity": "alpha|beta|stable|mature",
    "complexity": "beginner|intermediate|advanced|expert",
    "documentation_quality": "poor|basic|good|excellent",
    "activity_status": "active|maintained|stale",

    "similar_to": ["well-known-project-1", "well-known-project-2"],
    "keywords": ["search", "discovery", "keywords"],

    "standout_features": ["unique feature 1", "notable capability 2"],
    "potential_value": "Why would someone star this? What value does it provide?"
}}

IMPORTANT:
1. Taxonomy MUST use ">" separator for hierarchy depth (min 2 levels, max 4)
2. A repo can have multiple taxonomy paths (e.g., both AI and Security)
3. Tags should be flat, lowercase, and searchable
4. Be specific in taxonomy - don't just say "Tools", say what KIND of tools

Respond with ONLY valid JSON."""

    try:
        response = call_ollama(prompt)
        if response:
            parsed = extract_json_from_response(response)
            if parsed:
                analysis.summary = parsed.get('summary', '')
                analysis.purpose = parsed.get('purpose', '')
                analysis.target_audience = parsed.get('target_audience', '')
                analysis.taxonomy = parsed.get('taxonomy', [])
                analysis.tags = [t.lower() for t in parsed.get('tags', [])]
                analysis.tech_stack = parsed.get('tech_stack', [])
                analysis.use_cases = parsed.get('use_cases', [])
                analysis.maturity = parsed.get('maturity', '')
                analysis.complexity = parsed.get('complexity', '')
                analysis.documentation_quality = parsed.get('documentation_quality', '')
                analysis.activity_status = parsed.get('activity_status', '')
                analysis.similar_to = parsed.get('similar_to', [])
                analysis.keywords = parsed.get('keywords', [])
                analysis.standout_features = parsed.get('standout_features', [])
                analysis.potential_value = parsed.get('potential_value', '')
            else:
                analysis.error = "Failed to parse LLM response"
    except Exception as e:
        analysis.error = str(e)

    return analysis


def analyze_without_readme(repo: str, csv_meta: Dict) -> RepoAnalysis:
    """Create minimal analysis for repos without READMEs."""
    owner, name = repo.split('/', 1)

    lang = csv_meta.get('language', '')
    tags = [lang.lower()] if lang else []

    return RepoAnalysis(
        repo=repo,
        name=name,
        owner=owner,
        github_url=f"https://github.com/{repo}",
        stars=csv_meta.get('stars', 0),
        language=lang,
        analyzed_at=datetime.now().isoformat(),
        has_readme=False,
        summary=f"Repository by {owner} - no README available",
        taxonomy=["Uncategorized > No README"],
        tags=tags,
        tech_stack=[lang] if lang else [],
    )


def get_readme_files() -> Dict[str, str]:
    """Get all README files and their content."""
    readmes = {}
    if not os.path.exists(READMES_DIR):
        return readmes

    for filename in os.listdir(READMES_DIR):
        if filename.startswith('_'):
            continue
        if filename.endswith('.md'):
            filepath = os.path.join(READMES_DIR, filename)
            # Convert filename back to repo name
            repo_name = filename[:-3].replace('_', '/', 1)

            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
                # Remove the header we added
                if content.startswith('# README:'):
                    lines = content.split('\n')
                    # Find the --- separator and skip past it
                    for i, line in enumerate(lines):
                        if line.strip() == '---':
                            content = '\n'.join(lines[i+1:])
                            break
                readmes[repo_name] = content

    return readmes


def build_taxonomy_tree(repos: List[Dict]) -> Dict:
    """Build a tree structure from all taxonomy paths."""
    tree = {}

    for repo in repos:
        for path in repo.get('taxonomy', []):
            parts = [p.strip() for p in path.split('>')]
            current = tree
            for part in parts:
                if part not in current:
                    current[part] = {'_repos': [], '_children': {}}
                current[part]['_repos'].append(repo['repo'])
                current = current[part]['_children']

    return tree


def main():
    """Main execution function."""
    print("=" * 70)
    print("GitHub Stars README Analyzer v2.0")
    print(f"Using {MODEL} via Ollama")
    print("With Hierarchical Taxonomy (Depth Trees)")
    print("=" * 70)

    # Check Ollama availability
    print("\nChecking Ollama connection...")
    try:
        test_req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(test_req, timeout=5) as response:
            models = json.loads(response.read().decode('utf-8'))
            available_models = [m['name'] for m in models.get('models', [])]
            if not any(MODEL.split(':')[0] in m for m in available_models):
                print(f"Warning: Model {MODEL} may not be available.")
                print(f"Available models: {available_models}")
                print(f"Run: ollama pull {MODEL}")
            else:
                print(f"OK - {MODEL} is available")
    except Exception as e:
        print(f"Error: Cannot connect to Ollama at {OLLAMA_URL}")
        print(f"Make sure Ollama is running: ollama serve")
        print(f"And pull the model: ollama pull {MODEL}")
        sys.exit(1)

    # Load data
    csv_metadata = load_csv_metadata(CSV_FILE)
    readmes = get_readme_files()
    cache = load_cache()

    print(f"\nLoaded {len(csv_metadata)} repos from CSV")
    print(f"Found {len(readmes)} README files")

    # Determine what needs analysis
    all_repos = set(csv_metadata.keys())
    results = []
    to_analyze = []

    for repo in all_repos:
        csv_meta = csv_metadata.get(repo, {})

        if repo in readmes:
            content = readmes[repo]
            content_hash = compute_hash(content)

            # Check cache - also check version
            cached = cache.get(repo)
            if cached and cached.get('readme_hash') == content_hash and cached.get('analysis_version') == '2.0':
                print(f"[CACHED] {repo}")
                results.append(cached)
            else:
                to_analyze.append((repo, content, csv_meta))
        else:
            # No README - create minimal entry
            analysis = analyze_without_readme(repo, csv_meta)
            results.append(asdict(analysis))

    print(f"\nNeed to analyze: {len(to_analyze)} repos")
    print(f"Cached: {len(results) - len([r for r in results if not r.get('has_readme', True)])} repos")
    print(f"No README: {len([r for r in results if not r.get('has_readme', True)])} repos")

    if not to_analyze:
        print("\nAll repos already analyzed!")
    else:
        print(f"\nAnalyzing repos (this may take a while)...")
        print("-" * 70)

        completed = 0
        total = len(to_analyze)

        for repo, content, csv_meta in to_analyze:
            completed += 1
            print(f"[{completed}/{total}] Analyzing {repo}...", end=" ", flush=True)

            try:
                analysis = analyze_readme(repo, content, csv_meta)
                result = asdict(analysis)
                results.append(result)

                # Update cache
                cache[repo] = result

                if analysis.error:
                    print(f"WARN: {analysis.error[:30]}")
                else:
                    # Show first taxonomy path
                    tax = analysis.taxonomy[0] if analysis.taxonomy else "No taxonomy"
                    print(f"OK - {tax[:40]}")

                # Save cache periodically
                if completed % 5 == 0:
                    save_cache(cache)

            except Exception as e:
                print(f"ERROR: {str(e)[:50]}")
                analysis = analyze_without_readme(repo, csv_meta)
                analysis.error = str(e)
                results.append(asdict(analysis))

            # Small delay to be nice to the LLM
            time.sleep(0.3)

    # Save final cache
    save_cache(cache)

    # Sort by stars
    results.sort(key=lambda x: x.get('stars', 0), reverse=True)

    # Build taxonomy tree for insights
    taxonomy_tree = build_taxonomy_tree(results)

    # Collect all unique tags and taxonomy paths
    all_tags = {}
    all_taxonomy_paths = {}
    all_tech = {}

    for r in results:
        for tag in r.get('tags', []):
            all_tags[tag] = all_tags.get(tag, 0) + 1
        for path in r.get('taxonomy', []):
            # Count full paths and partial paths
            parts = [p.strip() for p in path.split('>')]
            for i in range(1, len(parts) + 1):
                partial = ' > '.join(parts[:i])
                all_taxonomy_paths[partial] = all_taxonomy_paths.get(partial, 0) + 1
        for tech in r.get('tech_stack', []):
            all_tech[tech.lower()] = all_tech.get(tech.lower(), 0) + 1

    # Save results
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_repos": len(results),
        "model_used": MODEL,
        "analysis_version": "2.0",
        "repos": results,
        "metadata": {
            "tags": dict(sorted(all_tags.items(), key=lambda x: -x[1])),
            "taxonomy_paths": dict(sorted(all_taxonomy_paths.items(), key=lambda x: -x[1])),
            "tech_stack": dict(sorted(all_tech.items(), key=lambda x: -x[1])),
        }
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Total repositories: {len(results)}")
    print(f"Output saved to: {OUTPUT_FILE}")

    print(f"\nTop Taxonomy Paths:")
    for path, count in sorted(all_taxonomy_paths.items(), key=lambda x: -x[1])[:15]:
        depth = path.count('>') + 1
        indent = "  " * (depth - 1)
        print(f"  {indent}{path}: {count}")

    print(f"\nTop Tags:")
    for tag, count in sorted(all_tags.items(), key=lambda x: -x[1])[:15]:
        print(f"  {tag}: {count}")

    print(f"\nTop Tech Stack:")
    for tech, count in sorted(all_tech.items(), key=lambda x: -x[1])[:10]:
        print(f"  {tech}: {count}")

    print("\nRun 'python generate_dashboard.py' to create the interactive dashboard.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
