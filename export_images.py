"""Dump every image attached to a set of mails into a folder. Files are named date_sender_hash_name and dated like the mail.
   CLI (one-time, from silver, contacts only):  python export_images.py [out_dir] [min_kb]
   API: app.py calls run() with the UI filters applied in SQL."""
# ponytail: reads bronze by byte range (same path as the attachment endpoint). No DB writes, no state; reruns overwrite.
import sys, os, json, re, hashlib, pathlib
from datetime import datetime
import parse, settings

OUT, MIN_KB = settings.IMAGE_DIR, settings.IMAGE_MIN_KB   # below 50 KB it is a logo, a signature or a tracking pixel


def run(mails, out=OUT, min_kb=MIN_KB):
    """mails: iterable of dicts with date, from_addr, source=[file,start,stop]. Returns counts."""
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True); min_bytes = min_kb * 1024
    seen, st = set(), {'mails': 0, 'images': 0, 'small': 0, 'written': 0, 'mails_with': 0, 'out': str(out)}
    for r in mails:
        st['mails'] += 1; found = False
        for part in parse.load_message(tuple(r['source'])).walk():
            if part.get_content_maintype() != 'image': continue
            data = part.get_payload(decode=True) or b''; st['images'] += 1
            if len(data) < min_bytes: st['small'] += 1; continue
            h = hashlib.sha1(data).hexdigest()
            if h in seen: continue                    # same photo forwarded twice
            seen.add(h); found = True
            who = re.sub(r'[^a-z0-9]+', '-', (r['from_addr'] or 'unknown').split('@')[0].lower()).strip('-')
            name = re.sub(r'[^\w.\-]+', '_', part.get_filename() or f"inline.{part.get_content_subtype()}")
            stem, ext = name.rsplit('.', 1) if '.' in name else (name, part.get_content_subtype())
            f = out / f"{(r['date'] or 'undated')[:10]}_{who}_{h[:6]}_{stem[:80]}.{ext}"; f.write_bytes(data); st['written'] += 1
            if r['date']: ts = datetime.fromisoformat(r['date']).timestamp(); os.utime(f, (ts, ts))   # file date = mail date; macOS pulls the creation date back too
        st['mails_with'] += found
    return st


if __name__ == '__main__':
    recs = ({'date': r['date'], 'from_addr': r['from'][0]['addr'] if r['from'] else '', 'source': r['source']}
            for r in map(json.loads, open(settings.SILVER)) if r.get('sender_class') == 'human' and r.get('source'))
    st = run(recs, sys.argv[1] if len(sys.argv) > 1 else OUT, int(sys.argv[2]) if len(sys.argv) > 2 else MIN_KB)
    print(f"{st['mails']} mails scanned, {st['images']} image parts, {st['small']} small, {st['written']} unique images from {st['mails_with']} mails -> {st['out']}/")
