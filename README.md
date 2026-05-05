# gopro-api

[![PyPI version](https://img.shields.io/pypi/v/gopro-api)](https://pypi.org/project/gopro-api/)
[![Python versions](https://img.shields.io/pypi/pyversions/gopro-api)](https://pypi.org/project/gopro-api/)
[![License](https://img.shields.io/github/license/himewel/gopro-api)](LICENSE)
[![CI](https://github.com/himewel/gopro-api/actions/workflows/ci.yml/badge.svg)](https://github.com/himewel/gopro-api/actions/workflows/ci.yml)
[![Release](https://github.com/himewel/gopro-api/actions/workflows/release.yml/badge.svg)](https://github.com/himewel/gopro-api/actions/workflows/release.yml)
[![Docs](https://img.shields.io/badge/docs-MkDocs-blue)](https://himewel.github.io/gopro-api/)

Unofficial Python client for the **GoPro cloud / Quik** HTTP API at [`api.gopro.com`](https://api.gopro.com): **search** your library and **fetch download metadata** (CDN URLs, filenames, variants). Built with **Pydantic** models, plus **sync** (`requests`) and **async** (`aiohttp`) clients and a small **`gopro-api`** CLI.

This project is not affiliated with or endorsed by GoPro.

## Features

- **`GoProAPI`** — synchronous client (`requests`), `with` context manager  
- **`AsyncGoProAPI`** — async client (`aiohttp`), `async with` context manager  
- **Pydantic** request/response types in `gopro_api.api.models`  
- **CLI** — `gopro-api search`, `gopro-api info`, `gopro-api pull`  
- **`GP_ACCESS_TOKEN`** from environment / `.env` (browser cookie value)

## Requirements

- Python **3.10+**
- **`GP_ACCESS_TOKEN`** — see [Configuration](#configuration)

## Install

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

From a local wheel (name matches your build):

```bash
pip install ./dist/gopro_api-*-py3-none-any.whl
```

Published package on PyPI (distribution name **`gopro-api`**, import **`gopro_api`**):

```bash
pip install gopro-api
```

## CLI

After install, **`gopro-api`** is on your `PATH`:

```bash
gopro-api --help
gopro-api --version
gopro-api search --start 2026-03-01 --end 2026-03-03 --per-page 30
gopro-api search --start 2026-03-01 --end 2026-03-03 --all-pages
gopro-api search --start 2026-03-01 --end 2026-03-03 --json
gopro-api info MEDIA_ID
gopro-api info MEDIA_ID --json
gopro-api pull MEDIA_ID ./downloads
gopro-api pull MEDIA_ID ./downloads --height 1080
gopro-api pull MEDIA_ID ./downloads --width 1920 --height 1080
```

| Command | Purpose |
|--------|---------|
| **`search`** | List media in a capture range. Default: a **`# _pages`** summary line, a tab-separated header (`id`, `type`, `captured_at`, `filename`, …; not `gopro_user_id` / `source_gumi` / `source_mgumi`), then one row per item (other API fields in an **`extra`** JSON column). **`--json`**: full API-shaped response; with **`--all-pages`**, a JSON array of every page. |
| **`info`** | Show download metadata for one media id (filename + file lines with size and URL), or **`--json`** for the full payload. |
| **`pull`** | Download asset(s) for a media id into **`destination`** (directory; created if missing). Videos (`.mp4` extension, case-insensitive): one **`variations`** entry — **tallest** by default, or closest to **`--height`** / **`--width`** (sum of squared pixel deltas; ties broken by larger resolution). Photos: uses **`files`** (one request per file). |

Global **`--timeout`** (seconds, default **`60`**) applies to API calls and to **`pull`** CDN downloads (`requests.get`).

Run without an installed script:

```bash
python -m gopro_api.cli search --start 2026-03-01 --end 2026-03-02
python -m gopro_api.cli info MEDIA_ID
python -m gopro_api.cli pull MEDIA_ID ./out
python -m gopro_api.cli pull MEDIA_ID ./out --height 720
```

## Configuration

`gopro_api.config` reads settings from the environment and from a `.env` file in the current working directory via **pydantic-settings**. The only required setting is **`GP_ACCESS_TOKEN`**.

Example `.env`:

```env
GP_ACCESS_TOKEN=your_token_here
```

The clients send it as a cookie: `gp_access_token=<value>`. Put **only the token string** in `GP_ACCESS_TOKEN` (not the `gp_access_token=` prefix).

You can override the token in code: `GoProAPI(access_token="...")` or `AsyncGoProAPI(access_token="...")`.

### Retrieving `gp_access_token` from your browser

Sign in to the GoPro web app (e.g. [gopro.com](https://gopro.com) media / Quik). The site sets a cookie **`gp_access_token`**.

**Chrome / Edge / Brave**

1. Open the site while logged in.  
2. **F12** → **Application** → **Cookies** → choose the origin (often `https://quik.gopro.com` or another `*.gopro.com` host).  
3. Copy the **Value** of **`gp_access_token`**.

**Firefox**

**F12** → **Storage** → **Cookies** → same idea.

**Network panel (Chromium)**

1. **Network** → trigger requests to **`api.gopro.com`**.  
2. Pick a request → **Headers** → **Cookie**.  
3. Copy the value after `gp_access_token=` up to the next `;` (or end of string).

**Notes**

- If the cookie is **HttpOnly**, use the **Network** method.  
- Tokens **expire**; refresh from the browser if you get **401**.  
- Treat the token like a password.

**Security:** Do not commit `.env` or tokens. Keep `.env` in `.gitignore`.

## Library usage

### Async (`AsyncGoProAPI`)

```python
import asyncio
from datetime import datetime

from gopro_api.api import AsyncGoProAPI
from gopro_api.api.models import CapturedRange, GoProMediaSearchParams


async def main() -> None:
    params = GoProMediaSearchParams(
        captured_range=CapturedRange(
            start=datetime.fromisoformat("2026-03-01"),
            end=datetime.fromisoformat("2026-03-02"),
        ),
        per_page=50,
        page=1,
    )

    async with AsyncGoProAPI() as api:
        search = await api.search(params)
        for item in search.embedded.media:
            meta = await api.download(item.id)
            print(meta.filename, len(meta.embedded.files), "files")


if __name__ == "__main__":
    asyncio.run(main())
```

### Sync (`GoProAPI`)

```python
from datetime import datetime

from gopro_api.api import GoProAPI
from gopro_api.api.models import CapturedRange, GoProMediaSearchParams


def main() -> None:
    params = GoProMediaSearchParams(
        captured_range=CapturedRange(
            start=datetime.fromisoformat("2026-03-01"),
            end=datetime.fromisoformat("2026-03-02"),
        ),
        per_page=50,
        page=1,
    )

    with GoProAPI() as api:
        search = api.search(params)
        for item in search.embedded.media:
            meta = api.download(item.id)
            print(meta.filename, len(meta.embedded.files), "files")


if __name__ == "__main__":
    main()
```

### Models

- **Requests:** `GoProMediaSearchParams`, `CapturedRange`, etc. in **`gopro_api.api.models`**.  
- **Responses:** search and download JSON shapes (including `_embedded` / `_pages` aliases).

List fields in search params are serialized to comma-separated strings when you call **`model_dump()`** (used by the HTTP clients).

## Project layout

| Path | Role |
|------|------|
| `gopro_api/api/gopro.py` | `GoProAPI` — sync `search`, `download` |
| `gopro_api/api/async_gopro.py` | `AsyncGoProAPI` — async `search`, `download` |
| `gopro_api/api/models.py` | Pydantic request/response models |
| `gopro_api/api/__init__.py` | Re-exports `GoProAPI`, `AsyncGoProAPI` |
| `gopro_api/config.py` | pydantic-settings `Settings`, `GP_ACCESS_TOKEN` |
| `gopro_api/cli.py` | `gopro-api` CLI |
| `setup.py` | Package metadata, dependencies, console entry point |

## CI and releases

[`.github/workflows/release.yml`](.github/workflows/release.yml):

- **Push to `main`** — builds wheel + source `.zip`, uploads **workflow artifacts**.  
- **Push tag `v*`** (e.g. `v0.0.5`) — attaches the same files to a **GitHub Release**.

## License

[MIT License](LICENSE).

GoPro, Quik, and related marks are trademarks of their respective owners.
