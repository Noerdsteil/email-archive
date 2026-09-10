"""Self-check for the MCP endpoint: python test_mcp.py [http://localhost:8000/mcp]. Prints counts and keys only, never mail content."""
import asyncio, sys, json
from mcp.client.client import Client

async def main(url):
    async with Client(url) as c:
        tools = {t.name for t in (await c.list_tools()).tools}
        assert tools == {'search_emails', 'get_email'}, tools
        r = await c.call_tool('search_emails', {'q': 'test', 'n': 2})
        hits = r.structured_content['result']
        assert 0 < len(hits) <= 2 and {'id', 'date', 'subject', 'snippet'} <= set(hits[0]), hits and list(hits[0])
        r = await c.call_tool('get_email', {'id': hits[0]['id']}); e = r.structured_content or json.loads(r.content[0].text)
        assert {'body', 'thread', 'attachments'} <= set(e) and 'body_raw' not in e, list(e)
        r = await c.call_tool('get_email', {'id': 'nope'}); assert 'error' in (r.structured_content or json.loads(r.content[0].text))
        print(f'mcp ok: {len(tools)} tools, {len(hits)} hits, body {len(e["body"])} chars, thread {len(e["thread"])}')

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000/mcp'))
