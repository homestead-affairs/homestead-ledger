"""Localhost web UI for homestead-ledger — entry forms, intake and dashboard.

Serves on 127.0.0.1 only.  All HTML/CSS/JS is embedded (no external files,
no CDN).  Imports of ``http.server`` and ``urllib.parse`` are **local** to
``build_server()`` — this module's top level touches nothing network-shaped,
so ``import homestead_ledger`` stays import-pure.

**This is where a household enters its own information.** The *Records* tab
has two forms: an obligation (payee, amount, due date, cadence — stored
through ``obligations.add_obligation`` at the pack's rungs, never a rung
chosen here) and a transaction (date, amount, description, the account
number — grown onto the canonical books through ``books.import_transaction``,
the one writer, "mirror, not judge"). Beneath them, what is on file, composed
through the gate: the obligations as the list pane shows them (the amount as
*"a payment is due"*), each opening into the detail pane where it renders; the
account's transactions as ``Window`` rows. The *Intake* tab is the other way
in: paste a bill or a receipt and each extracted item fills a form with one
click. *Queue* is what's due; *Subscriptions* is the recurring-charge pass
over the real books.

**Chokepoint**: this module never accesses ``.payload``.  Records reach the
browser as ``Row.text`` / served values, queue items as ``Due.shown``, and the
recurring pass reads the books through ``balance.dated_transactions`` at the
payload boundary.  Merchant resolution comes through Nestor's public API —
optional, and absent without the ``entity`` extra.

**The door answers.** Every request is routed inside a ``try``: a malformed
body, a ``Content-Length`` that is not a number or names a gigabyte, a JSON
value that is not an object, a field that is not text, an account the registry
does not know — each gets a status and a sentence, never a traceback on the
operator's terminal and a browser left spinning. A handler that fails anyway
answers with the *class* of what broke and nothing out of it: an exception's
text can carry the record it was handed, and this answer crosses to a browser
(I-15). No error here repeats an account number or an amount.

``build_server()`` returns the bound ``HTTPServer`` without serving, so a
test can drive the real handlers on an ephemeral port; ``serve()`` is the
operator's door and blocks until Ctrl+C.
"""
from __future__ import annotations

from homestead_ledger.cadence import CADENCES

__all__ = ["build_server", "serve"]

#: The `<option>`s for the cadence `<select>`, generated from the one
#: enumeration (`cadence.CADENCES`) rather than typed out here a second
#: time — the literal this page's `<select>` used to carry (`monthly`,
#: `weekly`, `biweekly`, `quarterly`, `annual`, `once`) named `annual` where
#: `CADENCES` says `yearly` and had no arithmetic holding either spelling to
#: anything; `tests/test_server.py` asserts the two stay equal structurally.
_CADENCE_OPTIONS = "".join(f'<option value="{c}">{c}</option>' for c in CADENCES)


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
.why{font-size:12px;color:var(--text-2);margin-top:6px}
.chk{font-size:13px;display:flex;align-items:center;gap:4px}
.rw{cursor:pointer}.rw:hover{background:var(--accent-l)}
.rk{font-size:13px;color:var(--text-2);min-width:110px}
.qn{font-size:13px;color:var(--text-2)}
.dt{padding:14px 16px;background:var(--accent-l);border-radius:var(--r);margin-top:8px}
.dt div{font-size:14px}
</style>
</head>
<body>
<header>
  <h1>homestead-ledger</h1>
  <span class="sub">the household's own entry desk</span>
</header>
<nav>
  <button class="tb on" onclick="show('records',this)">Records</button>
  <button class="tb" onclick="show('intake',this)">Intake</button>
  <button class="tb" onclick="show('queue',this)">What's Due</button>
  <button class="tb" onclick="show('entities',this)">Entities</button>
  <button class="tb" onclick="show('subscriptions',this)">Subscriptions</button>
</nav>
<main>

