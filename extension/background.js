/**
 * Background service worker (Manifest V3).
 *
 * Listens for extension install/update events and sets a default API URL
 * in local storage if none is present.
 */

const DEFAULT_API_URL = "http://localhost:8000";

chrome.runtime.onInstalled.addListener(async () => {
  const stored = await chrome.storage.local.get("apiUrl");
  if (!stored.apiUrl) {
    await chrome.storage.local.set({ apiUrl: DEFAULT_API_URL });
    console.log("[LunchMenu] Default API URL set:", DEFAULT_API_URL);
  }
});
