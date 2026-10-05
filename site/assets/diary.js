// Photodiary: reads /data/index.json (written by server/ on the VPS).
// On / it projects one night (the newest, or ?d=YYYY-MM-DD) with its record as subtitles;
// on /archive/ it lays all nights out as a contact sheet.
(function () {
  var today = document.querySelector('.today[data-source]');
  var sheet = document.querySelector('.sheet[data-source]');
  var root = today || sheet;
  if (!root) return;
  var DATA = '/data/';
  var still = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  var longDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  var shortDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  function date(iso, f) { return (f || longDate).format(new Date(iso + 'T12:00:00Z')); }

  function el(tag, className, text) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    if (text != null) e.textContent = text;
    return e;
  }

  // "23:41. 1/8 s, ISO 3200."
  function exposure(p) {
    var parts = [p.shutter, p.iso && 'ISO ' + p.iso].filter(Boolean).join(', ');
    return [p.time, parts].filter(Boolean).join('. ') + '.';
  }

  // Artist, <cite>Title</cite> as one line; link to Discogs when asked
  function recordLine(r, link) {
    var p = el('p');
    p.appendChild(document.createTextNode(r.artist + ', '));
    var c = el('cite', null, r.title);
    if (link && r.link) { var a = el('a'); a.href = r.link; a.rel = 'noopener'; a.appendChild(c); p.appendChild(a); }
    else p.appendChild(c);
    p.appendChild(document.createTextNode('.'));
    return p;
  }
  function recordInfo(r) {
    var info = [r.label, r.catno, r.year].filter(Boolean).join(', ');
    var extra = [r.format, r.style].filter(Boolean).join('. ');
    return [info, extra].filter(Boolean).join('. ') + '.';
  }

  function develop(img) {
    // the photo slowly rises out of the black once loaded
    function done() { img.classList.add('developed'); }
    if (img.complete && img.naturalWidth) done(); else img.addEventListener('load', done);
  }

  // The light flickers now and then: at irregular moments, once or twice, too briefly to be sure.
  function flicker() {
    if (still) return;
    var b = document.body;
    function dip(ms, then) { b.classList.add('flicker'); setTimeout(function () { b.classList.remove('flicker'); if (then) then(); }, ms); }
    (function next() {
      setTimeout(function () {
        if (!document.hidden) {
          if (Math.random() < .35) dip(60, function () { setTimeout(function () { dip(110); }, 90); });
          else dip(70 + Math.random() * 90);
        }
        next();
      }, 20000 + Math.random() * 50000);
    })();
  }

  // Click the photo (or "Listen" under it): a snippet of the record. A preview plays as audio with a
  // thin red line as progress; a YouTube video plays in place of the photo. Meanwhile the light goes red.
  function sound(plate, s, label, statusBox) {
    if (!s || !(s.preview || s.video)) return;
    var button = plate.querySelector('[data-field=play]');
    var close = plate.querySelector('[data-field=close]');
    var line = plate.querySelector('.progress');
    var frameBox = plate.querySelector('.print');
    var status = el('button', 'listen');
    status.type = 'button';
    statusBox.appendChild(status);
    button.hidden = false;

    function set(playing) {
      document.body.classList.toggle('red-lamp', playing);
      status.textContent = playing ? '■ ' + button.dataset.stop : '▶ ' + button.dataset.listen;
      var name = (playing ? button.dataset.stop : button.dataset.listen) + ': ' + label;
      button.setAttribute('aria-label', name);
      status.setAttribute('aria-label', name);
    }
    set(false);

    if (s.preview) {
      var audio = new Audio();
      audio.preload = 'none';
      audio.src = s.preview;
      function toggle() { if (audio.paused) audio.play().catch(function () {}); else { audio.pause(); audio.currentTime = 0; } }
      button.addEventListener('click', toggle);
      status.addEventListener('click', toggle);
      function stopped() { set(false); line.style.width = '0'; }
      audio.addEventListener('play', function () { set(true); });
      audio.addEventListener('pause', stopped);
      audio.addEventListener('ended', stopped);
      audio.addEventListener('timeupdate', function () {
        if (audio.duration) line.style.width = (100 * audio.currentTime / audio.duration) + '%';
      });
      return;
    }

    // video: start a minute in, where the record is usually well under way
    var frame;
    function open() {
      if (frame) return;
      frame = el('iframe');
      frame.src = 'https://www.youtube-nocookie.com/embed/' + s.video + '?autoplay=1&start=60&rel=0&modestbranding=1';
      frame.allow = 'autoplay; encrypted-media';
      frame.title = label;
      frameBox.appendChild(frame);
      plate.classList.add('playing-video');
      set(true);
      close.hidden = false;
      close.focus();
    }
    function shut() {
      if (frame) frame.remove();
      frame = null;
      plate.classList.remove('playing-video');
      set(false);
      close.hidden = true;
      button.focus();
    }
    button.addEventListener('click', open);
    status.addEventListener('click', function () { if (frame) shut(); else open(); });
    close.addEventListener('click', shut);
  }

  function project(days) {
    var wanted = new URLSearchParams(location.search).get('d');
    var n = 0;
    days.forEach(function (d, i) { if (d.date === wanted) n = i; });
    var d = days[n];
    var plate = today.querySelector('.screen');

    var time = today.querySelector('[data-field=date]');
    time.dateTime = d.date;
    time.textContent = date(d.date);
    if (n > 0) document.title = date(d.date) + ' — Photodiary';
    today.querySelector('[data-field=exposure]').textContent = d.photo ? exposure(d.photo) : today.dataset.noPhoto;

    var img = today.querySelector('[data-field=photo]');
    if (d.photo) {
      img.width = d.photo.width;
      img.height = d.photo.height;
      img.src = DATA + d.photo.src;
      img.hidden = false;
      develop(img);
    }

    var rec = today.querySelector('[data-field=record]');
    rec.textContent = '';
    if (d.record) {
      var head = recordLine(d.record, true);
      head.insertBefore(document.createTextNode('On the turntable: '), head.firstChild);
      rec.appendChild(head);
      rec.appendChild(el('p', 'info', recordInfo(d.record)));
      sound(plate, d.record.sound, d.record.artist + ', ' + d.record.title, today.querySelector('[data-field=status]'));
    }

    // the way to the neighbouring nights
    var before = today.querySelector('[data-field=before]');
    var later = today.querySelector('[data-field=later]');
    if (n + 1 < days.length) { before.href = '/?d=' + days[n + 1].date; before.hidden = false; }
    if (n > 0) { later.href = n === 1 ? '/' : '/?d=' + days[n - 1].date; later.hidden = false; }
  }

  function contactSheet(days) {
    days.forEach(function (d, i) {
      var li = el('li');
      var a = el('a');
      a.href = i === 0 ? '/' : '/?d=' + d.date;
      a.setAttribute('aria-label', date(d.date) + (d.record ? ': ' + d.record.artist + ', ' + d.record.title : ''));
      var frame = el('span', 'frame');
      if (d.photo) {
        var img = el('img');
        img.src = DATA + d.photo.small;
        img.alt = '';
        img.loading = 'lazy';
        img.width = 640;
        img.height = Math.round(640 * d.photo.height / d.photo.width);
        frame.appendChild(img);
        develop(img);
      }
      if (d.record) {
        var sub = el('span', 'subtitle');
        sub.appendChild(recordLine(d.record));
        frame.appendChild(sub);
      }
      a.appendChild(frame);
      var mark = el('span', 'mark');
      mark.appendChild(el('span', null, String(days.length - i)));
      mark.appendChild(el('span', null, date(d.date, shortDate)));
      a.appendChild(mark);
      li.appendChild(a);
      sheet.appendChild(li);
    });
  }

  flicker();
  fetch(root.dataset.source, { cache: 'no-cache' })
    .then(function (r) { return r.ok ? r.json() : []; })
    .then(function (days) {
      if (!Array.isArray(days) || !days.length) return;
      if (today) project(days);
      if (sheet) contactSheet(days);
    })
    .catch(function () {});
})();
