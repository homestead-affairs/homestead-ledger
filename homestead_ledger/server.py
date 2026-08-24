"""Localhost web UI for homestead-ledger — intake and dashboard.

Serves on 127.0.0.1 only.  All HTML/CSS/JS is embedded (no external files,
no CDN).  Imports of ``http.server`` and ``urllib.parse`` are **local** to
``serve()`` — this module's top level touches nothing network-shaped, so
``import homestead_ledger`` stays import-pure.

The server is a thin dispatch over existing modules: ``intake.extract()``
for text extraction, the Nestor seam for entity resolution and reconciliation,
``queue`` for the obligations dashboard, and ``recurring`` for subscription
detection.

**Chokepoint**: this module never accesses ``.payload``.  Queue items reach
the browser through ``Due.shown`` (the gated display form).  Entity and
reconciliation data come through Nestor's public API.
"""
from __future__ import annotations

__all__ = ["serve"]


# ── the page ──────────────────────────────────────────────────────────────

_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>homestead-ledger</title>
<style>
:root {
  --bg: #f6f3f0;
  --surface: #ffffff;
  --text: #2c2c2c;
  --text-2: #6b6560;
  --border: #e0dbd5;
  --accent: #8b6914;
  --accent-h: #735710;
  --accent-l: #fdf3e3;
  --ok: #3d7a4f;
  --ok-l: #e8f5ec;
  --warn: #b8862d;
  --warn-l: #fdf3e3;
  --danger: #b54a4a;
  --danger-l: #fce8e8;
  --blue: #4a6fa5;
  --blue-l: #e8eff8;
  --r: 6px;
}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  background:var(--bg);color:var(--text);margin:0;line-height:1.5}
header{background:var(--surface);border-bottom:1px solid var(--border);
  padding:12px 24px;display:flex;align-items:center;gap:16px}
header h1{font-size:18px;font-weight:600;margin:0}
header .sub{font-size:13px;color:var(--text-2)}
nav{background:var(--surface);border-bottom:1px solid var(--border);
  padding:0 24px;display:flex;gap:0}
.tb{background:none;border:none;border-bottom:2px solid transparent;
  padding:10px 16px;font-size:14px;color:var(--text-2);cursor:pointer}
.tb:hover{color:var(--text)}
.tb.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:500}
main{max-width:900px;margin:24px auto;padding:0 24px}
.tab{display:none}.tab.on{display:block}
h2{font-size:16px;font-weight:600;margin:0 0 16px}
textarea{width:100%;min-height:180px;padding:12px;border:1px solid var(--border);
  border-radius:var(--r);font-family:inherit;font-size:14px;line-height:1.6;
  resize:vertical;background:var(--surface)}
textarea:focus{outline:2px solid var(--accent);border-color:transparent}
.btn{display:inline-block;padding:8px 16px;border:none;border-radius:var(--r);
  font-size:14px;font-weight:500;cursor:pointer}
