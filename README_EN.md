# Tavily Key Generator - Rebuilt Edition

[中文说明](./README.md)

This is the fully rebuilt edition of the Tavily registration tool.

The old unstable script flow has been replaced with a single unified pipeline:

- Real local browser automation
- Local Turnstile solver
- Email API based verification-code retrieval
- Real Tavily API validation immediately after a key is extracted

The goal of this rebuild is simple: make the Tavily / Auth0 / Cloudflare registration flow usable, repeatable, concurrent, and suitable for unattended background execution.

For a general Cloudflare unlimited-alias domain mail guide, see:
[Cloudflare Mail Setup Guide](./docs/Cloudflare-Mail-Setup-Guide.md)

## Features

- Single launcher entry, no long command-line arguments required
- Automatically creates and reuses `venv`
- Automatically installs Python dependencies and browser dependencies
- Supports Cloudflare custom-domain mail API
- Supports DuckMail API
- Supports multiple domains with runtime selection
- Supports concurrent registration
- Runs the browser in headless mode by default
- Verifies each extracted API key with a real Tavily API call
- Optionally uploads verified keys to your own key pool server
- Startup scripts for Windows, macOS, and Linux

## Screenshots

### Launcher

![Launcher Overview](./docs/screenshots/launcher-overview.jpg)

### Concurrent Registration and Real API Validation

![Registration Success](./docs/screenshots/registration-success.jpg)

### Proxy Dashboard

![Proxy Dashboard](./docs/screenshots/proxy-dashboard.jpg)

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/skernelx/tavily-key-generator.git
cd tavily-key-generator
```

### 2. Configure the environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your mail provider settings and optional upload settings.

### 3. Run the launcher

macOS / Linux:

```bash
python3 run.py
```

or:

```bash
./start_auto.sh
```

Windows:

```bat
start_auto.bat
```

## What Happens on Startup

When you run the launcher, it will automatically:

1. Create or reuse `venv`
2. Upgrade `pip`, `setuptools`, and `wheel`
3. Install packages from `requirements.txt`
4. Download Camoufox if needed
5. Install Playwright Chromium if needed
6. Read `.env`
7. Check the configured mail provider
8. Let you choose a domain if multiple domains are configured
9. Ask for the registration count
10. Ask for the concurrency level
11. Ask whether to upload keys automatically
12. Start the local solver
13. Handle email verification and password setup
14. Recover from random password-page challenge failures
15. Extract the API key
16. Verify the API key with a real API call for the selected service
17. Save the result to `accounts.txt` or `firecrawl_accounts.txt`
18. Upload the verified key with its service tag if upload is enabled

## Runtime Flow

```text
run.py
  -> choose service (Tavily / Firecrawl)
  -> load .env
  -> choose domain
  -> input count / concurrency
  -> choose upload or not
  -> [Tavily only] start local Turnstile solver
  -> create mailbox with service-specific prefix
  -> open signup page
  -> [Tavily only] solve Turnstile locally
  -> receive email code or verification link
  -> set password / finish verification
  -> enter dashboard
  -> extract API key
  -> verify API key with the real service API
  -> save / upload
