"""Integration tests use actual ngspice; only failure injection is mocked."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

_tmp = tempfile.TemporaryDirectory()
os.environ['FALES_DATA_DIR'] = _tmp.name
from fastapi.testclient import TestClient
from backend.app import app, worker
from fastapi import HTTPException
from backend.engine import ROOT, core, circuits


class DemoIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def generate(self, topology='diffamp', task_type='size'):
        r = self.client.post('/api/generate', json={'topology':topology,'task_type':task_type})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def evaluate(self, task, params):
        return self.client.post('/api/evaluate',json={'task_id':task['id'],'parameters':params})

    def test_reference_and_failure(self):
        t = self.generate(task_type='debug')
        self.assertNotIn('reference',t)
        broken = {p['name']:p['value'] for p in t['parameters']}
        failed = self.evaluate(t,broken).json()
        self.assertFalse(failed['solved'])
        ref = self.client.post('/api/reference-solution',json={'task_id':t['id']}).json()['parameters']
        passed = self.evaluate(t,ref).json()
        self.assertTrue(passed['solved'],passed)
        self.assertEqual(passed['reward'],1.5)
        self.assertTrue(all(m['passed'] for m in passed['comparisons']))
        self.assertGreater(passed['simulation_ms'],0)
        self.assertEqual(core.reward(passed['measured'],t['targets'],t['topology'])[0],passed['reward'])
        other=self.generate()
        self.assertNotEqual(t['targets'],other['targets'])
        illegal=self.evaluate(t,{**ref,'W1':-1}).json()
        self.assertEqual(illegal['reward'],0)
        self.assertFalse(illegal['legality']['valid'])
        self.assertIsNone(illegal['simulation_ms'])
        self.assertIsNone(illegal['measured'])
        injection=self.evaluate(t,{**ref,'netlist':1}).json()
        self.assertFalse(injection['legality']['valid'])
        self.assertEqual(self.evaluate(t,{**ref,'W1':'1u; quit'}).status_code,422)
        self.assertEqual(self.evaluate(t,{**ref,'W1':True}).status_code,422)

    def test_analysis_is_single_shot_and_secret(self):
        t=self.generate(task_type='analyze')
        self.assertNotIn('measured',t)
        self.assertEqual(self.client.post('/api/reference-solution',json={'task_id':t['id']}).status_code,409)
        predictions={m['name']:1.0 for m in t['metrics']}
        r=self.evaluate(t,predictions).json()
        self.assertIsNone(r['simulation_ms'])
        self.assertEqual(self.evaluate(t,predictions).status_code,409)
        ref=self.client.post('/api/reference-solution',json={'task_id':t['id']}).json()['parameters']
        self.assertEqual(r['reward'],core.evaluate_analyze(predictions,ref)['reward'])

    def test_equal_metric_and_all_topologies(self):
        c=self.client.get('/api/catalog').json()
        self.assertEqual(len(c['topologies']),10)
        self.assertEqual(len(c['task_types']),3)
        for topology in c['topologies']:
            with self.subTest(topology=topology['id']):
                t=self.generate(topology['id'])
                ref=self.client.post('/api/reference-solution',json={'task_id':t['id']}).json()['parameters']
                r=self.evaluate(t,ref).json()
                self.assertTrue(r['solved'],r)
                self.assertEqual(r['reward'],1.5)

    def test_boundary_and_health(self):
        self.assertEqual(self.client.get('/api/health').status_code,200)
        self.assertEqual(self.client.post('/api/generate',json={'topology':'../../etc','task_type':'size'}).status_code,422)
        self.assertEqual(self.client.post('/api/evaluate',json={'task_id':'x'*36,'parameters':{}}).status_code,404)
        self.assertEqual(self.client.post('/api/generate',content='x'*17000).status_code,413)
        self.assertEqual(self.client.get('/assets/../backend/app.py').status_code,404)
        with patch('backend.app.shutil.which',return_value=None):
            self.assertEqual(self.client.get('/api/health').status_code,503)
            self.assertEqual(self.client.post('/api/generate',json={'topology':'ota','task_type':'size'}).status_code,503)

    def test_operation_timeout(self):
        async def check():
            with self.assertRaises(HTTPException) as caught:
                await worker({'operation':'generate','topology':'mod1','task_type':'size'},0.001)
            self.assertEqual(caught.exception.status_code,504)
            # A timed-out operation releases its capacity and its temporary files.
            result=await worker({'operation':'generate','topology':'diffamp','task_type':'size'},90)
            self.assertEqual(result['type'],'size')
        asyncio.run(check())
        self.assertFalse(list(Path(_tmp.name).glob('simulation-*')))

    def test_unchanged_engine_snapshot(self):
        manifest=json.loads((ROOT/'vendor/fales/SOURCE.json').read_text())
        for name,digest in manifest.items():
            self.assertEqual(hashlib.sha256((ROOT/'vendor/fales'/name).read_bytes()).hexdigest(),digest,name)

if __name__=='__main__':
    unittest.main()
