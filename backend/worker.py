"""One isolated process per operation; only trusted templates reach ngspice."""
import json
import sys
import time
from backend.engine import circuits, core, generate


def run(data):
    if data['operation'] == 'generate':
        c = circuits.get(data['topology'])
        deadline = time.monotonic() + 80
        for _ in range(500):
            # The existing online generator, without benchmark difficulty filtering.
            task = generate.MAKERS[data['task_type']](c, None, 0)
            if task is not None:
                return task
            if time.monotonic() > deadline:
                break
        raise RuntimeError('No valid task was found in time. Try generating again or select another topology.')
    task, params = data['task'], data['parameters']
    c = circuits.get(task['circuit'])
    analysis = task['type'] == 'analyze'
    legal, reason = (True, '') if analysis else core.is_legal(params, c)
    start = time.perf_counter()
    result = core.evaluate_task(task, params)
    elapsed = (time.perf_counter() - start) * 1000
    measured = task['measured'] if analysis else result['measured']
    comparisons = []
    for m in c.metrics:
        value = measured.get(m.name) if measured else None
        if analysis:
            prediction = params.get(m.name)
            ratio = core._closeness(prediction, value)
            passed = ratio is not None and ratio >= core.ANALYZE_TOL
            target = prediction
        else:
            target = task['targets'][m.name]
            passed = value is not None and core.spec_score(m, value, target) >= 1
        comparisons.append(dict(name=m.name, target=target, value=value, passed=passed))
    if result.get('error') == 'simulation failed':
        result['error'] = 'ngspice produced no usable measurements (non-convergence, timeout, or simulator failure). Try another set of parameters.'
    return {**result, 'measured': measured, 'legality': {'valid': legal, 'reason': reason},
            'comparisons': comparisons, 'simulation_ms': None if analysis or not legal else round(elapsed, 1),
            'verification': 'generation-time ngspice measurements' if analysis else 'ngspice',
            'fingerprint': c.fingerprint}


if __name__ == '__main__':
    try:
        print(json.dumps({'ok': True, 'result': run(json.load(sys.stdin))}, allow_nan=False))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
