"""Deliberately misleading reports must fail without breaking valid reports."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from helpers import MONTH, fq, run_json
from test_notes import context, completed
import findit_notes as notes


class NumericPresentationTests(unittest.TestCase):
    def test_rendering_cannot_change_or_join_verified_numbers(self):
        ctx = context()
        qty = notes.fact(ctx, 'fund', '/months/2026-01/changes/0/qty_change')
        flow = notes.fact(ctx, 'fund', '/months/2026-01/changes/0/flow_cr')
        attacks = {
            'minus': '-' + flow,
            'unicode minus': '−' + flow,
            'plus': '+' + flow,
            'formatted sign': '-**' + flow + '**',
            'hex sign': '&#x2d;' + flow,
            'named sign': '&minus;' + flow,
            'exponent': flow + 'e3',
            'signed exponent': flow + 'E+3',
            'decimal join': qty + '.' + qty,
            'comma join': qty + ',' + qty,
            'invisible join': qty + '\u200b' + qty,
            'HTML join': qty + '<span></span>' + qty,
            'encoded exponent': qty + '&#x65;' + qty,
            'superscript suffix': flow + '&sup2;',
            'unreferenced encoded number': '&#x39;&#x39;&#x39;',
        }
        for name, value in attacks.items():
            with self.subTest(attack=name):
                text = completed(ctx).replace('The disclosure shows a change in positioning.',
                                             'Flow was ' + value + ' cr.')
                result = notes.verify(text, ctx)
                self.assertFalse(result['ok'], result)
                self.assertTrue(result['claim_errors'] or result['unverified_numeric_lines'])

    def test_registered_links_cannot_hide_numeric_changes(self):
        ctx = context()
        flow = notes.fact(ctx, 'fund', '/months/2026-01/changes/0/flow_cr')
        qty = notes.fact(ctx, 'fund', '/months/2026-01/changes/0/qty_change')
        url = 'https://example.org/news'
        base = completed(ctx).replace('No external sources were retained.',
            '| Article | Company | 2026-01-15 | [Read](' + url + ') |')
        for value in ('[−](' + url + ')' + flow, '[&#x2d;](' + url + ')' + flow,
                      flow + '[e3](' + url + ')', qty + '[<!-- gap -->](' + url + ')' + qty,
                      qty + '[' + qty + '](' + url + ')'):
            with self.subTest(value=value):
                text = base.replace('The disclosure shows a change in positioning.', 'Flow ' + value + ' cr.')
                result = notes.verify(text, ctx)
                self.assertFalse(result['ok'], result)
                self.assertTrue(result['claim_errors'])
                self.assertEqual(result['citation_errors'], [])
        text = base.replace('The disclosure shows a change in positioning.', 'Flow [' + flow + '](' + url + ') cr.')
        self.assertTrue(notes.verify(text, ctx)['ok'])

    def test_correct_numbers_survive_ordinary_formatting_and_punctuation(self):
        for amount in (5.25, -5.25):
            ctx = context()
            ctx['data']['fund']['months']['2026-01']['changes'][0]['flow_cr'] = amount
            flow = notes.fact(ctx, 'fund', '/months/2026-01/changes/0/flow_cr')
            for prose in ('Flow was ₹' + flow + ' cr.', 'Flow was **' + flow + '** cr.',
                          'Flow was ' + flow + '.', 'Flow was ' + flow + ', according to FindIt.',
                          'Flows were ' + flow + '&nbsp;and ' + flow + ' cr.'):
                with self.subTest(amount=amount, prose=prose):
                    text = completed(ctx).replace('The disclosure shows a change in positioning.', prose)
                    self.assertTrue(notes.verify(text, ctx)['ok'])


class ReportVisibilityTests(unittest.TestCase):
    def test_verification_markers_must_not_be_literal_code_or_hidden_html(self):
        ctx = context()
        base = completed(ctx)
        token = notes.fact(ctx, 'fund', '/months/2026-01/changes/0/flow_cr')
        attacks = {
            'backtick fence': '```markdown\n' + base + '\n```',
            'long fence': '````markdown\n' + base + '\n````',
            'tilde fence': '~~~markdown\n' + base + '\n~~~',
            'inline code': base.replace('The disclosure shows a change in positioning.', '`' + token + '`'),
            'long inline code': base.replace('The disclosure shows a change in positioning.', '``' + token + '``'),
            'hidden HTML': '<div hidden>\n' + base + '\n</div>',
            'multiline hidden HTML': '<div\nhidden>\n' + base,
            'multiline style HTML': '<style\ntype="text/css">\n' + base,
        }
        for name, text in attacks.items():
            with self.subTest(attack=name):
                result = notes.verify(text, ctx)
                self.assertFalse(result['ok'], result)
                self.assertTrue(result['errors'])

    def test_ordinary_code_quotes_without_verification_markers_can_pass(self):
        ctx = context()
        for quote in ('Use `FindIt` for disclosure data.', '```text\nDisclosure data is available.\n```',
                      'Literal `<span>` example.', '~~~html\n<span>example</span>\n~~~'):
            with self.subTest(quote=quote):
                text = completed(ctx).replace('The disclosure shows a change in positioning.', quote)
                self.assertTrue(notes.verify(text, ctx)['ok'])


class ReferenceParsingTests(unittest.TestCase):
    def test_deep_fact_json_fails_verification_without_a_recursion_crash(self):
        ctx = context()
        spec = '{"source":"fund","path":' + '[' * 10000 + '0' + ']' * 10000 + '}'
        token = '<!-- findit-value ' + spec + ' -->5.25<!-- /findit-value -->'
        text = completed(ctx).replace('The disclosure shows a change in positioning.', token)
        result = notes.verify(text, ctx)
        self.assertFalse(result['ok'])
        self.assertTrue(result['claim_errors'])

    def test_deep_metadata_produces_a_structured_cli_error(self):
        ctx = context()
        spec = json.dumps(ctx['meta'])[:-1] + ',"extra":' + '[' * 10000 + '0' + ']' * 10000 + '}'
        text = notes.META.sub(lambda _: '<!-- findit-report ' + spec + ' -->', completed(ctx))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'malformed.md'
            path.write_text(text)
            code, result = run_json('verify', str(path))
        self.assertEqual(code, 1, result)
        self.assertIn('error', result)

    def test_duplicate_fact_keys_are_rejected_instead_of_using_the_last_one(self):
        ctx = context()
        spec = '{"source":"fund","path":"/bad","path":"/months/2026-01/changes/0/flow_cr"}'
        token = '<!-- findit-value ' + spec + ' -->5.25<!-- /findit-value -->'
        text = completed(ctx).replace('The disclosure shows a change in positioning.', token)
        result = notes.verify(text, ctx)
        self.assertFalse(result['ok'])
        self.assertTrue(result['claim_errors'])

    def test_duplicate_metadata_keys_and_boolean_versions_are_invalid(self):
        ctx = context()
        meta = json.dumps(ctx['meta'])
        for spec in (meta.replace('"version": 1', '"version": 0, "version": 1'),
                     meta.replace('"version": 1', '"version": true')):
            with self.subTest(spec=spec):
                text = notes.META.sub(lambda _: '<!-- findit-report ' + spec + ' -->', completed(ctx))
                with self.assertRaises(ValueError):
                    notes.metadata(text)


class SourceUrlTests(unittest.TestCase):
    def test_malformed_hosts_and_ports_return_citation_errors_without_crashing(self):
        ctx = context()
        for url in ('https://[bad/path', 'https://example.org:bad/news',
                    'https://example.org:70000/news', 'https://:443/news',
                    'https://exam\x00ple.org/news'):
            with self.subTest(url=url):
                text = completed(ctx).replace('No external sources were retained.',
                    '| Article | Company | 2026-01-15 | [Read](' + url + ') |')
                result = notes.verify(text, ctx)
                self.assertFalse(result['ok'], result)
                self.assertTrue(result['citation_errors'])

    def test_valid_explicit_ports_and_ipv6_urls_remain_supported(self):
        ctx = context()
        for url in ('https://example.org:443/news', 'https://[2001:db8::1]:443/news'):
            with self.subTest(url=url):
                text = completed(ctx).replace('No external sources were retained.',
                    '| Article | Company | 2026-01-15 | [Read](' + url + ') |')
                self.assertTrue(notes.verify(text, ctx)['ok'])


class CountInputTests(unittest.TestCase):
    cases = (
        ('top', (), '--n'), ('consensus', (), '--n'),
        ('trend', (), '--months'), ('trend', (), '--n'),
        ('search', ('example',), '--limit'), ('funds', (), '--limit'),
        ('fund', ('1',), '--months'),
    )

    def test_nonpositive_counts_fail_before_loading_data(self):
        for command, args, flag in self.cases:
            for value in ('0', '-1'):
                with self.subTest(command=command, flag=flag, value=value):
                    handler = Mock(return_value={'rows': []})
                    with patch.object(fq, 'cmd_' + command, handler):
                        code, result = run_json(command, *args, flag, value)
                    self.assertEqual(code, 1, result)
                    self.assertIn('positive', result['error'])
                    handler.assert_not_called()

    def test_positive_counts_reach_the_requested_command(self):
        for command, args, flag in self.cases:
            with self.subTest(command=command, flag=flag):
                handler = Mock(return_value={'rows': []})
                with patch.object(fq, 'cmd_' + command, handler):
                    code, result = run_json(command, *args, flag, '1')
                self.assertEqual(code, 0, result)
                handler.assert_called_once()

    def test_internal_month_selection_rejects_empty_spans_and_clips_large_valid_spans(self):
        for value in (0, -1):
            with self.subTest(months=value), self.assertRaises(ValueError):
                fq.prev_months(MONTH, value)
        self.assertTrue(fq.prev_months(MONTH, 1_000_000))
