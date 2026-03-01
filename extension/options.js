/**
 * Options page script.
 *
 * Loads the current API URL from chrome.storage.local,
 * saves changes, and shows a notice if the URL is managed via policy.
 */

async function loadSettings() {
  const apiUrlInput = document.getElementById("apiUrl");
  const managedNotice = document.getElementById("managedNotice");

  // Check managed storage first
  try {
    const managed = await chrome.storage.managed.get("MENU_API_URL");
    if (managed.MENU_API_URL) {
      apiUrlInput.value = managed.MENU_API_URL;
      apiUrlInput.disabled = true;
      document.getElementById("saveBtn").disabled = true;
      managedNotice.style.display = "block";
      return;
    }
  } catch {
    // Managed storage not available – ignore
  }

  // Load from local storage
  const local = await chrome.storage.local.get("apiUrl");
  apiUrlInput.value = local.apiUrl || "http://localhost:8000";
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();

  document.getElementById("saveBtn").addEventListener("click", async () => {
    const apiUrlInput = document.getElementById("apiUrl");
    const status = document.getElementById("status");
    const url = apiUrlInput.value.trim().replace(/\/$/, "");

    if (!url) {
      status.textContent = "Please enter a URL.";
      status.style.color = "#dc3545";
      return;
    }

    await chrome.storage.local.set({ apiUrl: url });
    status.textContent = "✓ Saved!";
    status.style.color = "#28a745";
    setTimeout(() => { status.textContent = ""; }, 2000);
  });
});
