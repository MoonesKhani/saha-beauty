(() => {
  function mountWhyMotion(section) {
    const grid = section.querySelector('.why-motion-grid');
    const cards = [...grid.querySelectorAll('.why-card')];
    const toggle = section.querySelector('.why-motion-toggle');
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const hover = window.matchMedia('(hover: hover)');
    let visible = false;
    let paused = false;
    let selected = null;
    let stackTimer;
    let copyTimer;
    let stackAnimations = [];

    function nextLine(card) {
      const lines = [...card.querySelectorAll('.why-line')];
      const current = Number(card.dataset.step || 0);
      const next = (current + 1) % lines.length;
      lines[current].setAttribute('data-inactive', '');
      lines[next].removeAttribute('data-inactive');
      card.dataset.step = String(next);
      if (!reduced.matches) {
        const glints = card.querySelector('.why-glints');
        glints.getAnimations().forEach(animation => animation.cancel());
        glints.animate([
          { opacity: 0, transform: 'translate(8px, 5px) scale(.56)' },
          { opacity: .94, offset: .35 },
          { opacity: 0, transform: 'translate(-9px, -9px) scale(1.14)' },
        ], { duration: 700, easing: 'ease-out' });
        lines[next].animate([{ opacity: 0, translate: '0 7px' }, { opacity: 1, translate: '0 0' }], {
          duration: 420,
          easing: 'ease-out',
        });
      }
    }

    function stopStack() {
      window.clearTimeout(stackTimer);
      for (const animation of stackAnimations) animation.cancel();
      stackAnimations = [];
    }

    function exchangeCards() {
      const order = [...grid.children];
      const before = order.map(card => card.offsetLeft);
      const center = before[1];
      grid.append(order[0]);
      stackAnimations = order.map((card, i) => {
        const end = card.offsetLeft;
        const stack = `${center - end}px`;
        const depth = i === 1 ? 5 : 1;
        const stackScale = i === 1 ? 1 : .97;
        return card.animate([
          { translate: `${before[i] - end}px 0`, scale: 1, zIndex: depth, easing: 'ease-in-out' },
          { translate: `${stack} 0`, scale: stackScale, zIndex: depth, offset: .24 },
          { translate: `${stack} 0`, scale: stackScale, zIndex: depth, offset: .65, easing: 'ease-in-out' },
          { translate: '0 0', scale: 1, zIndex: depth },
        ], { duration: 5600 });
      });
    }

    function canPlay() {
      return visible && !paused && !reduced.matches && !document.hidden;
    }

    function scheduleStack() {
      window.clearTimeout(stackTimer);
      if (!canPlay() || selected || (hover.matches && grid.matches(':hover')) ||
          grid.contains(document.activeElement)) return;
      stackTimer = window.setTimeout(() => {
        exchangeCards();
        scheduleStack();
      }, 9500);
    }

    function scheduleCopy() {
      window.clearTimeout(copyTimer);
      if (!canPlay()) return;
      copyTimer = window.setTimeout(() => {
        cards.forEach(nextLine);
        scheduleCopy();
      }, 4600);
    }

    function sync() {
      if (!canPlay()) stopStack();
      scheduleStack();
      scheduleCopy();
    }

    for (const card of cards) {
      card.addEventListener('click', () => {
        if (selected && selected !== card) selected.setAttribute('aria-pressed', 'false');
        selected = selected === card ? null : card;
        card.setAttribute('aria-pressed', String(selected === card));
        nextLine(card);
        stopStack();
        scheduleStack();
      });
    }
    grid.addEventListener('pointerenter', scheduleStack);
    grid.addEventListener('pointerleave', scheduleStack);
    grid.addEventListener('focusin', scheduleStack);
    grid.addEventListener('focusout', () => window.setTimeout(scheduleStack, 0));
    toggle.addEventListener('click', () => {
      paused = !paused;
      toggle.textContent = paused ? 'ادامهٔ حرکت' : 'توقف حرکت';
      if (selected) selected.setAttribute('aria-pressed', 'false');
      selected = null;
      sync();
    });
    function syncMotionPreference() {
      toggle.hidden = reduced.matches;
      sync();
    }
    const lifetime = new AbortController();
    const options = { signal: lifetime.signal };
    reduced.addEventListener('change', syncMotionPreference, options);
    document.addEventListener('visibilitychange', sync, options);
    const intersection = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    }, { threshold: .35 });
    intersection.observe(grid);
    syncMotionPreference();
    return () => {
      lifetime.abort();
      intersection.disconnect();
      stopStack();
      window.clearTimeout(copyTimer);
    };
  }

  let mounted;
  let unmount;
  function attach() {
    const section = [...document.querySelectorAll('#why .why-motion')]
      .find(candidate => candidate.getClientRects().length);
    if (section === mounted) return;
    unmount?.();
    mounted = section;
    unmount = section ? mountWhyMotion(section) : null;
  }
  new MutationObserver(attach).observe(document.body, { childList: true, subtree: true });
  attach();
})();
