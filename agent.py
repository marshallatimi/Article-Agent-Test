"""
Autonomous Business Website Agent
Uses Claude API with tool-use to research niches, write SEO content,
publish to a CMS, and track revenue — runs daily via GitHub Actions.

Requirements:
  pip install anthropic requests

Environment variables (set in GitHub Actions secrets):
  ANTHROPIC_API_KEY   — your Anthropic API key
  CMS_URL             — e.g. https://yourblog.ghost.io
  CMS_API_KEY         — Ghost Admin API key (or WordPress app password)
  CMS_TYPE            — "ghost" or "wordpress"
  ANALYTICS_SITE_ID   — Plausible site ID (optional)
  ANALYTICS_API_KEY   — Plausible API key (optional)
  ADSENSE_CODE        — your AdSense <script> snippet (optional)
  AFFILIATE_TAG       — your Amazon Associates tag (optional)
"""

import os
import json
import time
import re
import hashlib
import requests
import anthropic
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CMS_URL           = os.environ.get("CMS_URL", "")
CMS_API_KEY       = os.environ.get("CMS_API_KEY", "")
CMS_TYPE          = os.environ.get("CMS_TYPE", "ghost")       # "ghost" | "wordpress"
ANALYTICS_SITE_ID = os.environ.get("ANALYTICS_SITE_ID", "")
ANALYTICS_API_KEY = os.environ.get("ANALYTICS_API_KEY", "")
ADSENSE_CODE      = os.environ.get("ADSENSE_CODE", "")
AFFILIATE_TAG     = os.environ.get("AFFILIATE_TAG", "")

STATE_FILE  = "state.json"
MODEL       = "claude-sonnet-4-20250514"
MAX_TOKENS  = 4096

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "phase": "research",          # research | build | grow
        "niche": None,
        "site_url": CMS_URL or None,
        "published_slugs": [],
        "topic_queue": [],
        "last_run": None,
        "total_articles": 0,
    }

def save_state(state: dict):
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    print(f"[state] saved — phase={state['phase']}, articles={state['total_articles']}")

# ── Tool definitions ───────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for niche research, keyword ideas, trends, or competitor analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (3–8 words)"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "write_article",
        "description": "Write a full SEO-optimized article on a given topic for the website niche.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":    {"type": "string", "description": "Article title (H1)"},
                "topic":    {"type": "string", "description": "Topic / keyword to target"},
                "niche":    {"type": "string", "description": "Site niche for context"},
                "word_count": {"type": "integer", "description": "Target word count (800–1500)"},
            },
            "required": ["title", "topic", "niche"],
        },
    },
    {
        "name": "publish_article",
        "description": "Publish a written article to the CMS (Ghost or WordPress).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":   {"type": "string"},
                "html":    {"type": "string", "description": "Full HTML body of the article"},
                "tags":    {"type": "array", "items": {"type": "string"}},
                "excerpt": {"type": "string"},
            },
            "required": ["title", "html"],
        },
    },
    {
        "name": "get_analytics",
        "description": "Fetch top pages and traffic stats from Plausible Analytics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "Time period: '7d', '30d', or '12mo'"}
            },
            "required": ["period"],
        },
    },
    {
        "name": "save_niche",
        "description": "Save the chosen niche and generate an initial topic queue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "niche":       {"type": "string", "description": "The chosen niche"},
                "description": {"type": "string", "description": "One-sentence niche description"},
                "topics":      {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 20 article topic ideas for this niche",
                },
            },
            "required": ["niche", "description", "topics"],
        },
    },
]

# ── Tool executors ────────────────────────────────────────────────────────────

def tool_web_search(query: str) -> str:
    """Uses DuckDuckGo Instant Answer API (free, no key needed)."""
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10,
        )
        data = r.json()
        snippets = []
        if data.get("AbstractText"):
            snippets.append(data["AbstractText"])
        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                snippets.append(topic["Text"])
        result = "\n".join(snippets) if snippets else "No results found."
        print(f"[web_search] '{query}' → {len(snippets)} snippets")
        return result[:2000]
    except Exception as e:
        return f"Search error: {e}"


