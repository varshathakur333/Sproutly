/**
 * sproutly.js — Core JS for Sproutly
 * Handles: toasts, CSRF, AJAX helpers, autocomplete, steppers
 */

'use strict';

// ═══════════════════════════════════════════════════════════
// 1. CSRF
// ═══════════════════════════════════════════════════════════

function getCsrf() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.content;
  const cookie = document.cookie.split('; ').find(r => r.startsWith('csrftoken='));
  return cookie ? cookie.split('=')[1] : '';
}

async function apiGet(url) {
  const r = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function apiPost(url, data) {
  const r = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrf(),
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function apiPatch(url, data) {
  const r = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrf(),
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function apiDelete(url) {
  const r = await fetch(url, {
    method: 'DELETE',
    headers: {
      'X-CSRFToken': getCsrf(),
      'X-Requested-With': 'XMLHttpRequest',
    },
  });
  if (!r.ok) throw new Error(await r.text());
  return r.status === 204 ? null : r.json();
}

// ═══════════════════════════════════════════════════════════
// 2. Toast notifications
// ═══════════════════════════════════════════════════════════

function showToast(msg, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast${type === 'error' ? ' toast--error' : type === 'warn' ? ' toast--warn' : ''}`;
  toast.innerHTML = `<span>${type === 'success' ? '✅' : type === 'error' ? '❌' : '⚠️'}</span> ${msg}
    <button onclick="this.parentElement.remove()" style="margin-left:auto;background:none;border:none;color:inherit;cursor:pointer;font-size:1rem;">×</button>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('toast--out');
    setTimeout(() => toast.remove(), 400);
  }, 3500);
}

// Render Django messages as toasts
document.addEventListener('DOMContentLoaded', () => {
  const msgEl = document.getElementById('django-messages');
  if (msgEl) {
    try {
      const msgs = JSON.parse(msgEl.textContent);
      msgs.forEach(m => showToast(m.message, m.tags.includes('error') ? 'error' : m.tags.includes('warning') ? 'warn' : 'success'));
    } catch {}
  }
});

// ═══════════════════════════════════════════════════════════
// 3. Debounce
// ═══════════════════════════════════════════════════════════

function debounce(fn, delay = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

// ═══════════════════════════════════════════════════════════
// 4. Ingredient autocomplete
// ═══════════════════════════════════════════════════════════

function initAutocomplete(inputEl, listEl, onSelect, extraParams = '') {
  if (!inputEl || !listEl) return;

  const doSearch = debounce(async (q) => {
    if (q.length < 1) { listEl.classList.remove('open'); return; }
    try {
      const data = await apiGet(`/api/ingredients/?q=${encodeURIComponent(q)}${extraParams}`);
      const items = data.results || data;
      listEl.innerHTML = '';
      if (!items.length) { listEl.classList.remove('open'); return; }
      items.slice(0, 10).forEach(ing => {
        const div = document.createElement('div');
        div.className = 'autocomplete-item';
        div.textContent = ing.name;
        div.dataset.id = ing.id;
        div.addEventListener('mousedown', e => {
          e.preventDefault();
          onSelect(ing);
          listEl.classList.remove('open');
          inputEl.value = '';
        });
        listEl.appendChild(div);
      });
      listEl.classList.add('open');
    } catch {}
  }, 250);

  inputEl.addEventListener('input', e => doSearch(e.target.value));
  inputEl.addEventListener('blur', () => setTimeout(() => listEl.classList.remove('open'), 150));
}

// ═══════════════════════════════════════════════════════════
// 5. Recipe-filter autocomplete (tag input for "have_ids")
// ═══════════════════════════════════════════════════════════

function initTagInput(wrapEl, hiddenEl) {
  if (!wrapEl || !hiddenEl) return;
  const inputEl = wrapEl.querySelector('input[type=text]');
  const listEl  = wrapEl.nextElementSibling;
  const tags    = [];

  function render() {
    wrapEl.querySelectorAll('.tag-pill').forEach(el => el.remove());
    tags.forEach(t => {
      const pill = document.createElement('span');
      pill.className = 'tag-pill';
      pill.innerHTML = `${t.name} <span class="tag-pill__remove" data-id="${t.id}">×</span>`;
      pill.querySelector('.tag-pill__remove').addEventListener('click', () => {
        const idx = tags.findIndex(x => x.id === t.id);
        if (idx > -1) { tags.splice(idx, 1); render(); updateHidden(); }
      });
      wrapEl.insertBefore(pill, inputEl);
    });
  }

  function updateHidden() {
    hiddenEl.value = tags.map(t => t.id).join(',');
    hiddenEl.dispatchEvent(new Event('change', { bubbles: true }));
  }

  initAutocomplete(inputEl, listEl, (ing) => {
    if (!tags.find(t => t.id === ing.id)) { tags.push(ing); render(); updateHidden(); }
  });
}

// ═══════════════════════════════════════════════════════════
// 6. Recipe list AJAX filtering
// ═══════════════════════════════════════════════════════════

(function initRecipeFilter() {
  const grid     = document.getElementById('recipe-grid');
  const skeleton = document.getElementById('skeleton-grid');
  const empty    = document.getElementById('empty-state');
  if (!grid) return;

  const params = new URLSearchParams(window.location.search);

  async function loadRecipes(newParams) {
    if (skeleton) { grid.style.display = 'none'; skeleton.style.display = 'grid'; }
    if (empty)    { empty.style.display = 'none'; }

    try {
      const qs = newParams.toString();
      const data = await apiGet(`/api/recipes/?${qs}&format=json`);
      window.history.replaceState({}, '', `?${qs}`);

      if (skeleton) skeleton.style.display = 'none';

      const results = data.results || data;
      if (!results.length) {
        grid.style.display = 'none';
        grid.innerHTML = '';
        if (empty) empty.style.display = 'block';
        return;
      }

      grid.style.display = 'grid';
      grid.innerHTML = results.map(r => recipeCardHtml(r)).join('');
    } catch (e) {
      if (skeleton) skeleton.style.display = 'none';
      grid.style.display = 'grid';
      showToast('Could not load recipes', 'error');
    }
  }

  function recipeCardHtml(r) {
    const img = r.image
      ? `<img src="${r.image}" alt="${r.title}" loading="lazy">`
      : `<div class="recipe-card__placeholder">🥘</div>`;

    const dietClass = `diet-badge-${r.diet_type}`;
    const time = (r.prep_time || 0) + (r.cook_time || 0);
    const n = r.nutrition || {};

    const matchBadge = r.match
      ? `<div class="chip chip-teal" title="Ingredient match">${Math.round(r.match.score * 100)}% match</div>`
      : '';

    const missingNote = r.match && r.match.missing && r.match.missing.length
      ? `<p style="font-size:0.72rem;color:var(--clr-text-muted);margin-top:4px">Missing: ${r.match.missing.slice(0,3).join(', ')}</p>`
      : '';

    return `
    <a href="/recipes/${r.slug}/" class="recipe-card">
      <div class="recipe-card__img">${img}</div>
      <div class="recipe-card__body">
        <div class="chip ${dietClass}" style="margin-bottom:6px">${r.diet_type}</div>
        <div class="recipe-card__title">${r.title}</div>
        <div class="recipe-card__meta">⏱ ${time} min</div>
        <div class="recipe-card__chips">
          ${n.protein ? `<span class="chip chip-green">💪 ${parseFloat(n.protein).toFixed(1)}g protein</span>` : ''}
          ${n.calories ? `<span class="chip chip-yellow">🔥 ${parseFloat(n.calories).toFixed(0)} kcal</span>` : ''}
          ${n.iron ? `<span class="chip chip-red">🩸 ${parseFloat(n.iron).toFixed(1)}mg iron</span>` : ''}
          ${matchBadge}
        </div>
        ${missingNote}
      </div>
    </a>`;
  }

  // Collect filter values and trigger load
  const debouncedLoad = debounce(() => {
    const form = document.getElementById('filter-form');
    if (!form) return;
    const fd = new FormData(form);
    const p = new URLSearchParams();
    fd.forEach((v, k) => { if (v) p.set(k, v); });
    // Preserve tab
    const tab = new URLSearchParams(window.location.search).get('tab');
    if (tab) p.set('tab', tab);
    loadRecipes(p);
  }, 400);

  const filterForm = document.getElementById('filter-form');
  if (filterForm) {
    filterForm.addEventListener('input', debouncedLoad);
    filterForm.addEventListener('change', debouncedLoad);
  }

  // Preset pills
  document.querySelectorAll('.preset-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const isActive = pill.classList.contains('active');
      document.querySelectorAll('.preset-pill').forEach(p => p.classList.remove('active'));
      const inp = document.getElementById('preset-input');
      if (isActive) {
        if (inp) inp.value = '';
      } else {
        pill.classList.add('active');
        if (inp) inp.value = pill.dataset.preset;
      }
      debouncedLoad();
    });
  });

  // Clear button
  const clearBtn = document.getElementById('filter-clear');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      if (filterForm) filterForm.reset();
      document.querySelectorAll('.preset-pill').forEach(p => p.classList.remove('active'));
      const inp = document.getElementById('preset-input');
      if (inp) inp.value = '';
      loadRecipes(new URLSearchParams());
    });
  }

  // "Have ingredients" tag input
  const tagWrap   = document.getElementById('have-tags');
  const haveInput = document.getElementById('have-ids-input');
  if (tagWrap && haveInput) initTagInput(tagWrap, haveInput);

  // Sort select
  const sortSel = document.getElementById('sort-select');
  if (sortSel) sortSel.addEventListener('change', debouncedLoad);

  // Mobile drawer toggle
  const drawerBtn = document.getElementById('filter-drawer-btn');
  const drawer    = document.getElementById('filter-drawer');
  const overlay   = document.getElementById('drawer-overlay');
  if (drawerBtn && drawer) {
    drawerBtn.addEventListener('click', () => {
      drawer.classList.add('open');
      if (overlay) overlay.classList.add('open');
    });
    if (overlay) overlay.addEventListener('click', () => {
      drawer.classList.remove('open');
      overlay.classList.remove('open');
    });
  }
})();

