"use strict";

(() => {
  function initialize() {
    const root = document.querySelector(".client-workspace");
    if (!root || root.dataset.clientInitialized === "true") return;
    root.dataset.clientInitialized = "true";

    // Navigation client : les panneaux restent strictement limites a cet espace.
    const panels = [...root.querySelectorAll(".tab-panel[id]")];
    const valid = new Set(panels.map((panel) => panel.id));
    const tabs = [...root.querySelectorAll(".side-nav [data-tab]")];

    function currentTab() {
      let id = "";
      try {
        id = decodeURIComponent(window.location.hash.slice(1));
      } catch (error) {
        console.warn("DATENSIS : fragment d'URL invalide", error);
      }
      return valid.has(id) ? id : (valid.has("accueil") ? "accueil" : panels[0]?.id);
    }

    function activatePanel(id, updateUrl = false) {
      if (!valid.has(id)) return;

      panels.forEach((panel) => {
        const active = panel.id === id;
        panel.hidden = !active;
        panel.classList.toggle("active", active);
        panel.setAttribute("aria-hidden", String(!active));
        // Priorite aux onglets : evite les conflits avec display dans le CSS.
        if (active) {
          panel.style.setProperty("display", "block", "important");
        } else {
          panel.style.setProperty("display", "none", "important");
        }
      });

      tabs.forEach((link) => {
        const active = link.dataset.tab === id;
        link.classList.toggle("active", active);
        if (active) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
        link.removeAttribute("aria-selected");
        if (valid.has(link.dataset.tab)) link.setAttribute("aria-controls", link.dataset.tab);
      });

      if (updateUrl && window.location.hash !== `#${encodeURIComponent(id)}`) {
        window.history.pushState(null, "", `#${encodeURIComponent(id)}`);
      }
    }


    if (panels.length) {
      root.addEventListener("click", (event) => {
        if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        if (!(event.target instanceof Element)) return;
        const link = event.target.closest("[data-tab], [data-go]");
        if (!link || !root.contains(link)) return;
        const id = link.dataset.tab || link.dataset.go;
        if (!valid.has(id)) return;
        event.preventDefault();
        activatePanel(id, true);
        const message = root.querySelector("#message-body");
        if (link.dataset.requestTopic && message) {
          if (!message.value.trim()) {
            message.value = `Sujet : ${link.dataset.requestTopic}\n\n`;
            message.dispatchEvent(new Event("input", { bubbles: true }));
          }
          message.focus();
        } else {
          const panel = panels.find(item => item.id === id);
          const heading = panel?.querySelector("h2");
          if (heading) {
            heading.setAttribute("tabindex", "-1");
            heading.focus({ preventScroll: true });
          }
          root.querySelector("#client-main")?.scrollIntoView({ block: "start", behavior: "auto" });
        }
      });

      window.addEventListener("hashchange", () => activatePanel(currentTab()));
      window.addEventListener("popstate", () => activatePanel(currentTab()));
      activatePanel(currentTab());
    } else {
      console.warn("DATENSIS : aucun panneau .tab-panel[id] dans l'espace client");
    }

    // Recherche locale : aucune donnée n'est envoyée ni stockée.
    const normalize = value => String(value ?? "").normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("fr-FR").trim();
    root.querySelectorAll("[data-filter-target], #document-search").forEach(input => {
      const target = document.getElementById(input.dataset.filterTarget || "client-document-list");
      if (!target || !root.contains(target)) return;
      const items = [...target.querySelectorAll(".searchable, [data-document-record]")];
      const wrapper = input.closest('[data-enhancement="document-filter"]');
      if (wrapper) wrapper.hidden = false;
      const status = input.id === "document-search" ? root.querySelector("#document-search-status") : null;
      const update = () => {
        const query = normalize(input.value);
        let count = 0;
        items.forEach(item => {
          const match = normalize(item.textContent).includes(query);
          item.hidden = !match;
          if (match) count++;
        });
        if (status) status.textContent = query ? `${count} résultat(s) sur ${items.length}` : "";
      };
      input.addEventListener("input", update);
      input.addEventListener("keydown", event => {
        if (event.key === "Escape" && input.value) {
          event.preventDefault();
          input.value = "";
          update();
        }
      });
      update();
    });

    const message = root.querySelector("#message-body");
    const counter = root.querySelector("#message-counter");
    if (message && counter) {
      const update = () => {
        counter.textContent = `${message.value.length} / ${message.maxLength > 0 ? message.maxLength : 2000} caractères`;
      };
      counter.hidden = false;
      message.addEventListener("input", update);
      update();
    }

    // Les formulaires restent soumis normalement à Flask (CSRF conservé).
    root.querySelectorAll('form[method="post" i]').forEach(form => {
      form.addEventListener("submit", event => {
        if (event.defaultPrevented || !form.checkValidity()) return;
        if (form.dataset.clientSubmitting === "true") {
          event.preventDefault();
          return;
        }
        form.dataset.clientSubmitting = "true";
        form.setAttribute("aria-busy", "true");
      });
    });
    window.addEventListener("pageshow", () => {
      root.querySelectorAll("form[data-client-submitting]").forEach(form => {
        delete form.dataset.clientSubmitting;
        form.removeAttribute("aria-busy");
      });
    });


    // Notifications flash : uniquement sur une page client.
    // Le layout commun peut placer son conteneur hors du workspace.
    const containers = [...document.querySelectorAll('.flash-container')]
      .filter(box => root.contains(box) || !box.closest('.cabinet-workspace, .twofa-page'));
    containers.forEach(box => {
      const notices = [...box.querySelectorAll('.flash-message, .toast')]
        .filter(node => !node.parentElement.closest('.flash-message, .toast'));
      if (!notices.length) return;
      box.classList.add('client-flash-stack');
      box.dataset.theme = root.dataset.theme === 'dark' ? 'dark' : 'light';
      notices.forEach(notice => {
        notice.classList.add('client-flash-notice');
        const error = notice.matches('.error, .danger');
        const duration = error ? 0 : notice.matches('.warning') ? 8000 : notice.matches('.success') ? 4000 : 5000;
        notice.setAttribute('role', error ? 'alert' : 'status');
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'client-flash-close';
        close.setAttribute('aria-label', 'Fermer la notification');
        close.textContent = '×';
        notice.append(close);
        let timer;
        let dismissed = false;
        let hovered = false;
        const dismiss = () => {
          if (dismissed) return;
          dismissed = true;
          window.clearTimeout(timer);
          notice.remove();
          if (!box.querySelector('.client-flash-notice')) box.remove();
        };
        const pause = () => window.clearTimeout(timer);
        const resume = () => {
          pause();
          if (!dismissed && duration && !hovered && !notice.contains(document.activeElement)) {
            timer = window.setTimeout(dismiss, duration);
          }
        };
        close.addEventListener('click', dismiss);
        notice.addEventListener('mouseenter', () => { hovered = true; pause(); });
        notice.addEventListener('mouseleave', () => { hovered = false; resume(); });
        notice.addEventListener('focusin', pause);
        notice.addEventListener('focusout', () => window.setTimeout(resume, 0));
        resume();
      });
    });

    // Calendrier : les échéances réelles sont fournies par Flask en JSON.
    const app = document.getElementById("calendar-app");
    if (!app || !root.contains(app)) return;
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
    const raw = chargerEcheances();
    const validDate = value => {
      if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
      const [y, m, d] = value.split("-").map(Number);
      const date = new Date(y, m - 1, d, 12);
      return date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d;
    };
    const events = raw.filter(e => e && validDate(e.date) && typeof e.title === "string" && Object.prototype.hasOwnProperty.call(TYPES,e.type));
    const today = new Date(); today.setHours(12,0,0,0);
    let selected = new Date(today);
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
        if(time||status){const meta=element("div","deadline-event-meta"),badge=element("span","deadline-event-badge");badge.append(icon("clock"),element("span","",[time, status].filter(Boolean).join(" · ")));meta.append(badge);card.append(meta);}
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
        button.dataset.date = key(date);
        button.addEventListener("click",()=>{selected=date;render();days.querySelector(`[data-date="${key(date)}"]`)?.focus();});days.append(button);
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
  const headings = {taches:'Mes tâches',parcours:'Mes parcours',dossiers:'Mes dossiers','mon-cabinet':'Mon cabinet',pilotage:'Pilotage',theme:'Thème',aide:'Aide'};
  function openTab(id, updateHash = true) {
    if (!Object.prototype.hasOwnProperty.call(headings,id)) id = 'taches';
    panels.forEach(p => { const active = p.dataset.panel === id; p.hidden = !active; p.classList.toggle('active', active); p.style.setProperty('display', active ? 'block' : 'none', 'important'); });
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
  root.querySelectorAll('[data-message-client]').forEach(btn=>btn.addEventListener('click',()=>{const select=root.querySelector('#message-recipient');if(select){select.value=btn.dataset.messageClient;openTab('mon-cabinet');root.querySelector('#cabinet-message-body')?.focus();}}));
  root.querySelector('[data-client-quick-message]')?.addEventListener('click',()=>{const selected=root.querySelector('[data-client-quick-select]')?.value;const target=root.querySelector('#message-recipient');if(selected&&target){target.value=selected;openTab('mon-cabinet');root.querySelector('#cabinet-message-body')?.focus();}});
  const body=root.querySelector('#cabinet-message-body');const counter=root.querySelector('[data-counter-for="cabinet-message-body"]');if(body&&counter){const update=()=>counter.textContent=body.value.length+' / 2000 caractères';body.addEventListener('input',update);update();}
  const dateLabel=root.querySelector('[data-current-date]');if(dateLabel)dateLabel.textContent=new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'long',year:'numeric'}).format(new Date());
  const calendar=root.querySelector('[data-cal-grid]');const calLabel=root.querySelector('[data-cal-label]');let month=new Date();month.setDate(1);
  function renderCalendar(){if(!calendar||!calLabel)return;calendar.replaceChildren();calLabel.textContent=new Intl.DateTimeFormat('fr-FR',{month:'long',year:'numeric'}).format(month);['L','M','M','J','V','S','D'].forEach(day=>{const cell=document.createElement('span');cell.className='cal-weekday';cell.textContent=day;calendar.append(cell);});const offset=(month.getDay()+6)%7;const days=new Date(month.getFullYear(),month.getMonth()+1,0).getDate();const today=new Date();for(let i=0;i<offset+days;i++){const cell=document.createElement('span');if(i<offset){cell.className='cal-outside';cell.textContent='·';}else{const day=i-offset+1;cell.textContent=day;if(day===today.getDate()&&month.getMonth()===today.getMonth()&&month.getFullYear()===today.getFullYear())cell.classList.add('cal-today');}calendar.append(cell);}}
  root.querySelector('[data-cal-prev]')?.addEventListener('click',()=>{month.setMonth(month.getMonth()-1);renderCalendar();});root.querySelector('[data-cal-next]')?.addEventListener('click',()=>{month.setMonth(month.getMonth()+1);renderCalendar();});renderCalendar();
  const compact=root.querySelector('[data-compact-toggle]');const motion=root.querySelector('[data-motion-toggle]');
  function preference(control,key,cssClass){if(!control)return;try{control.checked=localStorage.getItem(key)==='1';}catch(_e){}root.classList.toggle(cssClass,control.checked);control.addEventListener('change',()=>{root.classList.toggle(cssClass,control.checked);try{localStorage.setItem(key,control.checked?'1':'0');}catch(_e){}});}
  preference(compact,'datensis-cabinet-compact','is-compact');preference(motion,'datensis-cabinet-reduce-motion','reduce-motion');preference(root.querySelector('[data-contrast-toggle]'),'datensis-cabinet-high-contrast','is-high-contrast');
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

/* DATENSIS Expert — progression locale des parcours et recherche dans l'aide */
(function(){
  function init(){
    const root=document.querySelector('[data-cabinet-app]');if(!root)return;
    root.querySelectorAll('[data-journey]').forEach(card=>{
      const boxes=[...card.querySelectorAll('[data-journey-step]')];
      const update=()=>{const done=boxes.filter(b=>b.checked).length;const counter=card.querySelector('[data-journey-count]');if(counter)counter.textContent=done+'/'+boxes.length;const bar=card.querySelector('[data-journey-progress]');if(bar)bar.style.width=(boxes.length?100*done/boxes.length:0)+'%';};
      boxes.forEach(box=>{try{box.checked=localStorage.getItem('datensis-guide-'+box.dataset.journeyStep)==='1';}catch(_e){}box.addEventListener('change',()=>{try{localStorage.setItem('datensis-guide-'+box.dataset.journeyStep,box.checked?'1':'0');}catch(_e){}update();});});
      card.querySelector('[data-journey-reset]')?.addEventListener('click',()=>{boxes.forEach(box=>{box.checked=false;try{localStorage.removeItem('datensis-guide-'+box.dataset.journeyStep);}catch(_e){}});update();});update();
    });
    root.querySelectorAll('[data-expert-filter]').forEach(input=>{const list=root.querySelector('#'+input.dataset.expertFilter);if(!list)return;const items=[...list.querySelectorAll('.searchable')];const empty=root.querySelector('[data-expert-empty="'+input.dataset.expertFilter+'"]');input.addEventListener('input',()=>{const query=input.value.trim().toLocaleLowerCase('fr');let count=0;items.forEach(item=>{const match=item.textContent.toLocaleLowerCase('fr').includes(query);item.hidden=!match;if(match)count++;});if(empty)empty.hidden=count!==0;});});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();



/* DATENSIS Expert — réglages supplémentaires et notes locales */
(function(){
 function ready(){
  const root=document.querySelector('[data-cabinet-app]');if(!root)return;
  const classes={'large-text':'is-large-text','roomy':'is-roomy','focus':'is-focus-visible'};
  root.querySelectorAll('[data-extra-toggle]').forEach(input=>{
   const key=input.dataset.extraToggle, cls=classes[key];if(!cls)return;
   try{input.checked=localStorage.getItem('datensis-cabinet-'+key)==='1';}catch(e){}
   root.classList.toggle(cls,input.checked);
   input.addEventListener('change',()=>{root.classList.toggle(cls,input.checked);try{localStorage.setItem('datensis-cabinet-'+key,input.checked?'1':'0');}catch(e){}});
  });
  root.querySelector('[data-reset-theme]')?.addEventListener('click',()=>{
   ['datensis-cabinet-compact','datensis-cabinet-reduce-motion','datensis-cabinet-high-contrast','datensis-cabinet-large-text','datensis-cabinet-roomy','datensis-cabinet-focus'].forEach(key=>{try{localStorage.removeItem(key);}catch(e){}});
   ['is-compact','reduce-motion','is-high-contrast','is-large-text','is-roomy','is-focus-visible'].forEach(cls=>root.classList.remove(cls));
   root.querySelectorAll('[data-extra-toggle],[data-compact-toggle],[data-motion-toggle],[data-contrast-toggle]').forEach(el=>el.checked=false);
  });
  root.querySelectorAll('[data-local-note]').forEach(area=>{
   const key='datensis-cabinet-note-'+area.dataset.localNote;try{area.value=localStorage.getItem(key)||'';}catch(e){}
   area.addEventListener('input',()=>{try{localStorage.setItem(key,area.value);}catch(e){}});
  });
  root.querySelectorAll('[data-clear-note]').forEach(btn=>btn.addEventListener('click',()=>{const area=root.querySelector('[data-local-note="'+btn.dataset.clearNote+'"]');if(!area)return;area.value='';try{localStorage.removeItem('datensis-cabinet-note-'+btn.dataset.clearNote);}catch(e){}}));
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready,{once:true});else ready();
})();

/* DATENSIS Expert — compléments d’accessibilité et confort de navigation. */
(function () {
  function init() {
    const root = document.querySelector('.cabinet-workspace[data-cabinet-app]');
    if (!root) return;
    const nav = root.querySelector('.cabinet-nav');
    const links = [...(nav?.querySelectorAll('[data-tab]') || [])];
    const panels = [...root.querySelectorAll('[data-panel]')];
    links.forEach(link => {
      const id = link.dataset.tab;
      const panel = panels.find(item => item.dataset.panel === id);
      if (!panel) return;
      if (!panel.id) panel.id = id;
      link.setAttribute('aria-controls', panel.id);
      link.setAttribute('aria-label', link.textContent.trim());
    });
    nav?.addEventListener('keydown', event => {
      if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
      const current = links.indexOf(document.activeElement);
      if (current === -1) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? links.length - 1 :
        (current + (event.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length;
      links[next].focus();
    });
    // Les recherches disposent d'un bouton d'effacement via la touche Échap.
    root.querySelectorAll('input[type="search"]').forEach(input => {
      input.addEventListener('keydown', event => {
        if (event.key !== 'Escape' || !input.value) return;
        event.preventDefault();
        input.value = '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
      });
    });
    // Le lien d'accès rapide positionne le focus sans changer d'onglet.
    document.querySelector('.cabinet-skip-link')?.addEventListener('click', () => {
      root.querySelector('#cabinet-main')?.focus({ preventScroll: true });
    });
    // Ne jamais stocker les messages ou les données de dossier dans localStorage.
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();

/* DATENSIS Expert 2FA : ajouter a la fin de static/js/app.js */
(() => {
  "use strict";
  function initTwoFactor() {
    const root = document.querySelector(".twofa-page");
    if (!root) return;

    const codeInput = root.querySelector("[data-twofa-code]");
    if (codeInput) {
      codeInput.addEventListener("input", () => {
        if (codeInput.dataset.mode === "totp") {
          codeInput.value = codeInput.value.replace(/\D/g, "").slice(0, 6);
        }
      });
      codeInput.focus();
    }

    root.querySelectorAll("[data-twofa-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        if (!form.checkValidity()) return;
        if (form.dataset.submitted === "true") {
          event.preventDefault();
          return;
        }
        form.dataset.submitted = "true";
        const button = form.querySelector('button[type="submit"]');
        if (button) {
          button.disabled = true;
          button.textContent = "Traitement en cours...";
        }
      });
    });

    const copyButton = root.querySelector("[data-twofa-copy]");
    const secret = root.querySelector("[data-twofa-secret]");
    const copyFeedback = root.querySelector("[data-twofa-feedback]");
    if (copyButton && secret) {
      copyButton.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(secret.textContent.trim());
          if (copyFeedback) copyFeedback.textContent = "Clé copiée.";
        } catch {
          if (copyFeedback) copyFeedback.textContent = "Copie indisponible : sélectionnez la clé manuellement.";
        }
      });
    }

    const download = root.querySelector("[data-twofa-download]");
    if (download) {
      download.addEventListener("click", () => {
        const codes = Array.from(root.querySelectorAll("[data-twofa-recovery-code]"), (el) => el.textContent.trim());
        if (!codes.length) return;
        const content = ["DATENSIS Expert - Codes de récupération", "Chaque code est à usage unique.", "Conservez ce fichier en lieu sûr : il n'est pas chiffré.", "", ...codes].join("\n");
        const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = "datensis-codes-recuperation.txt";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTwoFactor, { once: true });
  } else {
    initTwoFactor();
  }
})();

/* DATENSIS Expert - messagerie API */
(() => {
  'use strict';
  function init() {
    const client = document.getElementById('client-chat');
    const root = client || document.getElementById('cabinet-chat');
    if (!root || root.dataset.apiInitialized) return;
    const role = client ? 'client' : 'cabinet';
    const el = suffix => document.getElementById(`${role}-chat-${suffix}`);
    const form = el('form'), history = el('history'), older = el('older');
    const body = form?.querySelector('[name="body"]');
    const csrf = form?.querySelector('[name="csrf_token"]');
    const recipient = document.getElementById('message-recipient');
    if (!form || !history || !body || !csrf || (!client && !recipient)) return;
    root.dataset.apiInitialized = 'true';
    let selected = client ? 'self' : '', generation = 0, busy = false, sending = false;
    let rows = new Map(), more = false, initialized = false, stopped = false;
    const visible = () => !document.hidden && root.getClientRects().length > 0;
    const endpoint = (kind, id = selected) => client ? root.dataset[`${kind}Url`] :
      kind === 'unread' ? '/api/cabinet/messages/unread' :
      `/api/cabinet/messages/${encodeURIComponent(id)}${kind === 'read' ? '/read' : ''}`;
    async function api(url, payload) {
      const options = {credentials:'same-origin', cache:'no-store', headers:{Accept:'application/json'}};
      if (payload !== undefined) {
        options.method = 'POST';
        options.headers['Content-Type'] = 'application/json';
        options.headers['X-CSRF-Token'] = csrf.value;
        options.body = JSON.stringify(payload);
      }
      const response = await fetch(url, options);
      if (response.status === 401 || response.status === 403) {
        stopped = true;
        throw new Error('Session ou autorisation invalide. Rechargez la page.');
      }
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.error || 'Messagerie indisponible.');
      return result.data;
    }
    function status(error = '') {
      el('connection').textContent = error ? 'Connexion interrompue' : 'Messagerie synchronisée';
      el('error').textContent = error;
      el('error').hidden = !error;
      el('retry').hidden = !error;
    }
    function node(tag, cls, text) {
      const n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined) n.textContent = text;
      return n;
    }
    function render(prepend = false) {
      const height = history.scrollHeight, top = history.scrollTop;
      const bottom = height - top - history.clientHeight < 80;
      const ordered = [...rows.values()].sort((a,b) => a.id-b.id);
      const fragment = document.createDocumentFragment();
      for (const msg of ordered) {
        const mine = msg.author_role === role;
        const bubble = node('div', `chat-bubble ${mine ? 'mine' : 'theirs'}`);
        bubble.dataset.messageId = String(msg.id);
        bubble.append(node('small', '', `${mine ? 'Vous' : client ? 'Cabinet DATENSIS' : 'Client'} · ${msg.created_at}`), node('p', '', msg.body));
        if (mine) bubble.append(node('small', `${role}-chat-receipt`, msg.read_at ? 'Lu' : 'Envoyé'));
        fragment.append(bubble);
      }
      if (!ordered.length) fragment.append(node('p','empty-state','Aucun message pour le moment.'));
      history.replaceChildren(fragment);
      if (prepend) history.scrollTop = top + history.scrollHeight - height;
      else if (bottom || !initialized) history.scrollTop = history.scrollHeight;
      el('summary').textContent = `${ordered.length} message(s) chargé(s)`;
      if (older) older.hidden = !more;
      if (el('empty')) el('empty').hidden = true;
      initialized = true;
    }
    function badge(element, count) {
      if (!element) return;
      element.textContent = count ? String(count) : '';
      element.hidden = !count;
    }
    async function refresh(loadOlder = false) {
      if (busy || sending || stopped || document.hidden) return;
      busy = true;
      const token = generation, id = selected;
      try {
        if (!client) {
          const data = await api('/api/cabinet/conversations');
          for (const contact of root.querySelectorAll('[data-chat-client-id]')) {
            const item = data.conversations.find(c => String(c.user_id) === contact.dataset.chatClientId);
            badge(contact.querySelector('[data-chat-unread]'), item?.unread_count || 0);
          }
        }
        const unread = await api(endpoint('unread'));
        badge(el('unread'), unread.unread_count);
        if (!id || !visible() || token !== generation) return;
        const before = loadOlder && rows.size ? Math.min(...rows.keys()) : null;
        const url = new URL(endpoint('messages', id), location.origin);
        url.searchParams.set('limit','50');
        if (before) url.searchParams.set('before_id',String(before));
        const data = await api(url.href);
        if (token !== generation) return;
        let changed = !initialized;
        for (const msg of data.messages) {
          if (JSON.stringify(rows.get(msg.id)) !== JSON.stringify(msg)) changed = true;
          rows.set(msg.id,msg);
        }
        if (!initialized || loadOlder) more = data.has_more;
        if (changed) render(loadOlder);
        if (visible() && history.scrollHeight - history.scrollTop - history.clientHeight < 80 && data.messages.length) {
          const last = data.messages[data.messages.length-1].id;
          if (data.messages.some(m => m.author_role !== role && !m.read_at)) {
            await api(endpoint('read',id), {up_to_id:last});
          }
        }
        if (token === generation) status();
      } catch (error) { if (token === generation) status(error.message); }
      finally { busy = false; if (token !== generation) void refresh(); }
    }
    function select(id) {
      if (client || !id || id === selected || sending) return;
      selected = id; generation++; rows = new Map(); more = false; initialized = false;
      history.replaceChildren(); older.hidden = true;
      el('title').textContent = recipient.selectedOptions[0]?.textContent.trim() || 'Conversation client';
      root.querySelectorAll('[data-chat-client-id]').forEach(button => {
        const active = button.dataset.chatClientId === id;
        button.classList.toggle('active',active); button.setAttribute('aria-pressed',String(active));
      });
      void refresh();
    }
    if (!client) {
      recipient.addEventListener('change', () => select(recipient.value));
      document.addEventListener('click', () => { if (recipient.value) select(recipient.value); });
      if (recipient.value) select(recipient.value);
    }
    form.addEventListener('submit', async event => {
      event.preventDefault(); // Capture : neutralise le verrou de soumission classique.
      if (sending || stopped || !form.checkValidity()) return;
      const id = client ? 'self' : recipient.value;
      const text = body.value.trim();
      if (!id || !text || text.length > 2000) return;
      if (!client) select(id);
      sending = true; generation++;
      const button = form.querySelector('[type="submit"]');
      button.disabled = true; body.readOnly = true;
      if (recipient) recipient.disabled = true;
      form.setAttribute('aria-busy','true');
      try {
        await api(endpoint('send',id), {body:text});
        body.value = ''; body.dispatchEvent(new Event('input',{bubbles:true}));
        status();
      } catch (error) { status(error.message); }
      finally {
        sending = false; button.disabled = false; body.readOnly = false;
        if (recipient) recipient.disabled = false;
        form.removeAttribute('aria-busy'); delete form.dataset.clientSubmitting;
        if (!client && recipient.value !== selected) select(recipient.value);
        void refresh();
      }
    }, true);
    older?.addEventListener('click', () => void refresh(true));
    el('retry')?.addEventListener('click', () => { if (stopped) location.reload(); else void refresh(); });
    document.addEventListener('visibilitychange', () => void refresh());
    window.setInterval(() => void refresh(),3000);
    void refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
