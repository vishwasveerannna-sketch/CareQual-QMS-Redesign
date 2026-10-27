/* Runs before first paint so the saved theme / menu state never flashes. */
(function () {
  var root = document.documentElement;
  try {
    var theme = localStorage.getItem('cq-theme');
    if (theme === 'light' || theme === 'dark') root.setAttribute('data-theme', theme);
    var rail = localStorage.getItem('cq-rail');
    var narrow = window.matchMedia('(max-width: 1100px)').matches;
    if (rail === 'collapsed' || (rail === null && narrow)) root.setAttribute('data-rail', 'collapsed');
  } catch (e) { /* storage unavailable: keep defaults */ }
})();
