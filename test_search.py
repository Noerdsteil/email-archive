"""End-to-end: demo mailbox -> parse -> gold build -> three searches. Needs the embedding model (downloads into MODEL_DIR on first run).
   Run: python test_search.py     (~30 s, all inside a temp dir, never touches your archive)"""
import os, sys, tempfile, subprocess
tmp = tempfile.mkdtemp(); os.environ.update(DATA_DIR=tmp, OWN_ADDRESSES='@example.com')   # before the imports: settings reads env once
import parse, gold

subprocess.run([sys.executable, 'demo/make_demo.py', f'{tmp}/bronze'], check=True)
recs = parse.main(); assert len(recs) == 20, len(recs)
gold.build()
assert gold.connect().execute('select count(*) from emails').fetchone()[0] == 20

hit = gold.search('Bodensee', n=3)                                      # keyword: FTS must hit and rank the thread first
assert 'Bodensee' in hit[0]['subject'] and 'fts' in hit[0]['matched'], hit[0]
para = gold.search('Backup fehlgeschlagen', n=3)                        # paraphrase: no shared word, only the vector side can find it
assert any(h['subject'] == 'Externe Platte' and 'vec' in h['matched'] for h in para), [(h['subject'], h['matched']) for h in para]
humans = gold.search('Rechnung', n=10, human=True)                      # filter: the automated invoice is out, the shop I wrote to stays
assert all(h['from_addr'] != 'rechnung@energie.example' for h in humans), humans
att = gold.search('Foto', n=10, attachments=True)
assert [h['subject'] for h in att] == ['Fotos vom Wochenende'], att
print(f'search ok: 20 mails, keyword/paraphrase/filters pass ({tmp})')
