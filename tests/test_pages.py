import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_pages', ROOT/'scripts/build_pages.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class StaticPages(unittest.TestCase):
    def test_subpath_assets_and_no_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=builder.build(Path(tmp)/'repository',api_origin='')
            self.assertEqual({str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()},
                {'index.html','.nojekyll'})
            html=(root/'index.html').read_text()
            self.assertNotIn('="/assets/',html)
            self.assertNotIn('href="/"',html)
            self.assertNotIn('./assets/',html)
            self.assertNotIn('import.meta',html)
            self.assertIn('<style>',html)
            self.assertIn('data:image/svg+xml,',html)
            config=json.loads(html.split('const config = ',1)[1].split(';\n',1)[0])
            self.assertEqual(config['mode'],'pages')
            self.assertEqual(config['apiOrigin'],'')
            self.assertEqual(len(config['catalog']['topologies']),10)

    def test_api_origin_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=builder.build(tmp,api_origin='https://api.example.com/')
            self.assertIn('"apiOrigin": "https://api.example.com"',(root/'index.html').read_text())
            for value in ['http://api.example.com','https://api.example.com/api','https://u:p@api.example.com','https://api.example.com/?secret=x']:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    builder.build(tmp,api_origin=value)