<section id="t-records" class="tab on">
  <h2>Add an obligation</h2>
  <div class="card">
    <div class="rf">
      <input id="oid" placeholder="Short id (rent, car-insurance)" style="max-width:220px">
      <input id="oname" placeholder="Payee (who is owed)">
      <input id="oamount" placeholder="Amount (1450.00)" style="max-width:160px">
    </div>
    <div class="rf">
      <input id="odue" placeholder="Due date YYYY-MM-DD" style="max-width:190px">
      <select id="ocadence">__CADENCE_OPTIONS__</select>
      <label class="chk"><input type="checkbox" id="oreplace"> replace if the id exists</label>
      <button class="btn bg" onclick="storeObligation()">Add</button>
    </div>
    <div class="why">Payee L3 &middot; amount L4 (the list shows only that a payment is due) &middot; due date and cadence L2. No rung is chosen here.</div>
    <div id="omsg"></div>
  </div>

  <h2>Add an account</h2>
  <div class="card">
    <div class="rf">
      <input id="alabel" placeholder="Label (chk-main, visa-chase)" style="max-width:220px">
      <select id="akind" style="max-width:160px"></select>
      <input id="anumber" placeholder="Account number (L5, never shown)" style="max-width:260px" autocomplete="off" spellcheck="false">
    </div>
    <div class="rf">
      <input id="ainstitution" placeholder="Institution (optional)" style="max-width:220px">
      <label class="chk"><input type="checkbox" id="areplace"> replace if the label exists</label>
      <button class="btn bg" onclick="storeAccount()">Add</button>
    </div>
    <div class="why">A label is the household's own short name for one real account — never a kind name, never the number itself. Kind L2 &middot; institution L3 &middot; number L5 (never shown again on any surface).</div>
    <div id="amsg"></div>
  </div>

  <h2>Mark an obligation paid</h2>
  <div class="card">
    <div class="rf">
      <input id="poid" placeholder="Obligation id (rent)" style="max-width:220px">
      <select id="paccount"></select>
      <input id="pfp" placeholder="Transaction fingerprint" style="max-width:260px">
      <input id="pon" placeholder="Paid on YYYY-MM-DD (default today)" style="max-width:220px">
      <label class="chk"><input type="checkbox" id="preplace"> replace if already marked for that date</label>
      <button class="btn bg" onclick="markPaid()">Mark paid</button>
    </div>
    <div class="why">Records a reference to the account and the transaction &mdash; never an amount &mdash; and rolls the due date forward by the obligation's cadence (a one-time obligation is marked resolved instead).</div>
    <div id="pmsg"></div>
  </div>

  <h2>Add a transaction to the books</h2>
  <div class="card">
    <div class="rf">
      <input id="tdate" placeholder="Date YYYY-MM-DD" style="max-width:170px">
      <input id="tamount" placeholder="Amount (-84.23 debit, 1500.00 credit)" style="max-width:260px">
      <input id="tdesc" placeholder="Description / payee">
    </div>
    <div class="rf">
      <select id="taccount" style="max-width:220px"></select>
      <button class="btn bg" onclick="storeTransaction()">Add</button>
    </div>
    <div class="why">The books are the household's own record: a transaction is added once (a re-entry is refused) and never edited, under an account already added above. A whole statement: <code>python -m homestead_ledger --import FILE.csv --account &lt;label&gt;</code>.</div>
    <div id="tmsg"></div>
  </div>

  <h2>Tag a transaction</h2>
  <div class="card">
    <div class="rf">
      <input id="gfp" placeholder="Transaction fingerprint (click a row below to fill)" style="max-width:320px">
      <input id="gcategory" list="gcategories" placeholder="Category (groceries, medical-copay)" style="max-width:220px">
      <datalist id="gcategories"></datalist>
      <input id="gmerchant" placeholder="Confirmed merchant (optional)" style="max-width:220px">
    </div>
    <div class="rf">
      <input id="gnote" placeholder="Note (optional)">
      <label class="chk"><input type="checkbox" id="gdonotuse"> do not use (exclude from recurring, budget and every export)</label>
      <label class="chk"><input type="checkbox" id="greplace"> replace existing tag(s)</label>
      <button class="btn bg" onclick="storeTag()">Tag</button>
    </div>
    <div class="why">Category L3, raised automatically wherever it names a protected matter (medical, legal, &hellip;) &mdash; the advisory only ever raises this, never lowers it. Note L4. Confirmed merchant L3. Do-not-use L2.</div>
    <div id="gmsg"></div>
  </div>

  <h2>Obligations on file</h2>
  <div id="olist"></div>
  <div id="odetail"></div>

  <h2>On the books</h2>
  <div id="tlist"></div>
</section>

<section id="t-intake" class="tab">
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
  if(name==='records'){loadObligations();loadTransactions();loadAccountsForPaid();}
  if(name==='queue') loadQueue();
  if(name==='subscriptions') loadSubscriptions();
}

function storeObligation() {
  var msg=document.getElementById('omsg');
  var body={id:document.getElementById('oid').value.trim(),
    name:document.getElementById('oname').value.trim(),
    amount:document.getElementById('oamount').value.trim(),
    due_date:document.getElementById('odue').value.trim(),
    cadence:document.getElementById('ocadence').value,
    replace:document.getElementById('oreplace').checked};
  fetch('/api/obligation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(function(r){return r.json()}).then(function(data){
    if(data.ok){
      msg.innerHTML='<span class="sm s-ok">Stored '+esc(data.id)+(data.replaced?' (replaced)':'')+'</span>';
      ['oid','oname','oamount','odue'].forEach(function(id){document.getElementById(id).value='';});
      document.getElementById('oreplace').checked=false;
      loadObligations();
    } else {msg.innerHTML='<span class="sm s-err">'+esc(data.error||'Failed')+'</span>';}
  }).catch(function(){msg.innerHTML='<span class="sm s-err">Error</span>';});
}

function storeAccount() {
  var msg=document.getElementById('amsg');
  var body={label:document.getElementById('alabel').value.trim(),
    kind:document.getElementById('akind').value,
    number:document.getElementById('anumber').value.trim(),
    institution:document.getElementById('ainstitution').value.trim(),
    replace:document.getElementById('areplace').checked};
  fetch('/api/account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(function(r){return r.json()}).then(function(data){
    if(data.ok){
      msg.innerHTML='<span class="sm s-ok">Stored '+esc(data.label)+(data.replaced?' (replaced)':'')+'</span>';
      ['alabel','anumber','ainstitution'].forEach(function(id){document.getElementById(id).value='';});
      document.getElementById('areplace').checked=false;
      loadAccounts();
    } else {msg.innerHTML='<span class="sm s-err">'+esc(data.error||'Failed')+'</span>';}
  }).catch(function(){msg.innerHTML='<span class="sm s-err">Error</span>';});
}

