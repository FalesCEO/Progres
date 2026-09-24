"""Build a self-contained Pages artifact using only the Python standard library."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit, quote

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from backend.engine import catalog


def build(output=None, api_origin=None):
    destination = Path(output) if output else ROOT / 'dist'
    origin = (api_origin if api_origin is not None else os.environ.get('FALES_API_URL', '')).strip().rstrip('/')
    if origin:
        url = urlsplit(origin)
        if (url.scheme != 'https' or not url.hostname or url.path or url.query or url.fragment
                or url.username or url.password):
            raise ValueError('FALES_API_URL must be an HTTPS origin without /api, credentials, query or fragment.')
    destination.mkdir(parents=True, exist_ok=True)
    config = {'mode': 'pages', 'apiOrigin': origin, 'catalog': catalog()}
    html = (ROOT / 'web/index.html').read_text()
    css = (ROOT / 'web/style.css').read_text()
    helper = (ROOT / 'web/api-config.mjs').read_text().replace('export function ', 'function ')
    app = (ROOT / 'web/app.js').read_text()
    app = '\n'.join(line for line in app.splitlines() if not line.startswith('import '))
    app = app.replace("new URL('../', import.meta.url).pathname", "new URL('./', location.href).pathname")
    script = 'const config = ' + json.dumps(config, ensure_ascii=True) + ';\n' + helper + '\n' + app
    script = script.replace('</script', '<\\/script')
    icon = 'data:image/svg+xml,' + quote((ROOT / 'web/favicon.svg').read_text(), safe='')
    html = html.replace('href="./assets/favicon.svg"', 'href="' + icon + '"')
    html = html.replace('<link rel="stylesheet" href="./assets/style.css">', '<style>' + css + '</style>')
    html = html.replace('<script type="module" src="./assets/app.js"></script>', '')
    html = html.replace('</body>', '<script>\n' + script + '\n</script></body>')
    (destination / 'index.html').write_text(html)
    # Root file is also ready for the simplest main / (root) Pages publication.
    if output is None:
        (ROOT / 'index.html').write_text(html)
    (destination / '.nojekyll').touch()
    print(f'Pages artifact ready: {destination}')
    print('Simulator API: ' + (origin or 'not configured; the site will show connection setup'))
    return destination


if __name__ == '__main__':
    build()
