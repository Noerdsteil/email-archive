"""bronze/ (Apple Mail mbox exports or .eml files) -> silver/emails.jsonl

Usage:  python3 parse.py            # reads bronze/, writes silver/emails.jsonl, prints metrics
Env:    OWN_ADDRESSES="me@a.de,@mydomain.de"   decides direction (sent/received); "@domain" matches all aliases
"""
# ponytail: stdlib only. Lesson steps 0-5, 7, 8 in JonasWiki/EMAIL RAG Archive/Preprocessing.md
import os, sys, json, mailbox, hashlib, re, statistics
import settings
from collections import Counter
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, getaddresses
from pathlib import Path
from html.parser import HTMLParser

BRONZE, SILVER = Path(settings.BRONZE), Path(settings.SILVER)
OWN = settings.OWN_ADDRESSES
def is_own(addr):          # entries starting with '@' match a whole domain: "@example.com"
    return addr in OWN or any(addr.endswith(o) for o in OWN if o.startswith('@'))


class _Text(HTMLParser):
    SKIP = {'style', 'script', 'head', 'title'}
    def __init__(self): super().__init__(); self.out = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self.skip += 1
        elif tag in ('br', 'p', 'div', 'tr', 'li', 'h1', 'h2', 'h3'): self.out.append('\n')
    def handle_endtag(self, tag):
        if tag in self.SKIP: self.skip = max(0, self.skip - 1)
    def handle_data(self, d):
        if not self.skip: self.out.append(d)


def html_to_text(h):
    p = _Text(); p.feed(h)
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]+\n', '\n', ''.join(p.out))).strip()


def body_of(msg):
    plain, html = msg.get_body(preferencelist=('plain',)), msg.get_body(preferencelist=('html',))
    text = plain.get_content().strip() if plain else ''
    if text and not (html and len(text) < 200):        # ponytail: a <200-char plain part next to html is a "view in browser" stub
        return text, 'plain'
    if html: return html_to_text(html.get_content()), 'html'
    return text, 'plain' if text else 'none'


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


def record(msg, folder, source):
    raw, kind = body_of(msg)
    mid = msg.get('Message-ID') or 'sha1:' + hashlib.sha1(
        (msg.get('Date', '') + msg.get('Subject', '') + raw[:500]).encode()).hexdigest()
    try: date = parsedate_to_datetime(msg['Date']).isoformat()
    except Exception: date = None
    frm = addrs(msg, 'From'); subj = msg.get('Subject', '').replace('\ufeff', '').strip()
    by_folder = 'sent' if folder.endswith('_Sent') else 'received'
    by_addr = 'sent' if frm and is_own(frm[0]['addr']) else ('received' if OWN else None)
    return {
        'id': mid.strip(), 'date': date, 'folder': folder, 'source': source,
        # ponytail: the From address decides; the folder suffix is only the fallback when OWN_ADDRESSES is unset
        'direction': by_addr or by_folder, 'direction_mismatch': bool(by_addr and by_addr != by_folder),
        'from': frm, 'to': addrs(msg, 'To'), 'cc': addrs(msg, 'Cc'),
        'subject': subj, 'subject_norm': SUBJ_PREFIX.sub('', subj).strip(),
        'refs': (msg.get('References', '') + ' ' + msg.get('In-Reply-To', '')).split(),
        'body_kind': kind, 'body_raw': raw, 'body': clean(raw),
        'attachments': [p.get_filename() for p in msg.iter_attachments() if p.get_filename()],
        'list_id': msg.get('List-Id'),
        'is_machine': bool(msg.get('List-Id') or msg.get('Auto-Submitted')
                           or msg.get('Precedence') in ('bulk', 'list')
                           or looks_machine(frm[0]['addr'] if frm else '')),
    }


MACHINE_ADDR = re.compile(r'no[-_]?reply|keine.antwort|invoic|notification|mailer|rechnung|service@|kundenservice|newsletter|news@|webmaster@|marketing@|versand|^info@|^hello@|^team@|^support@|^mail@|^kontakt@|^contact@')
def looks_machine(addr): return bool(MACHINE_ADDR.search(addr))