// ═══════════════════════════════════════════════════════════
// 7. Recipe detail — servings scaler + log form + favorite
// ═══════════════════════════════════════════════════════════

(function initRecipeDetail() {
  const page = document.querySelector('[data-recipe-id]');
  if (!page) return;

  const recipeId   = page.dataset.recipeId;
  const servingsBtns = document.querySelectorAll('.servings-selector__btn');
  const servingsVal  = document.querySelector('.servings-selector__val');
  const baseServings = parseInt(page.dataset.baseServings || '1');
  let currentServings = baseServings;

  // Scale ingredient amounts & nutrition values
  function scaleDisplay(multiplier) {
    document.querySelectorAll('[data-base-amount]').forEach(el => {
      const base = parseFloat(el.dataset.baseAmount);
      el.textContent = (base * multiplier).toFixed(1);
    });
    document.querySelectorAll('[data-base-nutrient]').forEach(el => {
      const base = parseFloat(el.dataset.baseNutrient);
      el.textContent = (base * multiplier).toFixed(1);
    });
  }

  servingsBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const delta = btn.dataset.delta === '-1' ? -0.5 : 0.5;
      currentServings = Math.max(0.5, currentServings + delta);
      if (servingsVal) servingsVal.textContent = `${currentServings} serving${currentServings !== 1 ? 's' : ''}`;
      scaleDisplay(currentServings / baseServings);
      // Update log form servings
      const logServings = document.getElementById('log-servings');
      if (logServings) logServings.value = currentServings;
    });
  });

  // Add to meal log
  const logBtn = document.getElementById('log-meal-btn');
  if (logBtn) {
    logBtn.addEventListener('click', async () => {
      const date     = document.getElementById('log-date').value;
      const mealType = document.getElementById('log-meal-type').value;
      const servings = parseFloat(document.getElementById('log-servings').value) || 1;
      try {
        logBtn.disabled = true;
        await apiPost('/api/logs/', { recipe: parseInt(recipeId), date, meal_type: mealType, servings });
        showToast('Meal logged! 🌱');
      } catch {
        showToast('Could not log meal', 'error');
      } finally {
        logBtn.disabled = false;
      }
    });
  }

  // Favorite toggle
  const favBtn = document.getElementById('fav-btn');
  if (favBtn) {
    favBtn.addEventListener('click', async () => {
      try {
        const data = await apiPost(`/api/recipes/${recipeId}/favorite/`, {});
        favBtn.textContent = data.favorited ? '♥ Unfavorite' : '♡ Favorite';
        showToast(data.favorited ? 'Added to favorites!' : 'Removed from favorites');
      } catch {
        showToast('Could not update favorite', 'error');
      }
    });
  }

  // Delete modal
  const delBtn     = document.getElementById('delete-recipe-btn');
  const delModal   = document.getElementById('delete-modal');
  const cancelDel  = document.getElementById('cancel-delete');
  if (delBtn && delModal) {
    delBtn.addEventListener('click', () => delModal.classList.add('open'));
    if (cancelDel) cancelDel.addEventListener('click', () => delModal.classList.remove('open'));
    delModal.addEventListener('click', e => { if (e.target === delModal) delModal.classList.remove('open'); });
  }
})();

