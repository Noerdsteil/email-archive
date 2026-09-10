"""Search API + static UI + MCP.  Run: .venv/bin/uvicorn app:app --reload --port 8000  ->  http://localhost:8000, MCP at /mcp"""
# ponytail: thin HTTP layer over gold.search(); the MCP tools below call the same functions, no search logic of their own.
import json
from typing import Any
from contextlib import asynccontextmanager
from urllib.parse import quote
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from mcp.server.mcpserver import MCPServer
import gold, parse

mcp = MCPServer('email-archive', instructions=(
    'Private personal email archive, German and English. Call search_emails first (short results), then get_email for the '
    'full text of the one or two mails that matter. Dates are ISO (YYYY-MM-DD). human=true keeps only mail from real people.'))


@asynccontextmanager
async def lifespan(app):
    gold.model()                                   # load the embedding model once, not on first query
    async with mcp.session_manager.run(): yield    # mounted apps do not get their own lifespan run

app = FastAPI(title='email-archive', lifespan=lifespan)
app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
def index(): return FileResponse('static/index.html')


@app.get('/api/search')
def search(q: str = '', n: int = 30, from_: str | None = Query(None, alias='from'),
           since: str | None = None, until: str | None = None, human: bool = False, attachments: bool = False,
           before: str | None = None):
    if q.strip():
        return gold.search(q, n, from_, since, until, human, attachments)
    c = gold.connect(); where, args = ['1=1'], []              # empty query: newest first, same filters
    if before:                                                  # keyset cursor "date|id" from the last row -> infinite scroll
        bd, _, bid = before.partition('|'); where.append("(coalesce(date,'') < ? or (coalesce(date,'') = ? and e.id < ?))"); args += [bd, bd, bid]
    if from_: where.append('from_addr like ?'); args.append(f'%{from_}%')
    if since: where.append('date >= ?'); args.append(since)
    if until: where.append('date <= ?'); args.append(until)
    if human: where.append("e.id in (select id from classes where sender_class='human')")
    if attachments: where.append('has_attachments = 1')
    rows = c.execute(f"select e.id,thread_id,date,folder,direction,from_addr,from_name,subject,substr(body,1,160) snippet,is_machine,has_attachments,coalesce(sender_class,'unknown') sender_class from emails e left join classes using(id) where {' and '.join(where)} order by coalesce(date,'') desc, e.id desc limit ?", [*args, n])
    out = [dict(r) | {'score': 0, 'matched': []} for r in rows]
    if len(out) == n: out[-1]['next'] = f"{out[-1]['date'] or ''}|{out[-1]['id']}"
    return out


@app.get('/api/email')
def email(id: str):
    c = gold.connect()
    e = c.execute("select e.id,thread_id,date,folder,direction,from_addr,from_name,to_addrs,subject,body_raw,is_machine,attachments,coalesce(sender_class,'unknown') sender_class from emails e left join classes using(id) where e.id=?", (id,)).fetchone()
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


# --- MCP: two tools over the same functions. Descriptions are what the model sees; keep them honest and results small.
@mcp.tool()
def search_emails(q: str, from_: str = '', since: str = '', until: str = '', human: bool = False, attachments: bool = False, n: int = 10) -> list[dict]:
    """Hybrid keyword + semantic search over the personal mail archive. q may be German or English, a phrase or a topic.
    from_ filters the sender address (substring), since/until are ISO dates, human=true drops newsletters and automated mail,
    attachments=true keeps only mail with attachments. Returns id, date, from, subject, a 160-char snippet and sender_class per hit."""
    hits = gold.search(q, n, from_ or None, since or None, until or None, human, attachments)
    return [{k: h[k] for k in ('id', 'date', 'from_addr', 'from_name', 'subject', 'snippet', 'sender_class', 'has_attachments')} for h in hits]


@mcp.tool()
def get_email(id: str) -> dict[str, Any]:
    """Full text of one mail by id (from search_emails), quotes and signatures stripped, plus recipients, folder, direction,
    attachment file names and the thread it belongs to (id, date, from, subject per message)."""
    e = email(id)
    if 'error' in e: return e
    e['body'] = gold.connect().execute('select body from emails where id=?', (id,)).fetchone()[0]
    return {k: e[k] for k in ('id', 'date', 'from_addr', 'from_name', 'to_addrs', 'subject', 'folder', 'direction', 'sender_class', 'attachments', 'body', 'thread')}


app.mount('/mcp', mcp.streamable_http_app(streamable_http_path='/', stateless_http=True, json_response=True))   # localhost-only by default (DNS-rebinding guard)
