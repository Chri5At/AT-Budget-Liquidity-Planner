"""Application shell: a slim header, a collapsible left sidebar, and panel routing."""
from __future__ import annotations

from nicegui import ui

from ..config import APP_TITLE
from ..db import get_session, get_settings
from .pages import costs, employees, liquidity, pnl, revenue, scenarios, settings, snapshots

# Excel-style cell range selection + a status bar (Sum / Ø / Min / Max / Count).
# ag-Grid range selection is an Enterprise feature, so this is a small Community
# implementation: drag across cells to select; a plain click still edits a cell.
_CELL_SELECT_JS = """
<style>
.bl-cell-sel { background-color: rgba(37,99,235,.20) !important; }
#bl-selstatus { position:fixed; bottom:12px; left:50%; transform:translateX(-50%);
  background:#1f2937; color:#fff; padding:6px 16px; border-radius:8px; font-size:13px;
  box-shadow:0 3px 10px rgba(0,0,0,.30); z-index:10000; display:none;
  font-family:Roboto,Arial,sans-serif; white-space:nowrap; }
</style>
<script>
(function(){
  const EXCLUDE = new Set(['name','label','typ','bereich','pos','']);
  let selecting=false, moved=false, anchorXY=null;
  function bar(){ let b=document.getElementById('bl-selstatus');
    if(!b){ b=document.createElement('div'); b.id='bl-selstatus'; document.body.appendChild(b); } return b; }
  function hideBar(){ const b=document.getElementById('bl-selstatus'); if(b) b.style.display='none'; }
  function clearSel(){ document.querySelectorAll('.bl-cell-sel').forEach(c=>c.classList.remove('bl-cell-sel')); }
  function isNum(cell){
    if(cell.closest('.ag-floating-bottom')||cell.closest('.ag-floating-top')) return false;
    if(cell.querySelector('.ag-row-drag, .ag-drag-handle')) return false;
    const c=cell.getAttribute('col-id'); return c && !EXCLUDE.has(c); }
  function val(t){ const c=(t||'').replace(/[^0-9,-]/g,'').replace(',','.');
    if(c===''||c==='-') return null; const v=parseFloat(c); return isNaN(v)?null:v; }
  function fmt(x){ return Math.round(x).toLocaleString('de-DE'); }
  function update(cur){
    const r={left:Math.min(anchorXY.x,cur.x),right:Math.max(anchorXY.x,cur.x),
             top:Math.min(anchorXY.y,cur.y),bottom:Math.max(anchorXY.y,cur.y)};
    clearSel(); let nums=[];
    document.querySelectorAll('.ag-cell').forEach(cell=>{
      if(!isNum(cell)) return;
      const b=cell.getBoundingClientRect(), cx=b.left+b.width/2, cy=b.top+b.height/2;
      if(cx>=r.left&&cx<=r.right&&cy>=r.top&&cy<=r.bottom){
        cell.classList.add('bl-cell-sel'); const v=val(cell.innerText); if(v!==null) nums.push(v); }
    });
    const b=bar();
    if(nums.length<2){ b.style.display='none'; return; }
    const sum=nums.reduce((a,c)=>a+c,0), avg=sum/nums.length,
          mn=Math.min.apply(null,nums), mx=Math.max.apply(null,nums);
    b.innerHTML='Summe: <b>'+fmt(sum)+' &euro;</b> &nbsp;&middot;&nbsp; &Oslash; '+fmt(avg)
      +' &euro; &nbsp;&middot;&nbsp; Min '+fmt(mn)+' &nbsp;&middot;&nbsp; Max '+fmt(mx)
      +' &nbsp;&middot;&nbsp; Anzahl '+nums.length;
    b.style.display='block';
  }
  document.addEventListener('mousedown', e=>{
    const cell=e.target.closest && e.target.closest('.ag-cell');
    if(cell && isNum(cell)){
      const b=cell.getBoundingClientRect();
      anchorXY={x:b.left+b.width/2,y:b.top+b.height/2};
      selecting=true; moved=false; clearSel(); hideBar();
    } else if(!(e.target.closest && e.target.closest('#bl-selstatus'))){ clearSel(); hideBar(); }
  }, true);
  document.addEventListener('mousemove', e=>{
    if(!selecting) return;
    if(!moved && (Math.abs(e.clientX-anchorXY.x)+Math.abs(e.clientY-anchorXY.y))<5) return;
    moved=true; e.preventDefault(); update({x:e.clientX,y:e.clientY});
  }, true);
  document.addEventListener('mouseup', e=>{
    if(selecting && moved){ e.stopPropagation(); e.preventDefault(); update({x:e.clientX,y:e.clientY}); }
    selecting=false;
  }, true);
})();
</script>
"""