// ═══════════════════════════════════════════════════════════
// 8. Meal Tracker
// ═══════════════════════════════════════════════════════════

(function initTracker() {
  const trackerPage = document.getElementById('tracker-page');
  if (!trackerPage) return;

  const dateVal = trackerPage.dataset.date;

  // ---- Quick-add ----
  const qaSearch   = document.getElementById('qa-search');
  const qaList     = document.getElementById('qa-list');
  const qaServings = document.getElementById('qa-servings');
  const qaMealType = document.getElementById('qa-meal-type');
  const qaAddBtn   = document.getElementById('qa-add-btn');

  let selectedItem = null;

  if (qaSearch && qaList) {
    const doSearch = debounce(async (q) => {
      if (!q) { qaList.classList.remove('open'); return; }
      try {
        const data = await apiGet(`/api/recipes/?q=${encodeURIComponent(q)}&page_size=8`);
        const items = (data.results || []).map(r => ({ id: r.id, name: r.title, type: 'recipe', slug: r.slug }));
        // Also search ingredients
        const idata = await apiGet(`/api/ingredients/?q=${encodeURIComponent(q)}`);
        const ings  = (idata.results || idata).slice(0, 4).map(i => ({ id: i.id, name: i.name, type: 'ingredient' }));
        const all = [...items, ...ings];
        qaList.innerHTML = all.map(i =>
          `<div class="autocomplete-item" data-id="${i.id}" data-type="${i.type}">${i.type === 'ingredient' ? '🥦 ' : '🍽 '}${i.name}</div>`
        ).join('') || '<div class="autocomplete-item" style="color:var(--clr-text-muted)">No results</div>';
        qaList.classList.add('open');
        qaList.querySelectorAll('.autocomplete-item[data-id]').forEach(el => {
          el.addEventListener('mousedown', e => {
            e.preventDefault();
            selectedItem = { id: parseInt(el.dataset.id), type: el.dataset.type, name: el.textContent.trim() };
            qaSearch.value = el.textContent.replace(/^[^\s]+\s/, '').trim();
            qaList.classList.remove('open');
          });
        });
      } catch {}
    }, 300);

    qaSearch.addEventListener('input', e => doSearch(e.target.value));
    qaSearch.addEventListener('blur', () => setTimeout(() => qaList.classList.remove('open'), 150));
  }

  if (qaAddBtn) {
    qaAddBtn.addEventListener('click', async () => {
      if (!selectedItem) { showToast('Search and select a recipe or ingredient first', 'warn'); return; }
      const servings  = parseFloat(qaServings?.value || '1');
      const mealType  = qaMealType?.value || 'lunch';
      try {
        qaAddBtn.disabled = true;
        const payload = {
          date: dateVal,
          meal_type: mealType,
          servings,
          [selectedItem.type === 'recipe' ? 'recipe' : 'ingredient']: selectedItem.id,
        };
        const log = await apiPost('/api/logs/', payload);
        showToast(`Added to ${mealType}! 🌱`);
        addLogRowToDOM(log, mealType);
        updateTotalsBar();
        selectedItem = null;
        if (qaSearch) qaSearch.value = '';
      } catch {
        showToast('Could not add item', 'error');
      } finally {
        qaAddBtn.disabled = false;
      }
    });
  }

  // ---- Stepper on existing rows ----
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-stepper]');
    if (!btn) return;
    const row     = btn.closest('[data-log-id]');
    if (!row) return;
    const logId   = row.dataset.logId;
    const valEl   = row.querySelector('.stepper__val');
    let servings  = parseFloat(valEl?.textContent || '1');
    const delta   = btn.dataset.stepper === '-' ? -0.25 : 0.25;
    servings      = Math.max(0.25, parseFloat((servings + delta).toFixed(2)));
    if (valEl) valEl.textContent = servings;
    try {
      const updated = await apiPatch(`/api/logs/${logId}/`, { servings });
      // Update row nutrient display
      const calEl  = row.querySelector('[data-snap="calories"]');
      const proEl  = row.querySelector('[data-snap="protein"]');
      if (calEl)  calEl.textContent = `${parseFloat(updated.snap_calories).toFixed(0)} kcal`;
      if (proEl)  proEl.textContent = `${parseFloat(updated.snap_protein).toFixed(1)}g`;
      updateTotalsBar();
    } catch {
      showToast('Could not update portion', 'error');
      if (valEl) valEl.textContent = (servings - delta).toFixed(2);
    }
  });

  // ---- Delete row ----
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-delete-log]');
    if (!btn) return;
    const row   = btn.closest('[data-log-id]');
    if (!row) return;
    const logId = row.dataset.logId;
    try {
      await apiDelete(`/api/logs/${logId}/`);
      row.style.animation = 'toast-out .3s forwards';
      setTimeout(() => { row.remove(); updateTotalsBar(); }, 320);
      showToast('Removed');
    } catch {
      showToast('Could not delete', 'error');
    }
  });

  // ---- Date navigation ----
  const prevBtn    = document.getElementById('date-prev');
  const nextBtn    = document.getElementById('date-next');
  const datePicker = document.getElementById('date-picker');

  function navDate(offset) {
    const d = new Date(dateVal);
    d.setDate(d.getDate() + offset);
    window.location.href = `/tracker/?date=${d.toISOString().slice(0,10)}`;
  }

  if (prevBtn) prevBtn.addEventListener('click', () => navDate(-1));
  if (nextBtn) nextBtn.addEventListener('click', () => navDate(1));
  if (datePicker) datePicker.addEventListener('change', e => {
    window.location.href = `/tracker/?date=${e.target.value}`;
  });

  // ---- Totals bar ----
  async function updateTotalsBar() {
    try {
      const data = await apiGet(`/api/dashboard/?date=${dateVal}`);
      const totals = data.totals || {};
      const calEl  = document.getElementById('totals-cal');
      const proEl  = document.getElementById('totals-pro');
      if (calEl) calEl.textContent = `${parseFloat(totals.calories || 0).toFixed(0)} kcal`;
      if (proEl) proEl.textContent = `${parseFloat(totals.protein  || 0).toFixed(1)} g`;
    } catch {}
  }

  // ---- Inject a new log row into the DOM ----
  function addLogRowToDOM(log, mealType) {
    const section = document.querySelector(`.meal-section[data-meal="${mealType}"] .meal-rows`);
    if (!section) return;
    const name = log.recipe_title || log.ingredient_name || 'Unknown';
    const cal  = parseFloat(log.snap_calories || 0).toFixed(0);
    const pro  = parseFloat(log.snap_protein  || 0).toFixed(1);
    const row  = document.createElement('div');
    row.className = 'log-row';
    row.dataset.logId = log.id;
    row.innerHTML = `
      <div>
        <div class="log-row__name">${name}</div>
        <div class="log-row__nutrients">
          <span data-snap="calories">${cal} kcal</span> &middot;
          <span data-snap="protein">${pro}g protein</span>
        </div>
      </div>
      <div class="stepper">
        <button class="stepper__btn" data-stepper="-" aria-label="Decrease">−</button>
        <span class="stepper__val">${log.servings}</span>
        <button class="stepper__btn" data-stepper="+" aria-label="Increase">+</button>
      </div>
      <button class="btn btn-ghost btn-sm" data-delete-log="${log.id}" aria-label="Remove">×</button>`;
    section.appendChild(row);
  }
})();