def classify(recs):
    """sender_class: human | machine | unknown, plus silver/contacts.json.
    Contacts = everyone I ever wrote to (To/Cc of sent mail) except myself. Contacts beat patterns, so a shop I wrote
    to first stays human. Threads inherit human. Second pass, needs all records.
    ponytail: an accidental reply to a noreply address makes that sender human; fix by hand in contacts.json if it ever matters."""
    contacts = Counter(a['addr'] for r in recs if r['direction'] == 'sent' for a in r['to'] + r['cc'] if not is_own(a['addr']))
    for r in recs:
        frm = r['from'][0]['addr'] if r['from'] else ''
        r['sender_class'] = ('human' if r['direction'] == 'sent' or frm in contacts
                             else 'machine' if r['is_machine'] else 'unknown')
    human_threads = {r['thread_id'] for r in recs if r['sender_class'] == 'human'}
    for r in recs:
        if r['sender_class'] == 'unknown' and r['thread_id'] in human_threads: r['sender_class'] = 'human'
    return contacts


def messages(root):
    """Yields (msg, folder, source). source = [file, start, stop] locates the raw message in bronze for load_message()."""
    parse = BytesParser(policy=policy.default).parse
    for f in sorted(root.rglob('*')):
        if f.is_dir(): continue
        if f.name == 'mbox' and f.parent.suffix == '.mbox':
            folder, src = f.parent.stem, f
        elif f.suffix == '.mbox':
            folder, src = f.stem, f
        elif f.suffix == '.eml':
            yield parse(f.open('rb')), f.parent.name, [str(f), 0, f.stat().st_size]; continue
        else: continue
        mb = mailbox.mbox(src, factory=parse)
        for key, m in mb.iteritems():
            start, stop = mb._toc[key]                    # ponytail: private but unchanged since 2.5; start points at the "From " line
            yield m, folder, [str(src), start, stop]


def load_message(source):
    """Re-read one raw message from bronze by [file, start, stop]. Used for attachments / show-original."""
    file, start, stop = source
    with open(file, 'rb') as fh:
        fh.seek(start)
        if fh.readline()[:5] != b'From ': fh.seek(start)   # .eml has no From_ separator
        return BytesParser(policy=policy.default).parsebytes(fh.read(stop - fh.tell()))


def thread_ids(recs):
    parent = {}
    def find(x):
        while parent.setdefault(x, x) != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for r in recs:
        for ref in r['refs']: parent[find(ref)] = find(r['id'])
    for r in recs: r['thread_id'] = find(r['id'])


def metrics(recs, bad, dupes, contacts=0, read=None):
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
    cls = Counter(r['sender_class'] for r in recs)
    print(f"sender class: " + '  '.join(f"{k} {100 * v / max(n, 1):.0f}%" for k, v in sorted(cls.items())) + f"  |  contacts {contacts}")
    print(f"body words p50 {statistics.median(lens):.0f}  p95 {lens[int(0.95 * (len(lens) - 1))]}  max {lens[-1]}")
    print(f"threads {len(threads)}, singletons {sum(v == 1 for v in threads.values())}, largest {max(threads.values(), default=0)}")
    kept = Counter(r['folder'] for r in recs); read = read or kept
    print('folders (kept/read):', '  '.join(f"{f} {kept[f]}/{read[f]}" for f in sorted(read)))   # kept 0 = every mail already in an earlier folder


def main(root=BRONZE, out=SILVER):
    recs, seen, bad, dupes, read = [], set(), 0, 0, Counter()
    for msg, folder, source in messages(root):
        read[folder] += 1
        try: r = record(msg, folder, source)
        except Exception as e: bad += 1; print('skip:', e, file=sys.stderr); continue
        if r['id'] in seen: dupes += 1; continue
        seen.add(r['id']); recs.append(r)
    thread_ids(recs)
    contacts = classify(recs)
    out.parent.mkdir(exist_ok=True)
    with out.open('w') as f:
        for r in recs: f.write(json.dumps(r, ensure_ascii=False) + '\n')
    (out.parent / 'contacts.json').write_text(json.dumps(dict(contacts.most_common()), ensure_ascii=False, indent=0))
    metrics(recs, bad, dupes, len(contacts), read)
    return recs


if __name__ == '__main__':
    main()
