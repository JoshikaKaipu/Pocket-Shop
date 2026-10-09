#!/usr/bin/env python3
"""Print Ledger (web edition).

Setup (once):   pip install flask
Run:            python3 app.py
Then open the "Phone" address it prints, on a phone that is on the same Wi-Fi.
All numbers are calculated here in Python; the page just displays them.
Data is saved to print_data.json next to this file.
"""
import json
import math
import os
import socket
import threading
import time
import uuid

from flask import Flask, Response, jsonify, request

app = Flask(__name__)
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "print_data.json")
lock = threading.Lock()
state = {"prints": [], "sales": []}


# ---------- storage ----------
def load():
    global state
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
        if "prints" in d and "sales" in d:
            state = d
    except (OSError, ValueError):
        pass


def save():
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, DATA_FILE)


# ---------- calculations ----------
def money(n):
    return f"-${abs(n):,.2f}" if n < 0 else f"${n:,.2f}"


def stats(p):
    sales = [s for s in state["sales"] if s["pid"] == p["id"]]
    sold = len(sales)
    rev = sum(s["price"] for s in sales)
    return {
        "sold": sold,
        "left": max(0, p["qty"] - sold),
        "rev": rev,
        "spent": p["qty"] * p["cost"],
        "profit_sold": rev - sold * p["cost"],
        "net": rev - p["qty"] * p["cost"],
        "rate": sold / p["qty"] if p["qty"] else 0,
    }


def suggest(p, s):
    """Rule-of-thumb pricing. Edit the numbers here to change the advice."""
    floor = p["cost"] * 1.5
    new = p["price"]
    if s["left"] == 0 and s["sold"] > 0:
        new, why = p["price"] * 1.15, "Sold out. Demand beat supply. Raise the price and reprint."
    elif s["sold"] == 0:
        why = "No sales yet. Hold the price until you have data."
    elif s["rate"] >= 0.6:
        new, why = p["price"] * 1.10, f"Selling fast ({s['rate']:.0%} gone). Room to raise."
    elif s["rate"] < 0.25 and len(state["sales"]) >= 5:
        new, why = max(floor, p["price"] * 0.90), "Slow compared to the rest. Try a small cut or a bundle."
    else:
        why = "Selling steadily. Hold the price."
    if new < floor:
        new, why = floor, f"Margin is thin (under 50% of cost). Price floor is {money(floor)}."
    return max(p["cost"] + 0.5, round(new * 2) / 2), why


def build_state():
    rows = []
    t = dict(rev=0, spent=0, sold=0, left=0, profit_sold=0, net=0, potential=0)
    for p in state["prints"]:
        s = stats(p)
        new, why = suggest(p, s)
        be = math.ceil(p["qty"] * p["cost"] / p["price"]) if p["price"] > 0 else 0
        rows.append({**p, **s, "suggested": new, "why": why, "breakeven": be})
        for k in ("rev", "spent", "sold", "left", "profit_sold", "net"):
            t[k] += s[k]
        t["potential"] += s["left"] * (p["price"] - p["cost"])

    ranked = sorted(rows, key=lambda r: (-r["sold"], -r["rev"]))
    todo = []
    for r in rows:
        if r["left"] == 0 and r["sold"] > 0:
            todo.append(f"Reprint {r['name']}. It sold out.")
        elif 0 < r["left"] <= math.ceil(r["qty"] * 0.2) and r["sold"] > 0:
            todo.append(f"{r['name']} is almost gone ({r['left']} left). Plan a reprint.")
        if r["sold"] == 0 and len(state["sales"]) >= 5:
            todo.append(f"{r['name']} has no sales. Try new photos, a bundle, or a lower price.")
    if t["sold"] and t["net"] >= 0:
        todo.append("You are past break-even overall. Put some profit into new prints.")
    elif t["sold"]:
        todo.append(f"You still need {money(-t['net'])} in sales to break even overall.")
    if not todo:
        todo.append("Keep logging sales. Suggestions get sharper with more data.")

    names = {p["id"]: p["name"] for p in state["prints"]}
    recent = [
        {"name": names.get(s["pid"], "Removed print"), "price": s["price"], "t": s["t"]}
        for s in state["sales"][-5:][::-1]
    ]
    text = [f"PRINT SUMMARY", f"Revenue: {money(t['rev'])}", f"Print costs: {money(t['spent'])}",
            f"Net profit: {money(t['net'])}", f"Sold: {t['sold']} | Left: {t['left']}", ""]
    text += [f"{r['name']}: {r['sold']} sold, {r['left']} left, {money(r['price'])} -> {money(r['suggested'])}"
             for r in ranked]
    return {"prints": rows, "ranked": [r["id"] for r in ranked], "totals": t,
            "recent": recent, "todo": todo, "text": "\n".join(text)}


