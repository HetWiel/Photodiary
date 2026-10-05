// Photodiary: reads /data/index.json (written by server/ on the VPS) and uses it to fill
// today's plate on / and the list on /archive/.
(function () {
  lamp();
  var today = document.querySelector('.today[data-source]');
  var archive = document.querySelector('.register[data-source]');
  var root = today || archive;
  if (!root) return;
  var DATA = '/data/';

  var dateFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  function formatDate(iso) { return dateFormat.format(new Date(iso + 'T12:00:00Z')); }

  // The lamp flickers now and then: at irregular moments, once or twice, too briefly to be sure.
  function lamp() {
    if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var b = document.body;
    function dip(ms, then) { b.classList.add('flicker'); setTimeout(function () { b.classList.remove('flicker'); if (then) then(); }, ms); }
    function next() {
      setTimeout(function () {
        if (!document.hidden) {
          if (Math.random() < .35) dip(60, function () { setTimeout(function () { dip(110); }, 90); });
          else dip(70 + Math.random() * 90);
        }
        next();
      }, 20000 + Math.random() * 50000);
    }
    next();
  }

  function el(tag, className, text) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    if (text != null) e.textContent = text;
    return e;
  }

  // "1/15 s, ISO 2500, 23:52" (in the archive with "Phone camera, " in front)
  function exposure(p, camera) {
    var parts = camera ? [camera] : [];
    if (p.shutter) parts.push(p.shutter);
    if (p.iso) parts.push('ISO ' + p.iso);
    if (p.time) parts.push(p.time);
    return parts.join(', ');
  }

  // Artist, <cite>Title</cite> (linking to Discogs) and below it label, catalogue number, year, format, style
  function record(r, target) {
    var line = el('p', 'turntable-title');
    line.appendChild(document.createTextNode(r.artist + ', '));
    var a = el('a');
    a.href = r.link;
    a.rel = 'noopener';
    a.appendChild(el('cite', null, r.title));
    line.appendChild(a);
    target.appendChild(line);
    var info = [r.label, r.catno, r.year].filter(Boolean).join(', ');
    var extra = [r.format, r.style].filter(Boolean).join('. ');
    if (info || extra) target.appendChild(el('p', 'turntable-info', [info, extra].filter(Boolean).join('. ') + '.'));
  }

  function develop(img) {
    // the photo "develops": it slowly rises out of the black once loaded
    function done() { img.classList.add('developed'); }
    if (img.complete && img.naturalWidth) done(); else img.addEventListener('load', done);
  }

  // Click the photo: a snippet of the record. A preview (iTunes) plays as audio,
  // with a thin line as progress; a YouTube video plays visibly in place of the photo.
  function sound(plate, s, label) {
    if (!s || !(s.preview || s.video)) return;
    var button = plate.querySelector('[data-field=play]');
    var close = plate.querySelector('[data-field=close]');
    var line = plate.querySelector('.progress');
    var frameBox = plate.querySelector('.print');
    var head = plate.querySelector('.turntable-head');
    var status = el('span', 'playing');
    head.appendChild(status);
    button.hidden = false;

    function set(playing) {
      document.body.classList.toggle('red-lamp', playing);
      status.textContent = playing ? '■ ' + button.dataset.stop : '▶ ' + button.dataset.listen;
      button.setAttribute('aria-label', (playing ? button.dataset.stop : button.dataset.listen) + ': ' + label);
    }
    set(false);

    if (s.preview) {
      var audio = new Audio();
      audio.preload = 'none';
      audio.src = s.preview;
      button.addEventListener('click', function () {
        if (audio.paused) audio.play().catch(function () {}); else { audio.pause(); audio.currentTime = 0; }
      });
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
    button.addEventListener('click', function () {
      frame = el('iframe');
      frame.src = 'https://www.youtube-nocookie.com/embed/' + s.video + '?autoplay=1&start=60&rel=0&modestbranding=1';
      frame.allow = 'autoplay; encrypted-media';
      frame.title = label;
      frameBox.appendChild(frame);
      plate.classList.add('playing-video');
      document.body.classList.add('red-lamp');
      close.hidden = false;
      close.focus();
    });
    close.addEventListener('click', function () {
      if (frame) frame.remove();
      plate.classList.remove('playing-video');
      document.body.classList.remove('red-lamp');
      close.hidden = true;
      button.focus();
    });
  }

  fetch(root.dataset.source, { cache: 'no-cache' })
    .then(function (r) { return r.ok ? r.json() : []; })
    .then(function (days) {
      if (!Array.isArray(days) || !days.length) return;
      var noPhoto = root.dataset.noPhoto;

      if (today) {
        var d = days[0];
        var time = today.querySelector('[data-field=date]');
        time.dateTime = d.date;
        time.textContent = formatDate(d.date);
        today.querySelector('[data-field=exposure]').textContent = d.photo ? exposure(d.photo) : noPhoto;
        var img = today.querySelector('[data-field=photo]');
        if (d.photo) {
          img.width = d.photo.width;
          img.height = d.photo.height;
          img.src = DATA + d.photo.src;
          img.hidden = false;
          develop(img);
        }
        var r = today.querySelector('[data-field=record]');
        r.textContent = '';
        if (d.record) {
          r.appendChild(el('p', 'turntable-head', 'On the turntable'));
          record(d.record, r);
          sound(today, d.record.sound, d.record.artist + ', ' + d.record.title);
        }
      }

      if (archive) {
        var camera = archive.dataset.camera;
        var list = archive.querySelector('tbody');
        days.forEach(function (d, i) {
          var tr = el('tr');
          tr.appendChild(el('td', 'nr', String(days.length - i)));
          var th = el('th', 'title');
          th.scope = 'row';
          var t = el('time', null, formatDate(d.date));
          t.dateTime = d.date;
          th.appendChild(t);
          tr.appendChild(th);
          var cell = el('td', 'print-small');
          if (d.photo) {
            var a = el('a');
            a.href = DATA + d.photo.src;
            var img = el('img');
            img.src = DATA + d.photo.small;
            img.alt = archive.dataset.alt;
            img.loading = 'lazy';
            img.width = 640;
            img.height = Math.round(640 * d.photo.height / d.photo.width);
            a.appendChild(img);
            cell.appendChild(a);
            develop(img);
          } else {
            cell.appendChild(el('span', 'empty-print'));
          }
          tr.appendChild(cell);
          tr.appendChild(el('td', 'medium', d.photo ? exposure(d.photo, camera) : noPhoto));
          var desc = el('td', 'description');
          if (d.record) record(d.record, desc);
          tr.appendChild(desc);
          list.appendChild(tr);
        });
        var empty = document.querySelector('.empty');
        if (empty) empty.hidden = true;
      }
    })
    .catch(function () {});
})();
