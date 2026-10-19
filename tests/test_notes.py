"""Behavioral checks for report completeness, provenance and all three scopes."""
import copy
import json
import unittest

from helpers import fq
import findit_notes as notes


def context(scope='fund', ranked=True, withheld=False):
    data = {
        'release': {'release_id': 'a' * 64},
        'report': ('# Activity\n## Coverage\n2 schemes compared.\n'
                   '## Broadest buying\n| Stock | Buying |\n| Alpha | 2 |\n'
                   '## Broadest selling\n| Stock | Selling |\n| Beta | 1 |\n'
                   '## Evidence: does this predict returns?\nNo reliable edge.\n| Group | Return |\n| MF up | 0.4% |\n'),
        'amcs': {'not_loaded_this_month': ['Missing AMC']},
        'calendar': {'this_month_portfolios_public_by': '2026-02-10',
                     'next_month_portfolios_public_by': '2026-03-10',
                     'quarter_shareholding_filing_deadline': '2026-04-21',
                     'next_quarter_shareholding_filing_deadline': '2026-07-21'},
        'trend': {'note': 'Missing months were not ranked.', 'stocks': {'ISIN': {
            'stock_name': 'Alpha', 'by_month': {'2026-01': {'amcs_buying': 2, 'total_flow_cr': 5.25}}}}},
    }
    if scope == 'fund':
        entry = {'summary': 'Opened a new position.', 'summary_status': 'available',
                 'changes': [{'stock': 'Alpha', 'action': 'new', 'qty_change': 10, 'flow_cr': 5.25}]}
        if withheld:
            entry = {'summary': 'Withheld pending validation.', 'summary_status': 'quarantined',
                     'changes_withheld': 'FindIt withheld the comparison.'}
        data['fund'] = {'scheme_name': 'Example Fund', 'amc_name': 'Example AMC', 'months': {'2026-01': entry}}
    elif scope == 'stock':
        data['stock'] = {'name': 'Alpha', 'consensus': {'amcs_buying': 2} if ranked else None,
                         'consensus_note': 'No compared activity; not ranked.',
                         'evidence': {'funds': [{'scheme_name': 'Example Fund', 'quantity_curr': 10, 'flow_cr': 5.25}],
                                      'coverage_by_amc': {'Example AMC': {'withheld_count': 1}}},
                         'history': {'cohort_count': 1, 'scope': 'Fixed cohort.', 'limitation': 'Narrower scope.',
                                     'points': [{'month': '2026-01', 'shares': 10, 'net_flow_cr': 5.25}]},
                         'shareholding': [{'quarter_end': '2025-12-31', 'fii_pct': 4.2}]}
    return {'meta': {'version': 1, 'scope': scope, 'target': None if scope == 'market' else '123',
                     'month': '2026-01', 'release_id': 'a' * 64}, 'title': 'Example', 'data': data}


def completed(ctx):
    text = notes.draft(ctx)
    replacements = [
        'The disclosure shows a change in positioning.', notes.NO_NEWS,
        'If positioning persists, breadth may increase. If it reverses, breadth may narrow.',
        'No external sources were retained.'
    ]
    lines = iter(replacements)
    return '\n'.join(next(lines) if line.startswith('TODO:') else line for line in text.splitlines()) + '\n'


