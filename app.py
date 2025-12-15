from flask import Flask, request, render_template_string, Response
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin, urlparse
import os
import re

app = Flask(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

TIMEOUT = 15


# ---------- Core scraping logic ----------

def fetch_soup(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def resolve_latest_page(stream_url):
    """
    Given https://gocomics.com/pearlsbeforeswine
    return https://gocomics.com/pearlsbeforeswine/YYYY/MM/DD
    """
    soup = fetch_soup(stream_url)

    # Look for the canonical dated link
    for a in soup.find_all("a", href=True):
        if re.search(r"/\d{4}/\d{2}/\d{2}$", a["href"]):
            return urljoin(stream_url, a["href"])

    # Fallback: sometimes stream redirects to latest
    return stream_url


def extract_image(soup):
    # Prefer og:image
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content"):
        return meta["content"]

    # Fallback: scan images
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "assets.amuniversal.com" in src:
            return src

    raise ValueError("Comic image not found")


def extract_prev_next(soup, base_url):
    prev = next_ = None

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        if text == "previous":
            prev = urljoin(base_url, a["href"])
        elif text == "next":
            next_ = urljoin(base_url, a["href"])

    return prev, next_


def parse_comic_page(url):
    soup = fetch_soup(url)
    image = extract_image(soup)
    prev_url, next_url = extract_prev_next(soup, url)
    return image, prev_url, next_url


# ---------- Web UI ----------

HTML = """
<!doctype html>
<html>
<head>
  <title>GoComics Viewer</title>
  <style>
    body { font-family: sans-serif; max-width: 1000px; margin: 20px auto; }
    img { max-width: 100%; border: 1px solid #ccc; }
    .bar { margin: 12px 0; }
    a, button { padding: 8px 12px; margin-right: 6px; }
  </style>
</head>
<body>

<h2>GoComics Viewer</h2>

<form method="get">
  <input type="text" name="url" size="60"
         placeholder="https://www.gocomics.com/pearlsbeforeswine"
         value="{{ start_url or '' }}">
  <button type="submit">Load</button>
</form>

{% if error %}
  <p style="color:red">{{ error }}</p>
{% endif %}

{% if image %}
  <div class="bar">
    {% if prev_url %}
      <a href="/?url={{ prev_url }}">⬅ Previous</a>
    {% endif %}
    {% if next_url %}
      <a href="/?url={{ next_url }}">Next ➡</a>
    {% endif %}
    <a href="/download?img={{ image }}">Download</a>
  </div>

  <img src="{{ image }}">
{% endif %}

</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    start_url = request.args.get("url")

    if not start_url:
        return render_template_string(HTML)

    try:
        # Step 1: resolve stream → latest page
        if re.search(r"/\d{4}/\d{2}/\d{2}$", start_url):
            page_url = start_url
        else:
            page_url = resolve_latest_page(start_url)

        # Step 2: parse dated page
        image, prev_url, next_url = parse_comic_page(page_url)

        return render_template_string(
            HTML,
            start_url=start_url,
            image=image,
            prev_url=prev_url,
            next_url=next_url
        )

    except Exception as e:
        return render_template_string(HTML, error=str(e), start_url=start_url)


@app.route("/download")
def download():
    img_url = request.args.get("img")
    r = requests.get(img_url, headers=HEADERS, stream=True)
    r.raise_for_status()

    filename = os.path.basename(urlparse(img_url).path) or "comic.png"

    return Response(
        r.iter_content(65536),
        headers={
            "Content-Type": r.headers.get("Content-Type"),
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


if __name__ == "__main__":
    app.run(debug=True)