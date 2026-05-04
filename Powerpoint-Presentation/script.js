// ============================================================
// Ab Initio → PySpark Convertor — Presentation Deck
// Light theme · IBM Blue
// ============================================================

(() => {
  const slides = Array.from(document.querySelectorAll('.slide'));
  const totalEl = document.getElementById('tot');
  const curEl = document.getElementById('cur');
  const prevBtn = document.getElementById('prev');
  const nextBtn = document.getElementById('next');

  totalEl.textContent = slides.length;

  // ---------- Build TC grid for slide 10 ----------
  const tcGrid = document.getElementById('tc-grid');
  if (tcGrid) {
    const status = {
      20: 'warn',
      21: 'fail',
      22: 'fail',
      24: 'fail',
      25: 'fail',
    };
    for (let i = 1; i <= 25; i++) {
      const div = document.createElement('div');
      const s = status[i] || 'pass';
      div.className = `tc ${s}`;
      div.textContent = `TC-${String(i).padStart(3, '0')}`;
      tcGrid.appendChild(div);
    }
  }

  // ---------- Navigation ----------
  let current = 0;
  let focusMode = false;

  function setActive(i) {
    current = Math.max(0, Math.min(slides.length - 1, i));
    curEl.textContent = current + 1;

    if (focusMode) {
      slides.forEach((s, idx) => s.classList.toggle('active', idx === current));
    } else {
      slides[current].scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function next() { setActive(current + 1); }
  function prev() { setActive(current - 1); }

  prevBtn.addEventListener('click', prev);
  nextBtn.addEventListener('click', next);

  // Keyboard
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    switch (e.key) {
      case 'ArrowRight':
      case 'PageDown':
      case ' ':
        e.preventDefault(); next(); break;
      case 'ArrowLeft':
      case 'PageUp':
        e.preventDefault(); prev(); break;
      case 'Home':
        e.preventDefault(); setActive(0); break;
      case 'End':
        e.preventDefault(); setActive(slides.length - 1); break;
      case 'f':
      case 'F':
        toggleFocusMode();
        break;
      case 'Escape':
        if (focusMode) toggleFocusMode();
        break;
    }
  });

  function toggleFocusMode() {
    focusMode = !focusMode;
    document.body.classList.toggle('focus-mode', focusMode);
    if (focusMode && document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else if (!focusMode && document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
    setActive(current);
  }

  // ---------- Track which slide is in view (scroll mode) ----------
  const io = new IntersectionObserver((entries) => {
    if (focusMode) return;
    entries.forEach((entry) => {
      if (entry.isIntersecting && entry.intersectionRatio > 0.5) {
        const idx = slides.indexOf(entry.target);
        if (idx >= 0) {
          current = idx;
          curEl.textContent = idx + 1;
        }
      }
    });
  }, { threshold: [0.5] });
  slides.forEach((s) => io.observe(s));

  // Init
  setActive(0);
})();
