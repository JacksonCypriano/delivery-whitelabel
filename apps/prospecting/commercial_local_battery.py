"""Offline battery using immutable original cases and the operational local engine."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from .commercial_local import compose, HumanReview
from .commercial_local_knowledge import VERSION

CASES = Path(__file__).parent / 'fixtures' / 'commercial_battery07.json'


class MemoryRows(list):
    def order_by(self, key):
        return MemoryRows(sorted(self, key=lambda r: r[key.lstrip('-')], reverse=key.startswith('-')))

    def values(self, *keys):
        return MemoryRows({k: row[k] for k in keys} for row in self)


def conversation(case):
    return SimpleNamespace(messages=MemoryRows(
        dict(pk=i, text=text, reply='', from_me=False, created_at=datetime.now(timezone.utc))
        for i, text in enumerate(case['messages'].split(' | '), 1)))


def evaluate(case, publication, knowledge, links):
    trace = {}
    row = dict(case, outcome='', answer='', error='', sources=[], retry_at=0,
               manual_quality='pending', trace=trace, explanation='')
    try:
        row['answer'], row['sources'] = compose(conversation(case), publication, knowledge, links=links, trace=trace)
        row['outcome'] = 'answer'
    except HumanReview as exc:
        row.update(outcome='human', error=str(exc), explanation=exc.explanation)
    except ValueError:
        row.update(outcome='human', error='commercial_knowledge_review_required')
    except Exception:
        row.update(outcome='execution_error', error='unexpected_execution_error')
    row['outcome_compatible'] = (row['outcome'] == case['expectation'] or
        case['expectation'] == 'either' and row['outcome'] in {'answer', 'human'})
    row['characters'] = len(row['answer'])
    row['long_answer'] = len(row['answer']) > 500
    row['coverage'] = ('clarification' if trace.get('clarification') else
                       'uncovered' if trace.get('uncovered') or row['outcome'] != 'answer' else
                       'mapped_requires_manual_review')
    return row


def snapshot(publication, knowledge, links):
    data = dict(engine=VERSION, publication=publication, links=links,
                articles=[dict(pk=a.pk, slug=a.slug, title=a.title, body=a.body,
                               version=a.version, published=a.published) for a in knowledge])
    return dict(data=data, sha256=hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest())


def read_snapshot(path):
    wrapper = json.loads(Path(path).read_text())
    data = wrapper['data']
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if digest != wrapper['sha256']:
        raise ValueError('snapshot_integrity_error')
    if data['engine'] != VERSION or not data['publication'].get('valid'):
        raise ValueError('snapshot_version_or_catalog_error')
    knowledge = [SimpleNamespace(**a) for a in data['articles']]
    if not knowledge or any(not a.published for a in knowledge):
        raise ValueError('snapshot_unpublished_knowledge')
    return data['publication'], knowledge, data['links']


def write_reports(directory, rows, info):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if any((directory / name).exists() for name in ('checkpoint.json', 'report.csv', 'report.md')):
        raise ValueError('report_already_exists')
    (directory / 'checkpoint.json').write_text(json.dumps(dict(metadata=info, rows=rows), ensure_ascii=False, indent=2))
    with (directory / 'report.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# Bateria comercial contextual', '',
             'Compatibilidade não comprova correção. Cobertura e qualidade exigem revisão manual.', '']
    for row in rows:
        lines.extend([f"## {row['id']} — {row['outcome']}", '', row['messages'], '',
                      row['answer'] or row['error'], '',
                      'Intenções: ' + ', '.join(row['trace'].get('intents', [])),
                      'Cobertura: ' + row['coverage'], 'Qualidade manual: pendente', ''])
    (directory / 'report.md').write_text('\n'.join(lines))
