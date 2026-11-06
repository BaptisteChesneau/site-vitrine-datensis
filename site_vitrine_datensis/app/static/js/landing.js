
(function(){
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var small = window.innerWidth < 980;

  function count(el){
    if(el.dataset.done) return; el.dataset.done = 1;
    var to = +el.dataset.count;
    if(reduce || to === 0){ el.textContent = to; return; }
    var t0 = null;
    function step(t){ if(!t0) t0 = t; var p = Math.min((t - t0)/1400, 1); p = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(to * p); if(p < 1) requestAnimationFrame(step); }
    requestAnimationFrame(step);
  }

  /* Pixels du logo */
  var palette = ['#6FD6B6','#6FD6B6','#6FD6B6','#FFFFFF','#FF7F6E','#1F4258','#1F4258'];
  function field(id, n, area){
    var box = document.getElementById(id); if(!box) return [];
    var out = [];
    for(var i = 0; i < n; i++){
      var s = [6,8,10,12,14][Math.floor(Math.random()*5)];
      var d = document.createElement('span'); d.className = 'px';
      var c = palette[Math.floor(Math.random()*palette.length)];
      var o = c === '#FFFFFF' ? .55 : (c === '#1F4258' ? .9 : .75);
      d.style.cssText = '--s:'+s+'px;--c:'+c+';--o:'+o+';left:'+(area.x0 + Math.random()*(area.x1-area.x0))+'%;top:'+(area.y0 + Math.random()*(area.y1-area.y0))+'%';
      box.appendChild(d); out.push(d);
    }
    return out;
  }
  var heroPx = field('pixels', small ? 14 : 46, small ? {x0:62,x1:96,y0:4,y1:11} : {x0:52,x1:98,y0:8,y1:92});
  var contactPx = field('pixels2', small ? 8 : 22, {x0:84,x1:99,y0:3,y1:14});
  function animatePixels(list, base){
    if(reduce || !list.length || !list[0].animate) return;
    list.forEach(function(p, i){
      var dx = (Math.random()*-160 - 40), dy = (Math.random()*80 - 40);
      p.animate([{transform:'translate('+dx+'px,'+dy+'px) scale(.2)',opacity:0},{transform:'none',opacity:getComputedStyle(p).opacity}],
        {duration:900 + Math.random()*700, delay:base + i*28, easing:'cubic-bezier(.2,.7,.2,1)', fill:'backwards'});
      if(i % 3 === 0) p.animate([{transform:'translateY(0)'},{transform:'translateY(-'+(6+Math.random()*10)+'px)'},{transform:'translateY(0)'}],
        {duration:4000 + Math.random()*4000, delay:2600 + Math.random()*2000, iterations:Infinity, easing:'ease-in-out'});
    });
  }

  /* Ouverture : le flux d'une donnée traverse les modules */
  var started = false;
  function start(){
    if(started) return; started = true;
    document.body.classList.add('loaded');
    animatePixels(heroPx, 100);
    var items = document.querySelectorAll('#events li');
    var base = reduce ? 0 : 1100, gap = reduce ? 0 : 520;
    items.forEach(function(li, i){ setTimeout(function(){ li.classList.add('on'); }, base + i*gap); });
    setTimeout(function(){ document.getElementById('feedfoot').classList.add('go'); }, base + items.length*gap);
  }
  window.addEventListener('load', start); setTimeout(start, 1200);

  /* Places de l'offre fondateurs */
  var seats = document.getElementById('seats');
  for(var s = 0; s < 100; s++){ var q = document.createElement('i'); q.style.setProperty('--i', s); seats.appendChild(q); }

  /* Cycle : carré qui tourne autour de la donnée */
  var orbit = document.getElementById('orbit'), ang = 0, ringOn = false;
  function spin(){ if(!ringOn) return; ang = (ang + .35) % 360; orbit.setAttribute('transform','translate(250 250) rotate('+ang+')'); requestAnimationFrame(spin); }
  orbit.setAttribute('transform','translate(250 250)');

  /* Parcours guidé : phases chronométrées */
  var appRun = false;
  function runApp(){
    if(appRun) return; appRun = true;
    var lis = document.querySelectorAll('#phases li'), clock = document.getElementById('clock'), total = document.getElementById('total');
    var durs = [252, 418, 196, 143]; // secondes simulées par phase
    function fmt(x){ var m = Math.floor(x/60), s = Math.floor(x%60); return (m<10?'0':'')+m+':'+(s<10?'0':'')+s; }
    if(reduce){ var sum=0; lis.forEach(function(li,i){ li.classList.add('done'); sum+=durs[i]; li.querySelector('.tm').textContent = fmt(durs[i]); }); clock.textContent = total.textContent = fmt(sum); return; }
    var i = 0, elapsed = 0;
    function phase(){
      if(i >= lis.length){ return; }
      var li = lis[i]; li.classList.add('cur');
      var d = durs[i], t0 = null, start = elapsed;
      function tick(t){
        if(!t0) t0 = t; var p = Math.min((t - t0)/1300, 1), cur = d*p;
        li.querySelector('.tm').textContent = fmt(cur); clock.textContent = total.textContent = fmt(start + cur);
        if(p < 1) requestAnimationFrame(tick); else { elapsed += d; li.classList.remove('cur'); li.classList.add('done'); i++; setTimeout(phase, 250); }
      }
      requestAnimationFrame(tick);
    }
    phase();
  }

  /* Fusion des outils */
  function merge(el){ setTimeout(function(){ el.classList.add('merged'); }, reduce ? 0 : 1300); }
  function placeTools(){
    var tools = document.querySelectorAll('#merge .tool');
    tools.forEach(function(t, i){ t.dataset.top = t.style.top; });
  }
  placeTools();
  var mergedTop = [96, 156, 216, 276, 336];
  var mo = new MutationObserver(function(){
    if(document.getElementById('merge').classList.contains('merged')){
      document.querySelectorAll('#merge .tool').forEach(function(t, i){ t.style.top = mergedTop[i] + 'px'; });
      mo.disconnect();
    }
  });
  mo.observe(document.getElementById('merge'), {attributes:true, attributeFilter:['class']});

  /* Révélations au défilement */
  var targets = document.querySelectorAll('[data-reveal],[data-observe]');
  function onIn(el){
    el.classList.add('is-in');
    el.querySelectorAll && el.querySelectorAll('[data-count]:not([data-run])').forEach(count);
    if(el.id === 'merge') merge(el);
    if(el.id === 'ring'){ ringOn = !reduce; if(ringOn) requestAnimationFrame(spin); }
    if(el.id === 'app') setTimeout(runApp, reduce ? 0 : 600);
    if(el.id === 'contact-form') animatePixels(contactPx, 0);
  }
  if(!('IntersectionObserver' in window) || reduce){
    targets.forEach(onIn);
  } else {
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){ if(!e.isIntersecting) return; onIn(e.target); io.unobserve(e.target); });
    }, {threshold:.2, rootMargin:'0px 0px -6% 0px'});
    targets.forEach(function(el){ io.observe(el); });
  }

  /* En-tête et barre de lecture */
  var bar = document.getElementById('progress'), top = document.getElementById('top');
  function onScroll(){ var h = document.documentElement.scrollHeight - innerHeight;
    bar.style.transform = 'scaleX(' + (h > 0 ? scrollY/h : 0) + ')'; top.classList.toggle('solid', scrollY > 40); }
  addEventListener('scroll', onScroll, {passive:true}); onScroll();

  /* Formulaire (à relier au CRM du site vitrine) */
  var f = document.getElementById('contact-form');
  f.addEventListener('submit', async function(e){
    e.preventDefault();
    if(!f.checkValidity()){ f.reportValidity(); return; }
    const button = f.querySelector('button[type=submit]');
    const message = document.getElementById('form-ok');
    button.disabled = true;
    try {
      const response = await fetch(f.action, {method:'POST', body:new FormData(f), headers:{'Accept':'application/json'}});
      const result = await response.json();
      message.textContent = result.message || 'Erreur lors de la demande.';
      message.style.display = 'block';
      message.style.background = response.ok ? 'var(--mint-soft)' : 'var(--coral-soft)';
      if(response.ok) f.reset();
    } catch(error) {
      message.textContent = 'Connexion impossible. Veuillez réessayer.';
      message.style.display = 'block';
    } finally {button.disabled = false;}
  });
})();
