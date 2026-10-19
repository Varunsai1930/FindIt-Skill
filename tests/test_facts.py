"""Scalar lookups load only their source and share work within a batch."""
import argparse
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from helpers import fq, MONTH, run
import findit_notes as notes


class FactTests(unittest.TestCase):
    def helper(self):
        return SimpleNamespace(
            check_month=Mock(return_value=MONTH),
            current_release=Mock(return_value={'release_id': 'a' * 64}),
            resolve_stock=Mock(return_value=('INE880J01026', [])),
            cmd_top=Mock(return_value={'buying': [{'amcs_opening': 7, 'new_position_flow_cr': 1235.35}]}),
            cmd_trend=Mock(return_value={'stocks': {'INE880J01026': {'by_month': {MONTH: {'amcs_buying': 6}}}}}),
            cmd_calendar=Mock(return_value={'report_month': MONTH}),
            cmd_report=Mock(side_effect=AssertionError('Unrelated full report was loaded')),
            cmd_stock=Mock(side_effect=AssertionError('Unrelated stock evidence was loaded')),
            cmd_amcs=Mock(side_effect=AssertionError('Unrelated AMC coverage was loaded')),
        )

    def test_top_fact_loads_no_report_or_trends(self):
        helper = self.helper()
        ctx = notes.collect(helper, MONTH, sources=['top'])
        self.assertIn('-->7<!--', notes.fact(ctx, 'top', '/buying/0/amcs_opening'))
        helper.cmd_top.assert_called_once()
        helper.cmd_trend.assert_not_called()
        self.assertEqual(set(ctx['data']), {'release', 'top'})

    def test_stock_trend_does_not_load_stock_evidence(self):
        helper = self.helper()
        ctx = notes.collect(helper, MONTH, stock='JSW', sources=['trend'])
        token = notes.fact(ctx, 'trend', f'/stocks/INE880J01026/by_month/{MONTH}/amcs_buying')
        self.assertIn('"stock": "INE880J01026"', token)
        self.assertIn('-->6<!--', token)
        helper.cmd_trend.assert_called_once_with(
            argparse.Namespace(month=MONTH, stock=['INE880J01026'], months=12, n=15))
        helper.cmd_stock.assert_not_called()

    def test_multiple_paths_share_one_source_load(self):
        data = self.helper().cmd_top.return_value
        with patch.object(fq, 'cmd_top', return_value=data) as top, \
                patch.object(fq, 'cmd_report', side_effect=AssertionError('Full report loaded')):
            code, output = run('fact', '--month', MONTH, '--source', 'top',
                               '--path', '/buying/0/amcs_opening',
                               '--path', '/buying/0/new_position_flow_cr')
        self.assertEqual(code, 0, output)
        self.assertEqual(len(output.splitlines()), 2)
        self.assertIn('-->7<!--', output.splitlines()[0])
        self.assertIn('-->1,235.35<!--', output.splitlines()[1])
        top.assert_called_once()

    def test_invalid_batch_path_produces_no_partial_facts(self):
        data = self.helper().cmd_top.return_value
        with patch.object(fq, 'cmd_top', return_value=data), \
                patch.object(fq, 'cmd_report', side_effect=AssertionError('Full report loaded')):
            code, output = run('fact', '--month', MONTH, '--source', 'top',
                               '--path', '/buying/0/amcs_opening', '--path', '/missing')
        self.assertEqual(code, 1, output)
        self.assertIn('No field', output)
        self.assertNotIn('findit-value', output)