def tool_write_article(title: str, topic: str, niche: str, word_count: int = 1000) -> str:
    """Calls Claude to write the article body as HTML."""
    affiliate_note = (
        f"\n- Where relevant, naturally mention products and link them as Amazon affiliate URLs "
        f"using tag '{AFFILIATE_TAG}'. Format: https://www.amazon.com/s?k=KEYWORD&tag={AFFILIATE_TAG}"
        if AFFILIATE_TAG else ""
    )
    prompt = f"""Write a {word_count}-word SEO-optimized article for a {niche} website.

Title: {title}
Target keyword: {topic}

Requirements:
- Return ONLY valid HTML (use <h2>, <h3>, <p>, <ul>, <li>, <strong>)
- Include the target keyword naturally 3-5 times
- Add a compelling introduction and conclusion
- Use subheadings every 200-300 words
- Include practical tips and actionable advice{affiliate_note}
- Do NOT include <html>, <head>, <body>, or <title> tags — body content only"""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    html = resp.content[0].text
    # Inject AdSense after first paragraph if configured
    if ADSENSE_CODE and "<p>" in html:
        html = html.replace("</p>", f"</p>\n{ADSENSE_CODE}", 1)
    print(f"[write_article] '{title}' — {len(html)} chars")
    return html


def tool_publish_article(title: str, html: str, tags: list = None, excerpt: str = "") -> str:
    """Publish to Ghost or WordPress via REST API."""
    if not CMS_URL or not CMS_API_KEY:
        return "CMS not configured — article saved locally only."

    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

    if CMS_TYPE == "ghost":
        return _publish_ghost(title, slug, html, tags or [], excerpt)
    else:
        return _publish_wordpress(title, slug, html, tags or [])


