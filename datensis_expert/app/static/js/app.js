"use strict";

(() => {
  function initialize() {
    const root = document.querySelector(".client-workspace");
    if (!root) return;

    const tabs = [...root.querySelectorAll(".side-nav [data-tab]")];
    const panels = [...root.querySelectorAll(".tab-panel[id]")];
    const valid = new Set(panels.map(panel => panel.id));
    if (!panels.length) return;

    function currentTab() {
      let id = "";
      try {
        id = decodeURIComponent(window.location.hash.slice(1));
      } catch (error) {
        console.warn("DATENSIS : fragment d'URL invalide", error);
      }
      return valid.has(id) ? id : (valid.has("accueil") ? "accueil" : panels[0].id);
    }

    function activatePanel(id, updateUrl = false) {
      if (!valid.has(id)) return;
      panels.forEach(panel => {
        const active = panel.id === id;
        panel.hidden = !active;
        panel.classList.toggle("active", active);
      });
      tabs.forEach(link => {
        const active = link.dataset.tab === id;
        link.classList.toggle("active", active);
        if (active) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
      if (updateUrl && window.location.hash !== `#${id}`) {
        window.history.pushState(null, "", `#${encodeURIComponent(id)}`);
      }
    }

    root.addEventListener("click", event => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest("[data-tab], [data-go]");
      if (!link || !root.contains(link)) return;
      const id = link.dataset.tab || link.dataset.go;
      if (!valid.has(id)) return;
      event.preventDefault();
      activatePanel(id, true);
    });

    window.addEventListener("hashchange", () => activatePanel(currentTab()));
    window.addEventListener("popstate", () => activatePanel(currentTab()));
    activatePanel(currentTab());

    root.querySelectorAll("[data-filter-target]").forEach(input => {
      const target = document.getElementById(input.dataset.filterTarget);
      if (!target) return;
      input.addEventListener("input", () => {
        const search = input.value.trim().toLocaleLowerCase("fr-FR");
        target.querySelectorAll(".searchable").forEach(item => {
          item.hidden = !item.textContent.toLocaleLowerCase("fr-FR").includes(search);
        });
      });
    });

    // Calendrier : les échéances réelles sont fournies par Flask en JSON.
  const app = document.getElementById("calendar-app");
  if (!app) return;
  const required = ["calendar-days", "calendar-month-title", "calendar-event-list", "calendar-category-filter", "calendar-selected-day", "calendar-date-short", "calendar-selected-full-date", "calendar-selected-count", "calendar-month-count", "calendar-prev", "calendar-next", "calendar-today"];
  if (required.some(id => !document.getElementById(id))) {
    console.warn("DATENSIS : éléments du calendrier manquants");
    return;
  }
  const el = id => document.getElementById(id);
  const days = el("calendar-days"), monthTitle = el("calendar-month-title"), list = el("calendar-event-list");
  const filter = el("calendar-category-filter");
  const TYPES = {
    comptabilite:{label:"Comptabilité",color:"#38bdf8",icon:"document"},
    fiscalite:{label:"Fiscalité",color:"#f5b75b",icon:"document"},
    social:{label:"Social",color:"#ad9cf4",icon:"users"},
    juridique:{label:"Juridique",color:"#ee92bc",icon:"document"},
    rendez_vous:{label:"Rendez-vous",color:"#65d9c7",icon:"users"},
    urgent:{label:"Prioritaire",color:"#f07d7d",icon:"clock"}
  };
  // Démonstration uniquement si l'URL comporte ?demo_calendar=1.
  const DEMO = [
    {date:"2026-11-05",type:"fiscalite",title:"Préparation déclaration TVA",description:"Vérification des justificatifs"},
    {date:"2026-11-09",type:"social",title:"Éléments de paie",description:"Transmission des variables mensuelles"},
    {date:"2026-11-12",type:"comptabilite",title:"Dépôt des pièces comptables",description:"Transmission des factures et justificatifs du dossier",status:"À réaliser"},
    {date:"2026-11-12",type:"rendez_vous",title:"Point de suivi avec le cabinet",description:"Échange sur la situation comptable et les prochaines étapes",time:"14:30"},
    {date:"2026-11-18",type:"juridique",title:"Formalité juridique",description:"Préparation des documents"},
    {date:"2026-11-24",type:"urgent",title:"Document prioritaire",description:"Pièce manquante signalée par le cabinet"},
    {date:"2026-11-27",type:"comptabilite",title:"Rapprochement bancaire",description:"Vérification des écritures"}
  ];
  const demo = new URLSearchParams(location.search).get("demo_calendar") === "1";
  function chargerEcheances() {
    const source = document.getElementById("datensis-echeances-data");
    if (!source) return [];
    try {
      const data = JSON.parse(source.textContent);
      return Array.isArray(data) ? data : [];
    } catch (error) {
      console.error("DATENSIS Expert : JSON des échéances invalide", error);
      return [];
    }
  }
  const raw = demo ? DEMO : chargerEcheances();
  const validDate = value => {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const [y, m, d] = value.split("-").map(Number);
    const date = new Date(y, m - 1, d, 12);
    return date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d;
  };
  const events = raw.filter(e => e && validDate(e.date) && typeof e.title === "string" && Object.prototype.hasOwnProperty.call(TYPES,e.type));
  const today = new Date(); today.setHours(12,0,0,0);
  let selected = demo ? new Date(2026,10,12,12) : new Date(today);
  let year = selected.getFullYear(), month = selected.getMonth();
  const monthFmt = new Intl.DateTimeFormat("fr-FR",{month:"long",year:"numeric"});
  const fullFmt = new Intl.DateTimeFormat("fr-FR",{weekday:"long",day:"numeric",month:"long",year:"numeric"});
  const shortFmt = new Intl.DateTimeFormat("fr-FR",{month:"short",year:"numeric"});
  const key = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  const visible = () => events.filter(e => filter.value === "all" || e.type === filter.value);
  const iconPaths = {
    document:['M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8z','M8 3v5h13','M7 13h10M7 17h7'],
    users:['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2','M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8','M22 21v-2a4 4 0 0 0-3-3.87','M16 3.13a4 4 0 0 1 0 7.75'],
    clock:['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18','M12 7v5l3 2'],
    calendar:['M3 5h18v16H3z','M7 3v4M17 3v4M3 10h18']
  };
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg","svg");
    svg.setAttribute("viewBox","0 0 24 24"); svg.setAttribute("fill","none");svg.setAttribute("stroke","currentColor");svg.setAttribute("stroke-width","1.8");svg.setAttribute("stroke-linecap","round");svg.setAttribute("stroke-linejoin","round");svg.setAttribute("aria-hidden","true");
    (iconPaths[name]||iconPaths.calendar).forEach(path => {const p=document.createElementNS("http://www.w3.org/2000/svg","path");p.setAttribute("d",path);svg.appendChild(p);});
    return svg;
  }
  function element(tag, cls, text) {const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
  function details() {
    const chosen=visible().filter(e=>e.date===key(selected));
    el("calendar-selected-day").textContent=selected.getDate();
    el("calendar-date-short").textContent=shortFmt.format(selected).toUpperCase();
    el("calendar-selected-full-date").textContent=fullFmt.format(selected);
    el("calendar-selected-count").textContent=chosen.length ? `${chosen.length} échéance${chosen.length>1?"s":""} prévue${chosen.length>1?"s":""} pour votre dossier` : "Aucune échéance pour cette date";
    list.replaceChildren();
    if(!chosen.length){const empty=element("div","deadline-empty");empty.append(icon("calendar"),element("strong","","Aucune échéance"),element("p","","Aucune obligation ou rendez-vous n'est renseigné pour cette date."));list.append(empty);return;}
    chosen.forEach(event=>{
      const type=TYPES[event.type],card=element("article","deadline-event");card.style.setProperty("--event-color",type.color);
      const iconBox=element("div","deadline-event-icon");iconBox.append(icon(type.icon));
      const content=element("div","deadline-event-content");
      content.append(element("span","deadline-category",type.label),element("h4","deadline-event-title",event.title));
      if(event.description)content.append(element("p","deadline-event-description",String(event.description)));
      card.append(iconBox,content);
      const time=typeof event.time==="string"&&/^([01]\d|2[0-3]):[0-5]\d$/.test(event.time)?event.time.replace(":","h"):"";
      const status=typeof event.status==="string"?event.status.trim().slice(0,40):"";
      if(time||status){const meta=element("div","deadline-event-meta"),badge=element("span","deadline-event-badge");badge.append(icon("clock"),element("span","",time||status));meta.append(badge);card.append(meta);}
      list.append(card);
    });
  }
  function render() {
    const first=new Date(year,month,1,12),numDays=new Date(year,month+1,0).getDate(),offset=(first.getDay()+6)%7;
    monthTitle.textContent=monthFmt.format(first);
    const prefix=`${year}-${String(month+1).padStart(2,"0")}`;
    const monthly=visible().filter(e=>e.date.startsWith(prefix));
    el("calendar-month-count").textContent=`${monthly.length} échéance${monthly.length>1?"s":""} ce mois`;
    days.replaceChildren();
    for(let i=0;i<offset;i++){const blank=element("div","calendar-day other-month");blank.setAttribute("aria-hidden","true");days.append(blank);}
    for(let d=1;d<=numDays;d++){
      const date=new Date(year,month,d,12),items=monthly.filter(e=>e.date===key(date)),button=element("button","calendar-day");button.type="button";
      button.append(element("span","calendar-day-number",String(d)));
      if(items.length){const dots=element("span","calendar-event-dots");items.slice(0,4).forEach(e=>{const dot=element("span","calendar-event-dot");dot.style.setProperty("--event-color",TYPES[e.type].color);dots.append(dot);});button.append(dots);}
      if(key(date)===key(today))button.classList.add("today");
      const active=key(date)===key(selected);button.classList.toggle("selected",active);button.setAttribute("aria-pressed",String(active));button.setAttribute("aria-label",`${fullFmt.format(date)}, ${items.length} échéance(s)`);
      button.addEventListener("click",()=>{selected=date;render();});days.append(button);
    }
    details();
  }
  function move(delta){const next=new Date(year,month+delta,1,12);year=next.getFullYear();month=next.getMonth();selected=next;render();}
  el("calendar-prev").addEventListener("click",()=>move(-1));
  el("calendar-next").addEventListener("click",()=>move(1));
  el("calendar-today").addEventListener("click",()=>{selected=new Date(today);year=selected.getFullYear();month=selected.getMonth();render();});
  filter.addEventListener("change",render);
  render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();

/* ==========================================================
   DATENSIS EXPERT - ESPACE CABINET
   Integration sans modifier le module client ci-dessus
   ========================================================== */
function datensisInitializeCabinet() {
  'use strict';
  const root = document.querySelector('[data-cabinet-app]');
  if (!root) return;

  // Les valeurs proviennent des attributs data-progress rendus par Jinja2.
  root.querySelectorAll('.progress-line > [data-progress]').forEach(bar => {
    const value = Number(bar.dataset.progress);
    bar.style.width = `${Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0}%`;
  });
  const panels = [...root.querySelectorAll('[data-panel]')];
  const navLinks = [...root.querySelectorAll('[data-tab]')];
  const headings = {accueil:'Tableau de bord',dossiers:'Dossiers clients',taches:'Gestion des tâches',clients:'Annuaire clients',pilotage:'Pilotage',echeances:'Échéances',messages:'Messagerie',equipe:'Équipe',parametres:'Paramètres'};
  function openTab(id, updateHash = true) {
    if (!headings[id]) id = 'accueil';
    panels.forEach(p => { const active = p.dataset.panel === id; p.hidden = !active; p.classList.toggle('active', active); });
    navLinks.forEach(a => { const active = a.dataset.tab === id; a.classList.toggle('active', active); if(active) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current'); });
    const title = root.querySelector('#cabinet-page-title'); if(title) title.textContent = headings[id];
    if(updateHash && window.location.hash !== '#' + id) history.replaceState(null,'','#' + id);
  }
  root.querySelectorAll('[data-tab],[data-go-tab]').forEach(el => el.addEventListener('click', ev => {ev.preventDefault(); openTab(el.dataset.tab || el.dataset.goTab); root.querySelector('#cabinet-main')?.scrollIntoView({behavior:'auto',block:'start'}); if(el.dataset.focusTarget) root.querySelector('#'+el.dataset.focusTarget)?.focus(); }));
  window.addEventListener('hashchange', () => openTab(location.hash.slice(1),false));
  openTab(location.hash.slice(1),false);
  root.querySelectorAll('[data-filter-target]').forEach(input => {
    const list = document.getElementById(input.dataset.filterTarget); if(!list) return;
    const items = [...list.querySelectorAll('.searchable')];
    input.addEventListener('input', () => {const query = input.value.trim().toLocaleLowerCase('fr');let visible=0;items.forEach(item=>{const match=item.textContent.toLocaleLowerCase('fr').includes(query);const taskFilter=root.querySelector('[data-task-filter].active')?.dataset.taskFilter || 'all';const statusOk=!item.matches('[data-task-status]')||taskFilter==='all'||item.dataset.taskStatus===taskFilter;item.hidden=!(match&&statusOk);if(match&&statusOk)visible++;});const empty=root.querySelector('[data-empty-for="'+input.dataset.filterTarget+'"]');if(empty)empty.hidden=visible!==0||items.length===0;});
  });
  const taskItems = [...root.querySelectorAll('[data-task-status]')];
  root.querySelectorAll('[data-task-filter]').forEach(btn=>btn.addEventListener('click',()=>{const filter=btn.dataset.taskFilter;root.querySelectorAll('[data-task-filter]').forEach(b=>b.classList.toggle('active',b===btn));let count=0;taskItems.forEach(item=>{const query=(root.querySelector('#task-search')?.value||'').trim().toLocaleLowerCase('fr');const show=(filter==='all'||item.dataset.taskStatus===filter)&&item.textContent.toLocaleLowerCase('fr').includes(query);item.hidden=!show;if(show)count++;});const empty=root.querySelector('[data-empty-for="task-detail-list"]');if(empty)empty.hidden=count!==0||taskItems.length===0;}));
  root.querySelectorAll('[data-message-client]').forEach(btn=>btn.addEventListener('click',()=>{const select=root.querySelector('#message-recipient');if(select){select.value=btn.dataset.messageClient;openTab('messages');root.querySelector('#cabinet-message-body')?.focus();}}));
  root.querySelector('[data-client-quick-message]')?.addEventListener('click',()=>{const selected=root.querySelector('[data-client-quick-select]')?.value;const target=root.querySelector('#message-recipient');if(selected&&target){target.value=selected;openTab('messages');root.querySelector('#cabinet-message-body')?.focus();}});
  const body=root.querySelector('#cabinet-message-body');const counter=root.querySelector('[data-counter-for="cabinet-message-body"]');if(body&&counter){const update=()=>counter.textContent=body.value.length+' / 2000 caractères';body.addEventListener('input',update);update();}
  const dateLabel=root.querySelector('[data-current-date]');if(dateLabel)dateLabel.textContent=new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'long',year:'numeric'}).format(new Date());
  const calendar=root.querySelector('[data-cal-grid]');const calLabel=root.querySelector('[data-cal-label]');let month=new Date();month.setDate(1);
  function renderCalendar(){if(!calendar||!calLabel)return;calendar.replaceChildren();calLabel.textContent=new Intl.DateTimeFormat('fr-FR',{month:'long',year:'numeric'}).format(month);['L','M','M','J','V','S','D'].forEach(day=>{const cell=document.createElement('span');cell.className='cal-weekday';cell.textContent=day;calendar.append(cell);});const offset=(month.getDay()+6)%7;const days=new Date(month.getFullYear(),month.getMonth()+1,0).getDate();const today=new Date();for(let i=0;i<offset+days;i++){const cell=document.createElement('span');if(i<offset){cell.className='cal-outside';cell.textContent='·';}else{const day=i-offset+1;cell.textContent=day;if(day===today.getDate()&&month.getMonth()===today.getMonth()&&month.getFullYear()===today.getFullYear())cell.classList.add('cal-today');}calendar.append(cell);}}
  root.querySelector('[data-cal-prev]')?.addEventListener('click',()=>{month.setMonth(month.getMonth()-1);renderCalendar();});root.querySelector('[data-cal-next]')?.addEventListener('click',()=>{month.setMonth(month.getMonth()+1);renderCalendar();});renderCalendar();
  const compact=root.querySelector('[data-compact-toggle]');const motion=root.querySelector('[data-motion-toggle]');
  function preference(control,key,cssClass){if(!control)return;try{control.checked=localStorage.getItem(key)==='1';}catch(_e){}root.classList.toggle(cssClass,control.checked);control.addEventListener('change',()=>{root.classList.toggle(cssClass,control.checked);try{localStorage.setItem(key,control.checked?'1':'0');}catch(_e){}});}
  preference(compact,'datensis-cabinet-compact','is-compact');preference(motion,'datensis-cabinet-reduce-motion','reduce-motion');
 }
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', datensisInitializeCabinet, { once: true });
} else {
  datensisInitializeCabinet();
}

/* DATENSIS EXPERT : widgets du tableau de bord (données Flask uniquement) */
(function(){
  function initDashboard(){
    const root=document.querySelector('.cabinet-workspace[data-cabinet-app]');if(!root)return;
    const date=root.querySelector('[data-live-date]');if(date)date.textContent=new Intl.DateTimeFormat('fr-FR',{weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(new Date());
    const donut=root.querySelector('.dash-donut[data-completion]');if(donut){const n=Number(donut.dataset.completion);donut.style.setProperty('--pct',String(Number.isFinite(n)?Math.max(0,Math.min(100,n)):0));}
    const search=root.querySelector('#cabinet-global-search');if(search)search.addEventListener('keydown',event=>{if(event.key!=='Enter')return;event.preventDefault();const query=search.value.trim();if(!query)return;const tab=root.querySelector('[data-tab="taches"]');tab?.click();const taskSearch=root.querySelector('#task-search');if(taskSearch){taskSearch.value=query;taskSearch.dispatchEvent(new Event('input',{bubbles:true}));taskSearch.focus();}});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initDashboard,{once:true});else initDashboard();
})();
