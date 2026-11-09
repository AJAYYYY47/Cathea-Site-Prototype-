/**
 * Cathea Studio - Employee Portal Scripts
 */

document.addEventListener('DOMContentLoaded', () => {
  // Tab switching
  const tabBtns = document.querySelectorAll('.portal-tab-btn');
  const sectionContents = document.querySelectorAll('.portal-section-content');
  const pageTitle = document.getElementById('portalPageTitle');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.tab;
      
      tabBtns.forEach(b => b.classList.remove('active'));
      sectionContents.forEach(s => s.classList.remove('active'));

      btn.classList.add('active');
      const targetSection = document.getElementById(targetId);
      if (targetSection) {
        targetSection.classList.add('active');
      }

      if (pageTitle) {
        pageTitle.textContent = btn.querySelector('span')?.textContent || 'Employee Portal';
      }
    });
  });

  const requestedTab = new URLSearchParams(window.location.search).get('tab');
  const requestedButton = [...tabBtns].find(btn => btn.dataset.tab === requestedTab);
  requestedButton?.click();
});