def _publish_ghost(title, slug, html, tags, excerpt) -> str:
    """Ghost Admin API v3."""
    import jwt as pyjwt  # pip install PyJWT
    key_id, secret = CMS_API_KEY.split(":")
    iat = int(time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {"iat": iat, "exp": iat + 300, "aud": "/admin/"}
    token = pyjwt.encode(payload, bytes.fromhex(secret), algorithm="HS256", headers=header)

    url  = f"{CMS_URL.rstrip('/')}/ghost/api/admin/posts/"
    body = {
        "posts": [{
            "title":        title,
            "slug":         slug,
            "html":         html,
            "status":       "published",
            "excerpt":      excerpt,
            "tags":         [{"name": t} for t in tags],
            "published_at": datetime.now(timezone.utc).isoformat(),
        }]
    }
    r = requests.post(url, json=body, headers={"Authorization": f"Ghost {token}"}, timeout=15)
    if r.ok:
        post_url = r.json()["posts"][0].get("url", "")
        print(f"[publish_ghost] published: {post_url}")
        return f"Published: {post_url}"
    return f"Ghost error {r.status_code}: {r.text[:200]}"


def _publish_wordpress(title, slug, html, tags) -> str:
    """WordPress REST API with Application Password."""
    site = CMS_URL.rstrip("/")
    url  = f"{site}/wp-json/wp/v2/posts"
    # CMS_API_KEY format: "username:app_password"
    auth = tuple(CMS_API_KEY.split(":", 1))
    body = {
        "title":   title,
        "slug":    slug,
        "content": html,
        "status":  "publish",
    }
    r = requests.post(url, json=body, auth=auth, timeout=15)
    if r.ok:
        post_url = r.json().get("link", "")
        print(f"[publish_wordpress] published: {post_url}")
        return f"Published: {post_url}"
    return f"WordPress error {r.status_code}: {r.text[:200]}"


def tool_get_analytics(period: str = "7d") -> str:
    """Plausible Analytics API."""
    if not ANALYTICS_SITE_ID or not ANALYTICS_API_KEY:
        return "Analytics not configured."
    try:
        r = requests.get(
            "https://plausible.io/api/v1/stats/breakdown",
            params={
                "site_id":  ANALYTICS_SITE_ID,
                "period":   period,
                "property": "event:page",
                "limit":    10,
            },
            headers={"Authorization": f"Bearer {ANALYTICS_API_KEY}"},
            timeout=10,
        )
        data = r.json().get("results", [])
        lines = [f"{row['page']} — {row['visitors']} visitors" for row in data]
        return "\n".join(lines) if lines else "No data yet."
    except Exception as e:
        return f"Analytics error: {e}"


def tool_save_niche(niche: str, description: str, topics: list, state: dict) -> str:
    state["niche"]       = niche
    state["description"] = description
    state["topic_queue"] = topics
    state["phase"]       = "build"
    print(f"[save_niche] niche='{niche}', {len(topics)} topics queued")
    return f"Niche saved: {niche}. {len(topics)} topics queued."


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def execute_tool(tool_name: str, tool_input: dict, state: dict) -> str:
    print(f"[tool] {tool_name}({list(tool_input.keys())})")
    if tool_name == "web_search":
        return tool_web_search(tool_input["query"])
    elif tool_name == "write_article":
        return tool_write_article(**tool_input)
    elif tool_name == "publish_article":
        result = tool_publish_article(**tool_input)
        slug = re.sub(r"[^a-z0-9]+", "-", tool_input["title"].lower()).strip("-")
        state["published_slugs"].append(slug)
        state["total_articles"] += 1
        return result
    elif tool_name == "get_analytics":
        return tool_get_analytics(tool_input.get("period", "7d"))
    elif tool_name == "save_niche":
        return tool_save_niche(
            tool_input["niche"],
            tool_input["description"],
            tool_input["topics"],
            state,
        )
    return f"Unknown tool: {tool_name}"


# ── Agent loop ────────────────────────────────────────────────────────────────

def build_system_prompt(state: dict) -> str:
    niche_ctx = f"The site niche is: {state['niche']}." if state["niche"] else "The niche has NOT been chosen yet."
    queue_ctx = (
        f"Topic queue ({len(state['topic_queue'])} remaining): {state['topic_queue'][:5]}"
        if state["topic_queue"] else "Topic queue is empty."
    )
    return f"""You are an autonomous business agent managing a content website to generate passive income through ads and affiliate links.

Current state:
- Phase: {state['phase']}
- {niche_ctx}
- Articles published: {state['total_articles']}
- {queue_ctx}
- Site URL: {state.get('site_url') or 'not set'}

Your job today (pick the most important task):
1. RESEARCH phase: If no niche is chosen, search for a profitable low-competition niche and call save_niche with the niche + 20 topic ideas.
2. BUILD phase: If niche is set but fewer than 30 articles are published, write and publish one high-quality SEO article from the topic queue.
3. GROW phase: If 30+ articles exist, fetch analytics, identify top performers, and either update an existing article or write a new one on a related keyword.

Rules:
- Always use tools — don't just describe what you would do, do it.
- For articles: write_article first, then immediately publish_article with the result.
- Pick topics from the queue when available. If the queue runs low (< 5), generate more.
- Keep articles practical, helpful, and genuinely useful to readers.
- Today's date: {datetime.now().strftime('%B %d, %Y')}"""


def run_agent(state: dict):
    """Run one agent session — Claude decides what to do and executes tools."""
    print(f"\n{'='*60}")
    print(f"Agent run — phase={state['phase']}, articles={state['total_articles']}")
    print(f"{'='*60}")

    messages = [
        {
            "role": "user",
            "content": "Run your daily task. Use tools to take real action — research, write, or publish as needed.",
        }
    ]

    max_iterations = 10
    for iteration in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=build_system_prompt(state),
            tools=TOOLS,
            messages=messages,
        )

        # Collect text output
        for block in response.content:
            if hasattr(block, "text") and block.text:
                print(f"\n[claude] {block.text[:300]}{'...' if len(block.text) > 300 else ''}")

        # If no tool calls, Claude is done
        if response.stop_reason == "end_turn":
            print("[agent] Claude finished — no more tool calls.")
            break

        # Process tool calls
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            break

        # Append assistant message
        messages.append({"role": "assistant", "content": response.content})

        # Execute each tool and collect results
        tool_results = []
        for tool_use in tool_uses:
            result = execute_tool(tool_use.name, tool_use.input, state)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tool_use.id,
                "content":     result,
            })

        messages.append({"role": "user", "content": tool_results})

        # Update phase based on article count
        if state["total_articles"] >= 30 and state["phase"] == "build":
            state["phase"] = "grow"
            print("[agent] Transitioning to GROW phase.")

    print(f"\n[agent] Session complete. Articles total: {state['total_articles']}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    state = load_state()
    try:
        run_agent(state)
    finally:
        save_state(state)

if __name__ == "__main__":
    main()
