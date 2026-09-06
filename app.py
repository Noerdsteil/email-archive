"""Search API + static UI.  Run: .venv/bin/uvicorn app:app --reload --port 8000  ->  http://localhost:8000"""
# ponytail: thin HTTP layer over gold.search(); the MCP server calls the same endpoints.
import json
from urllib.parse import quote
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
import gold, parse

app = FastAPI(title='email-archive')
app.add_event_handler('startup', gold.model)   # load the embedding model once, not on first query
app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
def index(): return FileResponse('static/index.html')


@app.get('/api/search')
def search(q: str = '', n: int = 30, from_: str | None = Query(None, alias='from'),
           since: str | None = None, until: str | None = None, human: bool = False, attachments: bool = False):
    if q.strip():
        return gold.search(q, n, from_, since, until, human, attachments)
    c = gold.connect(); where, args = ['1=1'], []              # empty query: newest first, same filters
    if from_: where.append('from_addr like ?'); args.append(f'%{from_}%')
    if since: where.append('date >= ?'); args.append(since)
    if until: where.append('date <= ?'); args.append(until)
    if human: where.append('is_machine = 0')
    if attachments: where.append('has_attachments = 1')
    rows = c.execute(f"select id,thread_id,date,folder,direction,from_addr,from_name,subject,substr(body,1,160) snippet,is_machine,has_attachments from emails where {' and '.join(where)} order by date desc limit ?", [*args, n])
    return [dict(r) | {'score': 0, 'matched': []} for r in rows]


@app.get('/api/email')
def email(id: str):
    c = gold.connect()
    e = c.execute('select id,thread_id,date,folder,direction,from_addr,from_name,to_addrs,subject,body_raw,is_machine,attachments from emails where id=?', (id,)).fetchone()
    if not e: return {'error': 'not found'}
    e = dict(e); e['attachments'] = json.loads(e['attachments'] or '[]')
    e['thread'] = [dict(r) for r in c.execute('select id,date,from_name,from_addr,subject from emails where thread_id=? order by date', (e['thread_id'],))]
    return e


@app.get('/api/attachment')
def attachment(id: str, name: str):
    """Reads the one raw message from bronze by byte range and streams the named part. Nothing is stored."""
    src = gold.connect().execute('select file,start,stop from sources where id=?', (id,)).fetchone()
    if not src: raise HTTPException(404, 'no source for this mail (rerun parse + build)')
    for part in parse.load_message(tuple(src)).iter_attachments():
        if part.get_filename() == name:
            return Response(part.get_payload(decode=True), media_type=part.get_content_type(),
                            headers={'Content-Disposition': f"inline; filename*=UTF-8''{quote(name)}"})
    raise HTTPException(404, 'attachment not found')
