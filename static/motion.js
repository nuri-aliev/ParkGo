/* Local motion layer. The sheet spring retains position and velocity on interruption. */
(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const animations = new Map();
  const ease = 'cubic-bezier(.22,1,.36,1)';

  function play(element, frames, duration = 260, complete = () => {}, easing = ease) {
    if (!element) return;
    const previous = animations.get(element);
    if (previous) {
      const current = getComputedStyle(element);
      const start = {};
      for (const key of Object.keys(frames[0])) start[key] = current[key];
      frames = [start, ...frames.slice(1)];
      previous.cancel();
      animations.delete(element);
    }
    if (reduced.matches || !element.animate) {
      complete();
      return;
    }
    const animation = element.animate(frames, {duration, easing, fill: 'both'});
    animations.set(element, animation);
    animation.onfinish = () => {
      if (animations.get(element) !== animation) return;
      animations.delete(element);
      complete();
      animation.cancel();
    };
  }

  function reveal(element) {
    play(element, [
      {opacity: 0, transform: 'translateY(8px)'},
      {opacity: 1, transform: 'translateY(0)'}
    ]);
  }

  const screens = [...document.querySelectorAll('.scr')];
  screens.forEach(screen => { screen.inert = !screen.classList.contains('on'); });
  const depth = {home: 0, bookings: 0, support: 0, promos: 0, spaces: 1, faq: 1, ticket: 1, book: 2, done: 3};
  function navigate(previous, next) {
    if (!next || previous === next) return;
    const tabs = ['home', 'bookings', 'support', 'promos'];
    const fromTab = tabs.indexOf(previous?.id);
    const toTab = tabs.indexOf(next.id);
    const switchingTabs = fromTab !== -1 && toTab !== -1;
    const forward = (depth[next.id] ?? 0) >= (depth[previous?.id] ?? 0);
    const distance = forward ? 8 : -8;
    screens.forEach(screen => {
      if (screen !== previous) {
        animations.get(screen)?.cancel();
        animations.delete(screen);
        screen.classList.remove('motion-out');
      }
    });
    if (previous) previous.classList.add('motion-out');
    screens.forEach(screen => {
      screen.classList.toggle('on', screen === next);
      screen.inert = screen !== next;
    });
    next.classList.remove('motion-out');
    if (previous) {
      play(previous, switchingTabs
        ? [{opacity: 1}, {opacity: 0}]
        : [{opacity: 1, transform: 'translateX(0)'}, {opacity: 0, transform: `translateX(${-distance / 2}px)`}],
      150, () => previous.classList.remove('motion-out'));
    }
    play(next, switchingTabs
      ? [{opacity: 0}, {opacity: 1}]
      : [{opacity: 0, transform: `translateX(${distance}px)`}, {opacity: 1, transform: 'translateX(0)'}], 250);
    const nav = next.querySelector('.nav');
    if (nav) {
      const index = [...nav.querySelectorAll('button')].findIndex(button => button.classList.contains('on'));
      if (switchingTabs && index >= 0) {
        play(nav.querySelector('.nav-indicator'), [
          {transform: `translateX(${fromTab * 100}%)`},
          {transform: `translateX(${index * 100}%)`}
        ], 250);
      }
    }
  }

  const loader = document.querySelector('#loader');
  const logo = loader?.querySelector('.splash-logo');
  const app = document.querySelector('#app');
  const splashStarted = performance.now();
  let splashTimer = 0;
  let splashReady = false;
  if (loader) {
    if (app) app.inert = true;
    play(logo, [
      {opacity: 0, transform: 'rotate(-8deg) scale(.84)'},
      {opacity: 1, transform: 'rotate(-8deg) scale(1)'}
    ], 320);
  }

  function hideSplash() {
    clearTimeout(splashTimer);
    for (const element of [logo, loader]) {
      animations.get(element)?.cancel();
      animations.delete(element);
    }
    loader.hidden = true;
    if (app) app.inert = false;
  }

  function finishLoading() {
    if (!loader || loader.hidden || loader.dataset.leaving) return;
    splashReady = true;
    clearTimeout(splashTimer);
    if (reduced.matches) { hideSplash(); return; }
    const remaining = 360 - (performance.now() - splashStarted);
    if (remaining > 0) {
      splashTimer = setTimeout(finishLoading, remaining);
      return;
    }
    loader.dataset.leaving = 'true';
    // The intro has elapsed; discard it even if a background tab skipped frames.
    animations.get(logo)?.cancel();
    animations.delete(logo);
    // Expand the mark into the map as the splash disappears.
    play(logo, [
      {opacity: 1, transform: 'rotate(-8deg) scale(1)'},
      {opacity: 1, transform: 'rotate(-8deg) scale(1.18)', offset: .25},
      {opacity: .9, transform: 'rotate(-8deg) scale(3.2)', offset: .65},
      {opacity: 0, transform: 'rotate(-8deg) scale(16)'}
    ], 640, () => {}, 'cubic-bezier(.4,0,.8,.5)');
    play(loader, [{opacity: 1}, {opacity: 1, offset: .45}, {opacity: 0}], 640, hideSplash, 'ease-in');
  }

  // A tap or key can finish the introduction as soon as content is ready.
  loader?.addEventListener('pointerdown', () => { if (splashReady) hideSplash(); });
  document.addEventListener('keydown', event => {
    if (loader && !loader.hidden && splashReady && ['Escape', 'Enter', ' '].includes(event.key)) {
      event.preventDefault();
      hideSplash();
    }
  });

  function confirmBooking() {
    const badge = document.querySelector('#done .ok');
    const check = badge?.querySelector('path');
    play(badge, [{transform: 'translateY(8px) scale(.96)', opacity: 0}, {transform: 'translateY(0) scale(1)', opacity: 1}], 350);
    if (check) {
      const length = check.getTotalLength();
      check.style.strokeDasharray = length;
      play(check, [{strokeDashoffset: String(length)}, {strokeDashoffset: '0'}], 400);
    }
  }

  function selectSpot(element) {
    play(element?.querySelector('.bay-check'), [
      {transform: 'scale(.72)', opacity: 0},
      {transform: 'scale(1)', opacity: 1}
    ], 220);
  }

  const sheet = document.querySelector('#sheet');
  const handle = document.querySelector('#sheetHandle');
  const shade = document.querySelector('#shade');
  let sheetMotion = null;

  if (sheet && handle && shade) {
    let position = null;
    let velocity = 0;
    let target = 0;
    let frame = 0;
    let lastTime = 0;
    let drag = null;
    let returnFocus = null;
    let restoreFocus = true;
    let ignoreClickUntil = 0;
    const height = () => sheet.offsetHeight + 16;
    const background = [...sheet.parentElement.children].filter(element => element !== sheet && element !== shade);

    function draw() {
      sheet.style.transform = `translateY(${position}px)`;
      shade.style.opacity = Math.max(0, Math.min(1, 1 - position / height()));
    }

    function modal(open) {
      background.forEach(element => { element.inert = open; });
      sheet.inert = !open;
    }

    function settled() {
      frame = 0;
      velocity = 0;
      position = target;
      draw();
      sheet.style.willChange = '';
      if (!sheet.classList.contains('on')) {
        shade.classList.remove('on');
        modal(false);
        if (restoreFocus && returnFocus?.isConnected) returnFocus.focus({preventScroll: true});
      }
    }

    function tick(time) {
      const dt = Math.min((time - lastTime) / 1000, .064);
      lastTime = time;
      // Exact critically damped spring step, independent of refresh rate.
      const omega = 26;
      const distance = position - target;
      const carry = velocity + omega * distance;
      const decay = Math.exp(-omega * dt);
      position = target + (distance + carry * dt) * decay;
      velocity = (velocity - omega * carry * dt) * decay;
      draw();
      if (Math.abs(position - target) < .3 && Math.abs(velocity) < 5) settled();
      else frame = requestAnimationFrame(tick);
    }

    function settleTo(next, immediate = false) {
      target = next;
      if (immediate || reduced.matches) {
        cancelAnimationFrame(frame);
        settled();
      } else if (!frame) {
        sheet.style.willChange = 'transform';
        lastTime = performance.now();
        frame = requestAnimationFrame(tick);
      }
    }

    function open() {
      if (sheet.classList.contains('on')) return;
      restoreFocus = true;
      if (!shade.classList.contains('on')) returnFocus = document.activeElement;
      if (position === null || sheet.inert) position = height();
      sheet.classList.add('on');
      shade.classList.add('on');
      modal(true);
      draw();
      settleTo(0);
      handle.focus({preventScroll: true});
    }

    function close(immediate = false) {
      drag = null;
      restoreFocus = !immediate;
      sheet.classList.remove('on');
      if (position === null) position = height();
      settleTo(height(), immediate || sheet.inert);
    }

    handle.addEventListener('pointerdown', event => {
      if (!event.isPrimary || event.button !== 0) return;
      cancelAnimationFrame(frame);
      frame = 0;
      velocity = 0;
      sheet.classList.add('on');
      drag = {id: event.pointerId, y: event.clientY, start: position, moved: false, samples: [{time: performance.now(), y: position}]};
      handle.setPointerCapture(event.pointerId);
    });

    handle.addEventListener('pointermove', event => {
      if (!drag || event.pointerId !== drag.id) return;
      const delta = event.clientY - drag.y;
      drag.moved ||= Math.abs(delta) > 5;
      const raw = drag.start + delta;
      position = raw < 0 ? raw * .28 / (1 + Math.abs(raw) / height()) : Math.min(height(), raw);
      const now = performance.now();
      drag.samples.push({time: now, y: position});
      drag.samples = drag.samples.filter(sample => now - sample.time < 100);
      draw();
    });

    function release(event) {
      if (!drag || event.pointerId !== drag.id) return;
      const state = drag;
      drag = null;
      const now = performance.now();
      const first = state.samples.find(sample => now - sample.time <= 100);
      velocity = first && now > first.time ? (position - first.y) / (now - first.time) * 1000 : 0;
      if (state.moved) ignoreClickUntil = now + 300;
      const dismiss = event.type === 'pointerup' && state.moved && position + velocity * .18 > height() * .35;
      if (dismiss) close();
      else settleTo(0);
      if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
    }
    handle.addEventListener('pointerup', release);
    handle.addEventListener('pointercancel', release);
    handle.addEventListener('lostpointercapture', release);
    handle.addEventListener('click', event => {
      if (event.detail && performance.now() < ignoreClickUntil) return;
      close();
    });

    sheet.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const controls = [...sheet.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled)')];
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    });
    new ResizeObserver(() => {
      if (position === null) return;
      if (!sheet.classList.contains('on')) target = height();
      if (!frame && !drag) position = target;
      draw();
    }).observe(sheet);
    sheetMotion = {open, close, finish: () => {
      drag = null;
      settleTo(sheet.classList.contains('on') ? 0 : height(), true);
    }};
  }

  reduced.addEventListener('change', () => {
    if (!reduced.matches) return;
    if (loader && !loader.hidden && splashReady) hideSplash();
    for (const animation of animations.values()) animation.finish();
    sheetMotion?.finish();
  });
  window.ParkGoMotion = {navigate, reveal, finishLoading, confirmBooking, selectSpot, sheet: sheetMotion};
})();