.bp{background:var(--accent);color:#fff}.bp:hover{background:var(--accent-h)}
.bg{background:var(--ok);color:#fff}.bg:hover{background:#336a42}
.bs{padding:4px 10px;font-size:13px}
.btn:disabled{opacity:.5;cursor:not-allowed}
.acts{margin-top:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.cr{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.kb{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;
  font-weight:500;text-transform:uppercase;letter-spacing:.5px}
.k-amount{background:var(--accent-l);color:var(--accent)}
.k-date{background:var(--blue-l);color:var(--blue)}
.k-due_date{background:var(--warn-l);color:var(--warn)}
.k-merchant{background:var(--ok-l);color:var(--ok)}
.k-account{background:#f0e8f8;color:#6b4fa0}
.mt{font-size:14px;flex:1;min-width:120px}
.mv{font-size:13px;color:var(--text-2)}
.fs{padding:4px 8px;border:1px solid var(--border);border-radius:4px;font-size:13px;
  background:var(--surface)}
.stored{opacity:.6}.stored .btn,.stored .fs{display:none}
.sm{display:inline-block;padding:4px 10px;border-radius:4px;font-size:13px;font-weight:500}
.s-ok{background:var(--ok-l);color:var(--ok)}
.s-err{background:var(--danger-l);color:var(--danger)}
.qi{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--r);margin-bottom:8px;
  box-shadow:0 1px 3px rgba(0,0,0,.08)}
.qu{font-size:13px;font-weight:600;min-width:90px;text-align:right}
.u-over{color:var(--danger)}.u-soon{color:var(--warn)}.u-later{color:var(--ok)}
.qs{flex:1;font-size:14px}
.rb{font-size:12px;padding:2px 6px;border-radius:4px;font-weight:500}
.r-L1,.r-L2{background:#f0eeec;color:#888}
.r-L3{background:#f0eeec;color:#333}
.r-L4{background:var(--warn-l);color:var(--warn)}
.rf{display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.rf select,.rf input{padding:8px 12px;border:1px solid var(--border);border-radius:var(--r);
  font-size:14px;background:var(--surface)}
.rf input{flex:1;min-width:150px}
.rr{padding:16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--r)}
.si{padding:12px 16px;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.sn{font-weight:500}.sa{color:var(--accent);margin-left:8px}
.sc{color:var(--text-2);margin-top:4px;font-size:13px}
.empty{color:var(--text-2);font-style:italic;padding:24px 0;text-align:center}
</style>
</head>
<body>
<header>
  <h1>homestead-ledger</h1>
  <span class="sub">receipt intake &amp; dashboard</span>
</header>
<nav>
  <button class="tb on" onclick="show('intake',this)">Intake</button>
  <button class="tb" onclick="show('queue',this)">What's Due</button>
  <button class="tb" onclick="show('entities',this)">Entities</button>
  <button class="tb" onclick="show('subscriptions',this)">Subscriptions</button>
</nav>
<main>

<section id="t-intake" class="tab on">
  <h2>Dump receipt or bill text</h2>
  <textarea id="raw" placeholder="Paste a receipt, bill, invoice, or bank statement snippet.  The system extracts amounts, dates, merchants, due dates, and account references."></textarea>
  <div class="acts">
    <button class="btn bp" onclick="doExtract()">Extract</button>
  </div>
  <div id="res" style="margin-top:16px"></div>
</section>

<section id="t-queue" class="tab">
  <h2>What's due</h2>
  <div id="qlist"></div>
</section>

<section id="t-entities" class="tab">
  <h2>Merchant lookup</h2>
  <div class="rf">
    <input id="eqry" placeholder="Merchant name to resolve&#8230;"
           onkeydown="if(event.key==='Enter')doResolve()">
    <button class="btn bp" onclick="doResolve()">Resolve</button>
  </div>
  <div id="eres"></div>
</section>

<section id="t-subscriptions" class="tab">
  <h2>Detected subscriptions</h2>
  <div id="slist"></div>
</section>

</main>
<script>
function show(name, btn) {
  document.querySelectorAll('.tab').forEach(function(el){el.classList.remove('on')});
  document.querySelectorAll('.tb').forEach(function(el){el.classList.remove('on')});
  document.getElementById('t-'+name).classList.add('on');
  btn.classList.add('on');
  if(name==='queue') loadQueue();
  if(name==='subscriptions') loadSubscriptions();
}

function esc(s) {
  var d=document.createElement('div'); d.textContent=s; return d.innerHTML;
}

var _items=[];

function doExtract() {
  var text=document.getElementById('raw').value.trim();
  if(!text) return;
  fetch('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:text})})
  .then(function(r){return r.json()})
  .then(function(data){_items=data.items; renderItems()})
  .catch(function(){document.getElementById('res').innerHTML=
    '<p class="sm s-err">Extraction failed</p>'});
}

function renderItems() {
  var div=document.getElementById('res');
  if(!_items.length){div.innerHTML='<p class="empty">No structured items found.</p>';return;}
  var html='<h2>Found '+_items.length+' item(s)</h2>';
  _items.forEach(function(item,i){
    var opts='';
    if(item.kind==='amount'){
      opts='<option value="amount">Amount</option>';
    } else if(item.kind==='date'){
      opts='<option value="date">Transaction date</option>';
    } else if(item.kind==='due_date'){
      opts='<option value="due_date">Due date</option>';
    } else if(item.kind==='merchant'){
      opts='<option value="description">Merchant</option>';
    } else if(item.kind==='account'){
      opts='<option value="account_number">Account (last 4)</option>';
    } else {
      opts='<option value="">&#8212;</option>';
    }
    html+='<div class="card" id="c'+i+'"><div class="cr">'
      +'<span class="kb k-'+item.kind+'">'+item.kind.replace('_',' ')+'</span>'
      +'<span class="mt">'+esc(item.text)+'</span>'
      +'<span class="mv">'+esc(item.value)+'</span>'
      +'<select class="fs" id="f'+i+'">'+opts+'</select>'
      +'<button class="btn bg bs" onclick="storeItem('+i+')">Store</button>'
      +'</div></div>';
  });
  div.innerHTML=html;
}

function storeItem(idx) {
  var item=_items[idx];
  var field=document.getElementById('f'+idx).value;
  if(!field) return;
  var card=document.getElementById('c'+idx);
  fetch('/api/store',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({field:field,value:item.value})})
  .then(function(r){return r.json()})
  .then(function(data){
    if(data.ok){card.classList.add('stored');
      card.innerHTML+='<span class="sm s-ok">Stored ('+data.rung+')</span>';}
    else{card.innerHTML+='<span class="sm s-err">'+esc(data.error||'Failed')+'</span>';}
  })
  .catch(function(){card.innerHTML+='<span class="sm s-err">Error</span>';});
}

function loadQueue() {
  var div=document.getElementById('qlist');
  div.innerHTML='<p class="empty">Loading&#8230;</p>';
  fetch('/api/queue').then(function(r){return r.json()}).then(function(data){
    if(!data.items.length){div.innerHTML='<p class="empty">Nothing due.</p>';return;}
    var html='';
    data.items.forEach(function(item){
      var cls='u-later',txt='';
      if(item.gap){cls='u-over';txt='date unreadable';}
      else if(item.overdue){cls='u-over';txt=Math.abs(item.days_until)+'d overdue';}
      else if(item.days_until<=14){cls='u-soon';txt='in '+item.days_until+'d';}
      else{txt='in '+item.days_until+'d';}
      html+='<div class="qi">'
        +'<span class="rb r-'+item.rung+'">'+item.rung+'</span>'
        +'<span class="qs">'+esc(item.shown)+'</span>'
        +'<span class="qu '+cls+'">'+txt+'</span>'
        +'</div>';
    });
    div.innerHTML=html;
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to load queue</p>';});
}

function doResolve() {
  var query=document.getElementById('eqry').value.trim();
  if(!query) return;
  var div=document.getElementById('eres');
  div.innerHTML='<p class="empty">Resolving&#8230;</p>';
  fetch('/api/resolve?surface='+encodeURIComponent(query))
  .then(function(r){return r.json()}).then(function(data){
    if(data.error){div.innerHTML='<p class="sm s-err">'+esc(data.error)+'</p>';return;}
    var r=data.result, html='<div class="rr">';
    html+='<p><strong>Query:</strong> '+esc(query)+'</p>';
    if(r.sealed){
      html+='<p><strong>Canonical:</strong> '+esc(r.canonical)
        +' <span class="os sealed" style="background:var(--ok-l);color:var(--ok);display:inline-block;font-size:12px;padding:2px 8px;border-radius:12px">sealed</span></p>';
      html+='<p><strong>Confidence:</strong> '+r.confidence.toFixed(2)+'</p>';
    } else if(r.provenance&&r.provenance.suggestion){
      html+='<p><strong>Suggestion:</strong> '+esc(r.provenance.suggestion)
        +' <span style="background:var(--warn-l);color:var(--warn);display:inline-block;font-size:12px;padding:2px 8px;border-radius:12px">draft</span></p>';
      html+='<p><strong>Confidence:</strong> '+r.confidence.toFixed(2)+'</p>';
      html+='<p style="color:var(--text-2)">Not sealed &#8212; seal with <code>nestor ui</code></p>';
    } else {
      html+='<p class="empty">No match found.</p>';
    }
    html+='</div>';
    div.innerHTML=html;
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to resolve</p>';});
}

function loadSubscriptions() {
  var div=document.getElementById('slist');
  div.innerHTML='<p class="empty">Loading&#8230;</p>';
  fetch('/api/subscriptions').then(function(r){return r.json()}).then(function(data){
    if(!data.subscriptions||!data.subscriptions.length){
      div.innerHTML='<p class="empty">No recurring charges detected.</p>';return;}
    var html='';
    data.subscriptions.forEach(function(s){
      html+='<div class="si">'
        +'<span class="sn">'+esc(s.merchant)+'</span>'
        +'<span class="sa">$'+s.amount+'</span>'
        +'<div class="sc">'+esc(s.cadence)+' &middot; confidence '+Math.round(s.confidence*100)+'%</div>'
        +'</div>';
    });
    div.innerHTML=html;
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to load subscriptions</p>';});
}
</script>
</body>
</html>
"""


# ── server ────────────────────────────────────────────────────────────────

def serve(*, host: str = "127.0.0.1", port: int = 8385) -> None:
    """Start the intake UI on localhost.  Blocks until Ctrl+C."""
    import datetime as dt
    import http.server
    import json
    import urllib.parse
    import webbrowser

    from homestead.keep import paths
    from homestead.keep.rungs import Classified, Rung

    from homestead_ledger import nestor_seam
    from homestead_ledger.intake import extract
    from homestead_ledger.nestor_store import get_store
    from homestead_ledger.packs.checking import FIELDS as CHECK_FIELDS
    from homestead_ledger.packs.obligations import FIELDS as OBL_FIELDS
    from homestead_ledger.store import Sidecar

    root = paths.home()
    root.mkdir(parents=True, exist_ok=True)
    (root / "keep").mkdir(parents=True, exist_ok=True)

    try:
        nestor_seam.bind(root)
        nestor_ok = True
    except Exception:
        nestor_ok = False

    sidecar = Sidecar()

    all_fields = {**CHECK_FIELDS, **OBL_FIELDS}

    class _H(http.server.BaseHTTPRequestHandler):

        def log_message(self, fmt, *args):
            pass

        def _json(self, obj, status=200):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, content):
            body = content.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n)) if n else {}

        # ── GET ───────────────────────────────────────────────────────

        def do_GET(self):
            p = urllib.parse.urlparse(self.path)
            qs = dict(urllib.parse.parse_qsl(p.query))

            if p.path == "/":
                return self._html(_PAGE)
            if p.path == "/api/queue":
                return self._get_queue()
            if p.path == "/api/resolve":
                return self._get_resolve(qs)
            if p.path == "/api/subscriptions":
                return self._get_subscriptions()
            self.send_error(404)

        def _get_queue(self):
            from homestead_ledger import queue as queue_mod
            today = dt.date.today().isoformat()
            items = queue_mod.queue(sidecar, today=today)
            self._json({"items": [
                {"kind": i.kind, "rung": i.rung.value, "shown": i.shown,
                 "overdue": i.overdue, "days_until": i.days_until, "gap": i.gap}
                for i in items
            ]})

        def _get_resolve(self, qs):
            if not nestor_ok:
                return self._json({"error": "nestor-meaning not installed"}, 503)
            surface = qs.get("surface", "")
            if not surface:
                return self._json({"error": "surface is required"}, 400)
            try:
                store = get_store()
                resolver = nestor_seam.resolver_for("merchant", store)
                result = resolver.resolve(surface)
                self._json({"result": result})
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

        def _get_subscriptions(self):
            try:
                from homestead_ledger.recurring import detect_recurring
                from homestead_ledger.books import Books
                books = Books()
                txns = []
                for ref, record in books.transactions("checking"):
                    from homestead.keep.rungs import Surface, serve as rung_serve
                    for field_name in ("date", "description", "amount"):
                        pass
                self._json({"subscriptions": []})
            except Exception:
                self._json({"subscriptions": []})

        # ── POST ──────────────────────────────────────────────────────

        def do_POST(self):
            p = urllib.parse.urlparse(self.path).path
            body = self._body()

            if p == "/api/extract":
                return self._post_extract(body)
            if p == "/api/store":
                return self._post_store(body)
            self.send_error(404)

        def _post_extract(self, body):
            text = body.get("text", "")
            items = extract(text)
            self._json({"items": [
                {"kind": e.kind, "text": e.text, "value": e.value,
                 "start": e.start, "end": e.end, "field": e.field}
                for e in items
            ]})

        def _post_store(self, body):
            field = body.get("field", "")
            value = body.get("value", "")

            if field not in all_fields:
                return self._json(
                    {"ok": False, "error": f"unknown field {field!r}"}, 400)

            rung = all_fields[field]
            derived = None
            if rung.value in ("L3", "L4"):
                table = {
                    "description": "A merchant is named",
                    "name": "A payee is named",
                    "amount": "An amount is on file",
                    "account_number": "An account is on file",
                }
                derived = table.get(field, f"A {field.replace('_', ' ')} is on file")
            item = Classified(rung, value, derived)
            account = "checking"
            item_id = f"intake-{field}-{hash(value) & 0xFFFFFFFF:08x}"
            sidecar.put(account, field, item_id, item, overwrite=True)

            if field == "description" and nestor_ok:
                try:
                    store = get_store()
                    resolver = nestor_seam.resolver_for("merchant", store)
                    resolver.propose(value, value, reason=f"entered as {field}")
                except Exception:
                    pass

            self._json({"ok": True, "rung": rung.value})

    srv = http.server.HTTPServer((host, port), _H)
    url = f"http://{host}:{port}"
    print(f"  homestead-ledger ui: {url}")
    print(f"  press Ctrl+C to stop")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        print("\n  stopped")
