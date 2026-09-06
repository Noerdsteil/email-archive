"""silver/emails.jsonl -> gold.db (SQLite: metadata columns + FTS5 + sqlite-vec), and hybrid search.

  python gold.py build [--limit N] [--rebuild]      upsert new emails (newest first), embed, index
  python gold.py search "query" [--from x] [--since 2020-01-01] [--until ...] [--human] [--attachments] [-n 10]
"""
# ponytail: one file, one DB. Search API and MCP call search() from here.
import sys, json, sqlite3, argparse, time, os
import sqlite_vec
from fastembed import TextEmbedding

DB, SILVER, MODEL, DIM = 'gold.db', 'silver/emails.jsonl', 'jinaai/jina-embeddings-v2-base-de', 768
_model = None


def model():
    global _model
    if _model is None:
        os.environ.setdefault('HF_HUB_OFFLINE', '1')          # models/ is the only source after first download
        _model = TextEmbedding(MODEL, cache_dir='models')
    return _model


def connect():
    c = sqlite3.connect(DB); c.enable_load_extension(True); sqlite_vec.load(c); c.enable_load_extension(False)
    c.row_factory = sqlite3.Row
    c.executescript(f'''
      create table if not exists meta(key text primary key, value text);
      create table if not exists emails(
        rowid integer primary key, id text unique, thread_id text, date text, folder text, direction text,
        from_addr text, from_name text, to_addrs text, subject text, body text, body_raw text,
        is_machine integer, attachments text, has_attachments integer);
      create index if not exists emails_date on emails(date);
      create index if not exists emails_from on emails(from_addr);
      create virtual table if not exists fts using fts5(subject, body, from_name, from_addr, content='emails', content_rowid='rowid');
      create virtual table if not exists vec using vec0(rowid integer primary key, embedding float[{DIM}]);
    ''')
    stored = c.execute("select value from meta where key='model'").fetchone()
    if stored and stored[0] != MODEL:
        sys.exit(f'gold.db was built with {stored[0]}, code says {MODEL}. Run build --rebuild.')
    if not stored: c.execute("insert into meta values('model', ?)", (MODEL,)); c.commit()
    return c


def embed_text(r):
    f = r['from'][0] if r['from'] else {'name': '', 'addr': ''}
    return f"From: {f['name']} <{f['addr']}> | Date: {(r['date'] or '')[:10]} | Subject: {r['subject']}\n{r['body']}"


def build(limit=None, rebuild=False):
    if rebuild and os.path.exists(DB): os.remove(DB)
    c = connect()
    recs = [json.loads(l) for l in open(SILVER)]
    recs.sort(key=lambda r: r['date'] or '', reverse=True)
    if limit: recs = recs[:limit]
    have = {row[0] for row in c.execute('select id from emails')}
    new = [r for r in recs if r['id'] not in have]
    print(f'{len(recs)} in silver, {len(have)} already in gold, {len(new)} to add')
    if not new: return
    t = time.time(); vecs = list(model().embed([embed_text(r) for r in new], batch_size=16))
    print(f'embedded in {time.time() - t:.0f}s')
    for r, v in zip(new, vecs):
        f = r['from'][0] if r['from'] else {'name': '', 'addr': ''}
        cur = c.execute('insert into emails(id,thread_id,date,folder,direction,from_addr,from_name,to_addrs,subject,body,body_raw,is_machine,attachments,has_attachments) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (r['id'], r['thread_id'], r['date'], r['folder'], r['direction'], f['addr'], f['name'],
                         ' '.join(t['addr'] for t in r['to']), r['subject'], r['body'], r['body_raw'], int(r['is_machine']), json.dumps(r['attachments']), int(bool(r['attachments']))))
        c.execute('insert into fts(rowid,subject,body,from_name,from_addr) values(?,?,?,?,?)', (cur.lastrowid, r['subject'], r['body'], f['name'], f['addr']))
        c.execute('insert into vec(rowid,embedding) values(?,?)', (cur.lastrowid, sqlite_vec.serialize_float32(v.tolist())))
    c.commit(); print(f'gold.db now {c.execute("select count(*) from emails").fetchone()[0]} emails')


def fts_query(q):
    toks = [t.replace('"', '') for t in q.split() if t.replace('"', '')]
    return ' '.join(f'"{t}"' for t in toks[:-1]) + (f' "{toks[-1]}"*' if toks else '')   # prefix match on last token


def search(q, n=10, from_=None, since=None, until=None, human=False, attachments=False, k=60):
    c = connect()
    where, args = [], []
    if from_: where.append('emails.from_addr like ?'); args.append(f'%{from_}%')
    if since: where.append('emails.date >= ?'); args.append(since)
    if until: where.append('emails.date <= ?'); args.append(until)
    if human: where.append('emails.is_machine = 0')
    if attachments: where.append('emails.has_attachments = 1')
    filt = (' and ' + ' and '.join(where)) if where else ''

    fts = c.execute(f'select fts.rowid from fts join emails on emails.rowid = fts.rowid where fts match ? {filt} order by bm25(fts) limit ?', [fts_query(q), *args, k]).fetchall()
    qv = sqlite_vec.serialize_float32(next(model().query_embed(q)).tolist())
    vec = c.execute(f'select v.rowid from (select rowid, distance from vec where embedding match ? and k = ?) v join emails on emails.rowid = v.rowid where 1=1 {filt} order by distance limit ?', [qv, k * 4, *args, k]).fetchall()

    scores = {}                                            # ponytail: reciprocal rank fusion, weight 1:1
    for src, rows in (('fts', fts), ('vec', vec)):
        for rank, row in enumerate(rows):
            s = scores.setdefault(row[0], {'score': 0, 'src': []}); s['score'] += 1 / (60 + rank); s['src'].append(src)
    top = sorted(scores.items(), key=lambda kv: -kv[1]['score'])[:n]
    out = []
    for rowid, s in top:
        e = dict(c.execute('select id,thread_id,date,folder,direction,from_addr,from_name,subject,body,is_machine,has_attachments from emails where rowid=?', (rowid,)).fetchone())
        e['snippet'] = e.pop('body')[:160].replace('\n', ' '); e.update(score=round(s['score'], 4), matched=s['src']); out.append(e)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build'); b.add_argument('--limit', type=int); b.add_argument('--rebuild', action='store_true')
    s = sub.add_parser('search'); s.add_argument('q'); s.add_argument('-n', type=int, default=10)
    s.add_argument('--from', dest='from_'); s.add_argument('--since'); s.add_argument('--until'); s.add_argument('--human', action='store_true'); s.add_argument('--attachments', action='store_true')
    a = p.parse_args()
    if a.cmd == 'build': build(a.limit, a.rebuild)
    else:
        t = time.time(); hits = search(a.q, a.n, a.from_, a.since, a.until, a.human, a.attachments)
        for h in hits: print(f"{h['score']:.4f} {'+'.join(h['matched']):7} {(h['date'] or '')[:10]} {h['from_addr'][:28]:28} {h['subject'][:50]}")
        print(f'{len(hits)} hits in {(time.time() - t) * 1000:.0f} ms (incl. model load)')
