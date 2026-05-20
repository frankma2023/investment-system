/* ============================================================
   THEME.JS — Dark/Light Mode Toggle with Persistence
   ============================================================ */

(function() {
  const STORAGE_KEY = 'investment-dashboard-theme';
  const DARK = 'dark';
  const LIGHT = 'light';

  function getTheme() {
    return localStorage.getItem(STORAGE_KEY) || DARK;
  }

  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    updateToggleIcon(theme);
    document.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || DARK;
    setTheme(current === DARK ? LIGHT : DARK);
  }

  // 暴露到全局，供 nav.js 的 onclick 调用
  window.toggleTheme = toggleTheme;

  function updateToggleIcon(theme) {
    const btn = document.querySelector('.theme-toggle');
    if (!btn) return;
    btn.textContent = theme === DARK ? '☀' : '🌙';
    btn.title = theme === DARK ? '切换到浅色模式' : '切换到深色模式';
  }

  function initThemeToggle() {
    // Apply saved theme
    const saved = getTheme();
    setTheme(saved);

    // Bind toggle buttons
    document.querySelectorAll('.theme-toggle').forEach(btn => {
      btn.addEventListener('click', toggleTheme);
    });
  }

  // Initialize
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initThemeToggle);
  } else {
    initThemeToggle();
  }
})();
