// Het dagboek: leest /data/index.json (gemaakt door server/ op de VPS) en vult daarmee
// de plaat van vandaag op / en de lijst op /archive/.
(function () {
  var vandaag = document.querySelector('.vandaag[data-bron]');
  var archief = document.querySelector('.register[data-bron]');
  var bron = vandaag || archief;
  if (!bron) return;
  var DATA = '/data/';

  var datumtekst = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  function datum(iso) { return datumtekst.format(new Date(iso + 'T12:00:00Z')); }

  function el(naam, klasse, tekst) {
    var e = document.createElement(naam);
    if (klasse) e.className = klasse;
    if (tekst != null) e.textContent = tekst;
    return e;
  }

  // "1/15 s, ISO 2500, 23:52" (in het archief met "Phone camera, " ervoor)
  function techniek(f, camera) {
    var delen = camera ? [camera] : [];
    if (f.sluiter) delen.push(f.sluiter);
    if (f.iso) delen.push('ISO ' + f.iso);
    if (f.tijd) delen.push(f.tijd);
    return delen.join(', ');
  }

  // Artiest, <cite>Titel</cite> (link naar Discogs) en daaronder label, catalogusnummer, jaar, formaat, stijl
  function plaat(p, doel) {
    var regel = el('p', 'draait-titel');
    regel.appendChild(document.createTextNode(p.artiest + ', '));
    var a = el('a');
    a.href = p.link;
    a.rel = 'noopener';
    a.appendChild(el('cite', null, p.titel));
    regel.appendChild(a);
    doel.appendChild(regel);
    var info = [p.label, p.catno, p.jaar].filter(Boolean).join(', ');
    var extra = [p.formaat, p.stijl].filter(Boolean).join('. ');
    if (info || extra) doel.appendChild(el('p', 'draait-info', [info, extra].filter(Boolean).join('. ') + '.'));
  }

  function afdruk(img) {
    // de foto "ontwikkelt": hij komt langzaam uit het zwart op zodra hij geladen is
    function klaar() { img.classList.add('ontwikkeld'); }
    if (img.complete && img.naturalWidth) klaar(); else img.addEventListener('load', klaar);
  }

  // Klik op de foto: een fragment van de plaat. Een voorproef (iTunes) speelt als geluid,
  // met een dun lijntje als voortgang; een YouTube-video speelt zichtbaar op de plek van de foto.
  function geluid(held, g, naam) {
    if (!g || !(g.fragment || g.video)) return;
    var knop = held.querySelector('[data-veld=speel]');
    var sluit = held.querySelector('[data-veld=sluit]');
    var lijn = held.querySelector('.voortgang');
    var vak = held.querySelector('.afdruk');
    var kop = held.querySelector('.draait-kop');
    var staat = el('span', 'speelt');
    kop.appendChild(staat);
    knop.hidden = false;

    function zet(speelt) {
      staat.textContent = speelt ? '■ ' + knop.dataset.stop : '▶ ' + knop.dataset.luister;
      knop.setAttribute('aria-label', (speelt ? knop.dataset.stop : knop.dataset.luister) + ': ' + naam);
    }
    zet(false);

    if (g.fragment) {
      var audio = new Audio();
      audio.preload = 'none';
      audio.src = g.fragment;
      knop.addEventListener('click', function () {
        if (audio.paused) audio.play().catch(function () {}); else { audio.pause(); audio.currentTime = 0; }
      });
      function klaar() { zet(false); lijn.style.width = '0'; }
      audio.addEventListener('play', function () { zet(true); });
      audio.addEventListener('pause', klaar);
      audio.addEventListener('ended', klaar);
      audio.addEventListener('timeupdate', function () {
        if (audio.duration) lijn.style.width = (100 * audio.currentTime / audio.duration) + '%';
      });
      return;
    }

    // video: start een minuut in, daar zit de plaat meestal al goed op gang
    var frame;
    knop.addEventListener('click', function () {
      frame = el('iframe');
      frame.src = 'https://www.youtube-nocookie.com/embed/' + g.video + '?autoplay=1&start=60&rel=0&modestbranding=1';
      frame.allow = 'autoplay; encrypted-media';
      frame.title = naam;
      vak.appendChild(frame);
      held.classList.add('speelt-video');
      sluit.hidden = false;
      sluit.focus();
    });
    sluit.addEventListener('click', function () {
      if (frame) frame.remove();
      held.classList.remove('speelt-video');
      sluit.hidden = true;
      knop.focus();
    });
  }

  fetch(bron.dataset.bron, { cache: 'no-cache' })
    .then(function (r) { return r.ok ? r.json() : []; })
    .then(function (dagen) {
      if (!Array.isArray(dagen) || !dagen.length) return;
      var geenFoto = bron.dataset.geenFoto;

      if (vandaag) {
        var d = dagen[0];
        var tijd = vandaag.querySelector('[data-veld=datum]');
        tijd.dateTime = d.datum;
        tijd.textContent = datum(d.datum);
        vandaag.querySelector('[data-veld=techniek]').textContent = d.foto ? techniek(d.foto) : geenFoto;
        var img = vandaag.querySelector('[data-veld=foto]');
        if (d.foto) {
          img.width = d.foto.breed;
          img.height = d.foto.hoog;
          img.src = DATA + d.foto.src;
          img.hidden = false;
          afdruk(img);
        }
        var p = vandaag.querySelector('[data-veld=plaat]');
        p.textContent = '';
        if (d.plaat) {
          p.appendChild(el('p', 'draait-kop', 'On the turntable'));
          plaat(d.plaat, p);
          geluid(vandaag, d.plaat.geluid, d.plaat.artiest + ', ' + d.plaat.titel);
        }
      }

      if (archief) {
        var camera = archief.dataset.camera;
        var lijst = archief.querySelector('tbody');
        dagen.forEach(function (d, i) {
          var tr = el('tr');
          tr.appendChild(el('td', 'nr', String(dagen.length - i)));
          var th = el('th', 'titel');
          th.scope = 'row';
          var t = el('time', null, datum(d.datum));
          t.dateTime = d.datum;
          th.appendChild(t);
          tr.appendChild(th);
          var vak = el('td', 'afdruk-klein');
          if (d.foto) {
            var a = el('a');
            a.href = DATA + d.foto.src;
            var img = el('img');
            img.src = DATA + d.foto.klein;
            img.alt = archief.dataset.alt;
            img.loading = 'lazy';
            img.width = 640;
            img.height = Math.round(640 * d.foto.hoog / d.foto.breed);
            a.appendChild(img);
            vak.appendChild(a);
            afdruk(img);
          } else {
            vak.appendChild(el('span', 'leeg-vak'));
          }
          tr.appendChild(vak);
          tr.appendChild(el('td', 'materiaal', d.foto ? techniek(d.foto, camera) : geenFoto));
          var pl = el('td', 'omschrijving');
          if (d.plaat) plaat(d.plaat, pl);
          tr.appendChild(pl);
          lijst.appendChild(tr);
        });
        var leeg = document.querySelector('.leeg');
        if (leeg) leeg.hidden = true;
      }
    })
    .catch(function () {});
})();