class NotesTests(unittest.TestCase):
    def test_all_scopes_and_withheld_or_unranked_data_can_pass(self):
        for ctx in [context('market'), context('stock'), context('stock', ranked=False),
                    context('fund'), context('fund', withheld=True)]:
            with self.subTest(meta=ctx['meta'], data=ctx['data'].get('fund')):
                result = notes.verify(completed(ctx), ctx)
                self.assertTrue(result['ok'], result)

    def test_incomplete_draft_fails(self):
        ctx = context()
        self.assertFalse(notes.verify(notes.draft(ctx), ctx)['ok'])

    def test_missing_changed_and_duplicate_blocks_fail(self):
        for scope, block in [('market', 'rankings'), ('stock', 'history'), ('stock', 'stock'),
                             ('stock', 'shareholding'), ('fund', 'fund'), ('fund', 'evidence'), ('fund', 'coverage')]:
            ctx = context(scope)
            original = completed(ctx)
            marked = notes.marked(block, notes.data_blocks(ctx)[block])
            for text in [original.replace(marked, ''), original.replace(marked, marked.replace('\n', '\nwrong\n', 1)),
                         original + '\n' + marked]:
                with self.subTest(scope=scope, block=block):
                    self.assertFalse(notes.verify(text, ctx)['ok'])

    def test_correct_fact_passes_and_tampered_fact_fails(self):
        ctx = context()
        token = notes.fact(ctx, 'fund', '/months/2026-01/changes/0/flow_cr')
        text = completed(ctx).replace('The disclosure shows a change in positioning.', 'Alpha flow was ₹' + token + ' cr.')
        self.assertTrue(notes.verify(text, ctx)['ok'])
        result = notes.verify(text.replace('-->5.25<!--', '-->99.25<!--'), ctx)
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['claim_errors']), 1)

    def test_unannotated_numerical_prose_is_not_silently_approved(self):
        ctx = context()
        result = notes.verify(completed(ctx).replace('The disclosure shows a change in positioning.',
                                                    'Alpha flow was ₹999 cr.'), ctx)
        self.assertFalse(result['ok'])
        self.assertIn('₹999', result['unverified_numeric_lines'][0])

    def test_digits_outside_fact_markers_cannot_change_the_displayed_value(self):
        ctx = context()
        token = notes.fact(ctx, 'fund', '/months/2026-01/changes/0/flow_cr')
        for value in ['9' + token, token + '9', token + '.9', token + ',999']:
            with self.subTest(value=value):
                text = completed(ctx).replace('The disclosure shows a change in positioning.',
                                              'Alpha flow was ₹' + value + ' cr.')
                result = notes.verify(text, ctx)
                self.assertFalse(result['ok'], result)

    def test_citation_does_not_hide_a_digit_appended_to_a_fact(self):
        ctx = context()
        token = notes.fact(ctx, 'fund', '/months/2026-01/changes/0/flow_cr')
        text = completed(ctx).replace('The disclosure shows a change in positioning.',
            'Alpha flow was ₹' + token + '9 cr. [Article](https://example.org/news).')
        text = text.replace('No external sources were retained.',
                           '| Article | Company | 2026-01-15 | [Read](https://example.org/news) |')
        result = notes.verify(text, ctx)
        self.assertFalse(result['ok'])
        self.assertTrue(result['claim_errors'])

    def test_invalid_field_and_non_scalar_are_rejected(self):
        ctx = context()
        for source, path in [('fund', '/bad'), ('fund', '/months'), ('fund', '/months/2026-01/changes/-1/flow_cr'),
                             ('not-a-source', '/field')]:
            with self.subTest(source=source, path=path), self.assertRaises(ValueError):
                notes.fact(ctx, source, path)

    def test_release_and_month_mismatch_fail(self):
        ctx = context()
        for field, value in [('release_id', 'b' * 64), ('month', '2026-02')]:
            changed = copy.deepcopy(ctx)
            changed['meta'][field] = value
            self.assertFalse(notes.verify(completed(changed), ctx)['ok'])

    def test_missing_section_and_empty_explanation_fail(self):
        ctx = context()
        text = completed(ctx)
        self.assertFalse(notes.verify(text.replace('## 4. Possible future impact', '## Other'), ctx)['ok'])
        self.assertFalse(notes.verify(text.replace(notes.NO_NEWS, ''), ctx)['ok'])

    def test_generated_evidence_does_not_replace_authored_scenarios(self):
        ctx = context()
        text = completed(ctx).replace('If positioning persists, breadth may increase. If it reverses, breadth may narrow.', '')
        self.assertFalse(notes.verify(text, ctx)['ok'])

    def test_blocks_must_stay_in_their_report_sections(self):
        ctx = context()
        text = completed(ctx)
        block = notes.marked('fund', notes.data_blocks(ctx)['fund'])
        text = text.replace(block, '') + '\n' + block
        self.assertFalse(notes.verify(text, ctx)['ok'])

    def test_numerical_headings_and_source_section_prose_need_provenance(self):
        ctx = context()
        for extra in ['### Fund added 999 shares', 'The fund added 999 shares.']:
            with self.subTest(extra=extra):
                self.assertFalse(notes.verify(completed(ctx) + '\n' + extra, ctx)['ok'])

    def test_citations_require_exact_valid_date_and_registration(self):
        ctx = context()
        text = completed(ctx).replace(notes.NO_NEWS, 'Possible company context: [Announcement](https://example.org/news).')
        self.assertFalse(notes.verify(text, ctx)['ok'])
        for date in ['2026-01-15', 'date not shown', '2026-01', '2026-02-30', '2999-01-01']:
            cited = text.replace('No external sources were retained.',
                f'| Announcement | Example publisher | {date} | [Read](https://example.org/news) |')
            with self.subTest(date=date):
                self.assertEqual(notes.verify(cited, ctx)['ok'], date == '2026-01-15')

    def test_cited_external_numbers_are_reported_for_human_review(self):
        ctx = context()
        text = completed(ctx).replace(notes.NO_NEWS, 'Revenue grew 2%: [Announcement](https://example.org/news).')
        text = text.replace('No external sources were retained.',
                            '| Announcement | Example | 2026-01-15 | [Read](https://example.org/news) |')
        result = notes.verify(text, ctx)
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['externally_sourced_numeric_lines']), 1)
        self.assertTrue(result['manual_review'])

    def test_balanced_parentheses_in_source_urls(self):
        ctx = context()
        for url in ['https://example.org/News_(company)',
                    'https://example.org/News_(company_(India))?edition=(latest)']:
            with self.subTest(url=url):
                text = completed(ctx).replace(notes.NO_NEWS, 'Possible context: [Article](' + url + ').')
                text = text.replace('No external sources were retained.',
                    '| Article | Company | 2026-01-15 | [Read](' + url + ') |')
                result = notes.verify(text, ctx)
                self.assertTrue(result['ok'], result)
                sources, errors = notes.citation_check(text)
                self.assertEqual(errors, [])
                self.assertIn(url, sources)

    def test_parentheses_urls_still_require_complete_registration(self):
        ctx = context()
        url = 'https://example.org/News_(company)'
        text = completed(ctx).replace(notes.NO_NEWS, 'Possible context: [Article](' + url + ').')
        result = notes.verify(text, ctx)
        self.assertFalse(result['ok'])
        self.assertIn('Web link has no complete dated source entry: ' + url, result['citation_errors'])
        text = text.replace('No external sources were retained.',
            '| Article | Company | date not shown | [Read](' + url + ') |')
        self.assertFalse(notes.verify(text, ctx)['ok'])

    def test_unbalanced_source_urls_are_rejected(self):
        ctx = context()
        for url in ['https://example.org/News_(company', 'https://example.org/News_company)']:
            with self.subTest(url=url):
                text = completed(ctx).replace(notes.NO_NEWS, 'Possible context: [Article](' + url + ').')
                text = text.replace('No external sources were retained.',
                    '| Article | Company | 2026-01-15 | [Read](' + url + ') |')
                self.assertFalse(notes.verify(text, ctx)['ok'])

    def test_malformed_markers_and_reference_fail(self):
        ctx = context()
        text = completed(ctx)
        for changed in [text.replace('<!-- /findit-data -->', '<!-- broken -->', 1),
                        text.replace('The disclosure shows a change in positioning.',
                                     '<!-- findit-value {} -->5<!-- /findit-value -->')]:
            self.assertFalse(notes.verify(changed, ctx)['ok'])