# ---------- API ----------
def fail(msg, code=400):
    return jsonify(error=msg), code


def find(pid):
    return next((p for p in state["prints"] if p["id"] == pid), None)


def num(d, key, kind=float, minimum=0):
    try:
        v = kind(d.get(key))
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' must be a number")
    if v < minimum or (kind is float and not math.isfinite(v)):
        raise ValueError(f"'{key}' must be at least {minimum}")
    return v


@app.get("/api/state")
def get_state():
    with lock:
        return jsonify(build_state())


@app.post("/api/prints")
def add_print():
    d = request.get_json(silent=True) or {}
    try:
        name = str(d.get("name", "")).strip()[:60]
        if not name:
            return fail("Enter a name")
        item = {"id": uuid.uuid4().hex[:8], "name": name, "price": num(d, "price"),
                "cost": num(d, "cost"), "qty": num(d, "qty", int, 1)}
    except ValueError as e:
        return fail(str(e))
    with lock:
        state["prints"].append(item)
        save()
        return jsonify(build_state())


@app.post("/api/sell/<pid>")
def sell(pid):
    with lock:
        p = find(pid)
        if not p:
            return fail("Print not found", 404)
        if stats(p)["left"] <= 0:
            return fail("Sold out")
        state["sales"].append({"id": uuid.uuid4().hex[:8], "pid": pid, "price": p["price"], "t": time.time()})
        save()
        return jsonify(build_state())


@app.post("/api/undo")
def undo():
    with lock:
        if state["sales"]:
            state["sales"].pop()
            save()
        return jsonify(build_state())


@app.post("/api/prints/<pid>/restock")
def restock(pid):
    d = request.get_json(silent=True) or {}
    with lock:
        p = find(pid)
        if not p:
            return fail("Print not found", 404)
        try:
            q = num(d, "qty", int, 1)
            if d.get("cost") not in (None, ""):
                nc = num(d, "cost")
                p["cost"] = (p["qty"] * p["cost"] + q * nc) / (p["qty"] + q)  # blended cost
        except ValueError as e:
            return fail(str(e))
        p["qty"] += q
        save()
        return jsonify(build_state())


@app.post("/api/prints/<pid>/price")
def set_price(pid):
    d = request.get_json(silent=True) or {}
    with lock:
        p = find(pid)
        if not p:
            return fail("Print not found", 404)
        try:
            p["price"] = num(d, "price")
        except ValueError as e:
            return fail(str(e))
        save()
        return jsonify(build_state())


@app.delete("/api/prints/<pid>")
def remove(pid):
    with lock:
        state["prints"] = [p for p in state["prints"] if p["id"] != pid]
        state["sales"] = [s for s in state["sales"] if s["pid"] != pid]
        save()
        return jsonify(build_state())


@app.post("/api/reset")
def reset():
    with lock:
        state["prints"], state["sales"] = [], []
        save()
        return jsonify(build_state())


