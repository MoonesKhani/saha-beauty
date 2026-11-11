/* SAHA Blossom Burst. No remote services, credentials, statistics, or layout mutations. */
(() => {
  'use strict';
  if (window.__sahaPremiumCleanup) window.__sahaPremiumCleanup();
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const state = { canvas: null, context: null, width: 0, height: 0, particles: [], startedAt: null,
    burstStarts: 0, animationFrame: 0, scrollFrame: 0, paused: false, suspendedAt: null,
    heroVisible: true, resizeObserver: null, revealObserver: null, heroObserver: null, destroyed: false };
  const clamp = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
  const stopped = () => media.matches || state.paused;
  const deferred = new Set();
  function later(fn, ms) { const id = setTimeout(() => { deferred.delete(id); if (!state.destroyed) fn(); }, ms); deferred.add(id); }
  function seeded(seed) { return () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }; }
  function particles() {
    const rand = seeded(25017);
    const mobile = state.width < 700;
    const origins = mobile ? [[.78,.19],[.12,.36],[.89,.54]] : [[.79,.32],[.97,.64],[.12,.78]];
    state.particles = Array.from({length: mobile ? 26 : 58}, (_, i) => {
      const origin = origins[i % origins.length], angle = rand() * Math.PI * 2;
      const depth = .45 + rand() * .9;
      return { ox: origin[0], oy: origin[1], angle, distance: 120 + rand() * (mobile ? 240 : 470),
        size: (4 + rand() * 9) * depth, depth, rotation: rand() * 6.28, spin: (rand() - .5) * 7,
        delay: .48 + rand() * .55, lifetime: 1.65 + rand() * 1.1, phase: rand() * 6.28,
        blossom: i % 7 === 0, color: ['#e895b3','#f5bfd0','#d78baa','#f9d9df'][i % 4] };
    });
    if (state.canvas) state.canvas.dataset.particleCount = String(state.particles.length);
  }
  function resizeCanvas() {
    if (!state.canvas || !state.context) return;
    const rect = state.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    state.width = rect.width; state.height = rect.height;
    const dpr = Math.min(window.devicePixelRatio || 1, state.width < 700 ? 1.5 : 2);
    state.canvas.width = Math.round(rect.width * dpr); state.canvas.height = Math.round(rect.height * dpr);
    state.context.setTransform(dpr, 0, 0, dpr, 0, 0);
    particles();
    if (stopped()) clearCanvas(); else animate();
  }
  function clearCanvas() { if (state.context) state.context.clearRect(0, 0, state.width, state.height); }
  function petal(ctx, size, color) {
    const gradient = ctx.createLinearGradient(-size, -size, size, size);
    gradient.addColorStop(0, '#ffe5ed'); gradient.addColorStop(.45, color); gradient.addColorStop(1, '#b9698b');
    ctx.fillStyle = gradient; ctx.beginPath();
    ctx.moveTo(0, -size); ctx.bezierCurveTo(size * 1.1, -size * .75, size * 1.3, size * .25, 0, size);
    ctx.bezierCurveTo(-size * .7, size * .5, -size * .65, -size * .55, 0, -size); ctx.fill();
  }
  function animate() {
    if (state.animationFrame || state.destroyed || stopped() || !state.context || !state.heroVisible || document.hidden) return;
    state.animationFrame = requestAnimationFrame(draw);
  }
  function draw(now) {
    state.animationFrame = 0;
    if (state.destroyed || stopped() || !state.context || document.hidden) { clearCanvas(); return; }
    if (state.startedAt === null) { state.startedAt = now; state.burstStarts += 1; }
    const elapsed = (now - state.startedAt) / 1000;
    clearCanvas();
    state.canvas.dataset.burstStarts = String(state.burstStarts);
    state.canvas.dataset.phase = elapsed < .5 ? 'arrival' : elapsed < 1.5 ? 'burst' : elapsed < 3.6 ? 'dispersion' : 'settled';
    // At rest the scene is a static composition; the entrance never loops.
    if (elapsed > 6.2) return;
    const ctx = state.context;
    for (const item of state.particles) {
      const t = (elapsed - item.delay) / item.lifetime;
      if (t < 0 || t > 1) continue;
      const travel = 1 - Math.pow(1 - t, 2.1);
      const sway = Math.sin(t * 4 + item.phase) * (10 + item.depth * 7) * t;
      const x = item.ox * state.width + Math.cos(item.angle) * item.distance * travel + sway;
      const y = item.oy * state.height + Math.sin(item.angle) * item.distance * travel - Math.sin(t * Math.PI) * 45 + t * t * 25;
      let opacity = Math.sin(Math.min(1, t * 5) * Math.PI / 2) * Math.pow(1 - t, .65) * .88;
      // Keep the central text and booking controls clear.
      if (state.width > 700 && x < state.width * .49 && y > state.height * .1 && y < state.height * .78) opacity *= .3;
      ctx.save(); ctx.translate(x, y); ctx.rotate(item.rotation + item.spin * t); ctx.globalAlpha = opacity;
      if (item.depth > 1.15) ctx.filter = 'blur(.7px)';
      const scale = .65 + Math.sin(t * Math.PI) * .35; ctx.scale(scale, scale);
      if (item.blossom) {
        for (let n = 0; n < 5; n++) { ctx.save(); ctx.rotate(n * Math.PI * 2 / 5); ctx.translate(0, -item.size * .6); petal(ctx, item.size * .7, item.color); ctx.restore(); }
        ctx.fillStyle = '#f3d5aa'; ctx.beginPath(); ctx.arc(0, 0, item.size * .2, 0, Math.PI * 2); ctx.fill();
      } else petal(ctx, item.size, item.color);
      ctx.restore();
    }
    // A few distant flecks settle quietly after the main outward gust.
    if (elapsed > 3 && elapsed < 5.8) {
      for (let i = 0; i < 3; i++) {
        ctx.save(); ctx.globalAlpha = clamp((5.8 - elapsed) / 2.8) * .22;
        ctx.translate(state.width * (.57 + i * .16) + Math.sin(elapsed + i) * 12, state.height * (.22 + i * .17) - elapsed * 7);
        ctx.rotate(elapsed * .2 + i); petal(ctx, 4 + i, '#efb1c6'); ctx.restore();
      }
    }
    animate();
  }
  function updateScroll() {
    state.scrollFrame = 0;
    const art = document.querySelector('.saha-premium .saha-assembly');
    if (art) {
      const top = art.getBoundingClientRect().top;
      const progress = stopped() ? 1 : clamp((innerHeight * .94 - top) / (innerHeight * .52));
      art.style.setProperty('--assembly', progress.toFixed(4));
    }
    const hero = document.querySelector('.premium-hero');
    if (hero) {
      const r = hero.getBoundingClientRect();
      hero.style.setProperty('--hero-drift', stopped() ? '0px' : `${clamp(-r.top * .035, -12, 22).toFixed(2)}px`);
    }
  }
  function scheduleScroll() { if (!state.scrollFrame) state.scrollFrame = requestAnimationFrame(updateScroll); }
  function syncControls() {
    document.documentElement.dataset.sahaMotion = stopped() ? 'paused' : 'running';
    document.querySelectorAll('.saha-motion-toggle').forEach(button => {
      button.disabled = media.matches;
      button.setAttribute('aria-pressed', String(stopped()));
      button.setAttribute('aria-label', media.matches ? 'تنظیم کاهش حرکت دستگاه فعال است' : state.paused ? 'پخش جلوه‌های متحرک' : 'توقف جلوه‌های متحرک');
      const label = media.matches ? 'حرکت کمتر' : state.paused ? 'پخش حرکت' : 'توقف حرکت';
      if (button.textContent !== label) button.textContent = label;
    });
  }
  function toggleMotion(event) {
    if (!event.target.closest('.saha-motion-toggle') || media.matches) return;
    state.paused = !state.paused;
    if (state.paused) { state.suspendedAt = performance.now(); cancelAnimationFrame(state.animationFrame); state.animationFrame = 0; clearCanvas(); }
    else { if (state.suspendedAt !== null && state.startedAt !== null) state.startedAt += performance.now() - state.suspendedAt; state.suspendedAt = null; animate(); }
    syncControls(); scheduleScroll();
  }
  function onPreference() {
    cancelAnimationFrame(state.animationFrame); state.animationFrame = 0;
    if (media.matches) clearCanvas(); else animate();
    syncControls(); scheduleScroll();
  }
  const revealObserver = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) {
      entry.target.classList.remove('reveal-pending'); entry.target.classList.add('reveal-complete'); revealObserver.unobserve(entry.target);
    }
  }, {threshold:.08, rootMargin:'0px 0px -25px 0px'}) : null;
  state.revealObserver = revealObserver;
  function attach() {
    if (state.destroyed) return;
    const canvas = document.querySelector('.saha-premium .saha-blossom-canvas');
    if (canvas && canvas !== state.canvas && canvas.getBoundingClientRect().width > 0) {
      state.resizeObserver?.disconnect(); state.heroObserver?.disconnect(); cancelAnimationFrame(state.animationFrame); state.animationFrame = 0;
      state.canvas = canvas; state.context = canvas.getContext('2d', {alpha:true});
      if (state.context) {
        if ('ResizeObserver' in window) { state.resizeObserver = new ResizeObserver(resizeCanvas); state.resizeObserver.observe(canvas); }
        else resizeCanvas();
        if ('IntersectionObserver' in window) {
          state.heroObserver = new IntersectionObserver(entries => { state.heroVisible = entries[0].isIntersecting; if (state.heroVisible) animate(); else { cancelAnimationFrame(state.animationFrame); state.animationFrame = 0; } });
          state.heroObserver.observe(canvas);
        }
      }
    }
    if (revealObserver) document.querySelectorAll('.saha-premium .rv:not([data-saha-observed])').forEach(node => {
      node.dataset.sahaObserved = 'true';
      if (!stopped() && node.getBoundingClientRect().top > innerHeight) { node.classList.add('reveal-pending'); revealObserver.observe(node); }
    });
    syncControls(); scheduleScroll();
  }
  // Only child-list changes are observed. Motion styles never retrigger hydration work.
  let queued = false;
  const observer = new MutationObserver(() => {
    if (!queued) { queued = true; queueMicrotask(() => { queued = false; attach(); }); }
  });
  observer.observe(document.documentElement, {childList:true, subtree:true});
  document.addEventListener('click', toggleMotion);
  window.addEventListener('scroll', scheduleScroll, {passive:true});
  window.addEventListener('resize', scheduleScroll, {passive:true});
  media.addEventListener('change', onPreference);
  function visibility() { if (document.hidden) { cancelAnimationFrame(state.animationFrame); state.animationFrame = 0; } else { animate(); scheduleScroll(); } }
  document.addEventListener('visibilitychange', visibility);
  attach(); later(attach, 250); later(attach, 1000);
  window.__sahaPremiumCleanup = () => {
    state.destroyed = true; observer.disconnect(); revealObserver?.disconnect(); state.resizeObserver?.disconnect(); state.heroObserver?.disconnect();
    cancelAnimationFrame(state.animationFrame); cancelAnimationFrame(state.scrollFrame); deferred.forEach(clearTimeout);
    document.removeEventListener('click', toggleMotion); window.removeEventListener('scroll', scheduleScroll); window.removeEventListener('resize', scheduleScroll);
    media.removeEventListener('change', onPreference); document.removeEventListener('visibilitychange', visibility);
  };
})();