function loadAccountsForPaid() {
  // The same source as the transaction form's select: `/api/status`, whose
  // `accounts` is the household's own registered instances — never a list
  // kept here (I-23: the registry, and now the instances it classifies, are
  // the only enumeration, on this surface too). Bite G2b-account-instances
  // turned these from the four account *kinds* into `{label, kind}` rows,
  // so `mark_paid` is handed the same label a transaction is filed under
  // and the two doors cannot disagree about what an account is.
  var sel=document.getElementById('paccount');
  fetch('/api/status').then(function(r){return r.json()}).then(function(data){
    sel.innerHTML='';
    (data.accounts||[]).forEach(function(a){
      var opt=document.createElement('option');
      opt.value=a.label; opt.textContent=a.label+' ('+a.kind+')';
      sel.appendChild(opt);
    });
  }).catch(function(){});
}

function markPaid() {
  var msg=document.getElementById('pmsg');
  var body={id:document.getElementById('poid').value.trim(),
    account:document.getElementById('paccount').value,
    fingerprint:document.getElementById('pfp').value.trim(),
    paid_on:document.getElementById('pon').value.trim(),
    replace:document.getElementById('preplace').checked};
  fetch('/api/obligation/paid',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(function(r){return r.json()}).then(function(data){
    if(data.ok){
      var said = data.rolled===false
        ? 'Recorded &mdash; a later payment is already on file, so the due date stands at '+esc(data.old_due)
        : (data.new_due?('Due date rolled to '+esc(data.new_due)):'Resolved &mdash; a one-time obligation');
      msg.innerHTML='<span class="sm s-ok">'+said+'</span>';
      ['poid','pfp','pon'].forEach(function(id){document.getElementById(id).value='';});
      document.getElementById('preplace').checked=false;
      loadObligations();
    } else {msg.innerHTML='<span class="sm s-err">'+esc(data.error||'Failed')+'</span>';}
  }).catch(function(){msg.innerHTML='<span class="sm s-err">Error</span>';});
}

function storeTransaction() {
  var msg=document.getElementById('tmsg');
  var body={date:document.getElementById('tdate').value.trim(),
    amount:document.getElementById('tamount').value.trim(),
    description:document.getElementById('tdesc').value.trim(),
    account:currentAccount()};
  if(!body.account){msg.innerHTML='<span class="sm s-err">No account on file &#8212; add one above first</span>';return;}
  fetch('/api/transaction',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(function(r){return r.json()}).then(function(data){
    if(data.ok){
      msg.innerHTML='<span class="sm s-ok">On the books ('+esc(data.id.slice(0,12))+'&#8230;)</span>';
      ['tdate','tamount','tdesc'].forEach(function(id){document.getElementById(id).value='';});
      loadTransactions();
    } else {msg.innerHTML='<span class="sm s-err">'+esc(data.error||'Failed')+'</span>';}
  }).catch(function(){msg.innerHTML='<span class="sm s-err">Error</span>';});
}

function storeTag() {
  var msg=document.getElementById('gmsg');
  var body={fingerprint:document.getElementById('gfp').value.trim(),
    category:document.getElementById('gcategory').value.trim(),
    merchant:document.getElementById('gmerchant').value.trim(),
    note:document.getElementById('gnote').value.trim(),
    do_not_use:document.getElementById('gdonotuse').checked,
    replace:document.getElementById('greplace').checked};
  fetch('/api/transaction/tag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(function(r){return r.json()}).then(function(data){
    if(data.ok){
      msg.innerHTML='<span class="sm s-ok">Tagged ('+esc((data.fields||[]).join(', '))+')</span>';
      ['gcategory','gmerchant','gnote'].forEach(function(id){document.getElementById(id).value='';});
      document.getElementById('gdonotuse').checked=false;
      document.getElementById('greplace').checked=false;
      loadTransactions();
    } else {msg.innerHTML='<span class="sm s-err">'+esc(data.error||'Failed')+'</span>';}
  }).catch(function(){msg.innerHTML='<span class="sm s-err">Error</span>';});
}

// The one place this page reads which account it is working on. There is no
// literal fallback: the account instances come from /api/status and nowhere
// else, so a page that failed to load them says so rather than posting to,
// or listing, whichever label happened to be hardcoded here (I-11 — absence
// is refused by name, never defaulted; I-23 — the registry is the only
// enumeration, on this surface too).
function currentAccount() {
  return document.getElementById('taccount').value.trim();
}

function loadAccounts() {
  // The transaction form's account field is the household's own registered
  // instances, not a hand-kept list — a newly added account shows up here
  // with no change but the add itself. The list below is (re)drawn once the
  // options exist and again whenever the operator picks a different
  // account, so the rows on screen are always the rows of the account the
  // form names. The "Add an account" form's kind select is the registry of
  // *kinds* (`data.kinds`) — a separate, closed enumeration from the
  // instances themselves.
  var sel=document.getElementById('taccount');
  sel.onchange=loadTransactions;
  var kindSel=document.getElementById('akind');
  return fetch('/api/status').then(function(r){return r.json()}).then(function(data){
    var accountsList=data.accounts||[];
    sel.innerHTML=accountsList.map(function(a){
      return '<option value="'+attr(a.label)+'">'+esc(a.label)+' ('+esc(a.kind)+')</option>';
    }).join('');
    kindSel.innerHTML=(data.kinds||[]).map(function(k){
      return '<option value="'+attr(k)+'">'+esc(k)+'</option>';
    }).join('');
    loadTransactions();
  }).catch(function(){
    document.getElementById('tlist').innerHTML=
      '<p class="sm s-err">Failed to load the account instances</p>';
  });
}

function loadObligations() {
  var div=document.getElementById('olist');
  document.getElementById('odetail').innerHTML='';
  fetch('/api/obligations').then(function(r){return r.json()}).then(function(data){
    if(!data.rows||!data.rows.length){div.innerHTML='<p class="empty">No obligations on file yet.</p>';return;}
    var html='';
    data.rows.forEach(function(o){
      // `o.paid_on` and `o.resolved` are references (a date, a flag) — never
      // the account or fingerprint a paid-by record also carries (I-15).
      // The tick is gated on `paid_current`, which the server computes:
      // "there is a payment on file" and "this period is paid" are different
      // claims, and a row that ticks July's payment beside an August due
      // date makes the wrong one.
      var paid='';
      if(o.paid_current){paid+='<span class="sm s-ok">paid &#10003; '+esc(o.paid_on)+'</span>';}
      else if(o.paid_on){paid+='<span class="sm">last paid '+esc(o.paid_on)+'</span>';}
      if(o.resolved){paid+='<span class="sm s-ok">resolved</span>';}
      html+='<div class="qi rw" data-oid="'+attr(o.id)+'">'
        +'<span class="rb r-'+attr(o.rung)+'">'+esc(o.rung)+'</span>'
        +'<span class="rk">'+esc(o.id)+'</span>'
        +'<span class="qs">'+esc(o.name)+'</span>'
        +'<span class="qn">due '+esc(o.due_date)+' &middot; '+esc(o.cadence)+' &middot; '+esc(o.amount)+'</span>'
        +(o.gap?'<span class="qu u-over">incomplete</span>':'')
        +paid
        +'</div>';
    });
    div.innerHTML=html;
    // The id goes in as *data*, never as text spliced into an onclick — an
    // attribute escape is not a JavaScript-string escape, and an apostrophe
    // in an id would otherwise close the string and run what follows.
    div.querySelectorAll('[data-oid]').forEach(function(el){
      el.addEventListener('click',function(){openObligation(el.getAttribute('data-oid'))});
    });
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to load obligations</p>';});
}

function openObligation(id) {
  var div=document.getElementById('odetail');
  fetch('/api/obligation?id='+encodeURIComponent(id)).then(function(r){return r.json()}).then(function(data){
    if(data.error){div.innerHTML='<p class="sm s-err">'+esc(data.error)+'</p>';return;}
    var html='<div class="dt"><strong>'+esc(id)+'</strong>';
    Object.keys(data.fields).forEach(function(k){
      var f=data.fields[k];
      html+='<div><span class="rb r-'+attr(f.rung)+'">'+esc(f.rung)+'</span> <span class="rk">'+esc(k.replace(/_/g,' '))+'</span> '
        +(f.value===null?'(sealed)':esc(f.value))+'</div>';
    });
    div.innerHTML=html+'</div>';
  });
}

function loadTransactions() {
  var div=document.getElementById('tlist');
  var account=currentAccount();
  if(!account){div.innerHTML='<p class="sm s-err">No account kinds loaded</p>';return;}
  fetch('/api/transactions?account='+encodeURIComponent(account)).then(function(r){return r.json()}).then(function(data){
    if(data.error){div.innerHTML='<p class="sm s-err">'+esc(data.error)+'</p>';return;}
    if(!data.rows||!data.rows.length){div.innerHTML='<p class="empty">Nothing on the books for '+esc(account)+' yet.</p>';return;}
    var html='';
    data.rows.forEach(function(r){
      // `data-fp` is the fingerprint as *data*, never spliced into an
      // onclick string (the `data-oid` posture above).
      html+='<div class="qi rw" data-fp="'+attr(r.item_id)+'">'
        +'<span class="rb r-'+attr(r.rung)+'">'+esc(r.rung)+'</span>'
        +'<span class="rk">'+esc(r.item_id.slice(0,12))+' &middot; '+esc(r.field)+'</span>'
        +'<span class="qs">'+esc(r.text)+'</span>'
        +(r.category?'<span class="sm">'+esc(r.category)+'</span>':'')
        +(r.note?'<span class="sm">'+esc(r.note)+'</span>':'')
        +(r.do_not_use?'<span class="sm s-err">do-not-use</span>':'')
        +'</div>';
    });
    div.innerHTML=html;
    div.querySelectorAll('[data-fp]').forEach(function(el){
      el.addEventListener('click',function(){
        document.getElementById('gfp').value=el.getAttribute('data-fp');
      });
    });
    // Suggestions for the tag form's category field — real, rendered
    // categories only (never the derived placeholder), built with
    // `textContent` so a household-typed word needs no escaping.
    var seen={}, list=document.getElementById('gcategories');
    list.innerHTML='';
    data.rows.forEach(function(r){
      if(r.category&&r.category!=='a category is on file'&&!seen[r.category]){
        seen[r.category]=true;
        var opt=document.createElement('option');
        opt.textContent=r.category;
        list.appendChild(opt);
      }
    });
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to load the books</p>';});
}

function esc(s) {
  var d=document.createElement('div'); d.textContent=(s===null||s===undefined)?'':s; return d.innerHTML;
}

// Text bound for an *attribute* value. `esc` escapes &, < and > — enough for
// a text node, not enough inside quotes, where a ' or a " closes the
// attribute early and everything after it is markup again.
function attr(s) {
  return esc(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;');
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
      opts='<option value="oamount">Obligation amount</option><option value="tamount">Transaction amount</option>';
    } else if(item.kind==='date'){
      opts='<option value="tdate">Transaction date</option><option value="odue">Obligation due date</option>';
    } else if(item.kind==='due_date'){
      opts='<option value="odue">Obligation due date</option>';
    } else if(item.kind==='merchant'){
      opts='<option value="oname">Obligation payee</option><option value="tdesc">Transaction description</option>';
    } else if(item.kind==='account'){
      opts='<option value="anumber">Account number</option>';
    } else {
      opts='<option value="">&#8212;</option>';
    }
    html+='<div class="card" id="c'+i+'"><div class="cr">'
      +'<span class="kb k-'+item.kind+'">'+item.kind.replace('_',' ')+'</span>'
      +'<span class="mt">'+esc(item.text)+'</span>'
      +'<span class="mv">'+esc(item.value)+'</span>'
      +'<select class="fs" id="f'+i+'">'+opts+'</select>'
      +'<button class="btn bg bs" onclick="fillItem('+i+')">Use</button>'
      +'</div></div>';
  });
  div.innerHTML=html;
}

function fillItem(idx) {
  var item=_items[idx];
  var target=document.getElementById('f'+idx).value;
  if(!target) return;
  document.getElementById(target).value=item.value;
  var card=document.getElementById('c'+idx);
  card.classList.add('stored');
  card.innerHTML+='<span class="sm s-ok">Filled into the form (Records tab)</span>';
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
        +'<span class="rb r-'+attr(item.rung)+'">'+esc(item.rung)+'</span>'
        +'<span class="rk">'+esc(item.id)+'</span>'
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
        +'<span class="sa">'+(s.amount===null?'':'$'+s.amount.toFixed(2))+'</span>'
        +'<div class="sc">'+esc(s.cadence)+' &middot; confidence '+Math.round(s.confidence*100)+'%</div>'
        +'</div>';
    });
    div.innerHTML=html;
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to load subscriptions</p>';});
}
loadAccounts();loadObligations();loadAccountsForPaid();
</script>
</body>
</html>
"""

#: Substituted once, at import: the `<select>`'s options come from
#: `cadence.CADENCES`, never a copy of it inline in the markup above.
_PAGE = _PAGE.replace("__CADENCE_OPTIONS__", _CADENCE_OPTIONS)


# ── server ────────────────────────────────────────────────────────────────

def build_server(*, host: str = "127.0.0.1", port: int = 8385):
    """Bind the UI's ``HTTPServer`` on ``host:port`` and return it, unserved.

    Everything the handlers need is bound here — the household root, the
    stores, the (optional) Nestor seam — so ``serve()`` and a test share one
    construction. ``port=0`` asks the OS for a free port; read it back from
    ``server.server_address``.
    """
    import datetime as dt
    import http.server
    import json
    import urllib.parse

    from homestead.keep import paths
    from homestead.keep.dates import UnparseableDate, parse_deadline
    from homestead.keep.store import InvalidKey, RecordExists

    from homestead_ledger import accounts, balance, books, money, nestor_seam, obligations, overlay, registry
    from homestead_ledger.app.window import Window
    from homestead_ledger.cadence import UnknownCadence
    from homestead_ledger.intake import extract
    from homestead_ledger.nestor_store import get_store
    from homestead_ledger.recurring import detect_recurring
    from homestead_ledger.store import Canonical, Sidecar

    root = paths.home()
    root.mkdir(parents=True, exist_ok=True)
    (root / "keep").mkdir(parents=True, exist_ok=True)

    try:
        nestor_ok = nestor_seam.bind(root) is not None
    except Exception:
        # The extra is installed but would not bind (a ledger path it cannot
        # open, a version that moved a symbol). The books never needed Nestor;
        # the UI comes up with merchant resolution absent rather than not at
        # all, and `/api/resolve` says so with a 503.
        nestor_ok = False

    sidecar = Sidecar()
    canonical = Canonical()

    #: The largest request body this door will read. A browser form sends a few
    #: hundred bytes; an intake paste, a few thousand. Without a cap,
    #: `rfile.read(Content-Length)` is an instruction from the client to
    #: allocate whatever it names — and this process holds the household's
    #: books. 1 MiB is far above any honest paste and far below trouble.
    max_body = 1024 * 1024

    class _BadRequest(Exception):
        """A request refused at the door, with the status to answer it with."""

        def __init__(self, message: str, status: int = 400) -> None:
            super().__init__(message)
            self.status = status

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
            """The request body as a JSON object, or `_BadRequest`.

            Every failure mode here used to be an unhandled exception inside
            `do_POST`, which means no response at all and a traceback on the
            operator's terminal: a `Content-Length` that is not a number, a
            body that is not JSON, a body that is JSON but not an object
            (`[1,2]` — then `body.get` explodes), and a `Content-Length` that
            names a gigabyte. Each is answered, by status, naming the shape
            expected and never echoing what arrived.
            """
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise _BadRequest("a request body is required (send JSON)")
            try:
                n = int(raw_length)
            except (TypeError, ValueError):
                raise _BadRequest("Content-Length is not a number") from None
            if n < 0:
                raise _BadRequest("Content-Length is negative")
            if n > max_body:
                raise _BadRequest(
                    f"request body is larger than the {max_body}-byte limit", 413
                )
            if n == 0:
                return {}
            try:
                body = json.loads(self.rfile.read(n))
            except (ValueError, UnicodeDecodeError):
                raise _BadRequest("request body is not valid JSON") from None
            if not isinstance(body, dict):
                raise _BadRequest("request body is a JSON object, not a list or a bare value")
            return body

        # ── GET ───────────────────────────────────────────────────────

        def do_GET(self):
            try:
                return self._route_get()
            except _BadRequest as exc:
                return self._json({"ok": False, "error": str(exc)}, exc.status)
            except Exception as exc:
                # The handler failed. Say *that* — the class of what broke and
                # nothing out of it: an exception's text can carry a record it
                # was handed, and this answer crosses to a browser (I-15).
                return self._json(
                    {"ok": False, "error": f"the request failed ({type(exc).__name__})"}, 500
                )

        def _route_get(self):
            p = urllib.parse.urlparse(self.path)
            qs = dict(urllib.parse.parse_qsl(p.query))

            if p.path == "/":
                return self._html(_PAGE)
            if p.path == "/api/status":
                # Bite 2b: `accounts` is the household's own registered
                # *instances* — label + kind, never the number (I-13) — and
                # `kinds` is the separate, closed registry the "Add an
                # account" form's kind select draws from.
                return self._json({
                    "nestor": nestor_ok,
                    "accounts": [
                        {"label": label, "kind": accounts.kind_of(sidecar, label)}
                        for label in accounts.instances(sidecar)
                    ],
                    "kinds": list(registry.all_accounts()),
                })
            if p.path == "/api/obligations":
                return self._get_obligations()
            if p.path == "/api/obligation":
                return self._get_obligation(qs)
            if p.path == "/api/transactions":
                return self._get_transactions(qs)
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
                {"kind": i.kind, "id": i.ref[2], "rung": i.rung.value, "shown": i.shown,
                 "overdue": i.overdue, "days_until": i.days_until, "gap": i.gap}
                for i in items
            ]})

        def _get_obligations(self):
            self._json({"rows": [
                {"id": r.item_id, "name": r.name, "due_date": r.due_date,
                 "cadence": r.cadence, "amount": r.amount, "rung": r.rung.value,
                 "gap": r.gap, "paid_on": r.paid_on, "resolved": r.resolved,
                 "paid_current": r.paid_current}
                for r in obligations.rows(sidecar, today=dt.date.today().isoformat())
            ]})

        def _get_obligation(self, qs):
            item_id = qs.get("id", "")
            fields = obligations.detail(sidecar, item_id)
            if not fields:
                return self._json({"error": "no such obligation"}, 404)
            self._json({"fields": {
                f: {"rung": rung, "value": value} for f, (rung, value) in fields.items()
            }})

        def _get_transactions(self, qs):
            account = qs.get("account", "")
            if not account or not accounts.label_exists(sidecar, account):
                # Named, not echoed, and the same answer either way: an
                # unregistered label is refused exactly as an unregistered
                # kind used to be (I-23, one level down — bite 2b).
                return self._json({"error": "unknown account"}, 400)
            # The list pane over the read-only books (I-6): date and payee
            # render, the amount derives, the account number is never a row.
            window = Window()
            rows = window.open_list(canonical.records(account))
            # Bite 4: each row also carries the overlay, served the same
            # S1_LIST way — `do_not_use` is a reference (set membership),
            # never a value read off the field.
            excluded = overlay.excluded_fingerprints(sidecar)
            out_rows = []
            for r in rows:
                tags = overlay.tags_of(sidecar, r.ref[2])
                out_rows.append({
                    "item_id": r.ref[2], "field": r.ref[1], "rung": r.rung.value,
                    "text": r.text, "category": tags.get("category"),
                    "note": tags.get("note"), "do_not_use": r.ref[2] in excluded,
                })
            self._json({"rows": out_rows})

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
            # The recurring pass over the real books. Bite 4: a transaction
            # marked `do_not_use` is filtered out here, at the caller —
            # `recurring.py` never learns the overlay exists.
            today = dt.date.today()
            excluded = overlay.excluded_fingerprints(sidecar)
            found = []
            for label in accounts.instances(sidecar):
                txns = [
                    (txn_date, amount, description)
                    for item_id, txn_date, amount, description
                    in balance.dated_transactions(canonical, label)
                    if item_id not in excluded
                ]
                found.extend(detect_recurring(txns, today=today))
            self._json({"subscriptions": [
                {"merchant": c.merchant, "cadence": c.cadence, "amount": c.amount,
                 "next_expected": c.next_expected, "confidence": c.confidence,
                 "status": c.status}
                for c in found
            ]})

        # ── POST ──────────────────────────────────────────────────────

        def do_POST(self):
            try:
                return self._route_post()
            except _BadRequest as exc:
                # A refused body was never read: drain what arrived before
                # the connection closes, or the close becomes a reset.
                self._json({"ok": False, "error": str(exc)}, exc.status)
                self.close_connection = True
                _drain(self.connection)
                return
            except Exception as exc:
                return self._json(
                    {"ok": False, "error": f"the request failed ({type(exc).__name__})"}, 500
                )

        def _route_post(self):
            p = urllib.parse.urlparse(self.path).path
            body = self._body()

            if p == "/api/extract":
                return self._post_extract(body)
            if p == "/api/obligation":
                return self._post_obligation(body)
            if p == "/api/account":
                return self._post_account(body)
            if p == "/api/obligation/paid":
                return self._post_obligation_paid(body)
            if p == "/api/transaction":
                return self._post_transaction(body)
            if p == "/api/transaction/tag":
                return self._post_transaction_tag(body)
            self.send_error(404)

        def _field(self, body, name):
            """One form field out of a JSON body, as text.

            JSON carries objects, lists, booleans and nulls, and a form field
            is none of those. `str()` on whatever arrives would turn `{"a": 1}`
            into the string `"{'a': 1}"` and store *that* — so a value that is
            not a string or a number is refused by name here, before any
            parser sees it. The refusal names the type, never the value.
            """
            value = body.get(name)
            if value is None:
                return ""
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise _BadRequest(f"{name} is text, not a {type(value).__name__}")
            return str(value)

        def _post_extract(self, body):
            text = self._field(body, "text")
            items = extract(text)
            self._json({"items": [
                {"kind": e.kind, "text": e.text, "value": e.value,
                 "start": e.start, "end": e.end, "field": e.field}
                for e in items
            ]})

        def _post_obligation(self, body):
            name = self._field(body, "name")
            # JSON `true` and nothing else. `bool("false")` is `True` — so a
            # checkbox posted as the *string* `"false"`, which is what several
            # form serializers send, would have been read as "yes, replace it"
            # and silently overwritten an obligation (I-9). An explicit act
            # needs an explicitly true value.
            replace = body.get("replace") is True
            # ~~Cadence is stored as the household's own word for it. It is
            # not held against `recurring.py`'s buckets ... because nothing
            # yet rolls an obligation forward by its cadence — when that
            # lands, the accepted set becomes one enumeration and this door
            # validates against it.~~ It lands here: `add_obligation` itself
            # now refuses a cadence outside `cadence.CADENCES` (I-23's
            # reasoning applied to this word), so this door validates by
            # calling it, the same as every other refusal below.
            try:
                ref, replaced = obligations.add_obligation(
                    sidecar,
                    item_id=self._field(body, "id"),
                    name=name,
                    amount=self._field(body, "amount"),
                    due_date=self._field(body, "due_date"),
                    cadence=self._field(body, "cadence"),
                    replace=replace,
                )
            except (ValueError, UnparseableDate, InvalidKey, RecordExists) as exc:
                return self._json({"ok": False, "error": str(exc)}, 400)

            if nestor_ok:
                try:
                    resolver = nestor_seam.resolver_for("merchant", get_store())
                    resolver.propose(name.strip(), name.strip(), reason="entered as payee")
                except Exception:
                    pass
            self._json({"ok": True, "id": ref[2], "replaced": replaced is not None})

        def _post_account(self, body):
            # JSON `true` and nothing else — see `_post_obligation`'s own
            # comment on why (I-9).
            replace = body.get("replace") is True

            def optional(name: str) -> str | None:
                value = self._field(body, name).strip()
                return value or None

            try:
                ref, replaced = accounts.add_account(
                    sidecar,
                    self._field(body, "label"),
                    kind=self._field(body, "kind"),
                    number=self._field(body, "number"),
                    institution=optional("institution"),
                    opened=optional("opened"),
                    balance_as_of=optional("balance_as_of"),
                    rate=optional("rate"),
                    limit=optional("limit"),
                    payment_due_day=optional("payment_due_day"),
                    min_payment=optional("min_payment"),
                    replace=replace,
                )
            except (ValueError, UnparseableDate, InvalidKey, RecordExists) as exc:
                return self._json({"ok": False, "error": str(exc)}, 400)
            # The number posts once and is never echoed back — this response
            # names the label, never the number just stored (I-13).
            self._json({"ok": True, "label": ref[2], "replaced": replaced is not None})

        def _post_obligation_paid(self, body):
            # JSON `true` and nothing else — the same I-9 reasoning
            # `_post_obligation`'s `replace` already carries: a checkbox
            # posted as the string `"false"` must not read as `True`.
            replace = body.get("replace") is True
            item_id = self._field(body, "id")
            account = self._field(body, "account")
            fingerprint = self._field(body, "fingerprint")
            paid_on = self._field(body, "paid_on").strip() or dt.date.today().isoformat()
            try:
                _ref, rolled = obligations.mark_paid(
                    sidecar, item_id, account=account, fingerprint=fingerprint,
                    paid_on=paid_on, replace=replace,
                )
            except (ValueError, UnparseableDate, InvalidKey, RecordExists,
                    UnknownCadence, KeyError) as exc:
                # I-15: none of these refusals echo the fingerprint or an
                # amount — `mark_paid` itself never names either in a
                # message, so there is nothing here to accidentally repeat.
                return self._json({"ok": False, "error": str(exc)}, 400)
            self._json({"ok": True, "new_due": rolled.new_due,
                        "old_due": rolled.old_due, "rolled": rolled.rolled})

        def _post_transaction(self, body):
            # Bite 2b: `account` is a registered instance's label, this
            # door's one place a browser can name one. An unregistered label
            # would grow a phantom matter in the canonical books that nothing
            # iterating `accounts.instances()` would ever read back.
            account = self._field(body, "account")
            if not account or not accounts.label_exists(sidecar, account):
                return self._json({"ok": False, "error": "unknown account"}, 400)
            description = self._field(body, "description").strip()
            if not description:
                return self._json({"ok": False, "error": "a description is required"}, 400)
            try:
                date = parse_deadline(self._field(body, "date")).iso
            except UnparseableDate as exc:
                return self._json({"ok": False, "error": str(exc)}, 400)
            try:
                # `money.amount_text`, never `float()`: `float("nan")` and
                # `float("1e400")` both succeed, and `f"{float('nan'):.2f}"` is
                # the string "nan" — an amount on the books that makes every
                # balance after it `nan`. The refusal names the field and never
                # repeats what was typed (I-15 — an amount is L4).
                amount = money.amount_text(self._field(body, "amount"))
            except ValueError as exc:
                return self._json({"ok": False, "error": str(exc)}, 400)
            kind = accounts.kind_of(sidecar, account)
            txn = books.Transaction(
                account=account, kind=kind, date=date, amount=amount,
                description=description,
            )
            try:
                item_id = books.import_transaction(txn)
            except RecordExists as exc:
                return self._json({"ok": False, "error": str(exc)}, 409)
            self._json({"ok": True, "id": item_id})

        def _post_transaction_tag(self, body):
            # A transaction fingerprint, this door's one place a browser can
            # name one — never an account number, and `overlay.tag` refuses
            # by name (never echoing the row) when it is not on the books.
            fingerprint = self._field(body, "fingerprint")

            def optional(name: str) -> str | None:
                value = self._field(body, name).strip()
                return value or None

            # JSON `true` and nothing else — the same I-9/checkbox reasoning
            # `_post_obligation`'s `replace` already carries.
            replace = body.get("replace") is True
            do_not_use = body.get("do_not_use") is True
            try:
                written = overlay.tag(
                    sidecar, fingerprint,
                    category=optional("category"),
                    note=optional("note"),
                    confirmed_merchant=optional("merchant"),
                    do_not_use=do_not_use,
                    replace=replace,
                )
            except (ValueError, RecordExists) as exc:
                return self._json({"ok": False, "error": str(exc)}, 400)
            self._json({"ok": True, "fields": sorted(written)})

    return http.server.HTTPServer((host, port), _H)

#: How long a refused request's leftover bytes get to arrive before the
#: connection is closed anyway.  Short: the client sent them already or never
#: will; this waits for a segment in flight, not for a slow sender.
DRAIN_TIMEOUT_SECONDS = 0.2


def _drain(sock, *, limit=1024 * 1024, timeout=DRAIN_TIMEOUT_SECONDS):
    """Read and discard whatever the client already sent of a body the
    handler refused to read, so the socket closes with an empty receive
    buffer.

    Closing a socket that still holds unread bytes makes the kernel answer
    with a reset instead of an orderly close, and on Windows a reset discards
    data the peer has received but not yet read — the 400 the client was
    about to parse (``WinError 10053``, seen on the law module's release PR).
    The bytes are bounded by ``limit`` and the wait by ``timeout``; a slow or
    silent client is not waited for, and nothing read here is looked at
    (I-15).  Returns the count discarded.
    """
    discarded = 0
    try:
        sock.settimeout(timeout)
        while discarded < limit:
            chunk = sock.recv(min(65536, limit - discarded))
            if not chunk:
                break
            discarded += len(chunk)
    except OSError:
        pass
    return discarded



def serve(*, host: str = "127.0.0.1", port: int = 8385) -> None:
    """Start the UI on localhost, open a browser on it, and block until Ctrl+C."""
    import webbrowser

    srv = build_server(host=host, port=port)
    url = f"http://{host}:{srv.server_address[1]}"
    print(f"  homestead-ledger ui: {url}")
    print("  press Ctrl+C to stop")

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
