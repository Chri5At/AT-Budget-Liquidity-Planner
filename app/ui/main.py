"""Application shell: a slim header, a collapsible left sidebar, and panel routing."""
from __future__ import annotations

from nicegui import ui

from ..config import APP_TITLE
from ..db import get_session, get_settings
from .pages import costs, employees, liquidity, pnl, revenue, scenarios, settings, snapshots

# Excel-style cell selection + a status bar (Sum / Ø / Min / Max / Count).
# ag-Grid range selection is an Enterprise feature, so this is a small Community
# implementation: drag a rectangle, Ctrl/Cmd+click to toggle single cells, or
# Shift+click to extend a range. A plain click still edits a cell. Selected values
# are cached so the sum stays correct even when cells scroll out of view.
_CELL_SELECT_JS = """
<style>
.bl-cell-sel { background-color: rgba(37,99,235,.22) !important; }
#bl-selstatus { position:fixed; bottom:12px; left:50%; transform:translateX(-50%);
  background:#1f2937; color:#fff; padding:6px 16px; border-radius:8px; font-size:13px;
  box-shadow:0 3px 10px rgba(0,0,0,.30); z-index:10000; display:none;
  font-family:Roboto,Arial,sans-serif; white-space:nowrap; }
#bl-selstatus .bl-x { margin-left:14px; cursor:pointer; opacity:.7; }
</style>
<script>
(function(){
  const EXCLUDE = new Set(['name','label','typ','bereich','pos','']);
  const sel = new Map();                 // "rowKey|colId" -> number|null
  let activeRoot=null, anchorInfo=null;
  let selecting=false, moved=false, anchorXY=null, anchorRoot=null;

  function bar(){ let b=document.getElementById('bl-selstatus');
    if(!b){ b=document.createElement('div'); b.id='bl-selstatus'; document.body.appendChild(b); } return b; }
  function colId(c){ return c.getAttribute('col-id'); }
  function rowKey(cell){ const r=cell.closest('.ag-row'); if(!r) return null;
    return r.getAttribute('row-id') || ('r'+r.getAttribute('row-index')); }
  function key(cell){ const r=rowKey(cell), c=colId(cell); return (r&&c)? r+'|'+c : null; }
  function isNum(cell){
    if(cell.closest('.ag-floating-bottom')||cell.closest('.ag-floating-top')) return false;
    if(cell.querySelector('.ag-row-drag, .ag-drag-handle')) return false;
    const c=colId(cell); return !!c && !EXCLUDE.has(c); }
  function val(t){ const c=(t||'').replace(/[^0-9,-]/g,'').replace(',','.');
    if(c===''||c==='-') return null; const v=parseFloat(c); return isNaN(v)?null:v; }
  function fmt(x){ return Math.round(x).toLocaleString('de-DE'); }
  function order(root){ const m={}; let i=0;
    root.querySelectorAll('.ag-header-cell[col-id]').forEach(h=>{ const c=h.getAttribute('col-id'); if(!(c in m)) m[c]=i++; }); return m; }
  function info(cell, ord){ const r=cell.closest('.ag-row');
    return { ri: parseInt(r.getAttribute('row-index')), ci: ord[colId(cell)] }; }
  function setActive(root){ if(activeRoot!==root){ sel.clear(); activeRoot=root; } }

  function applyHighlight(){
    document.querySelectorAll('.bl-cell-sel').forEach(c=>c.classList.remove('bl-cell-sel'));
    if(!activeRoot) return;
    activeRoot.querySelectorAll('.ag-cell').forEach(cell=>{ const k=key(cell); if(k && sel.has(k)) cell.classList.add('bl-cell-sel'); });
  }
  function showBar(){ const b=bar(); const nums=[...sel.values()].filter(v=>v!==null);
    if(nums.length<2){ b.style.display='none'; return; }
    const sum=nums.reduce((a,c)=>a+c,0), avg=sum/nums.length,
          mn=Math.min.apply(null,nums), mx=Math.max.apply(null,nums);
    b.innerHTML='Summe: <b>'+fmt(sum)+' &euro;</b> &nbsp;&middot;&nbsp; &Oslash; '+fmt(avg)
      +' &euro; &nbsp;&middot;&nbsp; Min '+fmt(mn)+' &nbsp;&middot;&nbsp; Max '+fmt(mx)
      +' &nbsp;&middot;&nbsp; Anzahl '+nums.length+'<span class="bl-x" title="Auswahl aufheben">&times;</span>';
    b.querySelector('.bl-x').onclick=clearAll;
    b.style.display='block'; }
  function refresh(){ applyHighlight(); showBar(); }
  function clearAll(){ sel.clear(); refresh(); }

  document.addEventListener('mousedown', e=>{
    const cell=e.target.closest && e.target.closest('.ag-cell');
    if(cell && isNum(cell) && !(e.ctrlKey||e.metaKey||e.shiftKey)){
      anchorRoot=cell.closest('.ag-root-wrapper');
      const b=cell.getBoundingClientRect(); anchorXY={x:b.left+b.width/2,y:b.top+b.height/2};
      anchorInfo=info(cell, order(anchorRoot));
      selecting=true; moved=false;
    } else if(!cell && !(e.target.closest && e.target.closest('#bl-selstatus'))){ clearAll(); }
  }, true);

  document.addEventListener('mousemove', e=>{
    if(!selecting) return;
    if(!moved && (Math.abs(e.clientX-anchorXY.x)+Math.abs(e.clientY-anchorXY.y))<5) return;
    moved=true; e.preventDefault(); setActive(anchorRoot); sel.clear();
    const r={left:Math.min(anchorXY.x,e.clientX),right:Math.max(anchorXY.x,e.clientX),
             top:Math.min(anchorXY.y,e.clientY),bottom:Math.max(anchorXY.y,e.clientY)};
    anchorRoot.querySelectorAll('.ag-cell').forEach(cell=>{ if(!isNum(cell)) return;
      const b=cell.getBoundingClientRect(), cx=b.left+b.width/2, cy=b.top+b.height/2;
      if(cx>=r.left&&cx<=r.right&&cy>=r.top&&cy<=r.bottom){ const k=key(cell); if(k) sel.set(k, val(cell.innerText)); } });
    refresh();
  }, true);

  document.addEventListener('mouseup', e=>{
    if(selecting){ if(moved){ e.stopPropagation(); e.preventDefault(); } else { clearAll(); } }
    selecting=false;
  }, true);

  document.addEventListener('click', e=>{
    const cell=e.target.closest && e.target.closest('.ag-cell');
    if(!cell || !isNum(cell)) return;
    if(e.ctrlKey||e.metaKey){
      e.preventDefault(); e.stopPropagation();
      const root=cell.closest('.ag-root-wrapper'); setActive(root);
      const k=key(cell); if(sel.has(k)) sel.delete(k); else sel.set(k, val(cell.innerText));
      anchorInfo=info(cell, order(root)); refresh();
    } else if(e.shiftKey && anchorInfo){
      e.preventDefault(); e.stopPropagation();
      const root=cell.closest('.ag-root-wrapper'); setActive(root);
      const ord=order(root), t=info(cell, ord);
      const r0=Math.min(anchorInfo.ri,t.ri), r1=Math.max(anchorInfo.ri,t.ri);
      const c0=Math.min(anchorInfo.ci,t.ci), c1=Math.max(anchorInfo.ci,t.ci);
      root.querySelectorAll('.ag-cell').forEach(c=>{ if(!isNum(c)) return;
        const ci=ord[colId(c)], rr=c.closest('.ag-row'), ri=parseInt(rr.getAttribute('row-index'));
        if(ri>=r0&&ri<=r1&&ci>=c0&&ci<=c1){ const k=key(c); if(k) sel.set(k, val(c.innerText)); } });
      refresh();
    }
  }, true);

  document.addEventListener('scroll', ()=>{ if(activeRoot) applyHighlight(); }, true);
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