# (tab key, icon, label, render fn)
_NAV = [
    ("emp", "groups", "Mitarbeiter", employees.render),
    ("rev", "trending_up", "Einnahmen", revenue.render),
    ("cost", "trending_down", "Ausgaben", costs.render),
    ("pnl", "table_chart", "GuV / Budget", pnl.render),
    ("liq", "account_balance", "Liquidität", liquidity.render),
    ("scn", "alt_route", "Szenarien", scenarios.render),
    ("snap", "photo_camera", "Snapshots", snapshots.render),
    ("set", "settings", "Einstellungen", settings.render),
]


@ui.page("/")
def index() -> None:
    with get_session() as s:
        company = get_settings(s).company_name
    nav_state = {"mini": False}

    drawer = (ui.left_drawer(value=True, fixed=True).props("bordered :width=210 :mini-width=60")
              .classes("bg-grey-1"))

    def _toggle() -> None:
        nav_state["mini"] = not nav_state["mini"]
        drawer.props(add="mini") if nav_state["mini"] else drawer.props(remove="mini")
        # ag-Grid only reflows on a resize signal; the drawer animates ~300ms, so
        # nudge it a few times across the transition to avoid stale widths/glitches.
        ui.run_javascript("[60,180,320,420].forEach(t => setTimeout("
                          "() => window.dispatchEvent(new Event('resize')), t));")

    # After the user stops resizing the window, fire one clean resize so every
    # ag-Grid does a final settled reflow (guards against recursion).
    ui.add_body_html(
        "<script>(function(){let busy=false;window.addEventListener('resize',function(){"
        "if(busy)return;clearTimeout(window.__agReflow);window.__agReflow=setTimeout("
        "function(){busy=true;window.dispatchEvent(new Event('resize'));"
        "setTimeout(function(){busy=false;},80);},160);});})();</script>")

    # Excel-style cell range selection + a Sum/Ø/Min/Max status bar.
    ui.add_body_html(_CELL_SELECT_JS)

    with ui.header().props("dense").classes("items-center bg-primary"):
        ui.button(icon="menu", on_click=_toggle).props("flat color=white dense round")
        ui.label(f"{APP_TITLE} · {company}").classes("text-base font-bold text-white")

    # Hidden tab controller drives the panels; the sidebar sets its value.
    with ui.tabs().props("vertical").classes("hidden") as tabs:
        tab_refs = {key: ui.tab(key) for key, icon, label, _ in _NAV}  # tab name == key

    with drawer:
        with ui.list().props("padding").classes("w-full"):
            for key, icon, label, _ in _NAV:
                with ui.item(on_click=lambda t=tab_refs[key]: tabs.set_value(t)).props("clickable"):
                    with ui.item_section().props("avatar"):
                        ui.icon(icon).classes("text-primary")
                    with ui.item_section():
                        ui.item_label(label)

    # Pages may return an on-show refresh fn so computed views (GuV, Liquidität)
    # pick up the latest source data whenever the tab is opened.
    on_show: dict = {}
    with ui.tab_panels(tabs, value=tab_refs["emp"]).classes("w-full"):
        for key, icon, label, render in _NAV:
            with ui.tab_panel(tab_refs[key]):
                fn = render()
                if callable(fn):
                    on_show[key] = fn

    def _on_tab(e) -> None:
        fn = on_show.get(e.value)
        if fn:
            fn()
    tabs.on_value_change(_on_tab)
