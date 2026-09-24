"""Read-only integration with the byte-identical Fales engine snapshot."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'vendor' / 'fales'))
from env import circuits, core
# Configure output location before importing the generator, which binds WORK_ROOT.
core.WORK_ROOT = os.environ.get('FALES_WORK_ROOT', str(ROOT / '.demo-work' / 'engine'))
from env import generate

LABELS = {'diffamp': 'Differential amplifier', 'ota': 'Miller OTA',
          'bandgap': 'Bandgap reference', 'ldo': 'LDO regulator',
          'comparator': 'Comparator', 'lna': 'Low-noise amplifier',
          'buffer': 'Analog buffer', 'vco': 'Ring oscillator',
          'buck': 'Buck converter', 'mod1': 'Delta-sigma modulator'}
TYPES = {'size': 'Synthesis', 'debug': 'Repair / Debug', 'analyze': 'Analysis'}


def parameter_unit(c, name):
    # Units follow the actual placeholder's use in the engine's SPICE skeleton.
    escaped = re.escape(name)
    if re.search(r'(?:W|L)=\{' + escaped + r'\}', c.skeleton):
        return 'm'
    if re.search(r'area=\{' + escaped + r'\}', c.skeleton):
        return '×'
    if name == 'Ton':
        return 's'
    if name == 'Ron':
        return 'Ω'
    if name == 'Gm':
        return 'S'
    if name == 'Ain':
        return 'V'
    for line in c.skeleton.splitlines():
        if '{' + name + '}' in line:
            unit = {'R': 'Ω', 'C': 'F', 'I': 'A', 'V': 'V', 'L': 'H', 'E': 'V'}.get(line[0])
            if unit:
                return unit
    raise ValueError(f'No verified unit for {c.name}/{name}')


def metric_meta(m):
    return dict(name=m.name, label=m.label, unit=m.unit, direction=m.direction,
                tolerance=m.tol, sanity=list(m.sanity))


def public_task(task, task_id):
    c = circuits.get(task['circuit'])
    analysis = task['type'] == 'analyze'
    initial = task.get('broken_params', task.get('params', c.reference))
    return dict(id=task_id, topology=c.name, title=LABELS[c.name], task_type=task['type'],
                targets=task.get('targets'), metrics=[metric_meta(m) for m in c.metrics],
                parameters=[dict(name=n, unit=parameter_unit(c, n), bounds=list(c.bounds[n]),
                                 value=initial[n]) for n in c.param_names],
                initial_measured=task.get('broken_measured'), hint=c.hint,
                skeleton=c.render_skeleton(initial) if analysis else c.skeleton,
                models=c.models_block, fingerprint=c.fingerprint,
                reference_available=True, generation_profile='interactive / no random-search filter')


def catalog():
    return dict(topologies=[dict(id=c.name, label=LABELS[c.name], title=c.title,
                                summary=c.summary, parameters=len(c.param_names),
                                metrics=len(c.metrics), timeout=c.timeout)
                            for c in circuits.CIRCUITS.values()],
                task_types=[dict(id=k, label=v) for k,v in TYPES.items()],
                metric_count=len({m.name for c in circuits.CIRCUITS.values() for m in c.metrics}),
                combinations=len(circuits.NAMES)*len(generate.MAKERS))
