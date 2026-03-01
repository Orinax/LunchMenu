/**
 * Popup script for the Lunch Menu Chrome extension.
 *
 * Fetches GET /menu from the configured backend and renders:
 *   - "Week" view: all days Mon–Fri
 *   - "Today" view: only the current weekday
 *
 * Menu type (Ala Carte / Program) is selectable via a dropdown.
 */

const DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday"];
const DAY_LABELS = {
  monday: "Monday",
  tuesday: "Tuesday",
  wednesday: "Wednesday",
  thursday: "Thursday",
  friday: "Friday",
};

/**
 * Return today's day name in lowercase, or null if it's a weekend.
 */
function todayDayName() {
  const d = new Date().getDay(); // 0=Sun, 1=Mon, …, 6=Sat
  if (d === 0 || d === 6) return null;
  return DAY_NAMES[d - 1];
}

/**
 * Get the effective API base URL.
 * Checks managed storage first (admin policy), then local storage.
 */
async function getApiUrl() {
  try {
    const managed = await chrome.storage.managed.get("MENU_API_URL");
    if (managed.MENU_API_URL) return managed.MENU_API_URL.replace(/\/$/, "");
  } catch {
    // Managed storage not available in all environments
  }
  const local = await chrome.storage.local.get("apiUrl");
  return (local.apiUrl || "http://localhost:8000").replace(/\/$/, "");
}

/**
 * Fetch the menu data from the backend.
 */
async function fetchMenu(baseUrl) {
  const response = await fetch(`${baseUrl}/menu`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return response.json();
}

/**
 * Render a single category block.
 */
function renderCategory(category) {
  const block = document.createElement("div");
  block.className = "category-block";

  const nameEl = document.createElement("div");
  nameEl.className = "category-name";
  nameEl.textContent = category.category || "—";
  block.appendChild(nameEl);

  const items = category.items || [];
  if (items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "no-items";
    empty.textContent = "No items";
    block.appendChild(empty);
  } else {
    items.forEach((item) => {
      const itemEl = document.createElement("div");
      itemEl.className = "menu-item";

      if (item.en) {
        const enEl = document.createElement("div");
        enEl.className = "item-en";
        enEl.textContent = item.en;
        itemEl.appendChild(enEl);
      }
      if (item.th) {
        const thEl = document.createElement("div");
        thEl.className = "item-th";
        thEl.textContent = item.th;
        itemEl.appendChild(thEl);
      }
      block.appendChild(itemEl);
    });
  }

  return block;
}

/**
 * Render a single day section.
 */
function renderDay(dayName, categories, isToday = false) {
  const section = document.createElement("div");
  section.className = "day-section";

  const title = document.createElement("div");
  title.className = "day-title" + (isToday ? " today" : "");
  title.textContent =
    DAY_LABELS[dayName] + (isToday ? " (Today)" : "");
  section.appendChild(title);

  if (!categories || categories.length === 0) {
    const empty = document.createElement("div");
    empty.className = "no-items";
    empty.textContent = "No menu available";
    section.appendChild(empty);
  } else {
    categories.forEach((cat) => {
      section.appendChild(renderCategory(cat));
    });
  }

  return section;
}

/**
 * Main render function.
 */
function renderMenu(data, menuType, viewMode) {
  const content = document.getElementById("content");
  content.innerHTML = "";

  const weekLabel = document.getElementById("weekLabel");
  weekLabel.textContent = data.week?.label || "";

  const footer = document.getElementById("footer");
  if (data.lastFetched) {
    const dt = new Date(data.lastFetched);
    footer.textContent = `Last fetched: ${dt.toLocaleString()}`;
  }

  const menuData = data.menus?.[menuType];
  if (!menuData) {
    content.innerHTML = `<div class="error">Menu type "${menuType}" not found in API response.</div>`;
    return;
  }

  const days = menuData.days || {};
  const todayName = todayDayName();

  const daysToShow =
    viewMode === "today" && todayName ? [todayName] : DAY_NAMES;

  if (viewMode === "today" && !todayName) {
    content.innerHTML =
      '<div class="no-items">No menu on weekends 🎉</div>';
    return;
  }

  daysToShow.forEach((dayName) => {
    const categories = days[dayName] || [];
    const isToday = dayName === todayName;
    content.appendChild(renderDay(dayName, categories, isToday));
  });
}

// ── Main ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  const menuTypeSelect = document.getElementById("menuType");
  const weekBtn = document.getElementById("weekBtn");
  const todayBtn = document.getElementById("todayBtn");
  const optionsLink = document.getElementById("optionsLink");
  const content = document.getElementById("content");

  let menuData = null;
  let currentMenuType = "alacarte";
  let currentView = "week";

  // ── Options link ──
  optionsLink.addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });

  // ── Toggle view buttons ──
  function setView(view) {
    currentView = view;
    weekBtn.classList.toggle("active", view === "week");
    todayBtn.classList.toggle("active", view === "today");
    if (menuData) renderMenu(menuData, currentMenuType, currentView);
  }

  weekBtn.addEventListener("click", () => setView("week"));
  todayBtn.addEventListener("click", () => setView("today"));

  // ── Menu type change ──
  menuTypeSelect.addEventListener("change", () => {
    currentMenuType = menuTypeSelect.value;
    if (menuData) renderMenu(menuData, currentMenuType, currentView);
  });

  // ── Fetch and render ──
  try {
    const baseUrl = await getApiUrl();
    menuData = await fetchMenu(baseUrl);
    renderMenu(menuData, currentMenuType, currentView);
  } catch (err) {
    content.innerHTML = `<div class="error">Failed to load menu:<br>${err.message}<br><br>Check the backend URL in <a href="#" id="settingsLink">Settings</a>.</div>`;
    document.getElementById("settingsLink")?.addEventListener("click", (e) => {
      e.preventDefault();
      chrome.runtime.openOptionsPage();
    });
  }
});