```

## Configuration

See [`.env.example`](./.env.example) for the full configuration template.

### Cloudflare Mail API

```env
EMAIL_PROVIDER=cloudflare
EMAIL_API_URL=https://your-mail-api.example.com
EMAIL_API_TOKEN=replace-with-your-token
EMAIL_DOMAIN=example.com
EMAIL_DOMAINS=example.com,example.org
```

Notes:

- Use `EMAIL_DOMAIN` for a single domain
- Use `EMAIL_DOMAINS` for multiple domains
- The launcher will let you choose the active domain at runtime

### DuckMail API

```env
EMAIL_PROVIDER=duckmail
DUCKMAIL_API_URL=https://api.duckmail.sbs
DUCKMAIL_API_KEY=
DUCKMAIL_DOMAIN=
DUCKMAIL_DOMAINS=
```

Notes:

- You can configure either one domain or multiple domains
- If you have a private DuckMail domain and API key, just put them in `.env`
- Public DuckMail domains may work for mailbox creation and email retrieval, but may still be blocked by Tavily risk control

### Upload to Your Own Server

```env
SERVER_URL=https://your-server.example.com
SERVER_ADMIN_PASSWORD=replace-with-your-admin-password
DEFAULT_UPLOAD=true
```

Notes:

- `DEFAULT_UPLOAD=true` means the launcher defaults to upload enabled
- The actual upload decision still depends on the runtime choice you make when the launcher starts

### Runtime Options

```env
DEFAULT_COUNT=1
DEFAULT_CONCURRENCY=2
DEFAULT_DELAY=10
REGISTER_HEADLESS=true
FIRECRAWL_REGISTER_HEADLESS=true
EMAIL_CODE_TIMEOUT=90
API_KEY_TIMEOUT=20
EMAIL_POLL_INTERVAL=3
SOLVER_PORT=5073
SOLVER_THREADS=1
```

Notes:

- `REGISTER_HEADLESS=true` keeps the browser in the background
- If `FIRECRAWL_REGISTER_HEADLESS` is not set, it now inherits `REGISTER_HEADLESS`
- Firecrawl now runs headless by default; if you hit `Security check failed`, temporarily switch it to `false` for visible-browser debugging
- The actual solver thread count becomes `max(SOLVER_THREADS, selected concurrency)`
- In normal use, you do not need to pass extra command-line arguments

## Output

Successful registrations are saved to:

```text
accounts.txt
```

Format:

```text
email,password,api_key
email,password,api_key
```

## Real-World Validation

The current rebuilt flow has already been validated in real runs:

- Full registration works with the Cloudflare mail flow
- Email verification codes can be fetched automatically
- Extracted API keys are validated with real Tavily API requests
- Concurrent registration has been tested
- Random password-page challenge recovery has been added and verified in real runs

In the most recent regression runs, the password page twice reproduced the "submitted but did not redirect immediately" challenge case, and the new recovery logic successfully pulled the flow through both times.

## Known Limitations

### DuckMail Public Domains

The current status of public DuckMail domains is:

- Mailbox creation works
- 6-digit verification-code retrieval works
- Tavily may still block the flow on the password page

Common page message:

```text
Suspicious activity detected
```

If you want reliable full registration, prefer:

- Cloudflare custom-domain mail
- DuckMail private domain + API key

### First Run on a New Machine

On a new machine, it is better to run one account first before enabling concurrency.

The first run may need to download browser dependencies, and system/network/proxy conditions can differ across machines.

### System-Level Prerequisites

The launcher can bootstrap project dependencies and browser dependencies automatically, but it does not install Python itself.

At minimum, the target machine should already have:

- Python 3
- `venv` support
- A usable network environment for installing dependencies

## Project Structure

```text
.
├── run.py                    # Recommended entry point
├── tavily_core.py            # Unified registration entry, forwards to browser flow
├── tavily_browser_solver.py  # Main browser registration logic
├── api_solver.py             # Local Turnstile solver
├── mail_provider.py          # Mail provider abstraction
├── config.py                 # .env / environment loading
├── start_auto.sh             # macOS / Linux launcher
├── start_auto.bat            # Windows launcher
├── proxy/                    # Optional multi-service proxy (Tavily / Firecrawl)
├── README.md                 # Chinese README
└── README_EN.md              # English README
```

## Module Notes

Some files are not primary entry points, but they are still part of the working runtime:

- `tavily_core.py`
  A compatibility layer that forwards the unified entry to the browser-based registration flow.

- `browser_configs.py`
  Browser configuration helper for `api_solver.py`.

- `db_results.py`
  Result-storage helper for `api_solver.py`.

- `proxy/`
  An optional standalone module for turning Tavily / Firecrawl keys into separate pooled proxy services.

Runtime artifacts that should not be committed:

- `.env`
- `venv/`
- `__pycache__/`
- `accounts.txt`
- `firecrawl_accounts.txt`
- `proxy/data/`

## Optional Proxy Service

If you want to pool registered keys behind a single endpoint, use `proxy/`.
It now exposes isolated Tavily and Firecrawl pools, tokens, and quota sync.

Start it with:

```bash
cd proxy
docker compose up -d
```

See [`proxy/README.md`](./proxy/README.md) for details.

## Recommended Usage

If your goal is simply to batch-register and collect keys, the shortest path is:

1. Configure `.env`
2. Run `python3 run.py`
3. Choose the service (Tavily / Firecrawl)
4. Choose the mail domain
5. Enter the registration count
6. Enter the concurrency level
7. Read the results from `accounts.txt` or `firecrawl_accounts.txt`

If you also need centralized distribution, enable server upload or connect the generated keys to `proxy/`.

## Disclaimer

This project is provided for automation testing, research, and personal learning purposes only.

You are responsible for evaluating the target service's terms, risk controls, and account-usage implications.
