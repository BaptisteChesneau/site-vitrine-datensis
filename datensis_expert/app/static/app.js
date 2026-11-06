"use strict";
(() => {
  const root = document.querySelector(".client-workspace");
  if (!root) return;
  const tabs = [...root.querySelectorAll("[data-tab]")];
  const panels = [...root.querySelectorAll(".tab-panel")];
  const valid = new Set(panels.map(p => p.id));
  function activate() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); }
    catch { id = "accueil"; }
    if (!valid.has(id)) id = "accueil";
    tabs.forEach(link => {
      const active = link.dataset.tab === id;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    panels.forEach(panel => {
      const active = panel.id === id;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
  }
  window.addEventListener("hashchange", activate);
  root.querySelectorAll("[data-go]").forEach(link => link.addEventListener("click", () => {
    const target = link.dataset.go;
    if (valid.has(target)) activatePanel(target);
  }));
  function activatePanel(id) {
    panels.forEach(p => { p.hidden = p.id !== id; p.classList.toggle("active", p.id === id); });
    tabs.forEach(t => { const on = t.dataset.tab === id; t.classList.toggle("active", on); if(on)t.setAttribute("aria-current","page");else t.removeAttribute("aria-current"); });
  }
  root.querySelectorAll("[data-filter-target]").forEach(input => input.addEventListener("input", () => {
    const target = document.getElementById(input.dataset.filterTarget);
    if (!target) return;
    const search = input.value.trim().toLocaleLowerCase("fr-FR");
    target.querySelectorAll(".searchable").forEach(item => {
      item.hidden = !item.textContent.toLocaleLowerCase("fr-FR").includes(search);
    });
  }));
  activate();

  const app = document.getElementById("calendar-app");
  if (!app) return;
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
})();
