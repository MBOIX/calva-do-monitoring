"""Lance les pages tests/*.test.html dans Chrome headless et rapporte leur bilan."""
import functools
import http.server
import os
import re
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_PAGES = [
    "tests/situation.test.html",
    "tests/vigieau.test.html",
    "tests/situation.integration.test.html",
    "tests/smoke.test.html",
]
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]
PAGE_TIMEOUT_MS = 15000
PROCESS_TIMEOUT_SECONDS = 60
# Laisse les tests asynchrones se terminer avant la sérialisation du DOM.
VIRTUAL_TIME_BUDGET_MS = 30000

RESULTS_PATTERN = re.compile(
    r'<pre[^>]*id="test-results"[^>]*>(.*?)</pre>', re.DOTALL
)
STATUS_PATTERN = re.compile(r'data-status="(pass|fail)"')


def find_chrome():
    """Retourne le chemin de Chrome ($CHROME_BIN d'abord) ou None."""
    configured = os.environ.get("CHROME_BIN")
    if configured:
        return configured if shutil.which(configured) else None
    for candidate in CHROME_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@contextmanager
def serve_repository():
    """Sert la racine du dépôt sur un port libre ; produit le port."""
    handler = functools.partial(_QuietHandler, directory=str(REPO_ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def dump_dom(chrome, url):
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--timeout={PAGE_TIMEOUT_MS}",
        f"--virtual-time-budget={VIRTUAL_TIME_BUDGET_MS}",
        "--dump-dom",
        url,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=PROCESS_TIMEOUT_SECONDS,
    )
    return completed.stdout


def parse_report(dom):
    """Retourne (statut, détail) ; statut vaut 'pass', 'fail' ou 'missing'."""
    results = RESULTS_PATTERN.search(dom)
    if not results:
        return "missing", "bilan #test-results introuvable"
    status = STATUS_PATTERN.search(dom[results.start():results.end()])
    if not status:
        return "missing", "attribut data-status absent"
    return status.group(1), results.group(1).strip()


def run_page(chrome, port, page):
    """Exécute une page ; retourne (statut, détail). Ne lève pas sur timeout."""
    url = f"http://127.0.0.1:{port}/{page}"
    try:
        dom = dump_dom(chrome, url)
    except subprocess.TimeoutExpired:
        return "missing", f"Chrome n'a pas terminé en {PROCESS_TIMEOUT_SECONDS} s"
    return parse_report(dom)


def run_pages(pages=None):
    """Retourne {page: (statut, détail)} ; lève RuntimeError sans Chrome."""
    chrome = find_chrome()
    if chrome is None:
        raise RuntimeError("Chrome introuvable (définir $CHROME_BIN)")
    with serve_repository() as port:
        return {page: run_page(chrome, port, page) for page in (pages or TEST_PAGES)}


def main():
    try:
        reports = run_pages()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 2
    for page, (status, detail) in reports.items():
        print(f"[{status.upper()}] {page}")
        if status != "pass":
            print(detail)
    return 0 if all(status == "pass" for status, _ in reports.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
