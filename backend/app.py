import asyncio
import json
import logging
import math
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import sys
import tempfile
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt
from backend.engine import ROOT, TYPES, catalog, circuits, public_task

DATA = Path(os.environ.get('FALES_DATA_DIR', ROOT / '.demo-work' / 'api')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'tasks.sqlite3'
TTL = 3600
CAPACITY = 1000
slots = asyncio.Semaphore(2)


def connection():
    con = sqlite3.connect(DB)
    con.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, created REAL, data TEXT, attempted INTEGER DEFAULT 0)')
    return con


def get_task(task_id, claim_analysis=False):
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT data, attempted FROM tasks WHERE id=? AND created>?', (task_id, time.time()-TTL)).fetchone()
        if not row:
            raise HTTPException(404, 'This task expired or does not exist. Generate a new task.')
        task = json.loads(row[0])
        if claim_analysis and task['type'] == 'analyze' and row[1]:
            raise HTTPException(409, 'Analysis is single-shot. Generate a new task for another prediction.')
        if claim_analysis:
            con.execute('UPDATE tasks SET attempted=1 WHERE id=?', (task_id,))
        return task, bool(row[1])


async def worker(payload, timeout):
    if not shutil.which('ngspice'):
        raise HTTPException(503, 'ngspice is unavailable. Install it on the server before running the demo.')
    try:
        await asyncio.wait_for(slots.acquire(), timeout=0.1)
    except TimeoutError:
        raise HTTPException(429, 'The simulator is busy. Please try again shortly.')
    proc = None
    try:
        with tempfile.TemporaryDirectory(prefix='simulation-', dir=DATA) as work:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, '-B', '-m', 'backend.worker', cwd=ROOT,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'FALES_WORK_ROOT': work},
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, start_new_session=True)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(json.dumps(payload).encode()), timeout)
            except (TimeoutError, asyncio.CancelledError):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()
                raise HTTPException(504, 'Simulation time limit reached. Try again or choose another circuit.')
            if proc.returncode:
                logging.error('Worker failed: %s', stderr.decode()[-2000:])
                raise HTTPException(502, 'The simulation worker failed. Please try again.')
            result = json.loads(stdout)
            if not result['ok']:
                logging.warning('Engine operation failed: %s', result['error'])
                raise HTTPException(422, 'The engine could not complete this operation. Try generating another task.')
            return result['result']
    finally:
        slots.release()


ALLOWED_ORIGINS = [v.strip().rstrip('/') for v in os.environ.get('FALES_ALLOWED_ORIGINS', '').split(',') if v.strip()]

app = FastAPI(title='Fales verification API', docs_url=None, redoc_url=None, openapi_url='/api/openapi.json')


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logging.exception('Unexpected API failure', exc_info=exc)
    return JSONResponse({'detail': 'The server could not complete the request. Please try again.'}, status_code=500)


@app.middleware('http')
async def boundaries(request: Request, call_next):
    if request.method == 'POST':
        # Check streamed size too; Content-Length is not trusted.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                return JSONResponse({'detail': 'Request body is too large.'}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


class Generate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    topology: str = Field(max_length=32)
    task_type: str = Field(max_length=16)


class TaskID(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str = Field(min_length=32, max_length=36)


class Evaluate(TaskID):
    parameters: dict[str, StrictFloat | StrictInt] = Field(max_length=32)


@app.get('/api/catalog')
def get_catalog():
    return {**catalog(), 'simulator_available': bool(shutil.which('ngspice'))}


@app.get('/api/health')
def health():
    available = bool(shutil.which('ngspice'))
    return JSONResponse({'status': 'ok' if available else 'unavailable', 'ngspice': available}, status_code=200 if available else 503)


@app.post('/api/generate')
async def make_task(body: Generate):
    if body.topology not in circuits.NAMES or body.task_type not in TYPES:
        raise HTTPException(422, 'Select a supported topology and task type.')
    task = await worker({'operation': 'generate', **body.model_dump()}, 90)
    task_id = str(uuid.uuid4())
    with connection() as con:
        con.execute('DELETE FROM tasks WHERE created<?', (time.time()-TTL,))
        count = con.execute('SELECT count(*) FROM tasks').fetchone()[0]
        if count >= CAPACITY:
            raise HTTPException(503, 'Task capacity reached. Please try again later.')
        con.execute('INSERT INTO tasks(id,created,data) VALUES(?,?,?)', (task_id, time.time(), json.dumps(task)))
    return public_task(task, task_id)


@app.post('/api/evaluate')
async def evaluate(body: Evaluate):
    if any(not math.isfinite(v) for v in body.parameters.values()):
        raise HTTPException(422, 'All values must be finite numbers.')
    task, _ = get_task(body.task_id)
    if task['type'] == 'analyze':
        names = set(circuits.get(task['circuit']).metric_names)
        if set(body.parameters) != names or any(v <= 0 for v in body.parameters.values()):
            raise HTTPException(422, 'Provide one positive numeric prediction for every metric.')
    task, _ = get_task(body.task_id, claim_analysis=True)
    try:
        return await worker({'operation': 'evaluate', 'task': task, 'parameters': body.parameters},
                            circuits.get(task['circuit']).timeout + 5)
    except HTTPException:
        if task['type'] == 'analyze':
            with connection() as con:
                con.execute('UPDATE tasks SET attempted=0 WHERE id=?', (body.task_id,))
        raise


@app.post('/api/reference-solution')
def reference(body: TaskID):
    task, attempted = get_task(body.task_id)
    if task['type'] == 'analyze' and not attempted:
        raise HTTPException(409, 'Submit your prediction before revealing the measured answer.')
    return {'parameters': task.get('reference', task.get('measured')), 'kind': task['type']}


@app.get('/')
def index():
    return FileResponse(ROOT / 'web' / 'index.html')


app.mount('/assets', StaticFiles(directory=ROOT / 'web'), name='assets')

# Outermost CORS middleware also covers error responses from the API boundary.
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=['GET', 'POST'], allow_headers=['Content-Type'], allow_credentials=False)
