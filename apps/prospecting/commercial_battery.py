"""Read-only in-memory conversations for manual Gemini comparison.

No inbox rows, phone numbers, WhatsApp clients, sends or sequence increments.
"""
import csv
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from .commercial_quota import CommercialQuotaDeferred
from .commercial_smart import compose, redact

CASES = Path(__file__).parent / 'fixtures' / 'commercial_battery07.json'


class MemoryRows(list):
    def order_by(self, key):
        return MemoryRows(sorted(self, key=lambda r: r[key.lstrip('-')], reverse=key.startswith('-')))

    def filter(self, **kwargs):
        return MemoryRows(r for r in self if all(r[k] == v for k,v in kwargs.items()))

    def exclude(self, **kwargs):
        return MemoryRows(r for r in self if not all(r[k] == v for k,v in kwargs.items()))

    def values(self, *keys):
        return MemoryRows({k:r[k] for k in keys} for r in self)

    def values_list(self, key, flat=False):
        return MemoryRows(r[key] if flat else (r[key],) for r in self)

    def first(self):
        return self[0] if self else None


def conversation(case):
    return SimpleNamespace(messages=MemoryRows(
        dict(pk=i, text=text, reply='', from_me=False, created_at=datetime.now(timezone.utc))
        for i,text in enumerate(case['messages'].split(' | '),1)))


def evaluate(case, publication, knowledge):
    start=time.monotonic()
    row=dict(case, outcome='', answer='', error='', sources=[], retry_at=0, manual_quality='', trace={})
    try:
        answer, sources=compose(conversation(case), publication, knowledge, trace=row['trace'])
        row.update(outcome='answer', answer=answer, sources=sources)
    except CommercialQuotaDeferred as exc:
        row.update(outcome='deferred', error=exc.reason, retry_at=time.time()+exc.seconds)
    except ValueError as exc:
        # Only stable internal error codes, never exception bodies or credentials.
        code=str(exc)
        if not re.fullmatch('[a-z_0-9]+',code): code='unclassified_error'
        provider=code.startswith(('smart_provider_', 'smart_model_'))
        row.update(outcome='api_error' if provider else 'human', error=code)
    except Exception:
        row.update(outcome='execution_error',error='unexpected_execution_error')
    row['elapsed_s']=round(time.monotonic()-start,3)
    # Original expected outcomes are immutable. Compatibility is NOT correctness.
    row['outcome_compatible'] = (row['outcome']==case['expectation'] or
        case['expectation']=='either' and row['outcome'] in {'human','answer'}) if row['outcome'] in {'human','answer'} else ''
    return row


def write_reports(directory, rows, metadata):
    directory.mkdir(parents=True, exist_ok=True)
    checkpoint=directory/'checkpoint.json'
    temp=checkpoint.with_suffix('.tmp')
    safe_rows=[dict(row, messages=redact(row['messages'])) for row in rows]
    temp.write_text(json.dumps({'metadata':metadata,'rows':safe_rows},ensure_ascii=False,indent=2)+'\n')
    temp.replace(checkpoint)
    if not rows: return
    fields=list(rows[0])
    with (directory/'report.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:
            safe={k: (redact(v) if k=='messages' else v) for k,v in row.items()}
            writer.writerow(safe)
    lines=['# Bateria comercial 07', '',
           'Compatibilidade de desfecho não mede qualidade. Respostas exigem inspeção manual.',
           'Adiamentos de cota não são erros de compreensão. Nenhum WhatsApp é conectado.', '']
    for row in rows:
        lines.extend([f"## {row['id']} — {row['outcome']}", '',
                      redact(row['messages']), '', row['answer'] or row['error'], '',
                      'Qualidade manual: pendente', ''])
    (directory/'report.md').write_text('\n'.join(lines))


def metadata(publication, knowledge):
    from .commercial_models import CommercialControl
    control = CommercialControl.objects.filter(pk=1).first()
    # Include approval configuration in resume identity; never silently reuse
    # a case 094 result produced with a different demo link.
    links = [control.demo_url, control.contact_url] if control else ['', '']
    return dict(composer_version=10, commercial_links_sha256=hashlib.sha256(json.dumps(links).encode()).hexdigest(),
                demo_configured=bool(links[0]), cases_sha256=hashlib.sha256(CASES.read_bytes()).hexdigest(),
                catalog_fingerprint=publication['fingerprint'],
                articles_sha256=hashlib.sha256(json.dumps([(a.pk,a.version,a.body) for a in knowledge],ensure_ascii=False).encode()).hexdigest())
