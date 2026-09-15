"""Writes a small synthetic mailbox so the archive can be tried, tested and screenshotted without real mail.
   python demo/make_demo.py [bronze_dir]      default demo/bronze   (then: DATA_DIR=demo OWN_ADDRESSES=@example.com parse + build)"""
# ponytail: stdlib only, deterministic, ~20 mails. Own address is me@example.com. Every name and domain is invented.
import sys, mailbox, random, zlib, struct, shutil
from pathlib import Path
from email.message import EmailMessage

ME = 'Mia Example <me@example.com>'


def png(w=240, h=180, seed=1):
    """A noisy PNG of ~60 KB, big enough to pass the 50 KB image filter."""
    rnd = random.Random(seed); raw = b''.join(b'\x00' + bytes(rnd.randrange(256) for _ in range(w * 3)) for _ in range(h))
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 0)) + chunk(b'IEND', b'')


def mail(mid, frm, to, subj, date, body, refs=None, html=False, headers=None, attach=None):
    m = EmailMessage()
    m['Message-ID'], m['From'], m['To'], m['Subject'], m['Date'] = f'<{mid}@demo.example>', frm, to, subj, date
    if refs: m['References'] = ' '.join(f'<{r}@demo.example>' for r in refs); m['In-Reply-To'] = f'<{refs[-1]}@demo.example>'
    for k, v in (headers or {}).items(): m[k] = v
    m.set_content(body, subtype='html' if html else 'plain')
    if attach: m.add_attachment(attach[1], maintype='image', subtype='png', filename=attach[0])
    return m