// ═══════════════════════════════════════════════════════════
// 9. Dashboard charts
// ═══════════════════════════════════════════════════════════

(function initDashboard() {
  if (!document.getElementById('macroChart')) return;

  const dateEl = document.getElementById('dashboard-date');
  const dateVal = dateEl ? dateEl.dataset.date : new Date().toISOString().slice(0,10);

  async function loadDashboard() {
    try {
      const data = await apiGet(`/api/dashboard/?date=${dateVal}`);
      buildMacroChart(data.macro_split || {});
      buildMealChart(data.calories_by_meal || {});
    } catch {}
  }

  async function loadTrend(nutrient = 'calories') {
    try {
      const data = await apiGet(`/api/trend/?date=${dateVal}`);
      buildTrendChart(data, nutrient);
    } catch {}
  }

  async function loadRecommendations(mealType) {
    try {
      const data = await apiGet(`/api/recommendations/?date=${dateVal}&meal_type=${mealType}`);
      const grid = document.getElementById('reco-grid');
      if (!grid) return;
      grid.innerHTML = data.map(r => {
        const img = r.image
          ? `<img src="${r.image}" alt="${r.title}" style="width:100%;height:100%;object-fit:cover">`
          : '🥘';
        return `
        <a href="/recipes/${r.slug}/" class="reco-card">
          <div class="reco-card__img">${img}</div>
          <div class="reco-card__body">
            ${r.rec_badge ? `<div class="reco-card__badge">${r.rec_badge}</div>` : ''}
            <div class="reco-card__title">${r.title}</div>
            <div class="chip ${`diet-badge-${r.diet_type}`}" style="margin-top:4px;font-size:0.68rem">${r.diet_type}</div>
          </div>
        </a>`;
      }).join('') || '<p style="color:var(--clr-text-muted)">Nothing to recommend yet — log more meals!</p>';
    } catch {}
  }

  let macroChart, mealChart, trendChart;

  function buildMacroChart(macro) {
    const ctx = document.getElementById('macroChart');
    if (!ctx) return;
    if (macroChart) macroChart.destroy();
    macroChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Protein', 'Carbs', 'Fat'],
        datasets: [{
          data: [macro.protein || 0, macro.carbs || 0, macro.fat || 0],
          backgroundColor: ['#4A7C2F', '#F5C842', '#E05C3A'],
          borderWidth: 0,
        }],
      },
      options: {
        cutout: '65%',
        plugins: {
          legend: { position: 'bottom' },
          tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw}%` } },
        },
        aria: { label: 'Macro split donut chart' },
      },
    });
  }

  function buildMealChart(mealData) {
    const ctx = document.getElementById('mealChart');
    if (!ctx) return;
    if (mealChart) mealChart.destroy();
    mealChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Breakfast', 'Lunch', 'Dinner', 'Snack'],
        datasets: [{
          label: 'Calories',
          data: ['breakfast', 'lunch', 'dinner', 'snack'].map(m => mealData[m] || 0),
          backgroundColor: ['#F5C842', '#4A7C2F', '#3AA6A6', '#E05C3A'],
          borderRadius: 8,
        }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, title: { display: true, text: 'kcal' } } },
        aria: { label: 'Calories by meal bar chart' },
      },
    });
  }

  function buildTrendChart(trendData, nutrient) {
    const ctx = document.getElementById('trendChart');
    if (!ctx) return;
    if (trendChart) trendChart.destroy();
    const vals = (trendData.data || {})[nutrient] || [];
    trendChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: trendData.labels || [],
        datasets: [{
          label: nutrient.charAt(0).toUpperCase() + nutrient.slice(1),
          data: vals,
          borderColor: '#4A7C2F',
          backgroundColor: 'rgba(74,124,47,.1)',
          tension: 0.4,
          fill: true,
          pointBackgroundColor: '#4A7C2F',
        }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } },
        aria: { label: `7-day ${nutrient} trend line chart` },
      },
    });
  }

  // Trend nutrient selector
  document.querySelectorAll('[data-trend-nutrient]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-trend-nutrient]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      apiGet(`/api/trend/?date=${dateVal}`).then(d => buildTrendChart(d, btn.dataset.trendNutrient));
    });
  });

  // Recommendation meal type selector
  document.querySelectorAll('[data-reco-meal]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-reco-meal]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadRecommendations(btn.dataset.recoMeal);
    });
  });

  loadDashboard();
  loadTrend('calories');

  const defaultMealBtn = document.querySelector('[data-reco-meal].active');
  if (defaultMealBtn) loadRecommendations(defaultMealBtn.dataset.recoMeal);
})();

// ═══════════════════════════════════════════════════════════
// 10. Recipe form — ingredient formset + live preview
// ═══════════════════════════════════════════════════════════

(function initRecipeForm() {
  const form = document.getElementById('recipe-form');
  if (!form) return;

  let rowCount = document.querySelectorAll('.formset-row').length;

  // Add row
  document.getElementById('add-ingredient-row')?.addEventListener('click', () => {
    const template = document.getElementById('ingredient-row-template');
    if (!template) return;
    const clone = template.content.cloneNode(true);
    clone.querySelectorAll('[name]').forEach(el => {
      el.name = el.name.replace('__prefix__', rowCount);
      el.id   = el.id.replace('__prefix__', rowCount);
    });
    document.getElementById('ingredient-formset-body').appendChild(clone);
    rowCount++;
    document.getElementById('id_recipe_ingredients-TOTAL_FORMS').value = rowCount;
    attachRowEvents(document.querySelectorAll('.formset-row')[rowCount - 1]);
  });

  // Remove row
  function attachRowEvents(row) {
    row.querySelector('.btn-remove-row')?.addEventListener('click', () => {
      const delCheck = row.querySelector('[name$="-DELETE"]');
      if (delCheck) { delCheck.checked = true; row.style.display = 'none'; }
      else row.remove();
      updateLivePreview();
    });

    // Ingredient name autocomplete
    const nameInput = row.querySelector('.ing-name-input');
    const idInput   = row.querySelector('.ing-id-input');
    const listEl    = row.querySelector('.autocomplete-list');
    if (nameInput && idInput && listEl) {
      initAutocomplete(nameInput, listEl, (ing) => {
        nameInput.value = ing.name;
        idInput.value   = ing.id;
        updateLivePreview();
      });
    }

    row.querySelector('.ing-grams-input')?.addEventListener('input', updateLivePreview);
  }

  document.querySelectorAll('.formset-row').forEach(attachRowEvents);

  // Live nutrition preview
  async function updateLivePreview() {
    const rows    = [...document.querySelectorAll('.formset-row')].filter(r => r.style.display !== 'none');
    const servings = parseFloat(document.getElementById('id_servings')?.value || 1) || 1;
    const payload  = { servings, ingredients: [] };

    rows.forEach(row => {
      const ingId = row.querySelector('.ing-id-input')?.value;
      const grams = parseFloat(row.querySelector('.ing-grams-input')?.value || 0);
      if (ingId && grams > 0) payload.ingredients.push({ ingredient_id: parseInt(ingId), grams });
    });

    if (!payload.ingredients.length) return;

    try {
      const data = await apiPost('/api/recipes/preview_nutrition/', payload);
      const fields = ['calories','protein','carbs','fat','fiber','iron','calcium','b12'];
      fields.forEach(f => {
        const el = document.getElementById(`preview-${f}`);
        if (el) el.textContent = parseFloat(data[f] || 0).toFixed(1);
      });
    } catch {}
  }

  document.getElementById('id_servings')?.addEventListener('input', updateLivePreview);

  // Manual nutrition toggle
  const toggleBtn = document.getElementById('manual-toggle');
  const manualFields = document.getElementById('manual-nutrition-fields');
  if (toggleBtn && manualFields) {
    toggleBtn.addEventListener('click', () => {
      const isHidden = manualFields.style.display === 'none';
      manualFields.style.display = isHidden ? 'block' : 'none';
      toggleBtn.textContent = isHidden ? 'Use auto-calculated nutrition' : 'Enter nutrition manually';
    });
  }
})();

// ═══════════════════════════════════════════════════════════
// 11. Goals page — goal_type toggle
// ═══════════════════════════════════════════════════════════

(function initGoalsPage() {
  document.querySelectorAll('.goal-type-toggle').forEach(wrap => {
    const radios = wrap.querySelectorAll('input[type=radio]');
    const pills  = wrap.querySelectorAll('label');
    radios.forEach((radio, i) => {
      radio.addEventListener('change', () => {
        pills.forEach(p => p.classList.remove('active'));
        if (pills[i]) pills[i].classList.add('active');
      });
      if (radio.checked && pills[i]) pills[i].classList.add('active');
    });
  });
})();