/* Scoped enhancements: opt-in licensed audio and explicitly non-persistent demos. */
(() => {
  'use strict';
  if (window.__sahaRefinementsCleanup) window.__sahaRefinementsCleanup();
  const musicUrl = new URL('saha-quiet-bloom.mp3', document.currentScript.src).href;
  let audio = null, pendingMusic = false, musicError = '', gameChoice = null;
  const gameMessages = ['نتیجه نمایشی: گلبرگِ حال خوب سهمت شد ♡', 'نتیجه نمایشی: گلبرگِ تخفیف رو پیدا کردی ♡', 'نتیجه نمایشی: امروز نوبت درخشیدنته ✨'];
  const root = () => document.querySelector('.saha-premium');
  function text(node, value) { if (node && node.textContent !== value) node.textContent = value; }
  function sync() {
    const app = root(); if (!app) return;
    app.querySelectorAll('[data-saha-music]').forEach(button => {
      const playing = !!audio && !audio.paused;
      button.setAttribute('aria-pressed', String(playing)); button.disabled = pendingMusic;
      button.setAttribute('aria-label', playing ? 'قطع موسیقی بی‌کلام' : 'پخش موسیقی بی‌کلام');
      text(button, pendingMusic ? 'در حال آماده‌سازی…' : playing ? 'موسیقی روشن ♫' : 'موسیقی خاموش ♫');
    });
    text(app.querySelector('.music-feedback'), musicError);
    app.querySelectorAll('[data-beauty-petal]').forEach(button => {
      button.setAttribute('aria-pressed', String(gameChoice === Number(button.dataset.beautyPetal)));
      button.disabled = gameChoice !== null;
    });
    text(app.querySelector('.beauty-game-result'), gameChoice === null ? '' : gameMessages[gameChoice]);
  }
  async function toggleMusic() {
    if (pendingMusic) return;
    musicError = '';
    if (!audio) {
      audio = new Audio(); audio.preload = 'none'; audio.loop = true; audio.volume = .28; audio.src = musicUrl;
      audio.addEventListener('play', sync); audio.addEventListener('pause', sync);
      audio.addEventListener('error', () => { pendingMusic = false; musicError = 'پخش موسیقی ممکن نشد؛ دوباره امتحان کن.'; sync(); });
    }
    if (!audio.paused) { audio.pause(); sync(); return; }
    pendingMusic = true; sync();
    try { await audio.play(); }
    catch (_) { musicError = 'پخش موسیقی ممکن نشد؛ دوباره امتحان کن.'; }
    finally { pendingMusic = false; sync(); }
  }
  function demoForm(form) {
    // Never read, serialize, persist, log or transmit the sensitive field.
    form.reset();
    text(form.querySelector('.booking-demo-status'), 'این فقط یه امتحان بود؛ چیزی ذخیره یا ارسال نشد ♡');
  }
  function click(event) {
    if (!(event.target instanceof Element)) return;
    const target = event.target;
    if (target.closest('[data-saha-music]')) { event.preventDefault(); toggleMusic(); return; }
    if (target.closest('[data-saha-open-menu]')) {
      const dialog = root()?.querySelector('#saha-buffet-menu');
      if (dialog && !dialog.open) dialog.showModal(); return;
    }
    if (target.closest('[data-saha-close-menu]')) { root()?.querySelector('#saha-buffet-menu')?.close(); return; }
    const dialog = root()?.querySelector('#saha-buffet-menu');
    if (target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
      return;
    }
    const petal = target.closest('[data-beauty-petal]');
    if (petal && gameChoice === null) { gameChoice = Number(petal.dataset.beautyPetal); sync(); return; }
    if (target.closest('[data-beauty-reset]')) { gameChoice = null; sync(); return; }
    if (target.closest('[data-saha-demo-submit]')) { event.preventDefault(); window.location.assign('/booking-demo.html'); }
  }
  function submit(event) {
    if (event.target.matches('[data-saha-booking-demo]')) { event.preventDefault(); window.location.assign('/booking-demo.html'); }
  }
  function clearDemo() { root()?.querySelectorAll('[data-saha-booking-demo]').forEach(form => form.reset()); }
  function visibility() { if (document.hidden && audio) audio.pause(); }
  function leave() { if (audio) audio.pause(); clearDemo(); }
  // Hydration may recreate buttons; keep audio and non-sensitive game state in memory only.
  const observer = new MutationObserver(sync);
  observer.observe(document.documentElement, {childList:true, subtree:true});
  document.addEventListener('click', click); document.addEventListener('submit', submit);
  document.addEventListener('visibilitychange', visibility); window.addEventListener('pagehide', leave);
  sync();
  window.__sahaRefinementsCleanup = () => {
    observer.disconnect(); document.removeEventListener('click', click); document.removeEventListener('submit', submit);
    document.removeEventListener('visibilitychange', visibility); window.removeEventListener('pagehide', leave);
    if (audio) { audio.pause(); audio.removeAttribute('src'); audio.load(); } clearDemo();
  };
})();
