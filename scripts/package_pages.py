from pathlib import Path
import zipfile
from build_pages import build, ROOT

output = build()
archive = ROOT / 'fales-pages.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    z.write(output / 'index.html', 'index.html')
print(f'Ready to upload: {archive}')
