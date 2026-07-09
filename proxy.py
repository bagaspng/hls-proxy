"""
proxy.py — Stable HLS segment/key proxy.

Prinsip:
- Teruskan header Range dari browser ke CDN untuk segment.
- Balas 206 Partial Content bila CDN membalas 206 (wajib untuk seek).
- Balas 200 OK penuh bila browser tidak minta Range.
- Key selalu dibalas penuh (200).
- Jangan pakai shared Session.
"""

import time
import logging
import os
import hashlib
import threading
from flask import Response
from curl_cffi import requests
from config import REFERER

logger = logging.getLogger("hls_proxy")

UPSTREAM_TIMEOUT = 120

# Disk Cache Configuration for HLS segments
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_segments")
os.makedirs(CACHE_DIR, exist_ok=True)

# Lock and event mapping for request coalescing (Single Flight)
active_downloads = {}
active_downloads_lock = threading.Lock()


def parse_range(range_header: str, file_len: int) -> tuple[int, int]:
    """Parse range header (e.g. bytes=0- or bytes=1000-2000) and return start, end."""
    try:
        range_str = range_header.replace("bytes=", "").strip()
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_len - 1
        
        if start < 0:
            start = 0
        if end >= file_len:
            end = file_len - 1
        return start, end
    except Exception:
        return 0, file_len - 1


def get_cache_path(url: str) -> str:
    """Generate local filename for segment URL cache."""
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{url_hash}.dat")


def looks_like_html(body: bytes) -> bool:
    prefix = body[:500].lstrip().lower()

    return (
        prefix.startswith(b"<!doctype html")
        or prefix.startswith(b"<html")
        or b"<body" in prefix
        or b"</html>" in prefix
    )


def looks_like_real_jpeg(body: bytes) -> bool:
    """
    Mengecek JPEG asli dari magic bytes.

    Segment kamu memang berekstensi .jpg,
    tapi body-nya bukan JPEG asli.
    """
    return len(body) >= 3 and body[:3] == b"\xff\xd8\xff"


def normalize_content_type(url: str, upstream_type: str, kind: str) -> str:
    clean_url = url.split("?")[0].lower()
    clean_type = (upstream_type or "").split(";")[0].strip().lower()

    if kind == "key":
        return "application/octet-stream"

    if clean_url.endswith((".m4s", ".mp4", ".cmfv", ".cmfa")):
        return "video/mp4"

    if clean_url.endswith(".ts"):
        return "video/mp2t"

    if "segment-" in clean_url and clean_url.endswith(".jpg"):
        return "video/mp2t"

    if clean_type in (
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/html",
        "text/plain",
    ):
        return "video/mp2t"

    if clean_type:
        return clean_type

    return "application/octet-stream"


def build_upstream_headers(referer: str | None = None) -> dict:
    return {
        "Referer": referer or REFERER,
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    }


def make_response(
    body: bytes,
    content_type: str,
    status: int = 200,
    content_range: str | None = None,
) -> Response:
    headers = {
        "Content-Type": content_type,
        "Content-Length": str(len(body)),
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store, no-cache, must-revalidate, no-transform",
        "Pragma": "no-cache",
        "Expires": "0",
        "Access-Control-Allow-Origin": "*",
    }

    if content_range:
        headers["Content-Range"] = content_range

    return Response(
        body,
        status=status,
        headers=headers,
    )


