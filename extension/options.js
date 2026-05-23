// RePrompt options page

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8787";

document.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("backendUrl");
  const statusDiv = document.getElementById("status");
  const connDot = document.getElementById("conn-dot");
  const connText = document.getElementById("conn-text");

  // Load saved settings
  chrome.storage.sync.get({ backendUrl: DEFAULT_BACKEND_URL }, (items) => {
    urlInput.value = items.backendUrl || DEFAULT_BACKEND_URL;
    checkConnection(items.backendUrl || DEFAULT_BACKEND_URL);
  });

  // Save
  document.getElementById("saveBtn").addEventListener("click", () => {
    const url = urlInput.value.trim() || DEFAULT_BACKEND_URL;
    chrome.storage.sync.set({ backendUrl: url }, () => {
      statusDiv.className = "success";
      statusDiv.textContent = "Settings saved!";
      setTimeout(() => { statusDiv.style.display = "none"; }, 2000);
      checkConnection(url);
    });
  });

  // Test connection
  document.getElementById("testBtn").addEventListener("click", () => {
    const url = urlInput.value.trim() || DEFAULT_BACKEND_URL;
    checkConnection(url);
  });

  async function checkConnection(url) {
    connDot.className = "dot gray";
    connText.textContent = "Checking...";
    try {
      const resp = await fetch(url.replace(/\/+$/, "") + "/health");
      if (resp.ok) {
        connDot.className = "dot green";
        connText.textContent = "Connected";
      } else {
        connDot.className = "dot red";
        connText.textContent = "Server error";
      }
    } catch {
      connDot.className = "dot red";
      connText.textContent = "Not connected (is the server running?)";
    }
  }
});
