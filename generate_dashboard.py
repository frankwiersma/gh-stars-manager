#!/usr/bin/env python3
"""
Dashboard Generator - Creates an interactive HTML dashboard for starred repos.

Features:
- Hierarchical taxonomy tree navigation
- Full-text search with fuzzy matching
- Tag cloud and filtering
- Insights and analytics
- Beautiful, responsive design
"""

import json
import os
import sys
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

INPUT_FILE = "analyzed_repos.json"
OUTPUT_FILE = "dashboard.html"


def build_taxonomy_tree(repos: List[Dict]) -> Dict:
    """Build hierarchical tree from taxonomy paths."""
    tree = defaultdict(lambda: {"count": 0, "repos": [], "children": defaultdict(dict)})

    for repo in repos:
        for path in repo.get("taxonomy", []):
            parts = [p.strip() for p in path.split(">")]
            current = tree
            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {"count": 0, "repos": [], "children": {}}
                current[part]["count"] += 1
                if i == len(parts) - 1:
                    current[part]["repos"].append(repo["repo"])
                current = current[part]["children"]

    return dict(tree)


def generate_tree_html(tree: Dict, level: int = 0) -> str:
    """Generate HTML for taxonomy tree."""
    html = ""
    for name, data in sorted(tree.items(), key=lambda x: -x[1]["count"]):
        indent = "  " * level
        has_children = bool(data.get("children"))
        expanded = level < 1  # Auto-expand first level

        html += f'''
        <div class="tree-node" data-level="{level}">
            <div class="tree-item {'has-children' if has_children else ''}"
                 onclick="filterByTaxonomy('{name}', {level})"
                 data-taxonomy="{name}">
                <span class="tree-toggle">{('▼' if expanded else '▶') if has_children else '•'}</span>
                <span class="tree-label">{name}</span>
                <span class="tree-count">{data["count"]}</span>
            </div>
            <div class="tree-children {'expanded' if expanded else 'collapsed'}">
                {generate_tree_html(data.get("children", {}), level + 1)}
            </div>
        </div>'''

    return html


def get_insights(repos: List[Dict]) -> Dict:
    """Generate insights from repo data."""
    insights = {
        "total_repos": len(repos),
        "total_stars": sum(r.get("stars", 0) for r in repos),
        "top_languages": defaultdict(int),
        "top_tags": defaultdict(int),
        "maturity_dist": defaultdict(int),
        "complexity_dist": defaultdict(int),
        "top_level_taxonomy": defaultdict(int),
        "repos_with_readme": sum(1 for r in repos if r.get("has_readme", True)),
    }

    for r in repos:
        if r.get("language"):
            insights["top_languages"][r["language"]] += 1
        for tag in r.get("tags", []):
            insights["top_tags"][tag] += 1
        if r.get("maturity"):
            insights["maturity_dist"][r["maturity"]] += 1
        if r.get("complexity"):
            insights["complexity_dist"][r["complexity"]] += 1
        for tax in r.get("taxonomy", []):
            top_level = tax.split(">")[0].strip()
            insights["top_level_taxonomy"][top_level] += 1

    # Sort and limit
    insights["top_languages"] = dict(sorted(insights["top_languages"].items(), key=lambda x: -x[1])[:15])
    insights["top_tags"] = dict(sorted(insights["top_tags"].items(), key=lambda x: -x[1])[:30])
    insights["top_level_taxonomy"] = dict(sorted(insights["top_level_taxonomy"].items(), key=lambda x: -x[1]))

    return insights


