"""Live release checks for the commands not covered by the original suite."""
import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import COVERAGE, MONTH, fq, run, run_json, top
import findit_notes as notes
from test_notes import completed


class CommandTests(unittest.TestCase):
    def test_trend_matches_consensus_for_each_requested_month(self):
        isin = top()['buying'][0]['isin']
        code, trend = run_json('trend', '--stock', isin, '--month', MONTH, '--months', '3')
        self.assertEqual(code, 0)
        for month in trend['months']:
            code, consensus = run_json('consensus', '--stock', isin, '--month', month)
            self.assertEqual(code, 0)
            rows = consensus['rows']
            if rows:
                point = trend['stocks'][isin]['by_month'][month]
                for key in ('amcs_buying', 'amcs_selling', 'rank_buying', 'total_flow_cr'):
                    self.assertEqual(point[key], rows[0][key])
            else:
                self.assertIn(month, trend['stocks'][isin]['months_without_activity'])

    def test_trend_preserves_withheld_notices(self):
        with patch.object(fq, 'api', return_value={'results': [], 'message': 'withheld', 'quarantined_schemes': [7]}):
            data = fq.cmd_trend(argparse.Namespace(month=MONTH, months=1, stock=None, n=15))
        self.assertEqual(data['coverage_by_month'][MONTH]['message'], 'withheld')
        self.assertEqual(data['coverage_by_month'][MONTH]['quarantined_schemes'], [7])

    def test_history_preserves_cohort_status_and_original_totals(self):
        isin = top()['buying'][1]['isin']
        start = COVERAGE['months'][-3]
        original = fq.api(f'/api/history/{isin}', start=start, end=MONTH, active_only=1)
        code, result = run_json('history', isin, '--start', start, '--end', MONTH)
        self.assertEqual(code, 0)
        self.assertEqual(result['cohort_count'], original['cohort_count'])
        for actual, expected in zip(result['points'], original['points']):
            for field in ('month', 'shares', 'status', 'net_share_change'):
                self.assertEqual(actual[field], expected[field])

    def test_fund_and_digest_use_findit_summaries(self):
        code, funds = run_json('funds', 'flexi cap', '--month', MONTH)
        self.assertEqual(code, 0)
        scheme = next(s for s in funds['schemes'] if s['is_active_equity'])
        sid = scheme['scheme_id']
        code, fund = run_json('fund', str(sid), '--month', MONTH, '--months', '2')
        self.assertEqual(code, 0)
        for month, value in fund['months'].items():
            expected = fq.api(f'/api/summary/{sid}/{month}')
            self.assertEqual(value['summary'], expected['summary'])
            self.assertEqual(value['summary_status'], expected['summary_status'])
        from findit.cli.digest import build_digest
        with fq.closing(fq.ro_conn()) as conn:
            expected = build_digest(conn, [sid], MONTH)
        code, actual = run('digest', '--schemes', str(sid), '--month', MONTH)
        self.assertEqual(code, 0)
        self.assertEqual(actual.strip(), expected.strip())

    def test_fund_quarantine_withholds_change_rows(self):
        summary = {'summary': 'Withheld', 'summary_status': 'quarantined', 'has_data': True,
                   'quarantined': True, 'amc_name': 'AMC', 'scheme_name': 'Fund'}
        with patch.object(fq, 'api', return_value=summary), patch.object(fq, 'assess', return_value={'reason': 'quarantined'}):
            value = fq.cmd_fund(argparse.Namespace(month=MONTH, fund='1', months=1))
        self.assertNotIn('changes', value['months'][MONTH])
        self.assertIn('quarantined', value['months'][MONTH]['changes_withheld'])

    def test_calendar_uses_findit_rules_including_year_rollover(self):
        from findit.core import publication
        for month in [MONTH, next(m for m in COVERAGE['months'] if m.endswith('-12'))]:
            code, result = run_json('calendar', '--month', month)
            self.assertEqual(code, 0)
            self.assertEqual(result['this_month_portfolios_public_by'], publication.mf_disclosure_deadline(month).isoformat())
            if month.endswith('-12'):
                self.assertEqual(result['next_month'], f'{int(month[:4]) + 1}-01')
                self.assertEqual(result['next_quarter_end'], f'{int(month[:4]) + 1}-03-31')

    def test_live_scoped_drafts_verify_and_reject_changed_facts(self):
        stock = top()['buying'][1]['isin']
        _, funds = run_json('funds', 'flexi cap', '--month', MONTH)
        fund = str(next(s['scheme_id'] for s in funds['schemes'] if s['is_active_equity']))
        for scope, target in [('market', None), ('stock', stock), ('fund', fund)]:
            with self.subTest(scope=scope):
                ctx = notes.collect(fq, MONTH, stock=target if scope == 'stock' else None,
                                    fund=target if scope == 'fund' else None)
                text = completed(ctx)
                result = notes.verify(text, ctx)
                self.assertTrue(result['ok'], result)
                if scope == 'fund':
                    with tempfile.TemporaryDirectory() as tmp:
                        path = Path(tmp) / 'fund.md'
                        path.write_text(text)
                        code, verified = run_json('verify', str(path))
                        self.assertEqual(code, 0, verified)
                        path.write_text(text.replace('## 6. Sources', '## Missing sources'))
                        code, verified = run_json('verify', str(path))
                        self.assertEqual(code, 2, verified)

    def test_verify_bad_file_or_metadata_is_structured_error(self):
        code, result = run_json('verify', '/no/such/findskill-note.md')
        self.assertEqual(code, 1)
        self.assertIn('error', result)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'note.md'
            path.write_text('# A legacy note')
            code, result = run_json('verify', str(path))
            self.assertEqual(code, 1)
            self.assertIn('draft', result['error'])
