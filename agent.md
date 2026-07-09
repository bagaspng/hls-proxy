# AGENTS.md

## Project

HLS Proxy Research & Implementation

---

# Objective

This project is an educational reverse engineering exercise.

The goal is to understand how an HLS streaming provider protects its playlist and media files, then implement an HLS proxy capable of fetching and serving the playlist correctly.

The focus is understanding the streaming flow, not bypassing security through exploits.

---

# Current Research Context

A JSON response provides multiple streams:

- HLS (.m3u8)
- Embed page (kwik.cx)

Example:

```json
{
  "streams": [
    {
      "url": "...uwu.m3u8",
      "type": "hls",
      "referer": "https://kwik.cx/"
    }
  ]
}
```

Direct access to

```
uwu.m3u8
```

returns

```
HTTP 403
Cloudflare
```

Adding

```
Referer: https://kwik.cx/
```

using curl returns

```
HTTP 200
```

The same request using Python requests currently returns

```
HTTP 403
```

Current hypothesis:

Cloudflare validates more than the Referer.

Possible factors include:

- TLS fingerprint
- JA3
- HTTP2 fingerprint
- Header ordering
- Browser fingerprint

This hypothesis still needs experimentation.

---

# Current Milestone

All Milestones (2-6) Completed!

Goal:

Create a fully functional HLS Proxy and Video Player Dashboard.

✓ Milestone 2: Fetch remote playlist with Referer bypass.
✓ Milestone 3: Rewrite remote keys and segments to local proxy URLs.
✓ Milestone 4: Proxy segment requests (.jpg) through local FastAPI endpoint.
✓ Milestone 5: Proxy key requests (.key) through local FastAPI endpoint.
✓ Milestone 6: Video player integration (HTML5 + Hls.js) with live traffic dashboard.

---

# Completed Milestones

✓ **Milestone 2**: Fetch remote playlist & bypass Cloudflare.
✓ **Milestone 3**: Parse and rewrite m3u8 playlist file to route segments/keys locally.
✓ **Milestone 4**: Implement local `/segment` endpoint to stream video files.
✓ **Milestone 5**: Implement local `/key` endpoint to serve AES-128 decryption keys.
✓ **Milestone 6**: Implement a web interface at `/` with an integrated video player and real-time logs.

---

# Engineering Principles

Never jump to implementation.

Always follow:

Observe

↓

Hypothesis

↓

Experiment

↓

Evidence

↓

Conclusion

Every change must be justified by experimental results.

Avoid assumptions.

---

# Current Findings

Confirmed:

✓ Direct playlist access returns HTTP 403.

✓ curl + Referer returns HTTP 200.

✓ Python requests + Referer returns HTTP 403.

✓ Python curl_cffi with `impersonate="chrome"` + Referer returns HTTP 200.

Findings:

- Cloudflare blocks standard Python `requests` library because of TLS/JA3/HTTP2 fingerprints.
- Impersonating a modern web browser (e.g. Chrome) using `curl_cffi` is required and fully bypasses the restriction.
- The decryption key `mon.key` and segment files (disguised as `.jpg` images) are also protected by the same Cloudflare rules and must be proxied with Chrome impersonation.

---

# Preferred Stack

Python

FastAPI

Async capable if necessary

Avoid unnecessary abstraction.

Readable code is preferred over complex architecture.

---

# Coding Style

Prefer simple functions.

Avoid overengineering.

Keep every milestone independently testable.

Each endpoint should solve exactly one problem.

---

# Debugging Rules

Always print

- request headers
- response status
- response headers
- response body (first 500 bytes)

Never replace useful errors with generic messages.

Good debugging information is more valuable than clean output during research.

---

# What AI Should Do

When suggesting code:

- explain the reasoning
- explain the protocol
- explain why a solution works
- prefer experiments over guesses
  explain it simply

The project is about learning the streaming protocol, not only making it work.

Always preserve milestone progression.

# json

{
"streams": [
{
"url": "https://vault-01.uwucdn.top/stream/01/09 b5513e71f8df5bcc7b513b1157137cc14fef15899f278daa032478d87e36e9a1/uwu.m3u8",
"type": "hls",
"quality": "1080p",
"resolution": {
"width": 1920,
"height": 1080
},
"codec": "h264",
"audio": "sub",
"fansub": "MTBB",
"isActive": false,
"referer": "https://kwik.cx/"
},
{
"url": "https://kwik.cx/e/GP0FfcyJfpRW",
"type": "embed",
"quality": "1080p",
"resolution": {
"width": 1920,
"height": 1080
},
"codec": "h264",
"audio": "sub",
"fansub": "MTBB",
"isActive": false,
"referer": "https://kwik.cx/"
},
{
"url": "https://vault-01.uwucdn.top/stream/01/12/22664c54020a4336a1f770e17277b7239fa0f47fed70eaec2fc4fba36b60b1eb/uwu.m3u8",
"type": "hls",
"quality": "720p",
"resolution": {
"width": 1280,
"height": 720
},
"codec": "h264",
"audio": "sub",
"fansub": "MTBB",
"isActive": true,
"referer": "https://kwik.cx/"
},
{
"url": "https://kwik.cx/e/HuhxhD13kZai",
"type": "embed",
"quality": "720p",
"resolution": {
"width": 1280,
"height": 720
},
"codec": "h264",
"audio": "sub",
"fansub": "MTBB",
"isActive": true,
"referer": "https://kwik.cx/"
}
],
"download": "https://pahe.win/ADuBU"
}
