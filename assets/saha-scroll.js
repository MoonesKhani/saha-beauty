(() => {
  const hero = document.querySelector('.premium-hero');
  const gallery = document.querySelector('.saha-gallery-feature');
  if (!hero || !gallery || !('IntersectionObserver' in window)) return;

  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const small = matchMedia('(max-width: 760px)');
  const scenes = [hero, ...document.querySelectorAll('#perks, #why, #services, #packages'), gallery];
  const visible = new Set();
  let frame = 0;

  function update() {
    frame = 0;
    const paused = reduced.matches || root.dataset.sahaMotion === 'paused';
    const height = window.innerHeight;
    const offsets = [...visible].map(scene => {
      const rect = scene.getBoundingClientRect();
      return [scene, Math.max(-1, Math.min(1, (height / 2 - rect.top - rect.height / 2) / height))];
    });
    for (const [scene, progress] of offsets) {
      const isGallery = scene === gallery;
      const range = isGallery ? (small.matches ? 8 : 18) : (small.matches ? 12 : 32);
      const property = isGallery ? '--saha-gallery-drift' : '--saha-light-drift';
      scene.style.setProperty(property, paused ? '0px' : `${progress * range}px`);
    }
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(update);
  }

  const scenesObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) visible.add(entry.target);
      else visible.delete(entry.target);
    }
    schedule();
  }, { rootMargin: '80px 0px' });

  const titlesObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      if (!reduced.matches && root.dataset.sahaMotion !== 'paused') {
        entry.target.classList.add('saha-scroll-enter');
      }
      titlesObserver.unobserve(entry.target);
    }
  }, { threshold: .35 });

  for (const scene of scenes) {
    scenesObserver.observe(scene);
    const title = scene.querySelector('h2');
    if (title) titlesObserver.observe(title);
  }

  addEventListener('scroll', schedule, { passive: true });
  addEventListener('resize', schedule, { passive: true });
  reduced.addEventListener('change', schedule);
  new MutationObserver(schedule).observe(root, { attributeFilter: ['data-saha-motion'] });
})();
