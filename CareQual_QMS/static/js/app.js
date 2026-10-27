/* CareQual QMS - shared interactions. Business rules stay in Python; this file is presentation only. */
(function () {
  'use strict';
  var root = document.documentElement;
  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } }
  };
  var isMobile = function () { return window.matchMedia('(max-width: 900px)').matches; };

  /* ---------- theme ---------- */
  var themeBtn = $('#theme-toggle');
  function paintTheme() {
    var t = root.getAttribute('data-theme') || 'dark';
    $$('[data-theme-icon]').forEach(function (el) { el.hidden = el.getAttribute('data-theme-icon') !== t; });
    if (themeBtn) themeBtn.setAttribute('aria-label', t === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
  }
  if (themeBtn) themeBtn.addEventListener('click', function () {
    var next = (root.getAttribute('data-theme') === 'light') ? 'dark' : 'light';
    root.setAttribute('data-theme', next); store.set('cq-theme', next); paintTheme();
    document.dispatchEvent(new CustomEvent('cq:theme'));
  });
  paintTheme();

  /* ---------- navigation rail ---------- */
  var navToggle = $('#nav-toggle'), railCollapse = $('#rail-collapse');
  function paintRail() {
    var collapsed = root.getAttribute('data-rail') === 'collapsed';
    var open = root.getAttribute('data-nav-open') === 'true';
    if (navToggle) navToggle.setAttribute('aria-expanded', String(isMobile() ? open : !collapsed));
    if (railCollapse) {
      railCollapse.setAttribute('aria-pressed', String(collapsed));
      var label = $('span', railCollapse); if (label) label.textContent = collapsed ? 'Expand menu' : 'Collapse menu';
    }
  }
  function toggleRail() {
    if (isMobile()) {
      root.setAttribute('data-nav-open', root.getAttribute('data-nav-open') === 'true' ? 'false' : 'true');
    } else {
      var collapsed = root.getAttribute('data-rail') === 'collapsed';
      if (collapsed) root.removeAttribute('data-rail'); else root.setAttribute('data-rail', 'collapsed');
      store.set('cq-rail', collapsed ? 'expanded' : 'collapsed');
    }
    paintRail();
  }
  function closeMobileNav() { root.setAttribute('data-nav-open', 'false'); paintRail(); }
  if (navToggle) navToggle.addEventListener('click', toggleRail);
  if (railCollapse) railCollapse.addEventListener('click', toggleRail);
  $$('[data-nav-close]').forEach(function (el) { el.addEventListener('click', closeMobileNav); });
  $$('.rail .nav-link').forEach(function (el) { el.addEventListener('click', function () { if (isMobile()) closeMobileNav(); }); });
  window.addEventListener('resize', function () { if (!isMobile()) root.setAttribute('data-nav-open', 'false'); paintRail(); });
  paintRail();

  /* ---------- popovers (notifications, profile) ---------- */
  var popTriggers = $$('[data-popover]');
  function closePopovers(except) {
    popTriggers.forEach(function (btn) {
      var pop = document.getElementById(btn.getAttribute('data-popover'));
      if (pop && pop !== except && !pop.hidden) { pop.hidden = true; btn.setAttribute('aria-expanded', 'false'); }
    });
  }
  popTriggers.forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var pop = document.getElementById(btn.getAttribute('data-popover'));
      var willOpen = pop.hidden; closePopovers(pop);
      pop.hidden = !willOpen; btn.setAttribute('aria-expanded', String(willOpen));
    });
  });
  document.addEventListener('click', function (e) { if (!e.target.closest('.pop-anchor')) closePopovers(); });

  /* ---------- keyboard shortcuts ---------- */
  document.addEventListener('keydown', function (e) {
    var tag = (e.target.tagName || '').toLowerCase();
    var typing = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;
    if (e.key === 'Escape') {
      closePopovers();
      if (root.getAttribute('data-nav-open') === 'true') closeMobileNav();
    }
    if (((e.key === '/' && !typing) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) && $('#global-search')) {
      e.preventDefault(); $('#global-search').focus(); $('#global-search').select();
    }
  });

  /* ---------- dialogs and record drawers ---------- */
  function lockScroll() { root.classList.toggle('has-dialog', $$('dialog[open]').length > 0); }
  function openDialog(id, opts) {
    var dlg = document.getElementById(id);
    if (!dlg || typeof dlg.showModal !== 'function') return;
    closePopovers();
    if (!dlg.open) dlg.showModal();
    lockScroll();
    if (opts && opts.hash && dlg.classList.contains('drawer')) history.replaceState(null, '', '#' + id);
    var focusTarget = $('[data-autofocus]', dlg);
    if (focusTarget) focusTarget.focus();
  }
  $$('dialog').forEach(function (dlg) {
    dlg.addEventListener('close', function () {
      lockScroll();
      if (location.hash === '#' + dlg.id) history.replaceState(null, '', location.pathname + location.search);
    });
    dlg.addEventListener('click', function (e) { if (e.target === dlg && dlg.id !== 'confirm-dialog') dlg.close(); });
  });
  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-dialog-open]');
    if (opener) { e.preventDefault(); openDialog(opener.getAttribute('data-dialog-open'), { hash: true }); return; }
    var closer = e.target.closest('[data-dialog-close]');
    if (closer) { var d = closer.closest('dialog'); if (d) d.close(); return; }
    var row = e.target.closest('tr[data-open]');
    if (row && !e.target.closest('a, button, input, select, textarea, label')) openDialog(row.getAttribute('data-open'), { hash: true });
  });
  // deep links (#rec-def-3), "open on load" modals, and re-opening a drawer after a form round-trip
  var reopen = null;
  try { reopen = JSON.parse(sessionStorage.getItem('cq-reopen') || 'null'); sessionStorage.removeItem('cq-reopen'); } catch (e) { reopen = null; }
  if (location.hash.length > 1 && document.getElementById(location.hash.slice(1))) openDialog(location.hash.slice(1), { hash: true });
  else if (reopen && reopen.path === location.pathname && document.getElementById(reopen.id)) openDialog(reopen.id, { hash: true });
  $$('dialog[data-autoopen]').forEach(function (d) { openDialog(d.id); });

  /* ---------- forms: inline validation, confirmation, loading state ---------- */
  $$('form[method="post"], form[data-validate]').forEach(function (f) { f.setAttribute('novalidate', ''); });
  function labelOf(el) {
    var l = el.id && $('label[for="' + el.id + '"]'); if (!l) return 'this field';
    return l.childNodes[0] && l.childNodes[0].textContent ? l.childNodes[0].textContent.trim() : 'this field';
  }
  function fieldProblem(el) {
    if (el.disabled || el.type === 'hidden' || el.type === 'radio') return '';
    var v = (el.value || '');
    if (el.required && v.trim() === '') return el.tagName === 'SELECT' ? 'Choose ' + labelOf(el).toLowerCase() + '.' : 'Enter ' + labelOf(el).toLowerCase() + '.';
    if (el.maxLength > 0 && v.length > el.maxLength) return 'Use ' + el.maxLength + ' characters or fewer.';
    return '';
  }
  function showError(el, msg) {
    var wrap = el.closest('.field'); if (!wrap) return;
    wrap.classList.toggle('has-error', !!msg);
    var slot = $('[data-msg]', wrap); if (slot) slot.textContent = msg || '';
    if (msg) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid');
  }
  function validate(form) {
    var first = null;
    $$('input, select, textarea', form).forEach(function (el) {
      var msg = fieldProblem(el); showError(el, msg); if (msg && !first) first = el;
    });
    if (first) first.focus();
    return !first;
  }
  document.addEventListener('input', function (e) { if (e.target.closest('.field.has-error')) showError(e.target, fieldProblem(e.target)); });

  var confirmDlg = $('#confirm-dialog'), pending = null;
  function needsConfirm(form) {
    if (!form.hasAttribute('data-confirm')) return false;
    var when = form.getAttribute('data-confirm-when');
    if (!when) return true;
    var parts = when.split('='), field = form.elements[parts[0]];
    return !!field && parts[1].split('|').indexOf(field.value) !== -1;
  }
  document.addEventListener('submit', function (e) {
    var form = e.target; if (form.method !== 'post' && !form.hasAttribute('data-validate')) return;
    if (form.dataset.confirmed === '1') { form.dataset.confirmed = ''; }
    else {
      if (!validate(form)) { e.preventDefault(); return; }
      if (needsConfirm(form) && confirmDlg) {
        e.preventDefault(); pending = { form: form, submitter: e.submitter };
        $('#confirm-text').textContent = form.getAttribute('data-confirm');
        $('[data-confirm-ok]', confirmDlg).textContent = form.getAttribute('data-confirm-label') || 'Confirm';
        confirmDlg.showModal(); lockScroll(); $('[data-confirm-ok]', confirmDlg).focus(); return;
      }
    }
    var dlg = form.closest('dialog[data-reopen]');
    if (dlg) { try { sessionStorage.setItem('cq-reopen', JSON.stringify({ id: dlg.id, path: location.pathname })); } catch (err) { /* ignore */ } }
    var btn = e.submitter || $('button[type="submit"], button:not([type])', form);
    if (btn && form.method === 'post') {
      // delay so the browser still submits the button's own name/value
      setTimeout(function () { btn.classList.add('is-loading'); btn.setAttribute('aria-busy', 'true'); }, 0);
    }
  });
  if (confirmDlg) {
    $('[data-confirm-cancel]', confirmDlg).addEventListener('click', function () { pending = null; confirmDlg.close(); });
    $('[data-confirm-ok]', confirmDlg).addEventListener('click', function () {
      var p = pending; pending = null; confirmDlg.close();
      if (p) { p.form.dataset.confirmed = '1'; if (p.form.requestSubmit) p.form.requestSubmit(p.submitter || undefined); else p.form.submit(); }
    });
    confirmDlg.addEventListener('close', function () { pending = null; lockScroll(); });
  }
  window.addEventListener('pageshow', function () {
    $$('.btn.is-loading').forEach(function (b) { b.classList.remove('is-loading'); b.removeAttribute('aria-busy'); });
  });

  document.addEventListener('click', function (e) { if (e.target.closest('[data-history-back]')) history.back(); });

  /* ---------- toasts ---------- */
  function dismissToast(t) { t.classList.add('leaving'); setTimeout(function () { t.remove(); }, 220); }
  $$('.toast').forEach(function (t) {
    if (t.getAttribute('data-autoclose') === 'true') setTimeout(function () { if (document.body.contains(t)) dismissToast(t); }, 6500);
  });
  document.addEventListener('click', function (e) { var x = e.target.closest('[data-toast-close]'); if (x) dismissToast(x.closest('.toast')); });

  /* ---------- list filtering (presentation only; the server returns every record) ---------- */
  $$('[data-filter-root]').forEach(function (bar) {
    var scope = bar.closest('.table-card') || document;
    var table = $(bar.getAttribute('data-filter-root'));
    if (!table) return;
    var rows = $$('tbody tr[data-row]', table);
    var q = $('[data-filter-q]', bar), selects = $$('[data-filter-field]', bar);
    var clear = $('[data-filter-clear]', bar), count = $('[data-filter-count]', bar);
    var emptyMsg = $('[data-filter-empty]', scope), tableWrap = table.closest('.table-scroll') || table;
    var params = new URLSearchParams(location.search);
    if (q && params.get('q')) q.value = params.get('q');
    selects.forEach(function (s) {
      var want = params.get(s.getAttribute('data-filter-field'));
      if (want && $$('option', s).some(function (o) { return o.value === want; })) s.value = want;
    });
    function apply() {
      var term = q ? q.value.trim().toLowerCase() : '', shown = 0, active = !!term;
      selects.forEach(function (s) { if (s.value) active = true; });
      rows.forEach(function (r) {
        var ok = !term || (r.getAttribute('data-search') || '').indexOf(term) !== -1;
        selects.forEach(function (s) {
          if (!ok || !s.value) return;
          var key = s.getAttribute('data-filter-field');
          if (s.value === '__open') ok = r.getAttribute('data-unresolved') === '1';
          else ok = r.getAttribute('data-' + key) === s.value;
        });
        r.hidden = !ok; if (ok) shown++;
      });
      count.textContent = active ? 'Showing ' + shown + ' of ' + rows.length : rows.length + (rows.length === 1 ? ' record' : ' records');
      clear.hidden = !active;
      if (emptyMsg) emptyMsg.hidden = shown !== 0;
      tableWrap.hidden = shown === 0;
    }
    if (q) q.addEventListener('input', apply);
    selects.forEach(function (s) { s.addEventListener('change', apply); });
    clear.addEventListener('click', function () { if (q) q.value = ''; selects.forEach(function (s) { s.value = ''; }); apply(); (q || bar).focus(); });
    var reset = $('[data-filter-reset]', scope); if (reset) reset.addEventListener('click', function () { clear.click(); });
    apply();
  });
})();
