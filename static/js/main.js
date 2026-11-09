/**
 * Cathea Studio - Main JS
 */
document.addEventListener('DOMContentLoaded', () => {
  // Sticky navbar styling on scroll
  const navbar = document.querySelector('.navbar');
  if (navbar) {
    const themeSections = [...document.querySelectorAll('.homepage-theme')];
    const updateNavbarContrast = () => {
      if (themeSections.length) {
        const threshold = navbar.getBoundingClientRect().bottom;
        const currentSection = themeSections.find(section => {
          const bounds = section.getBoundingClientRect();
          return bounds.top <= threshold && bounds.bottom > threshold;
        });

        navbar.classList.toggle('is-dark', currentSection?.classList.contains('theme-dark') ?? false);
        return;
      }

      navbar.classList.toggle('is-dark', window.scrollY > 40);
    };

    updateNavbarContrast();
    window.addEventListener('scroll', updateNavbarContrast, { passive: true });
    window.addEventListener('resize', updateNavbarContrast);
  }

  const consultButton = document.querySelector('.consult-trigger-btn');
  const footer = document.querySelector('.footer-minimal');
  if (consultButton && footer) {
    const updateConsultButtonPosition = () => {
      const footerTop = footer.getBoundingClientRect().top + window.scrollY;
      const footerIsVisible = window.scrollY + window.innerHeight >= footerTop;

      consultButton.classList.toggle('at-page-end', footerIsVisible);
      if (footerIsVisible) {
        consultButton.style.top = `${footerTop - consultButton.offsetHeight - 24}px`;
      } else {
        consultButton.style.removeProperty('top');
      }
    };

    updateConsultButtonPosition();
    window.addEventListener('scroll', updateConsultButtonPosition, { passive: true });
    window.addEventListener('resize', updateConsultButtonPosition);
  }

  // Auto-dismiss flash alerts after 5 seconds
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    setTimeout(() => {
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-10px)';
      setTimeout(() => alert.remove(), 300);
    }, 5000);
  });
});
