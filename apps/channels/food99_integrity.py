"""Read-only structural integrity audit for the 99Food quarantine.

No snapshot decryption, customer identifiers, or provider access.
"""

VALID_STATES = frozenset(('review', 'changed', 'reviewed'))


def audit_row(row, *, revision_count):
    """Report structural warnings only, never claim financial certification."""
    problems = []
    if row.state not in VALID_STATES:
        problems.append('UNKNOWN_REVIEW_STATE')
    if not row.encrypted_snapshot:
        problems.append('MISSING_ORIGINAL_SNAPSHOT')
    if not row.latest_encrypted_snapshot:
        problems.append('MISSING_LATEST_SNAPSHOT')
    if not (row.latest_fingerprint or row.fingerprint):
        problems.append('MISSING_FINGERPRINT')
    if revision_count == 0:
        problems.append('NO_REVISIONS')
    if row.item_count < 1 or row.amount_minor < 0:
        problems.append('INVALID_COMMERCE_SUMMARY')
    if row.connection.provider != '99food' or row.connection.mode != 'test':
        problems.append('WRONG_CONNECTION')
    if row.connection.enabled:
        problems.append('UNEXPECTED_OPERATIONS_ENABLED')
    return problems


def audit_summary(rows, *, total, limit):
    findings = []
    affected = 0
    for row in rows:
        warnings = audit_row(row, revision_count=row.revision_count)
        if warnings:
            affected += 1
            findings.append({'id': row.pk, 'issues': warnings})
    return {
        'scanned': len(rows), 'total': total, 'truncated': total > limit,
        'affected_scanned': affected, 'findings': findings,
        'operational_enabled': False,
        'note': 'Auditoria estrutural: não homologa estados nem valores financeiros.',
    }
