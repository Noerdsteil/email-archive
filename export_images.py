"""One-time: dump every image attached to mail from/to contacts (sender_class = human) into a folder.
   python export_images.py [out_dir] [min_kb]     default exports/images, 50 KB (drops signature logos and tracking pixels)"""
# ponytail: reads silver for the list, bronze for the bytes (same path the attachment endpoint uses). No DB, no state.
import sys, json, re, hashlib, pathlib
import parse

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'exports/images'); out.mkdir(parents=True, exist_ok=True)
min_bytes = int(sys.argv[2] if len(sys.argv) > 2 else 50) * 1024
recs = [r for r in map(json.loads, open('silver/emails.jsonl')) if r.get('sender_class') == 'human' and r.get('source')]
seen, n_img, n_small, n_written, n_mails_with = set(), 0, 0, 0, 0
for r in recs:
    found = False
    for part in parse.load_message(tuple(r['source'])).walk():
        if part.get_content_maintype() != 'image': continue
        data = part.get_payload(decode=True) or b''; n_img += 1
        if len(data) < min_bytes: n_small += 1; continue
        h = hashlib.sha1(data).hexdigest()
        if h in seen: continue                    # same photo forwarded twice
        seen.add(h); found = True
        who = re.sub(r'[^a-z0-9]+', '-', (r['from'][0]['addr'] if r['from'] else 'unknown').split('@')[0].lower()).strip('-')
        name = re.sub(r'[^\w.\-]+', '_', part.get_filename() or f"inline.{part.get_content_subtype()}")
        stem, ext = name.rsplit('.', 1) if '.' in name else (name, part.get_content_subtype())
        (out / f"{(r['date'] or 'undated')[:10]}_{who}_{h[:6]}_{stem[:80]}.{ext}").write_bytes(data); n_written += 1
    n_mails_with += found
print(f"{len(recs)} human mails scanned, {n_img} image parts, {n_small} below {min_bytes // 1024} KB, {n_written} unique images written from {n_mails_with} mails -> {out}/")