def proxy_request(
    url: str,
    client_headers,
    kind: str = "segment",
    referer: str | None = None,
) -> Response:
    start_time = time.time()
    client_range = client_headers.get("Range")
    filename = url.split('/')[-1]

    try:
        # Hanya cache jenis segment. Key/Playlist tidak perlu di-cache di disk.
        if kind == "segment":
            cache_path = get_cache_path(url)
            body = None

            # 1. Cek cache disk terlebih dahulu
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "rb") as f:
                        body = f.read()
                    logger.info(f"CACHE HIT  | {len(body):>8} bytes | kind={kind} | {filename}")
                except Exception as e:
                    logger.warning(f"Failed to read cache for {filename}: {e}")

            # 2. Jika tidak ada di cache, gunakan Request Coalescing (Single Flight)
            if body is None:
                download_event = None
                is_first_downloader = False

                with active_downloads_lock:
                    if url in active_downloads:
                        download_event = active_downloads[url]
                    else:
                        download_event = threading.Event()
                        active_downloads[url] = download_event
                        is_first_downloader = True

                if not is_first_downloader:
                    logger.info(f"COALESCE   | Waiting for concurrent download of {filename}...")
                    # Tunggu thread pertama selesai mendownload (max 60 detik)
                    download_event.wait(timeout=60.0)

                    # Coba baca hasil download dari cache
                    if os.path.exists(cache_path):
                        try:
                            with open(cache_path, "rb") as f:
                                body = f.read()
                            logger.info(f"CACHE COAL | {len(body):>8} bytes | kind={kind} | {filename}")
                        except Exception as e:
                            logger.error(f"Failed to read coalesced cache for {filename}: {e}")

                if is_first_downloader:
                    try:
                        # Lakukan download dengan retry otomatis (hingga 3 kali) jika terjadi error jaringan/reset
                        response = None
                        last_err = None
                        for attempt in range(3):
                            try:
                                response = requests.get(
                                    url,
                                    headers=build_upstream_headers(referer),
                                    impersonate="chrome",
                                    timeout=UPSTREAM_TIMEOUT,
                                )
                                if response.status_code == 200:
                                    break
                                # Jika server/CDN rate limit atau error sementara, tunggu sebentar lalu retry
                                if response.status_code in (429, 500, 502, 503, 504):
                                    logger.warning(f"UPSTREAM ERR | Status {response.status_code} on attempt {attempt+1} for {filename}. Retrying...")
                                    time.sleep(1)
                                    continue
                            except Exception as e:
                                last_err = e
                                logger.warning(f"DOWNLOAD ERR | {e} on attempt {attempt+1} for {filename}. Retrying...")
                                time.sleep(1)

                        if response is None or response.status_code >= 400:
                            err_msg = f"CDN error {response.status_code if response else 'No Response'}"
                            if last_err:
                                err_msg += f" ({last_err})"
                            raise Exception(err_msg)

                        body = response.content
                        if not body:
                            raise Exception("Upstream returned empty body")

                        if looks_like_html(body):
                            raise Exception("Upstream returned HTML instead of media")

                        if looks_like_real_jpeg(body):
                            raise Exception("Upstream returned real JPEG instead of HLS segment")

                        temp_path = cache_path + ".tmp"
                        with open(temp_path, "wb") as f:
                            f.write(body)
                        os.replace(temp_path, cache_path)

                        duration = time.time() - start_time
                        logger.info(
                            f"CACHE MISS | {len(body):>8} bytes | {duration:.2f}s | kind={kind} | {filename}"
                        )

                    except Exception as e:
                        with active_downloads_lock:
                            if url in active_downloads:
                                del active_downloads[url]
                        download_event.set()
                        raise e
                    else:
                        with active_downloads_lock:
                            if url in active_downloads:
                                del active_downloads[url]
                        download_event.set()

            if body is not None:
                content_type = normalize_content_type(
                    url=url,
                    upstream_type="",
                    kind=kind,
                )
                body_len = len(body)

                if client_range:
                    start, end = parse_range(client_range, body_len)
                    sliced_body = body[start:end+1]
                    out_status = 206
                    out_range = f"bytes {start}-{end}/{body_len}"
                else:
                    sliced_body = body
                    out_status = 200
                    out_range = None

                logger.info(
                    f"PROXY      | {out_status} | {len(sliced_body):>8} bytes | kind={kind} | type={content_type} | range={out_range or '-'} | {filename}"
                )

                return make_response(
                    body=sliced_body,
                    content_type=content_type,
                    status=out_status,
                    content_range=out_range,
                )
            else:
                raise Exception("No data could be retrieved")

        else:
            response = requests.get(
                url,
                headers=build_upstream_headers(referer),
                impersonate="chrome",
                timeout=UPSTREAM_TIMEOUT,
            )
            duration = time.time() - start_time
            body = response.content
            upstream_type = response.headers.get("content-type", "")

            logger.info(
                f"UPSTREAM   | {response.status_code} | {len(body):>8} bytes | {duration:.2f}s | kind={kind} | type={upstream_type or '-'} | {filename}"
            )

            if response.status_code >= 400:
                return Response(
                    f"CDN error {response.status_code}",
                    status=response.status_code,
                    headers={"Content-Type": "text/plain", "Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
                )

            content_type = normalize_content_type(
                url=url,
                upstream_type=upstream_type,
                kind=kind,
            )

            logger.info(
                f"PROXY      | 200 | {len(body):>8} bytes | kind={kind} | type={content_type} | {filename}"
            )

            return make_response(
                body=body,
                content_type=content_type,
                status=200,
            )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"PROXY FAIL | {duration:.2f}s | kind={kind} | range={client_range or 'none'} | {e} | {url}")

        return Response(
            b"",
            status=502,
            headers={
                "Content-Type": "application/octet-stream",
                "Cache-Control": "no-store",
                "Access-Control-Allow-Origin": "*",
            },
        )