(() => {
  const root = document.documentElement;
  const sections = [...document.querySelectorAll('.saha-premium :is(#perks, #why, #services, #packages, #team)')];
  if (!sections.length || !('IntersectionObserver' in window)) return;

  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const meter = document.createElement('div');
  meter.className = 'saha-scroll-meter';
  meter.setAttribute('aria-hidden', 'true');
  document.body.append(meter);
  const visible = new Set();
  const animations = new Set();
  let frame;

  const paused = () => reduce.matches || root.dataset.sahaMotion === 'paused';

  function update() {
    frame = undefined;
    const stopped = paused();
    const height = window.innerHeight;
    const travel = root.scrollHeight - height;
    meter.style.setProperty('--saha-scroll-progress', travel > 0 ? Math.min(1, Math.max(0, window.scrollY / travel)) : 0);
    for (const section of visible) {
      const rect = section.getBoundingClientRect();
      const offset = Math.max(-48, Math.min(48, (height * .5 - rect.top - rect.height * .5) * .16));
      section.style.setProperty('--saha-scroll-light', stopped ? '0px' : offset + 'px');
    }
  }

  function schedule() {
    if (frame === undefined) frame = requestAnimationFrame(update);
  }

  const scenes = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) visible.add(entry.target);
      else visible.delete(entry.target);
    }
    schedule();
  });

  const entrances = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const title = entry.target;
      entrances.unobserve(title);
      if (paused() || !title.animate) continue;
      title.classList.add('saha-scroll-arrived');
      const animation = title.animate([
        { opacity: .3, transform: 'translate(26px, 19px) scale(.94)' },
        { opacity: 1, transform: 'none' },
      ], { duration: 650, easing: 'cubic-bezier(.18,.8,.3,1)' });
      animations.add(animation);
      animation.finished.then(() => animations.delete(animation), () => animations.delete(animation));
    }
  }, { threshold: .18 });

  for (const section of sections) {
    scenes.observe(section);
    const title = section.querySelector('h2');
    if (!title) continue;
    title.setAttribute('data-saha-scroll-title', '');
    entrances.observe(title);
  }

  function refreshPreference() {
    if (paused()) {
      for (const animation of animations) animation.cancel();
      document.querySelectorAll('.saha-scroll-arrived').forEach(title => title.classList.remove('saha-scroll-arrived'));
    }
    schedule();
  }

  addEventListener('scroll', schedule, { passive: true });
  addEventListener('resize', schedule, { passive: true });
  reduce.addEventListener('change', refreshPreference);
  new MutationObserver(refreshPreference).observe(root, { attributeFilter: ['data-saha-motion'] });
  schedule();
})();
