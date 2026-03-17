# Autonomous Business Website Agent

A fully automated agent that researches a profitable niche, writes SEO content, publishes it daily, and monetizes with ads + affiliate links — runs free on GitHub Actions.

---

## How it works

1. **Research phase** — Claude searches for a low-competition niche and builds a queue of 20 article topics
2. **Build phase** — Every day, Claude writes and publishes one SEO article to your CMS
3. **Grow phase** — After 30 articles, Claude reads your analytics and optimizes top-performing content

---

## Setup (step by step)

### 1. Fork or clone this repo to GitHub

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO
```

### 2. Get your Anthropic API key

Sign up at https://console.anthropic.com and create an API key.
Free tier works to start; budget ~$5/month once content scales.

### 3. Set up a free CMS

**Option A — Ghost (recommended)**
- Sign up free at https://ghost.org/pricing (or self-host on Oracle Cloud free tier)
- Go to Settings → Integrations → Add custom integration
- Copy the Admin API Key (format: `KEY_ID:SECRET`)

**Option B — WordPress**
- Use WordPress.com free plan or self-host
- Go to Users → Profile → Application Passwords
- Format your key as `username:app_password`

### 4. Add GitHub Actions secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret

| Secret | Value | Required |
|--------|-------|----------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | Yes |
| `CMS_URL` | e.g. `https://yourblog.ghost.io` | Yes |
| `CMS_API_KEY` | Ghost or WordPress API key | Yes |
| `CMS_TYPE` | `ghost` or `wordpress` | Yes |
| `ANALYTICS_SITE_ID` | Plausible site ID | Optional |
| `ANALYTICS_API_KEY` | Plausible API key | Optional |
| `ADSENSE_CODE` | Your AdSense `<script>` tag | Optional |
| `AFFILIATE_TAG` | Amazon Associates tag | Optional |

### 5. Enable the workflow

Push the `.github/workflows/agent.yml` file to your repo.
Go to Actions tab → enable workflows if prompted.

### 6. Run it manually first (optional)

Go to Actions → "Business Agent Daily Run" → Run workflow.
Check the logs to confirm it connects to your CMS.

---

## Monetization setup

### Google AdSense
1. Apply at https://adsense.google.com (need 10+ published posts)
2. Once approved, paste your ad `<script>` tag as the `ADSENSE_CODE` secret
3. The agent will automatically inject it after the first paragraph of every article

### Amazon Associates
1. Sign up at https://affiliate-program.amazon.com
2. Add your Associates tag as the `AFFILIATE_TAG` secret
3. The agent will link relevant product mentions to Amazon search URLs

### Plausible Analytics (free self-hosted)
1. Deploy Plausible Community Edition: https://plausible.io/self-hosted
2. Or use Plausible Cloud (free 30-day trial, then $9/mo)
3. Add the site ID and API key as secrets

---

## File structure

```
├── agent.py                        # Main agent script
├── state.json                      # Auto-generated: tracks progress
└── .github/
    └── workflows/
        └── agent.yml               # GitHub Actions scheduler
```

## State file

`state.json` is committed automatically after each run. It tracks:

```json
{
  "phase": "build",
  "niche": "indoor herb gardening for beginners",
  "published_slugs": ["how-to-grow-basil", "best-grow-lights"],
  "topic_queue": ["mint varieties", "hydroponic herbs", "..."],
  "total_articles": 12,
  "last_run": "2026-03-16T08:02:14+00:00"
}
```

---

## Costs

| Service | Cost |
|---------|------|
| GitHub Actions | Free (2,000 min/month — you'll use ~10/day) |
| Ghost / WordPress | Free plan or self-hosted |
| Anthropic API | ~$0.05–0.20 per article (Sonnet pricing) |
| Domain name | $10–12/year (only needed once you're earning) |

**Total monthly cost to start: ~$3–6/month in API calls.**

---

## Customizing

- **Change publishing frequency**: Edit the cron in `agent.yml` (e.g., `"0 8 * * 1,3,5"` for Mon/Wed/Fri)
- **Change article length**: Modify `word_count` default in `tool_write_article()`
- **Target a specific niche**: Pre-set `state["niche"]` and `state["phase"] = "build"` in `state.json` before first run
- **Add more tools**: Extend the `TOOLS` list and `execute_tool()` dispatcher

---

## Limitations

- Web search uses DuckDuckGo Instant Answers (free, no key). For richer research, swap in a SerpAPI or Brave Search API key.
- AdSense requires manual approval — you must apply once you have content.
- The agent cannot open bank accounts or accept payments on your behalf — that's a one-time human step.
