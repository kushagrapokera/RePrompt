// RePrompt popup

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8787";

document.addEventListener("DOMContentLoaded", () => {
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusText");

  chrome.storage.sync.get({ backendUrl: DEFAULT_BACKEND_URL }, async (items) => {
    const url = (items.backendUrl || DEFAULT_BACKEND_URL).replace(/\/+$/, "");
    try {
      const resp = await fetch(`${url}/health`);
      if (resp.ok) {
        dot.className = "dot green";
        text.textContent = "Server connected";
      } else {
        dot.className = "dot red";
        text.textContent = "Server error";
      }
    } catch {
      dot.className = "dot red";
      text.textContent = "Server offline";
    }
  });

  document.getElementById("optionsLink").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });
});