ANNA, BEN, LENA, SHOP, BOB = 'Anna Beispiel <anna@beispiel.example>', 'Ben Carter <ben@northwind.example>', 'Lena Ortiz <lena@uni.example>', 'Laden Nord <info@laden-nord.example>', 'Bob <bob@somewhere.example>'
RECEIVED = [
    mail('a1', ANNA, ME, 'Wochenendtrip Bodensee', 'Fri, 03 May 2019 18:12:00 +0200', 'Hi Mia,\n\nhast du Lust auf ein Wochenende am Bodensee Ende Mai? Ich hätte eine Unterkunft in Lindau im Blick.\n\nLiebe Grüße\nAnna\n-- \nAnna Beispiel'),
    mail('a3', ANNA, ME, 'Re: Wochenendtrip Bodensee', 'Sat, 04 May 2019 10:40:00 +0200', 'Super, dann buche ich. Fahrrad mitnehmen?\n\nAnna\n\nAm 03.05.2019 schrieb Mia:\n> Ja, gerne! Der 25. passt mir.', refs=['a1', 'a2']),
    mail('a4', ANNA, ME, 'Fotos vom Wochenende', 'Tue, 28 May 2019 21:05:00 +0200', 'Das schönste Bild vom Steg, wie versprochen.\n\nAnna', attach=('steg.png', png(seed=7))),
    mail('a5', ANNA, ME, 'Externe Platte', 'Sun, 14 Feb 2021 09:30:00 +0100', 'Kurze Frage: die Sicherung auf die externe Platte ist heute Nacht nicht durchgelaufen, das Skript hat einfach abgebrochen. Hattest du das Problem auch mal?\n\nAnna'),
    mail('b1', BEN, ME, 'Quarterly report draft', 'Mon, 08 Mar 2021 09:02:00 +0000', 'Hi Mia,\n\nattached in spirit: the Q1 draft is in the shared folder. Could you look at the revenue chart before Thursday?\n\nThanks,\nBen'),
    mail('b3', BEN, ME, 'Re: Quarterly report draft', 'Tue, 09 Mar 2021 14:15:00 +0000', 'Perfect, thanks for catching the axis label.\n\nBen\n\nOn Mon, Mar 8, 2021 Mia wrote:\n> Looked at it, one comment on the chart.', refs=['b1', 'b2']),
    mail('l1', LENA, ME, 'Conference talk proposal', 'Wed, 15 Jun 2022 11:20:00 +0200', 'Dear Mia,\n\nwould you be up for a joint talk on archiving personal data at the autumn conference? Deadline for proposals is July 1.\n\nBest,\nLena'),
    mail('s2', SHOP, ME, 'Re: Frage zu Bestellung 4711', 'Thu, 11 Jan 2024 08:45:00 +0100', 'Guten Tag,\n\nja, die Lampe ist wieder lieferbar. Wir haben Ihre Bestellung entsprechend ergänzt.\n\nMit freundlichen Grüßen\nLaden Nord', refs=['s1']),
    mail('bob', BOB, ME, 'Kennen wir uns?', 'Sat, 21 Nov 2020 16:00:00 +0100', 'Hallo, wir haben uns glaube ich auf der Konferenz in Hamburg getroffen. Hast du noch die Folien?\n\nBob'),
    mail('n1', 'Weekly Deals <noreply@shop.example>', ME, 'Your weekly deals are here', 'Fri, 07 Oct 2022 06:00:00 +0000', '<html><body><h1>Deals</h1><p>Up to <b>40%</b> off on lamps this week.</p></body></html>', html=True, headers={'List-Id': 'deals.shop.example'}),
    mail('n2', 'Weekly Deals <noreply@shop.example>', ME, 'Last chance: deals end tonight', 'Sun, 09 Oct 2022 06:00:00 +0000', '<html><body><p>Only a few hours left.</p></body></html>', html=True, headers={'List-Id': 'deals.shop.example'}),
    mail('r1', 'Stadtwerke <rechnung@energie.example>', ME, 'Rechnung 2023-0042', 'Mon, 06 Feb 2023 03:10:00 +0100', 'Ihre Rechnung für Januar 2023 liegt im Kundenportal bereit. Betrag: 84,20 EUR.\n\nDiese Nachricht wurde automatisch erstellt.'),
    mail('g1', 'GitHub <notifications@github.example>', ME, '[example/archive] Build failed (#12)', 'Wed, 03 Apr 2024 22:47:00 +0000', 'Run #12 failed on main.\n\nView it on GitHub.', headers={'Precedence': 'bulk'}),
    mail('k1', 'Kanzlei Weber <steuer@kanzlei.example>', ME, 'Steuererklärung 2022', 'Tue, 12 Sep 2023 10:00:00 +0200', 'Sehr geehrte Frau Example,\n\nfür die Steuererklärung 2022 fehlen uns noch die Belege zur Weiterbildung. Können Sie diese bis Ende des Monats nachreichen?\n\nMit freundlichen Grüßen\nKanzlei Weber'),
]
SENT = [
    mail('a2', ME, ANNA, 'Re: Wochenendtrip Bodensee', 'Fri, 03 May 2019 20:01:00 +0200', 'Ja, gerne! Der 25. passt mir.\n\nMia\n\nAm 03.05.2019 schrieb Anna:\n> hast du Lust auf ein Wochenende am Bodensee', refs=['a1']),
    mail('b2', ME, BEN, 'Re: Quarterly report draft', 'Mon, 08 Mar 2021 17:30:00 +0000', 'Looked at it, one comment on the chart: the axis label says 2020.\n\nMia', refs=['b1']),
    mail('l2', ME, LENA, 'Re: Conference talk proposal', 'Thu, 16 Jun 2022 08:05:00 +0200', 'Yes! Let us draft an abstract next week.\n\nMia', refs=['l1']),
    mail('s1', ME, SHOP, 'Frage zu Bestellung 4711', 'Wed, 10 Jan 2024 19:20:00 +0100', 'Guten Abend,\n\nist die Stehlampe aus Bestellung 4711 noch lieferbar?\n\nViele Grüße\nMia Example'),
    mail('k2', ME, 'steuer@kanzlei.example', 'Re: Steuererklärung 2022', 'Wed, 13 Sep 2023 07:55:00 +0200', 'Guten Morgen,\n\ndie Belege kommen bis Freitag.\n\nMia Example', refs=['k1']),
    mail('h1', ME, 'hr@firma.example', 'Bewerbung Praktikum Datenarchivierung', 'Mon, 05 Mar 2018 09:00:00 +0100', 'Sehr geehrte Damen und Herren,\n\nhiermit bewerbe ich mich um das Praktikum im Bereich Datenarchivierung.\n\nMit freundlichen Grüßen\nMia Example'),
]


def make(root):
    root = Path(root); shutil.rmtree(root, ignore_errors=True)
    for name, msgs in (('Inbox.mbox', RECEIVED), ('Inbox_Sent.mbox', SENT)):
        (root / name).mkdir(parents=True); box = mailbox.mbox(root / name / 'mbox')
        for m in msgs: box.add(m)
        box.add(RECEIVED[0]) if name == 'Inbox.mbox' else None   # one duplicate, so the dedupe shows in the metrics
        box.flush()
    return len(RECEIVED) + len(SENT)


if __name__ == '__main__':
    root = sys.argv[1] if len(sys.argv) > 1 else 'demo/bronze'
    print(f'{make(root)} demo mails written to {root}/ (Inbox.mbox, Inbox_Sent.mbox)')
