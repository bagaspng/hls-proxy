# HLS Proxy (Flask Implementation)

An educational reverse-proxy server implemented in Flask to bypass anti-scraping,
referrer validation, and Cloudflare protection (using `curl_cffi`) for HTTP Live
Streaming (HLS) content, plus a built-in hls.js player.

## Project Structure

```text
hls/
├── app.py            # Flask routes: / (player), /playlist, /segment, /key
├── main.py           # Entry point — configures logging and starts the server
├── config.py         # Stream source URL, Referer, host/port
├── playlist.py       # .m3u8 downloader and URL rewriter
├── proxy.py          # Segment/key proxy with HTTP Range (206) support
├── player.html       # Built-in hls.js player page (served at /)
├── static/
│   └── hls.min.js    # hls.js 1.5.17, served locally (no CDN needed)
├── logs/proxy.log    # Rotating request log
├── requirements.txt  # flask, curl-cffi
└── README.md
```

## How It Works (Request Flow)

```text
  Browser (player.html + hls.js)          Flask Proxy                 Upstream CDN (Vault)
         │                                     │                              │
         │──── GET /  ────────────────────────>│  (serves player.html)        │
         │──── GET /static/hls.min.js ────────>│  (serves hls.js locally)     │
         │                                     │                              │
         │──── GET /playlist ─────────────────>│──── GET uwu.m3u8 ───────────>│  Chrome TLS impersonation
         │                                     │<─── m3u8 ────────────────────│  Referer: kwik.cx
         │                                 [Rewriter]                         │
         │<─── rewritten m3u8 ─────────────────│  segment/key URLs -> local   │
         │                                     │                              │
         │──── GET /segment?url=... ──────────>│──── GET segment (+ Range) ──>│
         │       (Range: bytes=N-)             │<─── 206 Partial Content ─────│
         │<─── 206 + Content-Range ────────────│                              │
```

1. **Player (`GET /`)** — serves `player.html`, which loads hls.js from
   `/static/hls.min.js` and points it at `/playlist`. hls.js runs in the browser
   and handles decode, buffering, and **seeking**.

2. **Playlist (`GET /playlist`)** — `playlist.py` fetches the original `.m3u8`
   via `curl_cffi` (Chrome TLS fingerprint + `Referer`), then rewrites:
   * segment URLs → `/segment?url=...`
   * `#EXT-X-KEY` / `#EXT-X-MAP` → `/key?url=...` / `/segment?url=...`
   * nested playlists / media → `/playlist?url=...`

3. **Segment (`GET /segment`)** — fetches the segment from the CDN. If the browser
   sends a `Range` header it is **forwarded** to the CDN and the proxy replies with
   `206 Partial Content` + `Content-Range` (required for seeking); otherwise `200`.

4. **Key (`GET /key`)** — returns the AES-128 key (16 bytes) so the browser never
   talks to the CDN directly.

## Installation & Running

1. Create a virtualenv and install dependencies:
   ```bash
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

2. Set the stream in `config.py` (`STREAM_URL`, `REFERER`).

3. Start the server:
   ```bash
   ./venv/bin/python main.py
   ```

4. Open the **player** in your browser:
   ```text
   http://127.0.0.1:8000/
   ```

### Changing the stream without editing `config.py`

Pass the stream URL (and optionally a Referer) as query parameters — or just paste
them into the input boxes on the player page:

```text
http://127.0.0.1:8000/?url=<m3u8-url>
http://127.0.0.1:8000/?url=<m3u8-url>&referer=<referer-url>
```

* `url` — the source `.m3u8`. Empty → falls back to `STREAM_URL` in `config.py`.
* `referer` — Referer sent to the CDN. Empty → falls back to `REFERER` in `config.py`.

Both are threaded through the whole chain: the player loads `/playlist?url=…&referer=…`,
and the rewriter embeds the same `referer` into every `/segment` and `/key` URL so the
upstream fetch uses it too.

> **Note:** Open `/`, not `/playlist`. Chrome cannot play HLS natively, so opening
> the raw `.m3u8` in the address bar relies on an ad-hoc/extension player with
> unreliable seeking. The `/` page uses a known hls.js build that seeks correctly.
>
> **Recommended browser: Chrome** (hls.js + MSE) — seeking is reliable there.
> Safari is **not supported**: this content is AES-128 encrypted MPEG-TS, and
> Safari's media stack cannot seek it reliably through the proxy — its native HLS
> player buffers without settling on the seek point, and the hls.js MSE path throws
> `fragParsingError ("Found no media")`. The proxy itself is correct (bytes are
> byte-identical to the CDN and decrypt to valid TS with video+audio); the
> limitation is Safari-side. Supporting Safari would require remuxing TS → fMP4
> (CMAF) on the fly in the proxy.

## Stopping the Server

The server is a stateless Flask dev server — it only reads from the CDN and writes
to `logs/proxy.log`. It is safe to stop at any time (`Ctrl+C`, or kill the process);
nothing is corrupted and there is no state to clean up.
