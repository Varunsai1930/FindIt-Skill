"""Deliberately misleading reports must fail without breaking valid reports."""
import unittest

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
