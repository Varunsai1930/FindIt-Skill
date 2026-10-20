"""Deterministic research-note data blocks and scoped verification.

The agent writes analysis; this module renders and verifies FindIt facts. Citation
checks validate metadata, not the truth of an article or a causal explanation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import unicodedata
from collections import Counter
from urllib.parse import urlsplit

META = re.compile(r'<!-- findit-report (\{[^\n]*\}) -->')
BLOCK = re.compile(r'<!-- findit-data:([a-z-]+) -->\n(.*?)\n<!-- /findit-data -->', re.S)
VALUE = re.compile(r'<!-- findit-value (\{[^\n]*?\}) -->(.*?)<!-- /findit-value -->', re.S)
LINK_START = re.compile(r'\[([^\]\n]+)\]\((https?://)')
NUMBER = re.compile(r'(?<!\w)[+−-]?\d[\d,]*(?:\.\d+)?%?')
SECTIONS = ('Summary', 'What changed', 'Why it may have changed',
            'Possible future impact', 'What to keep an eye on', 'Sources')
DISCLAIMER = ('Research, not investment advice. No buy, sell or hold recommendation is made or implied. '
              'Flows are estimates from disclosed month-end prices, not execution prices or returns.')
NO_NEWS = 'No usable dated sources were found in this session, so no explanations are given.'
NO_WEB = 'No web search was available in this session, so no explanations are given.'


def visible_text(text):
    """Normalize presentation that can conceal a numeric sign or boundary."""
    text = without_links(text, keep_labels=True)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'</?[A-Za-z][^>]*>', '', text)
    text = unicodedata.normalize('NFKC', html.unescape(text))
    text = ''.join(char for char in text if unicodedata.category(char) != 'Cf')
    return re.sub(r'[*_`~]', '', text)


def markup_errors(text):
    """Protocol markers must be active Markdown comments, not literal code."""
    marker = re.compile(r'<!-- findit-(?:report |data:|value )')
    inline = re.compile(r'(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)', re.S)
    errors, prose = [], []
    fence = None
    hidden_marker = False
    for line in text.splitlines(keepends=True):
        delimiter = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            hidden_marker |= bool(marker.search(line))
            if (delimiter and delimiter[1][0] == fence[0] and
                    len(delimiter[1]) >= fence[1] and not delimiter[2].strip()):
                fence = None
        elif delimiter:
            fence = (delimiter[1][0], len(delimiter[1]))
            hidden_marker |= bool(marker.search(line))
        else:
            prose.append(line)
    prose = ''.join(prose)
    if hidden_marker or any(marker.search(match[2]) for match in inline.finditer(prose)):
        errors.append('Report metadata, data and fact markers cannot appear inside code spans or fences')
    prose = inline.sub('', prose)
    prose = BLOCK.sub('', META.sub('', prose))
    prose = re.sub(r'<!--.*?-->', '', prose, flags=re.S)
    if re.search(r'</?[A-Za-z][^>]*>', prose):
        errors.append('Raw HTML outside generated data blocks is unsupported; use Markdown or escaped text')
    return errors


def reference_json(spec):
    """Parse small protocol objects without duplicate keys or recursion leaks."""
    if len(spec) > 16_384:
        raise ValueError('Reference JSON exceeds the 16384-character limit')
    def unique_fields(pairs):
        fields = {}
        for key, value in pairs:
            if key in fields:
                raise ValueError(f'Duplicate reference JSON field: {key}')
            fields[key] = value
        return fields
    try:
        return json.loads(spec, object_pairs_hook=unique_fields)
    except RecursionError as exc:
        raise ValueError('Reference JSON nesting is too deep') from exc


def scalar(value):
    if value is None or isinstance(value, float) and not math.isfinite(value):
        return 'unavailable'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, (int, float)):
        return format(value, ',')
    if isinstance(value, str) and '\n' not in value and '<!--' not in value:
        return value
    raise ValueError('A fact must reference a single scalar field, not a list, object or multiline text')


def cell(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return scalar(value).replace('|', '&#124;').replace('\n', '<br>')


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '|' + '|'.join('---' for _ in headers) + '|'] +
                     ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows])


def fields_table(rows, fields):
    return table([label for _, label in fields],
                 [[r.get(key) for key, _ in fields] for r in rows])


def section(report, prefix):
    parts = re.split(r'^## ', report, flags=re.M)
    found = [p for p in parts[1:] if p.startswith(prefix)]
    if len(found) != 1:
        raise LookupError(f'FindIt report section {prefix!r} is missing or ambiguous')
    return '### ' + found[0].strip()


def collect(fq, month, stock=None, fund=None, sources=None):
    """Read fresh data; scalar lookups can request just the sources they need."""
    if stock and fund:
        raise ValueError('Choose a stock or a fund, not both')
    month = fq.check_month(month)
    scope = 'stock' if stock else 'fund' if fund else 'market'
    scoped_sources = {'stock': ('stock', 'trend'), 'fund': ('fund',), 'market': ('top', 'trend')}[scope]
    if sources is not None and any(s not in ('release', 'amcs', 'calendar', *scoped_sources) for s in sources):
        raise ValueError('Unknown structured source for this report scope')
    wanted = sources if sources is not None else ('amcs', 'calendar', 'report', *scoped_sources)
    def run(command, **kwargs):
        return getattr(fq, 'cmd_' + command)(argparse.Namespace(month=month, **kwargs))
    data = {'release': fq.current_release()}
    target, title = None, 'market-wide'
    if stock:
        if 'stock' in wanted:
            data['stock'] = run('stock', stock=stock, holdings=True)
            target, title = data['stock']['isin'], data['stock']['name']
        else:
            target = fq.resolve_stock(stock)[0]
            title = target
    elif fund:
        data['fund'] = run('fund', fund=fund, months=3)
        target, title = str(data['fund']['scheme_id']), data['fund']['scheme_name']
    for source in wanted:
        if source in data:
            continue
        if source == 'top':
            data[source] = run('top', n=15)
        elif source == 'trend':
            data[source] = run('trend', stock=[target] if stock else None, months=12 if stock else 6, n=15)
        else:
            data[source] = run(source)
    meta = {'version': 1, 'scope': scope, 'target': target, 'month': month,
            'release_id': data['release']['release_id']}
    return {'meta': meta, 'title': title, 'data': data}


def data_blocks(ctx):
    d, meta = ctx['data'], ctx['meta']
    month, scope = meta['month'], meta['scope']
    blocks = {
        'provenance': (f"FindIt release `{meta['release_id']}`. Report month: {month}. "
                       f"Portfolios public by {d['calendar']['this_month_portfolios_public_by']}."),
        'coverage': section(d['report'], 'Coverage'),
        'evidence': section(d['report'], 'Evidence:'),
        'disclaimer': DISCLAIMER,
    }
    dropped = d['amcs']['not_loaded_this_month']
    blocks['coverage'] += ('\n\nAMCs not loaded this month: ' + ', '.join(dropped) +
                           '. Their activity is unknown and excluded from comparisons.' if dropped else
                           '\n\nNo AMC loaded in the previous month dropped out this month.')
    blocks['calendar'] = table(['When', 'What', 'Source'], [
        [d['calendar']['next_month_portfolios_public_by'], 'Next monthly portfolio disclosure', 'FindIt publication rules'],
        [d['calendar']['quarter_shareholding_filing_deadline'], 'Quarterly shareholding filing deadline', 'FindIt publication rules'],
        [d['calendar']['next_quarter_shareholding_filing_deadline'], 'Following quarterly filing deadline', 'FindIt publication rules']])
    if scope == 'market':
        blocks['rankings'] = section(d['report'], 'Broadest buying') + '\n\n' + section(d['report'], 'Broadest selling')
    if scope in ('market', 'stock'):
        t = d['trend']
        rows = [[s['stock_name'] or isin, m, *[v.get(k) for k in (
            'rank_buying', 'amcs_buying', 'amcs_selling', 'net_active_amc_count',
            'accumulation_flow_cr', 'total_flow_cr')]]
            for isin, s in t['stocks'].items() for m, v in s['by_month'].items()]
        blocks['trend'] = ('### Month-by-month ranking scope\n' + t['note'] + '\n\n' +
                           table(['Stock', 'Month', 'Buying rank', 'AMCs buying', 'AMCs selling',
                                  'Discretionary net', 'Existing flow (₹ cr)', 'Total flow (₹ cr)'], rows))
        if t.get('coverage_by_month'):
            blocks['trend'] += '\n\nComparison notices: ' + json.dumps(t['coverage_by_month'], ensure_ascii=False, sort_keys=True)
    if scope == 'stock':
        s = d['stock']
        blocks['stock'] = '### ' + s['name'] + '\n\n'
        if s['consensus']:
            blocks['stock'] += fields_table([s['consensus']], [
                ('rank_buying', 'Buying rank'), ('amcs_buying', 'AMCs buying'), ('amcs_selling', 'AMCs selling'),
                ('net_active_amc_count', 'Discretionary net'), ('new_position_flow_cr', 'New positions (₹ cr)'),
                ('accumulation_flow_cr', 'Existing positions (₹ cr)'), ('total_flow_cr', 'Total flow (₹ cr)'),
                ('fii_direction', 'FII'), ('dii_direction', 'DII')])
        else:
            blocks['stock'] += s['consensus_note']
        e = s['evidence']
        blocks['stock'] += '\n\n### Per-fund changes (compared active schemes)\n\n' + fields_table(e['funds'], [
            ('amc_name', 'AMC'), ('scheme_name', 'Scheme'), ('change', 'Action'),
            ('quantity_prev', 'Previous shares'), ('quantity_curr', 'Current shares'),
            ('qty_change', 'Share change'), ('flow_cr', 'Flow (₹ cr)'),
            ('pct_nav_prev', 'Previous % NAV'), ('pct_nav_curr', 'Current % NAV')])
        blocks['stock'] += '\n\nCoverage by AMC: ' + json.dumps(e['coverage_by_amc'], ensure_ascii=False, sort_keys=True)
        for key in ('review_status', 'ownership_note', 'price_convention'):
            blocks['stock'] += '\n\n' + key.replace('_', ' ').capitalize() + ': ' + cell(e.get(key))
        h = s['history']
        blocks['history'] = (f"### Fixed-cohort history\nAmong the {h['cohort_count']} funds tracked in every month. "
                              + h['scope'] + ' ' + h['limitation'] + '\n\n' + fields_table(h['points'], [
            ('month', 'Month'), ('shares', 'Shares'), ('net_share_change', 'Share change'),
            ('net_flow_cr', 'Net flow (₹ cr)'), ('houses_buying', 'Houses buying'),
            ('houses_selling', 'Houses selling'), ('status', 'Status'), ('adjustments', 'Adjustments')]))
        blocks['shareholding'] = ('### Quarterly shareholding\nStatus: ' + cell(s.get('shareholding_status')) + '\n\n' +
            fields_table(s.get('shareholding') or [], [('quarter_end', 'Quarter end'), ('fii_pct', 'FII %'),
                         ('dii_pct', 'DII %'), ('published_on', 'Published'), ('source', 'Source')]))
    if scope == 'fund':
        f = d['fund']
        pieces = ['### ' + f['scheme_name'] + ' — ' + f['amc_name']]
        for m, info in f['months'].items():
            pieces += [f"#### {m} — {info['summary_status']}", info['summary'] or 'No summary available.']
            if 'changes_withheld' in info:
                pieces.append(info['changes_withheld'])
            if 'changes' in info:
                pieces.append(fields_table(info['changes'], [('stock', 'Stock'), ('action', 'Action'),
                    ('qty_change', 'Share change'), ('flow_cr', 'Flow (₹ cr)'), ('value_change_cr', 'Value change (₹ cr)')]))
        blocks['fund'] = '\n\n'.join(pieces)
    return blocks


def marked(name, value):
    return f'<!-- findit-data:{name} -->\n{value}\n<!-- /findit-data -->'


def draft(ctx):
    b = data_blocks(ctx)
    ordered = ['coverage', 'rankings', 'stock', 'fund', 'trend', 'history', 'shareholding']
    return '\n\n'.join([
        f"# FindIt research note — {ctx['title']} — {ctx['meta']['month']}",
        '<!-- findit-report ' + json.dumps(ctx['meta'], ensure_ascii=False) + ' -->',
        marked('provenance', b['provenance']),
        '## 1. Summary\nTODO: Summarise the findings; annotate any numerical claims with fact output.',
        '## 2. What changed\n' + '\n\n'.join(marked(k, b[k]) for k in ordered if k in b),
        '## 3. Why it may have changed\nTODO: Add dated sources and possible explanations, or describe the actual search limitation.',
        '## 4. Possible future impact\nTODO: Add conditional scenarios grounded in the findings.',
        marked('evidence', b['evidence']),
        '## 5. What to keep an eye on\n' + marked('calendar', b['calendar']),
        '## 6. Sources\nFindIt active release and the helper commands used for this report.\n\n'
        '| Title | Publisher | Published | Link |\n|---|---|---|---|\n'
        'TODO: Register each web source with its exact publication date (YYYY-MM-DD); remove this line after research.',
        marked('disclaimer', b['disclaimer'])]) + '\n'


def fact(ctx, source, path):
    if source not in ctx['data'] or source == 'report':
        raise ValueError(f'Unknown structured source {source!r} for this report scope')
    if not path.startswith('/'):
        raise ValueError('Fact path must be a JSON pointer starting with /')
    value = ctx['data'][source]
    try:
        for token in path[1:].split('/'):
            token = token.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                if not re.fullmatch(r'0|[1-9]\d*', token):
                    raise ValueError('List indexes must be nonnegative integers')
                value = value[int(token)]
            else:
                value = value[token]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f'No field at {source}{path}') from exc
    reference = {'source': source, 'path': path}
    if ctx['meta']['scope'] == 'stock' and source in ('stock', 'trend'):
        reference.update(stock=ctx['meta']['target'], month=ctx['meta']['month'],
                         release_id=ctx['meta']['release_id'])
    return ('<!-- findit-value ' + json.dumps(reference) + ' -->' +
            scalar(value) + '<!-- /findit-value -->')


def metadata(text):
    matches = META.findall(text)
    if len(matches) != 1:
        raise ValueError('Expected one report metadata marker; start with the draft command')
    m = reference_json(matches[0])
    if (not isinstance(m, dict) or type(m.get('version')) is not int or m.get('version') != 1 or
            m.get('scope') not in ('market', 'stock', 'fund') or
            not isinstance(m.get('month'), str) or not isinstance(m.get('release_id'), str)):
        raise ValueError('Invalid report metadata')
    if m['scope'] != 'market' and (not isinstance(m.get('target'), str) or not m['target']):
        raise ValueError('Stock/fund reports require a target')
    if m['scope'] == 'market' and m.get('target') is not None:
        raise ValueError('Market reports cannot have a target')
    return m


def markdown_links(text):
    """Yield (start, end, label, URL), preserving balanced URL parentheses."""
    consumed = 0
    for match in LINK_START.finditer(text):
        if match.start() < consumed:
            continue
        start = match.start(2)
        depth = 0
        i = match.end()
        while i < len(text) and not text[i].isspace():
            char = text[i]
            if char == '\\' and i + 1 < len(text):
                i += 2
                continue
            if char == '(':
                depth += 1
            elif char == ')':
                if depth == 0:
                    consumed = i + 1
                    yield match.start(), consumed, match[1], text[start:i]
                    break
                depth -= 1
            i += 1


def without_links(text, keep_labels=False):
    pieces, end = [], 0
    for start, stop, label, _ in markdown_links(text):
        pieces.extend((text[end:start], label if keep_labels else ''))
        end = stop
    pieces.append(text[end:])
    return ''.join(pieces)


def valid_source_url(url):
    try:
        parsed = urlsplit(url)
        # Accessing .port also validates its numeric form and range.
        parsed.port
        return (parsed.scheme in ('http', 'https') and bool(parsed.hostname) and
                not any(char.isspace() or unicodedata.category(char).startswith('C') for char in url))
    except ValueError:
        return False


def citation_check(text):
    """Only visible metadata is checked; never fetch or execute links from the report."""
    errors, sources = [], {}
    source_section = re.split(r'^## 6\. Sources[^\n]*\n', text, flags=re.M)
    body = source_section[1] if len(source_section) == 2 else ''
    for line in body.splitlines():
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if cells == ['Title', 'Publisher', 'Published', 'Link'] or all(re.fullmatch(r'[-: ]+', c) for c in cells):
            continue
        if len(cells) != 4:
            errors.append('Source rows need Title, Publisher, Published, Link')
            continue
        title, publisher, published, link = cells
        matches = list(markdown_links(link))
        match = matches[0] if len(matches) == 1 and matches[0][:2] == (0, len(link)) else None
        valid_date = False
        try:
            valid_date = bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', published)) and dt.date.fromisoformat(published) <= dt.date.today()
        except ValueError:
            pass
        if not title or not publisher or not valid_date or not match or not valid_source_url(match[3]):
            errors.append(f'Incomplete or invalid source metadata: {title or line}')
            continue
        if match[3] in sources:
            errors.append(f'Duplicate source URL: {match[3]}')
        sources[match[3]] = {'title': title, 'publisher': publisher, 'published': published}
    for _, _, _, url in markdown_links(text):
        if url not in sources:
            errors.append(f'Web link has no complete dated source entry: {url}')
    # Naked URLs are not an acceptable substitute for registered citations.
    if re.search(r'https?://\S+', without_links(text)):
        errors.append('Use Markdown links and register every web URL in Sources')
    return sources, errors


def verify(text, ctx, stock_context=None):
    errors, block_errors, claim_errors = markup_errors(text), [], []
    m = metadata(text)
    if m != ctx['meta']:
        errors.append('Report month, scope, target or release differs from the active verification context')
    expected = data_blocks(ctx)
    found = BLOCK.findall(text)
    counts = Counter(k for k, _ in found)
    for name in expected:
        if counts[name] != 1:
            block_errors.append({'block': name, 'reason': 'missing or repeated block'})
    for name, content in found:
        if name not in expected or content.strip() != expected[name].strip():
            block_errors.append({'block': name, 'reason': 'content differs from current FindIt output'})
    remainder = BLOCK.sub('', META.sub('', text))
    if '<!-- findit-data' in remainder or '<!-- /findit-data' in remainder:
        errors.append('Malformed data block markers')
    # Enforce complete report structure, including order and nonempty authored sections.
    headings = list(re.finditer(r'^## ([1-6])\. ([^\n]+)', text, flags=re.M))
    if [h[1] for h in headings] != list('123456') or any(
            not h[2].startswith(name) for h, name in zip(headings, SECTIONS)):
        errors.append('Required sections 1–6 are missing, repeated, renamed or out of order')
    else:
        for i, h in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            content = text[h.end():end]
            if i in (0, 2, 3):
                content = BLOCK.sub('', content)
            if not re.sub(r'<!--.*?-->', '', content, flags=re.S).strip():
                errors.append(f'Section {h[1]} is empty')
        for block in BLOCK.finditer(text):
            name = block[1]
            required_section = (0 if name == 'provenance' else 4 if name == 'evidence' else
                                5 if name == 'calendar' else 6 if name == 'disclaimer' else 2)
            actual_section = sum(h.start() < block.start() for h in headings)
            if actual_section != required_section:
                block_errors.append({'block': name, 'reason': 'block is in the wrong report section'})
        why = text[headings[2].end():headings[3].start()]
        if next(markdown_links(why), None) is None and NO_NEWS.rstrip('.') not in why and NO_WEB.rstrip('.') not in why:
            errors.append('Explanations need cited dated sources or an explicit search limitation')
    if re.search(r'\bTODO\b|<[^>\n]*…[^>\n]*>', text):
        errors.append('Unfinished report placeholders remain')
    resolved_stocks = {}
    for match in VALUE.finditer(remainder):
        spec, shown = match.groups()
        try:
            info = reference_json(spec)
            basic = {'source', 'path'}
            scoped = basic | {'stock', 'month', 'release_id'}
            if not isinstance(info, dict) or set(info) not in (basic, scoped) or not all(isinstance(v, str) for v in info.values()):
                raise ValueError('Fact references require source/path and optional pinned stock context')
            selected = ctx
            if 'stock' in info:
                if (info['month'] != ctx['meta']['month'] or info['release_id'] != ctx['meta']['release_id'] or
                        info['source'] not in ('stock', 'trend') or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', info['stock'])):
                    raise ValueError('Stock fact must use this report month/release and a valid stock source/ISIN')
                if ctx['meta']['scope'] != 'stock' or ctx['meta']['target'] != info['stock']:
                    if stock_context is None:
                        raise ValueError('Stock fact needs a read-only stock context resolver')
                    key = (info['stock'], info['source'])
                    if key not in resolved_stocks:
                        resolved_stocks[key] = stock_context(*key)
                    selected = resolved_stocks[key]
                if any(selected['meta'].get(k) != v for k, v in (
                        ('scope', 'stock'), ('target', info['stock']), ('month', info['month']), ('release_id', info['release_id']))):
                    raise ValueError('Resolved stock context differs from the pinned fact')
            actual = VALUE.fullmatch(fact(selected, info['source'], info['path']))[2]
            if shown != actual:
                claim_errors.append({'reference': info, 'written': shown, 'expected': actual})
            # Inspect neighboring displayed values too: adjacent annotated facts
            # (even across invisible comments) must not concatenate into a new number.
            before = VALUE.sub(lambda value: value[2], remainder[:match.start()])
            after = VALUE.sub(lambda value: value[2], remainder[match.end():])
            before, after = visible_text(before), visible_text(after)
            if (re.search(r'[\d+−-]$|\d[.,]+$', before) or
                    re.match(r'\d|[.,]\d|[eE][+−-]?\d', after)):
                claim_errors.append({'reference': info, 'error': 'Surrounding text changes the displayed fact value'})
        except (ValueError, TypeError) as exc:
            claim_errors.append({'reference': spec, 'error': str(exc)})
    # Whitespace keeps any remaining digits visible to NUMBER, including suffixes.
    remainder = VALUE.sub(' ', remainder)
    if '<!-- findit-value' in remainder or '<!-- /findit-value' in remainder:
        errors.append('Malformed fact markers')
    sources, citation_errors = citation_check(remainder)
    numeric_lines, external_lines = [], []
    # The generated title and source registry carry dates/identifiers. Other
    # headings and prose must obey the same provenance rules as body paragraphs.
    in_sources = False
    for line in remainder.splitlines():
        if line.startswith('## 6. Sources'):
            in_sources = True
        if line == f"# FindIt research note — {ctx['title']} — {m['month']}":
            continue
        if in_sources and line.startswith('|'):
            continue
        line = re.sub(r'^## [1-6]\. ', '', line)
        clean = visible_text(without_links(line, keep_labels=True))
        if NUMBER.search(clean):
            if any(url in sources for _, _, _, url in markdown_links(line)):
                external_lines.append(line)
            else:
                numeric_lines.append(line)
    ok = not (errors or block_errors or claim_errors or citation_errors or numeric_lines)
    return {'ok': ok, 'scope': m['scope'], 'month': m['month'], 'release_id': ctx['meta']['release_id'],
            'blocks_checked': len(found), 'facts_checked': len(VALUE.findall(text)),
            'errors': errors, 'block_errors': block_errors, 'claim_errors': claim_errors,
            'citation_errors': citation_errors, 'unverified_numeric_lines': numeric_lines,
            'externally_sourced_numeric_lines': external_lines,
            'manual_review': ['Check that cited pages actually show the registered dates and support the claims.',
                              'Check that each field reference describes the right company, fund, month and scope.',
                              'Check explanations, scenarios and absence of investment recommendations.']}