# ---------- page ----------
PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="theme-color" content="#1B2140">
<title>Print Ledger</title>
<style>
:root{--bg:#EDF0F3;--card:#fff;--ink:#1B2140;--mute:#667088;--line:#D8DDE6;--acc:#2F5BEA;--accink:#fff;--good:#16794D;--bad:#C0392B;--warn:#9A6200;--hero:#1B2140;--heroink:#F2F4FA;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
@media (prefers-color-scheme:dark){:root{--bg:#0F1220;--card:#181C30;--ink:#EEF0F8;--mute:#9AA3BD;--line:#2A3050;--acc:#7C9BFF;--accink:#0F1220;--good:#4CC38A;--bad:#FF7A6B;--warn:#E5B04A;--hero:#212848}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:400 16px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-tap-highlight-color:transparent}
main{max-width:640px;margin:0 auto;padding:0 14px 110px}
.hero{background:var(--hero);color:var(--heroink);margin:0 -14px 16px;padding:22px 20px 20px;border-radius:0 0 24px 24px}
.hero small{opacity:.7;font-size:14px}.hero .big{font-size:44px;font-weight:800;letter-spacing:-.02em;line-height:1.1}
.hero .row{display:flex;gap:18px;margin-top:10px;font-size:14px;flex-wrap:wrap}
h2{font-size:20px;margin:22px 0 10px;font-weight:800}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin-bottom:10px}
.item{display:flex;align-items:center;gap:12px}.grow{flex:1;min-width:0}
.name{font-weight:600;font-size:17px;overflow-wrap:anywhere}.mute{color:var(--mute);font-size:14px}
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}
button{font:inherit;cursor:pointer;border:0;border-radius:12px;padding:12px 16px;font-weight:600;background:var(--acc);color:var(--accink);min-height:46px}
button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}
button.sm{padding:8px 12px;min-height:38px;font-size:14px}button:disabled{opacity:.4;cursor:not-allowed}
button:focus-visible,input:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
.sell{min-width:104px;font-size:17px}
form{display:grid;grid-template-columns:1fr 1fr;gap:10px}form .full{grid-column:1/-1}
label{display:flex;flex-direction:column;gap:4px;font-size:14px;color:var(--mute)}
input{font:inherit;font-size:16px;padding:12px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--ink);width:100%}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px 14px}.stat b{display:block;font-size:22px;font-weight:800}
.bar{height:10px;border-radius:6px;background:var(--line);margin-top:8px;overflow:hidden}.bar i{display:block;height:100%;background:var(--acc);border-radius:6px}
.tag{display:inline-block;padding:2px 10px;border-radius:99px;border:1px solid var(--line);font-size:13px;color:var(--mute);margin-right:6px}
ul.todo{margin:0;padding-left:20px}ul.todo li{margin:6px 0}.empty{text-align:center;padding:30px 16px;color:var(--mute)}
nav{position:fixed;left:0;right:0;bottom:0;padding:8px 14px calc(8px + env(safe-area-inset-bottom,0px));background:var(--card);border-top:1px solid var(--line);display:flex;gap:8px;justify-content:center;z-index:5}
nav button{flex:1;max-width:200px;background:transparent;color:var(--mute)}nav button[aria-current="true"]{background:var(--acc);color:var(--accink)}
.toast{position:fixed;left:50%;bottom:calc(86px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:10px 18px;border-radius:99px;font-weight:600;z-index:9;transition:opacity .25s;max-width:90%}
</style></head><body>
<main>
<section class="hero" aria-live="polite"><small>Net profit so far</small><div class="big" id="net">$0.00</div><div class="row" id="heroRow"></div></section>
<div id="app"></div>
</main>
<nav><button data-tab="sell">Sell</button><button data-tab="prints">Prints</button><button data-tab="summary">Summary</button></nav>
<div class="toast" id="toast" style="opacity:0" role="status"></div>
<script>
var S=null,tab="sell",$=function(s){return document.querySelector(s)};
var money=function(n){return (n<0?"-":"")+"$"+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})};
var esc=function(s){return String(s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})};
function toast(m){var t=$("#toast");t.textContent=m;t.style.opacity=1;clearTimeout(toast.h);toast.h=setTimeout(function(){t.style.opacity=0},1800)}
function api(method,url,body,msg){
  return fetch(url,{method:method,headers:{"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined})
  .then(function(r){return r.json().then(function(d){if(!r.ok)throw new Error(d.error||"Something went wrong");return d})})
  .then(function(d){S=d;render();if(msg)toast(msg);return d})
  .catch(function(e){toast(e.message)});
}
function viewSell(){
  if(!S.prints.length)return '<div class="card empty">No prints yet. Add your first one in the Prints tab.</div>';
  var h="<h2>Tap when you sell one</h2>";
  S.prints.forEach(function(p){h+='<div class="card item"><div class="grow"><div class="name">'+esc(p.name)+'</div><div class="mute">'+money(p.price)+' each &middot; '+p.left+' left of '+p.qty+'</div></div><button class="sell" data-act="sell" data-id="'+p.id+'"'+(p.left?"":" disabled")+'>'+(p.left?"Sold 1":"Sold out")+'</button></div>'});
  if(S.recent.length){h+="<h2>Recent sales</h2>";S.recent.forEach(function(x,i){h+='<div class="card item"><div class="grow"><div class="name">'+esc(x.name)+'</div><div class="mute">'+money(x.price)+' &middot; '+new Date(x.t*1000).toLocaleString([],{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"})+'</div></div>'+(i===0?'<button class="ghost sm" data-act="undo">Undo</button>':"")+'</div>'})}
  return h;
}
function viewPrints(){
  var h='<h2>Add a print</h2><div class="card"><form id="addForm"><label class="full">Name<input name="name" required maxlength="60" placeholder="e.g. Harbor at Dusk"></label><label>Sell price ($)<input name="price" type="number" min="0" step="0.01" inputmode="decimal" required></label><label>Print cost each ($)<input name="cost" type="number" min="0" step="0.01" inputmode="decimal" required></label><label class="full">Number of prints<input name="qty" type="number" min="1" step="1" inputmode="numeric" required></label><button class="full" type="submit">Add print</button></form></div><h2>Your prints ('+S.prints.length+')</h2>';
  if(!S.prints.length)h+='<div class="card empty">Nothing here yet.</div>';
  S.prints.forEach(function(p){h+='<div class="card"><div class="name">'+esc(p.name)+'</div><div class="mute">Price '+money(p.price)+' &middot; cost '+money(p.cost)+' &middot; margin '+money(p.price-p.cost)+'</div><div class="mute">'+p.left+' left of '+p.qty+'</div><div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap"><button class="ghost sm" data-act="restock" data-id="'+p.id+'">Add stock</button><button class="ghost sm" data-act="price" data-id="'+p.id+'">Change price</button><button class="ghost sm" data-act="remove" data-id="'+p.id+'">Remove</button></div></div>'});
  return h;
}
function viewSummary(){
  if(!S.prints.length)return '<div class="card empty">Add prints and log some sales to see your summary.</div>';
  var t=S.totals,by={};S.prints.forEach(function(p){by[p.id]=p});
  var h='<h2>Sales summary</h2><div class="grid"><div class="stat"><span class="mute">Revenue</span><b>'+money(t.rev)+'</b></div><div class="stat"><span class="mute">Print costs paid</span><b>'+money(t.spent)+'</b></div><div class="stat"><span class="mute">Net profit</span><b class="'+(t.net<0?"bad":"good")+'">'+money(t.net)+'</b></div><div class="stat"><span class="mute">Profit on sold prints</span><b>'+money(t.profit_sold)+'</b></div><div class="stat"><span class="mute">Units sold</span><b>'+t.sold+'</b></div><div class="stat"><span class="mute">Still to earn</span><b>'+money(t.potential)+'</b></div></div><p class="mute">Net profit counts every print you paid for. Profit on sold prints counts only the cost of what has sold. "Still to earn" is the profit left if the remaining stock sells at current prices.</p>';
  var max=Math.max(1,by[S.ranked[0]].sold);
  h+="<h2>Best sellers</h2>";
  S.ranked.forEach(function(id,i){var p=by[id];h+='<div class="card"><div class="name">'+(i===0&&p.sold?"Top: ":"")+esc(p.name)+'</div><div class="mute">'+p.sold+' sold &middot; '+money(p.rev)+' revenue &middot; '+Math.round(p.rate*100)+'% of stock</div><div class="bar"><i style="width:'+(p.sold/max*100)+'%"></i></div></div>'});
  h+="<h2>Updated pricing</h2>";
  S.prints.forEach(function(p){var d=p.suggested-p.price;h+='<div class="card"><div class="item"><div class="grow"><div class="name">'+esc(p.name)+'</div><div class="mute">'+esc(p.why)+'</div></div><div style="text-align:right"><div class="mute">'+money(p.price)+' to</div><b style="font-size:20px" class="'+(d>0?"good":d<0?"warn":"")+'">'+money(p.suggested)+'</b></div></div><div style="margin-top:8px"><span class="tag">Break-even: '+p.breakeven+' sold</span><span class="tag">'+(p.sold>=p.breakeven?"Covered":(p.breakeven-p.sold)+" to go")+'</span></div></div>'});
  h+="<h2>Next steps</h2><div class='card'><ul class='todo'>"+S.todo.map(function(x){return "<li>"+esc(x)+"</li>"}).join("")+"</ul></div>";
  return h+'<div style="display:flex;gap:8px;flex-wrap:wrap"><button data-act="copy">Copy summary</button><button class="ghost" data-act="reset">Reset everything</button></div>';
}
function render(){
  if(!S)return;
  var t=S.totals;$("#net").textContent=money(t.net);
  $("#heroRow").innerHTML="<span>Revenue <b>"+money(t.rev)+"</b></span><span>Print costs <b>"+money(t.spent)+"</b></span><span>Sold <b>"+t.sold+"</b> / left <b>"+t.left+"</b></span>";
  document.querySelectorAll("nav button").forEach(function(b){b.setAttribute("aria-current",b.dataset.tab===tab)});
  $("#app").innerHTML=tab==="sell"?viewSell():tab==="prints"?viewPrints():viewSummary();
  var f=$("#addForm");
  if(f)f.addEventListener("submit",function(e){e.preventDefault();var d=new FormData(f);
    api("POST","/api/prints",{name:d.get("name"),price:d.get("price"),cost:d.get("cost"),qty:d.get("qty")},"Print added")});
}
document.addEventListener("click",function(e){
  var tb=e.target.closest("nav button");if(tb){tab=tb.dataset.tab;render();window.scrollTo(0,0);return}
  var b=e.target.closest("[data-act]");if(!b)return;
  var a=b.dataset.act,id=b.dataset.id,p=S.prints.find(function(q){return q.id===id});
  if(a==="sell"&&p)api("POST","/api/sell/"+id,null,"Sold: "+p.name+" +"+money(p.price));
  else if(a==="undo")api("POST","/api/undo",null,"Last sale undone");
  else if(a==="restock"&&p){var q=prompt("How many more prints of "+p.name+"?","10");if(q){var c=prompt("Print cost each? (blank keeps "+money(p.cost)+")","");api("POST","/api/prints/"+id+"/restock",{qty:q,cost:c},"Stock added")}}
  else if(a==="price"&&p){var v=prompt("New price for "+p.name+" ($)",p.price);if(v!==null)api("POST","/api/prints/"+id+"/price",{price:v},"Price updated (past sales keep their price)")}
  else if(a==="remove"&&p){if(confirm("Remove "+p.name+" and its sales history?"))api("DELETE","/api/prints/"+id,null,"Removed")}
  else if(a==="copy"){try{navigator.clipboard.writeText(S.text).then(function(){toast("Summary copied")},function(){prompt("Copy this:",S.text)})}catch(er){prompt("Copy this:",S.text)}}
  else if(a==="reset"){if(confirm("Delete all prints and sales? This cannot be undone."))api("POST","/api/reset",null,"Reset")}
});
api("GET","/api/state");
</script></body></html>"""


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packets are sent
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "your-computer-ip"


if __name__ == "__main__":
    load()
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Computer: http://localhost:{port}")
    print(f"  Phone:    http://{lan_ip()}:{port}   (same Wi-Fi)\n")
    app.run(host="0.0.0.0", port=port)
