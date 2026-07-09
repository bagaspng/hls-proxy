"""
app.py — Flask application with HLS proxy routes.

Routes:
    /          — Halaman player hls.js (buka ini di browser)
    /playlist  — Fetch, rewrite, and serve .m3u8 playlist
    /segment   — Proxy video segment
    /key       — Proxy decryption key
"""

import os
from flask import Flask, request, Response
from playlist import get_playlist_response
from proxy import proxy_request

app = Flask(__name__)

PLAYER_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player.html")
EMBED_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "embed.html")


@app.route("/")
def index():
    with open(PLAYER_HTML_PATH, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


@app.route("/embed")
def embed():
    with open(EMBED_HTML_PATH, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Range, Content-Type, Origin, Accept, User-Agent, Cache-Control, Pragma"
    )
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Expose-Headers"] = (
        "Content-Length, Content-Range, Accept-Ranges, Content-Type"
    )
    return response


@app.route("/playlist", methods=["GET", "OPTIONS"])
def playlist():
    if request.method == "OPTIONS":
        return Response(status=204)

    source_url = request.args.get("url")
    referer = request.args.get("referer")
    return get_playlist_response(source_url, referer)


@app.route("/segment", methods=["GET", "OPTIONS"])
def segment():
    if request.method == "OPTIONS":
        return Response(status=204)

    url = request.args.get("url")

    if not url:
        return Response(
            "Missing 'url' parameter",
            status=400,
            headers={
                "Content-Type": "text/plain",
                "Cache-Control": "no-store",
            },
        )

    return proxy_request(
        url=url,
        client_headers=request.headers,
        kind="segment",
        referer=request.args.get("referer"),
    )


@app.route("/key", methods=["GET", "OPTIONS"])
def key():
    if request.method == "OPTIONS":
        return Response(status=204)

    url = request.args.get("url")

    if not url:
        return Response(
            "Missing 'url' parameter",
            status=400,
            headers={
                "Content-Type": "text/plain",
                "Cache-Control": "no-store",
            },
        )

    return proxy_request(
        url=url,
        client_headers=request.headers,
        kind="key",
        referer=request.args.get("referer"),
    )