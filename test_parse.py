"""Smallest check that fails if parsing, cleaning, dedupe, threading or direction break.  Run: python3 test_parse.py"""
import mailbox, tempfile, os
from email.message import EmailMessage
from pathlib import Path
import parse

def mail(mid, frm, to, subj, body, refs=None, html=False):
    m = EmailMessage()
    m['Message-ID'], m['From'], m['To'], m['Subject'] = mid, frm, to, subj
    m['Date'] = 'Mon, 01 Sep 2025 10:00:00 +0200'
    if refs: m['References'] = refs
    m.set_content(body, subtype='html' if html else 'plain')
    return m

with tempfile.TemporaryDirectory() as d:
    d = Path(d); os.environ['OWN_ADDRESSES'] = 'me@x.de'; parse.OWN = {'me@x.de'}
    inbox = d / 'bronze/Inbox.mbox'; sent = d / 'bronze/Inbox_Sent.mbox'
    inbox.mkdir(parents=True); sent.mkdir(parents=True)
    a = mailbox.mbox(inbox / 'mbox')
    a.add(mail('<1@x>', 'Anna <anna@y.de>', 'me@x.de', 'Angebot', 'Hallo Jonas,\nhier das Angebot.\n-- \nAnna'))
    a.add(mail('<1@x>', 'Anna <anna@y.de>', 'me@x.de', 'Angebot', 'dupe'))          # duplicate Message-ID
    a.add(mail('<3@x>', 'News <noreply@shop.de>', 'me@x.de', 'Deals', '<p>Big <b>sale</b></p>', html=True))
    a.flush()
    s = mailbox.mbox(sent / 'mbox')
    s.add(mail('<2@x>', 'me@x.de', 'anna@y.de', 'Re: Angebot', 'Danke!\n\nAm 1.9. schrieb Anna:\n> hier das Angebot', refs='<1@x>'))
    s.flush()

    recs = {r['id']: r for r in parse.main(d / 'bronze', d / 'silver/emails.jsonl')}

    assert len(recs) == 3, recs.keys()                                   # dedupe
    assert recs['<1@x>']['body'] == 'Hallo Jonas,\nhier das Angebot.'    # signature stripped
    assert recs['<2@x>']['body'] == 'Danke!'                             # quote stripped
    assert recs['<2@x>']['subject_norm'] == 'Angebot'
    assert recs['<1@x>']['thread_id'] == recs['<2@x>']['thread_id']      # threaded via References
    assert recs['<3@x>']['thread_id'] != recs['<1@x>']['thread_id']
    assert recs['<3@x>']['body_kind'] == 'html' and 'Big sale' in recs['<3@x>']['body'] and recs['<3@x>']['is_machine']
    assert recs['<2@x>']['direction'] == 'sent' and not recs['<2@x>']['direction_mismatch']
    assert recs['<1@x>']['direction'] == 'received' and not recs['<1@x>']['direction_mismatch']
    assert (d / 'silver/emails.jsonl').read_text().count('\n') == 3
print('ok')
