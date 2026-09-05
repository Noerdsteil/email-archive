"""bronze/ (Apple Mail mbox exports or .eml files) -> silver/emails.jsonl

Usage:  python3 parse.py            # reads bronze/, writes silver/emails.jsonl, prints metrics
Env:    OWN_ADDRESSES="me@a.de,me@b.com"   used to derive direction as a cross-check
"""
# ponytail: stdlib only. Lesson steps 0-5, 7, 8 in JonasWiki/EMAIL RAG Archive/Preprocessing.md
import os, sys, json, mailbox, hashlib, re, statistics
from collections import Counter
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, getaddresses
from pathlib import Path
from html.parser import HTMLParser

BRONZE, SILVER = Path('bronze'), Path('silver/emails.jsonl')
OWN = {a.strip().lower() for a in os.environ.get('OWN_ADDRESSES', '').split(',') if a.strip()}


class _Text(HTMLParser):
    def __init__(self): super().__init__(); self.out = []
    def handle_data(self, d): self.out.append(d)


def html_to_text(h):
    p = _Text(); p.feed(h)
    return re.sub(r'\n{3,}', '\n\n', ''.join(p.out))


def body_of(msg):
    part = msg.get_body(preferencelist=('plain',))
    if part: return part.get_content(), 'plain'
    part = msg.get_body(preferencelist=('html',))
    if part: return html_to_text(part.get_content()), 'html'
    return '', 'none'


# ponytail: regex quote stripping; swap for email-reply-parser when it misfires
QUOTE = re.compile(r'^(On .* wrote:|Am .* schrieb .*:|-----Original Message-----|-----Ursprüngliche Nachricht-----|Von: .*)$', re.M)
def clean(t):
    m = QUOTE.search(t)
    t = t[:m.start()] if m else t
    t = '\n'.join(l for l in t.splitlines() if not l.startswith('>'))
    return t.split('\n-- \n')[0].strip()


SUBJ_PREFIX = re.compile(r'^\s*((re|aw|fwd?|wg|fw)\s*:\s*)+', re.I)
def addrs(msg, h):
    return [{'name': n, 'addr': a.lower()} for n, a in getaddresses(msg.get_all(h, []))]


def record(msg, folder):
    raw, kind = body_of(msg)
    mid = msg.get('Message-ID') or 'sha1:' + hashlib.sha1(
        (msg.get('Date', '') + msg.get('Subject', '') + raw[:500]).encode()).hexdigest()
    try: date = parsedate_to_datetime(msg['Date']).isoformat()
    except Exception: date = None
    frm = addrs(msg, 'From')
    by_folder = 'sent' if folder.startswith('_Sent') else 'received'
    by_addr = 'sent' if frm and frm[0]['addr'] in OWN else ('received' if OWN else None)
    return {
        'id': mid.strip(), 'date': date, 'folder': folder,
        'direction': by_folder, 'direction_mismatch': bool(by_addr and by_addr != by_folder),
        'from': frm, 'to': addrs(msg, 'To'), 'cc': addrs(msg, 'Cc'),
        'subject': msg.get('Subject', ''), 'subject_norm': SUBJ_PREFIX.sub('', msg.get('Subject', '')).strip(),
        'refs': (msg.get('References', '') + ' ' + msg.get('In-Reply-To', '')).split(),
        'body_kind': kind, 'body_raw': raw, 'body': clean(raw),
        'attachments': [p.get_filename() for p in msg.iter_attachments() if p.get_filename()],
        'list_id': msg.get('List-Id'),
        'is_machine': bool(msg.get('List-Id') or msg.get('Auto-Submitted')
                           or msg.get('Precedence') in ('bulk', 'list')
                           or re.search(r'no-?reply|notification|mailer', frm[0]['addr'] if frm else '')),
    }


def messages(root):
    """Yields (msg, folder). Apple Mail: Name.mbox/mbox -> folder 'Name'. Also plain *.mbox files and *.eml."""
    parse = BytesParser(policy=policy.default).parse
    for f in sorted(root.rglob('*')):
        if f.is_dir(): continue
        if f.name == 'mbox' and f.parent.suffix == '.mbox':
            folder, src = f.parent.stem, f
        elif f.suffix == '.mbox':
            folder, src = f.stem, f
        elif f.suffix == '.eml':
            yield parse(f.open('rb')), f.parent.name; continue
        else: continue
        for m in mailbox.mbox(src, factory=parse): yield m, folder


def thread_ids(recs):
    parent = {}
    def find(x):
        while parent.setdefault(x, x) != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for r in recs:
        for ref in r['refs']: parent[find(ref)] = find(r['id'])
    for r in recs: r['thread_id'] = find(r['id'])


def metrics(recs, bad, dupes):
    n = len(recs); c = Counter()
    for r in recs:
        c['html'] += r['body_kind'] == 'html'; c['empty'] += not r['body']
        c['no_mid'] += r['id'].startswith('sha1:'); c['machine'] += r['is_machine']
        c['mismatch'] += r['direction_mismatch']; c['attach'] += bool(r['attachments'])
    lens = sorted(len(r['body'].split()) for r in recs) or [0]
    threads = Counter(r['thread_id'] for r in recs)
    pct = lambda k: f"{100 * c[k] / max(n, 1):.0f}%"
    print(f"{n} emails, {dupes} dupes dropped, {bad} parse failures")
    print(f"html-only {pct('html')}  empty {pct('empty')}  no Message-ID {pct('no_mid')}  machine {pct('machine')}  with attachments {pct('attach')}")
    print(f"direction mismatch (folder vs From) {pct('mismatch')}")
    print(f"body words p50 {statistics.median(lens):.0f}  p95 {lens[int(0.95 * (len(lens) - 1))]}  max {lens[-1]}")
    print(f"threads {len(threads)}, singletons {sum(v == 1 for v in threads.values())}, largest {max(threads.values(), default=0)}")
    print('folders:', dict(Counter(r['folder'] for r in recs)))


def main(root=BRONZE, out=SILVER):
    recs, seen, bad, dupes = [], set(), 0, 0
    for msg, folder in messages(root):
        try: r = record(msg, folder)
        except Exception as e: bad += 1; print('skip:', e, file=sys.stderr); continue
        if r['id'] in seen: dupes += 1; continue
        seen.add(r['id']); recs.append(r)
    thread_ids(recs)
    out.parent.mkdir(exist_ok=True)
    with out.open('w') as f:
        for r in recs: f.write(json.dumps(r, ensure_ascii=False) + '\n')
    metrics(recs, bad, dupes)
    return recs


if __name__ == '__main__':
    main()