def generate_dashboard(data: Dict) -> str:
    """Generate the complete HTML dashboard."""
    repos = data.get("repos", [])
    metadata = data.get("metadata", {})

    tree = build_taxonomy_tree(repos)
    tree_html = generate_tree_html(tree)
    insights = get_insights(repos)

    # Generate tag cloud HTML
    tag_counts = metadata.get("tags", {})
    max_count = max(tag_counts.values()) if tag_counts else 1
    tag_cloud_html = ""
    for tag, count in list(tag_counts.items())[:50]:
        size = 0.7 + (count / max_count) * 1.0
        tag_cloud_html += f'<span class="tag-cloud-item" style="font-size: {size}em" onclick="filterByTag(\'{tag}\')" data-count="{count}">{tag}</span> '

    # Language chart data
    lang_labels = list(insights["top_languages"].keys())[:10]
    lang_values = list(insights["top_languages"].values())[:10]

    # Top level taxonomy chart
    tax_labels = list(insights["top_level_taxonomy"].keys())
    tax_values = list(insights["top_level_taxonomy"].values())

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Stars Manager - Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/fuse.js@6.6.2"></script>
    <style>
        :root {{
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --border-color: #30363d;
            --text-primary: #e6edf3;
            --text-secondary: #8b949e;
            --text-muted: #6e7681;
            --accent-blue: #58a6ff;
            --accent-green: #3fb950;
            --accent-purple: #a371f7;
            --accent-orange: #d29922;
            --accent-red: #f85149;
            --accent-pink: #db61a2;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
        }}

        /* Header */
        .header {{
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 16px 24px;
            position: sticky;
            top: 0;
            z-index: 100;
        }}

        .header-content {{
            max-width: 1800px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            gap: 24px;
            flex-wrap: wrap;
        }}

        .logo {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 20px;
            font-weight: 600;
        }}

        .logo svg {{
            width: 32px;
            height: 32px;
        }}

        .search-container {{
            flex: 1;
            max-width: 600px;
            min-width: 300px;
        }}

        .search-input {{
            width: 100%;
            padding: 10px 16px;
            font-size: 14px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-primary);
            outline: none;
        }}

        .search-input:focus {{
            border-color: var(--accent-blue);
            box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
        }}

        .stats {{
            display: flex;
            gap: 20px;
            font-size: 14px;
            color: var(--text-secondary);
        }}

        .stat {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .stat-value {{
            font-weight: 600;
            color: var(--text-primary);
        }}

        /* Layout */
        .main-container {{
            display: flex;
            max-width: 1800px;
            margin: 0 auto;
            min-height: calc(100vh - 73px);
        }}

        /* Sidebar */
        .sidebar {{
            width: 300px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            padding: 20px;
            overflow-y: auto;
            position: sticky;
            top: 73px;
            height: calc(100vh - 73px);
        }}

        .sidebar-section {{
            margin-bottom: 24px;
        }}

        .sidebar-title {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 12px;
            letter-spacing: 0.5px;
        }}

        /* Taxonomy Tree */
        .tree-node {{
            margin-left: 0;
        }}

        .tree-node[data-level="1"] {{
            margin-left: 16px;
        }}

        .tree-node[data-level="2"] {{
            margin-left: 32px;
        }}

        .tree-node[data-level="3"] {{
            margin-left: 48px;
        }}

        .tree-item {{
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 8px;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.15s;
            font-size: 13px;
        }}

        .tree-item:hover {{
            background: var(--bg-tertiary);
        }}

        .tree-item.active {{
            background: rgba(88, 166, 255, 0.15);
            color: var(--accent-blue);
        }}

        .tree-toggle {{
            width: 16px;
            font-size: 10px;
            color: var(--text-muted);
        }}

        .tree-label {{
            flex: 1;
        }}

        .tree-count {{
            font-size: 11px;
            background: var(--bg-tertiary);
            padding: 2px 8px;
            border-radius: 10px;
            color: var(--text-secondary);
        }}

        .tree-children {{
            overflow: hidden;
            transition: max-height 0.3s ease;
        }}

        .tree-children.collapsed {{
            max-height: 0;
        }}

        .tree-children.expanded {{
            max-height: 2000px;
        }}

        /* Tag Cloud */
        .tag-cloud {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}

        .tag-cloud-item {{
            padding: 4px 10px;
            background: var(--bg-tertiary);
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.15s;
            white-space: nowrap;
        }}

        .tag-cloud-item:hover {{
            background: var(--accent-blue);
            color: var(--bg-primary);
        }}

        /* Content */
        .content {{
            flex: 1;
            padding: 24px;
            overflow-y: auto;
        }}

        /* Filter Bar */
        .filter-bar {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}

        .active-filters {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}

        .filter-tag {{
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 4px 12px;
            background: rgba(88, 166, 255, 0.15);
            color: var(--accent-blue);
            border-radius: 20px;
            font-size: 13px;
        }}

        .filter-tag button {{
            background: none;
            border: none;
            color: inherit;
            cursor: pointer;
            padding: 0;
            font-size: 16px;
            line-height: 1;
        }}

        .sort-select {{
            padding: 8px 12px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 13px;
            cursor: pointer;
        }}

        .results-count {{
            color: var(--text-secondary);
            font-size: 14px;
            margin-left: auto;
        }}

        /* View Toggle */
        .view-toggle {{
            display: flex;
            background: var(--bg-tertiary);
            border-radius: 6px;
            overflow: hidden;
        }}

        .view-btn {{
            padding: 8px 12px;
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.15s;
        }}

        .view-btn.active {{
            background: var(--accent-blue);
            color: var(--bg-primary);
        }}

        /* Repo Grid */
        .repo-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
            gap: 16px;
        }}

        .repo-grid.list-view {{
            grid-template-columns: 1fr;
        }}

        /* Repo Card */
        .repo-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px;
            transition: border-color 0.15s, transform 0.15s;
        }}

        .repo-card:hover {{
            border-color: var(--accent-blue);
            transform: translateY(-2px);
        }}

        .repo-header {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 12px;
        }}

        .repo-avatar {{
            width: 40px;
            height: 40px;
            border-radius: 6px;
            background: var(--bg-tertiary);
        }}

        .repo-title {{
            flex: 1;
            min-width: 0;
        }}

        .repo-name {{
            font-size: 16px;
            font-weight: 600;
            color: var(--accent-blue);
            text-decoration: none;
            display: block;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .repo-name:hover {{
            text-decoration: underline;
        }}

        .repo-owner {{
            font-size: 13px;
            color: var(--text-secondary);
        }}

        .repo-stars {{
            display: flex;
            align-items: center;
            gap: 4px;
            color: var(--accent-orange);
            font-size: 14px;
            font-weight: 500;
        }}

        .repo-summary {{
            font-size: 14px;
            color: var(--text-secondary);
            margin-bottom: 12px;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}

        .repo-taxonomy {{
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            margin-bottom: 12px;
        }}

        .taxonomy-path {{
            font-size: 11px;
            padding: 3px 8px;
            background: rgba(163, 113, 247, 0.15);
            color: var(--accent-purple);
            border-radius: 4px;
        }}

        .repo-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            margin-bottom: 12px;
        }}

        .repo-tag {{
            font-size: 11px;
            padding: 2px 8px;
            background: var(--bg-tertiary);
            color: var(--text-secondary);
            border-radius: 20px;
            cursor: pointer;
        }}

        .repo-tag:hover {{
            background: var(--accent-blue);
            color: var(--bg-primary);
        }}

        .repo-meta {{
            display: flex;
            gap: 12px;
            font-size: 12px;
            color: var(--text-muted);
            flex-wrap: wrap;
        }}

        .repo-meta-item {{
            display: flex;
            align-items: center;
            gap: 4px;
        }}

        .lang-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--accent-blue);
        }}

        .badge {{
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 500;
        }}

        .badge-maturity-stable {{ background: rgba(63, 185, 80, 0.2); color: var(--accent-green); }}
        .badge-maturity-mature {{ background: rgba(88, 166, 255, 0.2); color: var(--accent-blue); }}
        .badge-maturity-beta {{ background: rgba(210, 153, 34, 0.2); color: var(--accent-orange); }}
        .badge-maturity-alpha {{ background: rgba(248, 81, 73, 0.2); color: var(--accent-red); }}

        .badge-complexity-beginner {{ background: rgba(63, 185, 80, 0.2); color: var(--accent-green); }}
        .badge-complexity-intermediate {{ background: rgba(88, 166, 255, 0.2); color: var(--accent-blue); }}
        .badge-complexity-advanced {{ background: rgba(210, 153, 34, 0.2); color: var(--accent-orange); }}
        .badge-complexity-expert {{ background: rgba(248, 81, 73, 0.2); color: var(--accent-red); }}

        /* Right Sidebar - Insights */
        .insights-sidebar {{
            width: 320px;
            background: var(--bg-secondary);
            border-left: 1px solid var(--border-color);
            padding: 20px;
            overflow-y: auto;
            position: sticky;
            top: 73px;
            height: calc(100vh - 73px);
        }}

        .insight-card {{
            background: var(--bg-tertiary);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }}

        .insight-title {{
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .chart-container {{
            position: relative;
            height: 200px;
        }}

        /* No results */
        .no-results {{
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
        }}

        .no-results h3 {{
            font-size: 20px;
            margin-bottom: 8px;
            color: var(--text-primary);
        }}

        /* Mobile responsive */
        @media (max-width: 1400px) {{
            .insights-sidebar {{
                display: none;
            }}
        }}

        @media (max-width: 900px) {{
            .sidebar {{
                display: none;
            }}
            .main-container {{
                flex-direction: column;
            }}
        }}

        /* Loading */
        .loading {{
            display: none;
            text-align: center;
            padding: 40px;
        }}

        /* Keyboard shortcut hints */
        .kbd {{
            font-size: 11px;
            padding: 2px 6px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            font-family: monospace;
        }}

        /* Expandable details */
        .repo-details {{
            display: none;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid var(--border-color);
        }}

        .repo-card.expanded .repo-details {{
            display: block;
        }}

        .detail-section {{
            margin-bottom: 12px;
        }}

        .detail-label {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 4px;
        }}

        .detail-content {{
            font-size: 13px;
            color: var(--text-secondary);
        }}

        .standout-list {{
            list-style: none;
            padding: 0;
        }}

        .standout-list li {{
            padding: 4px 0;
            padding-left: 16px;
            position: relative;
        }}

        .standout-list li::before {{
            content: "✦";
            position: absolute;
            left: 0;
            color: var(--accent-orange);
        }}
    </style>
</head>
<body>
    <header class="header">
        <div class="header-content">
            <div class="logo">
                <svg viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"/>
                </svg>
                Stars Manager
            </div>
            <div class="search-container">
                <input type="text" class="search-input" id="searchInput"
                       placeholder="Search repos, tags, technologies... (Press /)"
                       autocomplete="off">
            </div>
            <div class="stats">
                <div class="stat">
                    <span class="stat-value">{insights["total_repos"]}</span>
                    <span>repos</span>
                </div>
                <div class="stat">
                    <span class="stat-value">{insights["total_stars"]:,}</span>
                    <span>total stars</span>
                </div>
            </div>
        </div>
    </header>

    <div class="main-container">
        <aside class="sidebar">
            <div class="sidebar-section">
                <div class="sidebar-title">Categories</div>
                <div id="taxonomyTree">
                    {tree_html}
                </div>
            </div>

            <div class="sidebar-section">
                <div class="sidebar-title">Popular Tags</div>
                <div class="tag-cloud" id="tagCloud">
                    {tag_cloud_html}
                </div>
            </div>
        </aside>

        <main class="content">
            <div class="filter-bar">
                <div class="active-filters" id="activeFilters"></div>
                <select class="sort-select" id="sortSelect" onchange="sortRepos()">
                    <option value="stars-desc">Most Stars</option>
                    <option value="stars-asc">Least Stars</option>
                    <option value="name-asc">Name A-Z</option>
                    <option value="name-desc">Name Z-A</option>
                    <option value="complexity-asc">Complexity: Easy First</option>
                    <option value="complexity-desc">Complexity: Hard First</option>
                </select>
                <div class="view-toggle">
                    <button class="view-btn active" onclick="setView('grid')" id="gridViewBtn">Grid</button>
                    <button class="view-btn" onclick="setView('list')" id="listViewBtn">List</button>
                </div>
                <div class="results-count" id="resultsCount"></div>
            </div>

            <div class="repo-grid" id="repoGrid"></div>
            <div class="no-results" id="noResults" style="display: none;">
                <h3>No repositories found</h3>
                <p>Try adjusting your search or filters</p>
            </div>
            <div class="loading" id="loading">Loading...</div>
        </main>

        <aside class="insights-sidebar">
            <div class="insight-card">
                <div class="insight-title">
                    <span>📊</span> Top Categories
                </div>
                <div class="chart-container">
                    <canvas id="categoryChart"></canvas>
                </div>
            </div>

            <div class="insight-card">
                <div class="insight-title">
                    <span>💻</span> Languages
                </div>
                <div class="chart-container">
                    <canvas id="languageChart"></canvas>
                </div>
            </div>

            <div class="insight-card">
                <div class="insight-title">
                    <span>🎯</span> Your Interests
                </div>
                <div id="interestsList" style="font-size: 13px; color: var(--text-secondary);">
                    <!-- Populated by JS -->
                </div>
            </div>
        </aside>
    </div>

    <script>
        // Data
        const repos = {json.dumps(repos, ensure_ascii=False)};
        const langLabels = {json.dumps(lang_labels)};
        const langValues = {json.dumps(lang_values)};
        const taxLabels = {json.dumps(tax_labels)};
        const taxValues = {json.dumps(tax_values)};

        // State
        let currentFilters = {{
            search: '',
            tags: [],
            taxonomy: [],
            language: ''
        }};
        let currentSort = 'stars-desc';
        let currentView = 'grid';

        // Fuse.js for fuzzy search
        const fuse = new Fuse(repos, {{
            keys: [
                {{ name: 'name', weight: 2 }},
                {{ name: 'repo', weight: 1.5 }},
                {{ name: 'summary', weight: 1 }},
                {{ name: 'purpose', weight: 1 }},
                {{ name: 'tags', weight: 1.5 }},
                {{ name: 'tech_stack', weight: 1.5 }},
                {{ name: 'taxonomy', weight: 1 }},
                {{ name: 'keywords', weight: 1 }},
                {{ name: 'use_cases', weight: 0.8 }}
            ],
            threshold: 0.3,
            ignoreLocation: true
        }});

        // Language colors (subset)
        const langColors = {{
            'Python': '#3572A5', 'JavaScript': '#f1e05a', 'TypeScript': '#3178c6',
            'Go': '#00ADD8', 'Rust': '#dea584', 'Java': '#b07219',
            'C#': '#178600', 'C++': '#f34b7d', 'Ruby': '#701516',
            'PHP': '#4F5D95', 'Shell': '#89e051', 'PowerShell': '#012456',
            'HTML': '#e34c26', 'CSS': '#563d7c', 'Jupyter Notebook': '#DA5B0B'
        }};

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {{
            renderRepos();
            initCharts();
            initKeyboardShortcuts();
            generateInterests();
        }});

        // Render repos
        function renderRepos() {{
            let filtered = filterRepos();
            filtered = sortReposList(filtered);

            const grid = document.getElementById('repoGrid');
            const noResults = document.getElementById('noResults');
            const resultsCount = document.getElementById('resultsCount');

            if (filtered.length === 0) {{
                grid.innerHTML = '';
                noResults.style.display = 'block';
                resultsCount.textContent = '0 repositories';
                return;
            }}

            noResults.style.display = 'none';
            resultsCount.textContent = `${{filtered.length}} repositories`;

            grid.innerHTML = filtered.map(repo => `
                <div class="repo-card" onclick="toggleExpand(this)">
                    <div class="repo-header">
                        <img class="repo-avatar" src="https://github.com/${{repo.owner}}.png?size=80"
                             onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%2321262d%22 width=%2240%22 height=%2240%22/></svg>'"
                             alt="${{repo.owner}}">
                        <div class="repo-title">
                            <a href="${{repo.github_url}}" target="_blank" class="repo-name" onclick="event.stopPropagation()">
                                ${{repo.name}}
                            </a>
                            <div class="repo-owner">${{repo.owner}}</div>
                        </div>
                        <div class="repo-stars">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                                <path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"/>
                            </svg>
                            ${{formatNumber(repo.stars)}}
                        </div>
                    </div>
                    <div class="repo-summary">${{repo.summary || 'No description available'}}</div>
                    <div class="repo-taxonomy">
                        ${{(repo.taxonomy || []).map(t => `<span class="taxonomy-path">${{t}}</span>`).join('')}}
                    </div>
                    <div class="repo-tags">
                        ${{(repo.tags || []).slice(0, 6).map(t => `<span class="repo-tag" onclick="event.stopPropagation(); filterByTag('${{t}}')">${{t}}</span>`).join('')}}
                        ${{(repo.tags || []).length > 6 ? `<span class="repo-tag">+${{repo.tags.length - 6}}</span>` : ''}}
                    </div>
                    <div class="repo-meta">
                        ${{repo.language ? `<span class="repo-meta-item"><span class="lang-dot" style="background: ${{langColors[repo.language] || '#8b949e'}}"></span>${{repo.language}}</span>` : ''}}
                        ${{repo.maturity ? `<span class="badge badge-maturity-${{repo.maturity}}">${{repo.maturity}}</span>` : ''}}
                        ${{repo.complexity ? `<span class="badge badge-complexity-${{repo.complexity}}">${{repo.complexity}}</span>` : ''}}
                    </div>
                    <div class="repo-details">
                        ${{repo.purpose ? `<div class="detail-section"><div class="detail-label">Purpose</div><div class="detail-content">${{repo.purpose}}</div></div>` : ''}}
                        ${{repo.target_audience ? `<div class="detail-section"><div class="detail-label">For</div><div class="detail-content">${{repo.target_audience}}</div></div>` : ''}}
                        ${{repo.potential_value ? `<div class="detail-section"><div class="detail-label">Value</div><div class="detail-content">${{repo.potential_value}}</div></div>` : ''}}
                        ${{(repo.standout_features || []).length > 0 ? `
                            <div class="detail-section">
                                <div class="detail-label">Standout Features</div>
                                <ul class="standout-list">
                                    ${{repo.standout_features.map(f => `<li>${{f}}</li>`).join('')}}
                                </ul>
                            </div>
                        ` : ''}}
                        ${{(repo.similar_to || []).length > 0 ? `
                            <div class="detail-section">
                                <div class="detail-label">Similar To</div>
                                <div class="detail-content">${{repo.similar_to.join(', ')}}</div>
                            </div>
                        ` : ''}}
                        ${{(repo.tech_stack || []).length > 0 ? `
                            <div class="detail-section">
                                <div class="detail-label">Tech Stack</div>
                                <div class="repo-tags">${{repo.tech_stack.map(t => `<span class="repo-tag">${{t}}</span>`).join('')}}</div>
                            </div>
                        ` : ''}}
                    </div>
                </div>
            `).join('');
        }}

        function toggleExpand(card) {{
            card.classList.toggle('expanded');
        }}

        function filterRepos() {{
            let result = repos;

            // Search filter
            if (currentFilters.search) {{
                const searchResults = fuse.search(currentFilters.search);
                result = searchResults.map(r => r.item);
            }}

            // Tag filter
            if (currentFilters.tags.length > 0) {{
                result = result.filter(r =>
                    currentFilters.tags.every(tag =>
                        (r.tags || []).includes(tag) ||
                        (r.tech_stack || []).map(t => t.toLowerCase()).includes(tag.toLowerCase())
                    )
                );
            }}

            // Taxonomy filter
            if (currentFilters.taxonomy.length > 0) {{
                result = result.filter(r =>
                    currentFilters.taxonomy.some(tax =>
                        (r.taxonomy || []).some(t => t.toLowerCase().includes(tax.toLowerCase()))
                    )
                );
            }}

            return result;
        }}

        function sortReposList(list) {{
            const complexityOrder = {{'beginner': 1, 'intermediate': 2, 'advanced': 3, 'expert': 4}};

            return [...list].sort((a, b) => {{
                switch(currentSort) {{
                    case 'stars-desc': return (b.stars || 0) - (a.stars || 0);
                    case 'stars-asc': return (a.stars || 0) - (b.stars || 0);
                    case 'name-asc': return a.name.localeCompare(b.name);
                    case 'name-desc': return b.name.localeCompare(a.name);
                    case 'complexity-asc':
                        return (complexityOrder[a.complexity] || 5) - (complexityOrder[b.complexity] || 5);
                    case 'complexity-desc':
                        return (complexityOrder[b.complexity] || 0) - (complexityOrder[a.complexity] || 0);
                    default: return 0;
                }}
            }});
        }}

        function filterByTag(tag) {{
            if (!currentFilters.tags.includes(tag)) {{
                currentFilters.tags.push(tag);
                updateFilterUI();
                renderRepos();
            }}
        }}

        function filterByTaxonomy(taxonomy, level) {{
            if (!currentFilters.taxonomy.includes(taxonomy)) {{
                currentFilters.taxonomy.push(taxonomy);
                updateFilterUI();
                renderRepos();
            }}

            // Toggle tree expansion
            event.stopPropagation();
            const treeItem = event.target.closest('.tree-item');
            if (treeItem) {{
                const node = treeItem.closest('.tree-node');
                const children = node.querySelector('.tree-children');
                const toggle = treeItem.querySelector('.tree-toggle');
                if (children) {{
                    children.classList.toggle('collapsed');
                    children.classList.toggle('expanded');
                    toggle.textContent = children.classList.contains('expanded') ? '▼' : '▶';
                }}
                treeItem.classList.add('active');
            }}
        }}

        function removeFilter(type, value) {{
            if (type === 'tag') {{
                currentFilters.tags = currentFilters.tags.filter(t => t !== value);
            }} else if (type === 'taxonomy') {{
                currentFilters.taxonomy = currentFilters.taxonomy.filter(t => t !== value);
            }} else if (type === 'search') {{
                currentFilters.search = '';
                document.getElementById('searchInput').value = '';
            }}
            updateFilterUI();
            renderRepos();
        }}

        function clearAllFilters() {{
            currentFilters = {{ search: '', tags: [], taxonomy: [], language: '' }};
            document.getElementById('searchInput').value = '';
            document.querySelectorAll('.tree-item.active').forEach(el => el.classList.remove('active'));
            updateFilterUI();
            renderRepos();
        }}

        function updateFilterUI() {{
            const container = document.getElementById('activeFilters');
            let html = '';

            if (currentFilters.search) {{
                html += `<span class="filter-tag">Search: "${{currentFilters.search}}" <button onclick="removeFilter('search')">&times;</button></span>`;
            }}

            currentFilters.tags.forEach(tag => {{
                html += `<span class="filter-tag">${{tag}} <button onclick="removeFilter('tag', '${{tag}}')">&times;</button></span>`;
            }});

            currentFilters.taxonomy.forEach(tax => {{
                html += `<span class="filter-tag">${{tax}} <button onclick="removeFilter('taxonomy', '${{tax}}')">&times;</button></span>`;
            }});

            if (currentFilters.search || currentFilters.tags.length || currentFilters.taxonomy.length) {{
                html += `<button class="filter-tag" onclick="clearAllFilters()" style="background: var(--bg-tertiary); color: var(--text-secondary);">Clear all</button>`;
            }}

            container.innerHTML = html;
        }}

        function sortRepos() {{
            currentSort = document.getElementById('sortSelect').value;
            renderRepos();
        }}

        function setView(view) {{
            currentView = view;
            const grid = document.getElementById('repoGrid');
            grid.classList.toggle('list-view', view === 'list');
            document.getElementById('gridViewBtn').classList.toggle('active', view === 'grid');
            document.getElementById('listViewBtn').classList.toggle('active', view === 'list');
        }}

        // Search handling
        const searchInput = document.getElementById('searchInput');
        let searchTimeout;
        searchInput.addEventListener('input', (e) => {{
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {{
                currentFilters.search = e.target.value;
                updateFilterUI();
                renderRepos();
            }}, 200);
        }});

        // Keyboard shortcuts
        function initKeyboardShortcuts() {{
            document.addEventListener('keydown', (e) => {{
                if (e.key === '/' && document.activeElement !== searchInput) {{
                    e.preventDefault();
                    searchInput.focus();
                }}
                if (e.key === 'Escape') {{
                    searchInput.blur();
                    if (currentFilters.search || currentFilters.tags.length || currentFilters.taxonomy.length) {{
                        clearAllFilters();
                    }}
                }}
            }});
        }}

        // Charts
        function initCharts() {{
            // Category chart
            new Chart(document.getElementById('categoryChart'), {{
                type: 'doughnut',
                data: {{
                    labels: taxLabels.slice(0, 8),
                    datasets: [{{
                        data: taxValues.slice(0, 8),
                        backgroundColor: [
                            '#58a6ff', '#3fb950', '#a371f7', '#d29922',
                            '#f85149', '#db61a2', '#79c0ff', '#7ee787'
                        ]
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            position: 'right',
                            labels: {{ color: '#8b949e', font: {{ size: 11 }} }}
                        }}
                    }}
                }}
            }});

            // Language chart
            new Chart(document.getElementById('languageChart'), {{
                type: 'bar',
                data: {{
                    labels: langLabels,
                    datasets: [{{
                        data: langValues,
                        backgroundColor: langLabels.map(l => langColors[l] || '#8b949e')
                    }}]
                }},
                options: {{
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: false }}
                    }},
                    scales: {{
                        x: {{
                            grid: {{ color: '#30363d' }},
                            ticks: {{ color: '#8b949e' }}
                        }},
                        y: {{
                            grid: {{ display: false }},
                            ticks: {{ color: '#8b949e', font: {{ size: 10 }} }}
                        }}
                    }}
                }}
            }});
        }}

        function generateInterests() {{
            const interests = [];

            // Analyze top categories
            const taxCounts = {{}};
            repos.forEach(r => {{
                (r.taxonomy || []).forEach(t => {{
                    const top = t.split('>')[0].trim();
                    taxCounts[top] = (taxCounts[top] || 0) + 1;
                }});
            }});

            const sortedTax = Object.entries(taxCounts).sort((a, b) => b[1] - a[1]);
            if (sortedTax.length > 0) {{
                interests.push(`🎯 You're most interested in <strong>${{sortedTax[0][0]}}</strong> (${{sortedTax[0][1]}} repos)`);
            }}

            // Languages
            const langCounts = {{}};
            repos.forEach(r => {{
                if (r.language) langCounts[r.language] = (langCounts[r.language] || 0) + 1;
            }});
            const sortedLang = Object.entries(langCounts).sort((a, b) => b[1] - a[1]);
            if (sortedLang.length > 0) {{
                interests.push(`💻 Favorite language: <strong>${{sortedLang[0][0]}}</strong> (${{sortedLang[0][1]}} repos)`);
            }}

            // Complexity preference
            const complexCounts = {{}};
            repos.forEach(r => {{
                if (r.complexity) complexCounts[r.complexity] = (complexCounts[r.complexity] || 0) + 1;
            }});
            const sortedComplex = Object.entries(complexCounts).sort((a, b) => b[1] - a[1]);
            if (sortedComplex.length > 0) {{
                interests.push(`📈 You prefer <strong>${{sortedComplex[0][0]}}</strong> level projects`);
            }}

            // Top tags
            const tagCounts = {{}};
            repos.forEach(r => {{
                (r.tags || []).forEach(t => {{
                    tagCounts[t] = (tagCounts[t] || 0) + 1;
                }});
            }});
            const sortedTags = Object.entries(tagCounts).sort((a, b) => b[1] - a[1]).slice(0, 3);
            if (sortedTags.length > 0) {{
                interests.push(`🏷️ Top interests: <strong>${{sortedTags.map(t => t[0]).join('</strong>, <strong>')}}</strong>`);
            }}

            document.getElementById('interestsList').innerHTML = interests.map(i => `<p style="margin-bottom: 8px;">${{i}}</p>`).join('');
        }}

        function formatNumber(num) {{
            if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
            if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
            return num.toString();
        }}
    </script>
</body>
</html>'''

    return html


def main():
    """Main execution."""
    print("=" * 60)
    print("Dashboard Generator")
    print("=" * 60)

    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        print("Run 'python analyze_readmes.py' first.")
        return 1

    print(f"\nLoading {INPUT_FILE}...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"Loaded {data.get('total_repos', 0)} repositories")

    print(f"\nGenerating dashboard...")
    html = generate_dashboard(data)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nDashboard saved to: {OUTPUT_FILE}")
    print(f"Open in browser: file://{os.path.abspath(OUTPUT_FILE)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
