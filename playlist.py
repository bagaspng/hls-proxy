"""
playlist.py — Fetches and rewrites HLS playlists from the CDN.

Fungsi:
- Fetch playlist .m3u8 dari CDN.
- Rewrite key ke /key.
- Rewrite segment ke /segment.
- Rewrite nested playlist ke /playlist.
- Mendukung URL absolute dan relative.
"""

import re
import time
import logging
import urllib.parse
from flask import Response
from curl_cffi import requests
from config import REFERER, STREAM_URL

logger = logging.getLogger("hls_proxy")


def make_absolute_url(base_url: str, target_url: str) -> str:
    return urllib.parse.urljoin(base_url, target_url)


def make_local_url(
    original_url: str,
    base_url: str,
    endpoint: str,
    referer: str | None = None,
) -> str:
    absolute_url = make_absolute_url(base_url, original_url)
    encoded_url = urllib.parse.quote(absolute_url, safe="")
    local_url = f"{endpoint}?url={encoded_url}"

    if referer:
        local_url += "&referer=" + urllib.parse.quote(referer, safe="")

    return local_url


def rewrite_uri_attribute(
    line: str,
    base_url: str,
    endpoint: str,
    referer: str | None = None,
) -> str:
    match = re.search(r'URI="([^"]+)"', line)

    if not match:
        return line

    original_url = match.group(1)
    local_url = make_local_url(original_url, base_url, endpoint, referer)

    return line.replace(f'URI="{original_url}"', f'URI="{local_url}"')


def is_playlist_url(url: str) -> bool:
    clean_url = url.split("?")[0].lower()
    return clean_url.endswith(".m3u8")


def rewrite_playlist(content: str, base_url: str, referer: str | None = None) -> str:
    lines = content.splitlines()
    result = []

    next_line_is_variant_playlist = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            result.append(line)
            continue

        if stripped.startswith("#EXT-X-KEY:"):
            result.append(
                rewrite_uri_attribute(
                    line=line,
                    base_url=base_url,
                    endpoint="/key",
                    referer=referer,
                )
            )
            continue

        if stripped.startswith("#EXT-X-SESSION-KEY:"):
            result.append(
                rewrite_uri_attribute(
                    line=line,
                    base_url=base_url,
                    endpoint="/key",
                    referer=referer,
                )
            )
            continue

        if stripped.startswith("#EXT-X-MAP:"):
            result.append(
                rewrite_uri_attribute(
                    line=line,
                    base_url=base_url,
                    endpoint="/segment",
                    referer=referer,
                )
            )
            continue

        if stripped.startswith("#EXT-X-MEDIA:"):
            result.append(
                rewrite_uri_attribute(
                    line=line,
                    base_url=base_url,
                    endpoint="/playlist",
                    referer=referer,
                )
            )
            continue

        if stripped.startswith("#EXT-X-I-FRAME-STREAM-INF:"):
            result.append(
                rewrite_uri_attribute(
                    line=line,
                    base_url=base_url,
                    endpoint="/playlist",
                    referer=referer,
                )
            )
            continue

        if stripped.startswith("#EXT-X-STREAM-INF:"):
            next_line_is_variant_playlist = True
            result.append(line)
            continue

        if stripped.startswith("#"):
            result.append(line)
            continue

        if next_line_is_variant_playlist or is_playlist_url(stripped):
            result.append(
                make_local_url(
                    original_url=stripped,
                    base_url=base_url,
                    endpoint="/playlist",
                    referer=referer,
                )
            )
            next_line_is_variant_playlist = False
            continue

        result.append(
            make_local_url(
                original_url=stripped,
                base_url=base_url,
                endpoint="/segment",
                referer=referer,
            )
        )

    return "\n".join(result) + "\n"


def get_playlist_response(
    source_url: str | None = None,
    referer: str | None = None,
) -> Response:
    start_time = time.time()

    if not source_url:
        source_url = STREAM_URL

    # Referer dari query dipakai bila ada; jika tidak, pakai default config.py.
    effective_referer = referer or REFERER

    try:
        response = requests.get(
            source_url,
            headers={
                "Referer": effective_referer,
                "Accept": "*/*",
                "Accept-Encoding": "identity",
            },
            impersonate="chrome",
            timeout=30,
        )

        duration = time.time() - start_time

        logger.info(
            f"PLAYLIST {response.status_code} | "
            f"{duration:.2f}s | "
            f"{source_url.split('/')[-1]}"
        )

        if response.status_code != 200:
            return Response(
                f"CDN playlist error {response.status_code}: {response.text[:300]}",
                status=response.status_code,
                headers={
                    "Content-Type": "text/plain",
                    "Cache-Control": "no-store",
                },
            )

        content = response.text

        if content.lstrip().lower().startswith("<html"):
            return Response(
                "Upstream returned HTML instead of HLS playlist",
                status=502,
                headers={
                    "Content-Type": "text/plain",
                    "Cache-Control": "no-store",
                },
            )

        rewritten = rewrite_playlist(
            content=content,
            base_url=source_url,
            referer=referer,
        )

        return Response(
            rewritten,
            status=200,
            headers={
                "Content-Type": "application/vnd.apple.mpegurl",
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    except Exception as e:
        duration = time.time() - start_time

        logger.error(
            f"PLAYLIST FAIL | "
            f"{duration:.2f}s | "
            f"{e} | "
            f"{source_url}"
        )

        return Response(
            f"Playlist error: {e}",
            status=502,
            headers={
                "Content-Type": "text/plain",
                "Cache-Control": "no-store",
            },
        )