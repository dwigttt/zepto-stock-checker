# Running Zepto Finder locally

A step-by-step guide to get the app running on your own computer — from a fresh
machine, no prior setup assumed. Works on **Linux**, **macOS**, and **Windows**.

When you're done you'll have the app open in your browser at
**http://localhost:5173**.

> ⚠️ **You need an Indian internet connection.** Zepto only answers requests
> from Indian IP addresses. If you're in India, you're good. If you're not (or
> you're on a non-Indian VPN), searches will fail until you add an Indian proxy —
> see [Step 3](#step-3-optional-add-a-proxy-if-youre-outside-india).

---

## What you need (3 tools)

| Tool | What it's for |
| --- | --- |
| **git** | Download the code |
| **uv** | Runs the Python backend (it also installs the right Python for you) |
| **Node.js + pnpm** | Runs the web frontend |

You don't need to install Python or worry about versions — `uv` handles that.

---

## Step 1 — Install the tools

Pick your operating system. Copy-paste the block, then **close and reopen your
terminal** afterwards (so the new commands are found).

### 🐧 Linux

```bash
# 1. git (Debian/Ubuntu shown — use dnf/pacman on Fedora/Arch)
sudo apt update && sudo apt install -y git curl

# 2. uv (Python runner)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. pnpm (frontend runner)
curl -fsSL https://get.pnpm.io/install.sh | sh -

# --- close and reopen your terminal here, then: ---

# 4. Node.js (pnpm installs it for you)
pnpm env use --global lts
```

### 🍎 macOS

```bash
# Install Homebrew first if you don't have it (https://brew.sh):
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Then install all four tools at once:
brew install git uv node pnpm
```

### 🪟 Windows

Open **PowerShell** and run (winget is built into Windows 10/11):

```powershell
winget install -e --id Git.Git
winget install -e --id astral-sh.uv
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id pnpm.pnpm
```

Then **close and reopen PowerShell.**

> 💡 If you have **WSL** or **Git Bash**, you can follow the Linux steps instead —
> it's a bit smoother because you can use the one-command `./dev.sh` later.

---

## Step 2 — Get the code

```bash
git clone https://github.com/dwigttt/zepto-stock-checker.git zepto-finder
cd zepto-finder
```

(Replace the URL if you got the project from somewhere else.)

---

## Step 3 — (Optional) Add a proxy if you're outside India

**Skip this if you're in India.** Otherwise, Zepto will block you and searches
will fail. You'll need an **Indian residential proxy** (e.g. from a provider like
DataImpulse, Bright Data, etc.).

```bash
# Linux / macOS
cp .env.example .env

# Windows (PowerShell)
copy .env.example .env
```

Open `.env` in a text editor and set your proxy URL:

```
PROXY_URL="http://username:password@host:port"
```

See `.env.example` for the exact format. `.env` is gitignored, so your
credentials stay private.

> Tip: a **sticky** residential session is far more reliable than a rotating one —
> rotating IPs frequently land on addresses Zepto has blocked.

---

## Step 4 — Run it

### 🐧 Linux / 🍎 macOS — one command

```bash
./dev.sh
```

This installs everything (first run takes a minute), starts the backend and
frontend together, and prints the link. To stop, press **Ctrl+C**.

> If you get "permission denied", run `chmod +x dev.sh` once, then `./dev.sh`
> again (or just run `bash dev.sh`).

### 🪟 Windows — two terminals

`dev.sh` is a Mac/Linux script, so on Windows run the two halves yourself.

**PowerShell window 1 — backend:**

```powershell
cd backend
uv sync
$env:DEV_MODE = "1"
# If you set up a proxy in Step 3, also run:
# $env:PROXY_URL = "http://username:password@host:port"
uv run uvicorn app.main:app --port 8400 --reload
```

**PowerShell window 2 — frontend:**

```powershell
cd frontend
pnpm install
pnpm dev
```

Stop each with **Ctrl+C**.

---

## Step 5 — Use it

Open **http://localhost:5173** in your browser.

1. Paste a shared Zepto product link (from the Zepto app's "Share" button).
2. Enter your pincode (or allow location access).
3. Pick a radius and search.

The first search in a new area is slow — the app maps every nearby dark store
once, then caches them, so later searches there are fast.

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| **"command not found: uv / pnpm"** | Close and reopen your terminal — the installers add to your PATH only in new sessions. |
| **Search fails / times out / "Zepto API may be down"** | You're not on an Indian IP, or your proxy is down. Add/refresh `PROXY_URL` (Step 3). |
| **"403 Forbidden" in the logs** | Your proxy's IP is blocked by Zepto. Use an Indian **sticky residential** session, or rotate to a fresh IP. |
| **Check if Zepto is reachable** | `cd backend && uv run python scripts/smoke_zepto.py` — prints `SMOKE OK` when it can reach Zepto (honors `PROXY_URL`). |
| **Port already in use (8400 or 5173)** | Stop whatever's using it, or close other copies of the app. |
| **Page is blank / won't load** | Make sure *both* terminals are running. Open the **5173** URL (the frontend), not 8400. |

---

## Running the tests (optional)

```bash
cd backend
uv run pytest                          # fast unit tests, no network
uv run python scripts/smoke_zepto.py   # live check against the real Zepto API
```
