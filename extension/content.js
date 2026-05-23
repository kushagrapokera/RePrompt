// RePrompt content script injected into supported LLM sites.
// Shows a draggable floating enhance button and saves its position per site.

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8787";
const LOGO_URL = chrome.runtime.getURL("icons/reprompt-mark.svg");
const BUTTON_POSITION_KEY = "repromptButtonPositions";
const DRAG_THRESHOLD = 6;

const SITE_CONFIG = {
  "chatgpt.com": {
    textarea: ['#prompt-textarea', 'textarea[placeholder*="Message"]'],
    container: ['form', '[class*="composer"]', '[class*="input"]'],
    upload: ['button[aria-label*="Attach"]', 'button[aria-label*="Upload"]'],
    placement: { x: -6, y: -54 },
  },
  "chat.openai.com": {
    textarea: ['#prompt-textarea', 'textarea'],
    container: ['form', '[class*="composer"]', '[class*="input"]'],
    upload: ['button[aria-label*="Attach"]', 'button[aria-label*="Upload"]'],
    placement: { x: -6, y: -54 },
  },
  "claude.ai": {
    textarea: ['div[contenteditable="true"][role="textbox"]'],
    container: ['form', '[class*="ProseMirror"]', '[class*="input"]', '[class*="composer"]'],
    upload: ['button[aria-label*="Upload"]', 'button[aria-label*="Attach"]'],
    placement: { x: -4, y: -52 },
  },
  "perplexity.ai": {
    textarea: ['textarea[placeholder*="Ask"]', 'textarea'],
    container: ['form', '[class*="input-area"]', '[class*="composer"]'],
    upload: ['button[aria-label*="Upload"]', 'button[aria-label*="Attach"]'],
    placement: { x: -4, y: -52 },
  },
  "gemini.google.com": {
    textarea: ['div[contenteditable="true"][role="textbox"]'],
    container: ['form', '[class*="input-area"]', '[class*="text-input"]', '[class*="prompt"]'],
    upload: ['button[aria-label*="Upload"]', 'button[aria-label*="Attach"]'],
    placement: { x: -4, y: -52 },
  },
};

let enhanceButton = null;
let intentBadge = null;
let observer = null;
let currentSite = null;
let savedButtonPosition = null;
let positionLoaded = false;
let dragState = null;
let suppressNextClick = false;

function init() {
  const hostname = window.location.hostname;
  currentSite = Object.keys(SITE_CONFIG).find((site) => hostname.includes(site));

  if (!currentSite) {
    console.log("RePrompt: Unsupported site:", hostname);
    return;
  }

  loadSavedPosition().finally(() => {
    injectButton();
  });

  observer = new MutationObserver(() => {
    injectButton();
  });
  observer.observe(document.body, { childList: true, subtree: true, attributes: true });

  window.addEventListener("resize", onViewportChange);
}

function getBackendUrl() {
  return new Promise((resolve) => {
    chrome.storage.sync.get({ backendUrl: DEFAULT_BACKEND_URL }, (items) => {
      resolve((items.backendUrl || DEFAULT_BACKEND_URL).replace(/\/+$/, ""));
    });
  });
}

function loadSavedPosition() {
  return new Promise((resolve) => {
    chrome.storage.sync.get({ [BUTTON_POSITION_KEY]: {} }, (items) => {
      const positions = items[BUTTON_POSITION_KEY] || {};
      savedButtonPosition = positions[currentSite] || null;
      positionLoaded = true;
      resolve(savedButtonPosition);
    });
  });
}

function saveButtonPosition(position) {
  savedButtonPosition = clampPosition(position);

  chrome.storage.sync.get({ [BUTTON_POSITION_KEY]: {} }, (items) => {
    const positions = items[BUTTON_POSITION_KEY] || {};
    positions[currentSite] = savedButtonPosition;
    chrome.storage.sync.set({ [BUTTON_POSITION_KEY]: positions });
  });
}

function findTextarea() {
  const config = SITE_CONFIG[currentSite];
  if (!config) return null;

  if (
    document.activeElement &&
    config.textarea.some((selector) => document.activeElement.matches?.(selector)) &&
    isVisible(document.activeElement)
  ) {
    return document.activeElement;
  }

  for (const selector of config.textarea) {
    const elements = Array.from(document.querySelectorAll(selector));
    const visibleElement = elements.find((element) => isVisible(element));
    if (visibleElement) return visibleElement;
  }

  return null;
}

function isVisible(element) {
  if (!element) return false;

  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
}

function findComposer(textarea) {
  const config = SITE_CONFIG[currentSite];
  if (!config?.container || !textarea) return textarea?.parentElement || null;

  for (const selector of config.container) {
    const composer = textarea.closest(selector);
    if (composer) return composer;
  }

  return textarea.parentElement || null;
}

function distanceBetween(firstRect, secondRect) {
  const firstX = firstRect.left + firstRect.width / 2;
  const firstY = firstRect.top + firstRect.height / 2;
  const secondX = secondRect.left + secondRect.width / 2;
  const secondY = secondRect.top + secondRect.height / 2;
  return Math.hypot(firstX - secondX, firstY - secondY);
}

function findUploadAnchor(textarea) {
  const composer = findComposer(textarea);
  const config = SITE_CONFIG[currentSite];

  if (config?.upload) {
    const scopedCandidates = [];

    for (const selector of config.upload) {
      const matches = composer ? Array.from(composer.querySelectorAll(selector)) : [];
      scopedCandidates.push(...matches.filter((element) => isVisible(element)));
    }

    if (scopedCandidates.length > 0) {
      const textareaRect = textarea.getBoundingClientRect();
      return scopedCandidates.sort((a, b) => {
        return (
          distanceBetween(a.getBoundingClientRect(), textareaRect) -
          distanceBetween(b.getBoundingClientRect(), textareaRect)
        );
      })[0];
    }
  }

  return textarea?.parentElement || textarea;
}

function getDefaultButtonPosition() {
  const textarea = findTextarea();
  if (!textarea) {
    return clampPosition({
      left: window.innerWidth - 92,
      top: window.innerHeight - 140,
    });
  }

  const placement = SITE_CONFIG[currentSite]?.placement || { x: -4, y: -52 };
  const anchor = findUploadAnchor(textarea);
  const anchorRect = anchor?.getBoundingClientRect();
  const textareaRect = textarea.getBoundingClientRect();

  if (anchorRect && anchorRect.width > 0 && anchorRect.height > 0) {
    return clampPosition({
      left: anchorRect.left + anchorRect.width / 2 - 24 + placement.x,
      top: anchorRect.top + placement.y,
    });
  }

  return clampPosition({
    left: textareaRect.right - 56,
    top: textareaRect.bottom - 56,
  });
}

function clampPosition(position) {
  const buttonSize = 48;
  const margin = 12;
  const maxLeft = Math.max(margin, window.innerWidth - buttonSize - margin);
  const maxTop = Math.max(margin, window.innerHeight - buttonSize - margin);

  return {
    left: Math.min(Math.max(margin, Math.round(position.left)), maxLeft),
    top: Math.min(Math.max(margin, Math.round(position.top)), maxTop),
  };
}

function applyButtonPosition(position) {
  if (!enhanceButton) return;

  const clamped = clampPosition(position);
  enhanceButton.style.left = `${clamped.left}px`;
  enhanceButton.style.top = `${clamped.top}px`;
  positionIntentBadge();
}

function positionIntentBadge() {
  if (!enhanceButton || !intentBadge || intentBadge.style.display === "none") return;

  const rect = enhanceButton.getBoundingClientRect();
  const badgeRect = intentBadge.getBoundingClientRect();
  const left = Math.max(12, rect.left + rect.width / 2 - badgeRect.width / 2);
  const top = Math.max(12, rect.top - badgeRect.height - 10);

  intentBadge.style.left = `${left}px`;
  intentBadge.style.top = `${top}px`;
}

function injectButton() {
  const textarea = findTextarea();
  if (!textarea || !positionLoaded) {
    removeButton();
    return;
  }

  if (!enhanceButton || !document.contains(enhanceButton)) {
    removeButton();

    enhanceButton = document.createElement("button");
    enhanceButton.className = "reprompt-btn";
    enhanceButton.type = "button";
    enhanceButton.title = "RePrompt: Enhance this prompt";
    enhanceButton.setAttribute("aria-label", "RePrompt: Enhance this prompt");
    enhanceButton.dataset.status = "ready";
    enhanceButton.innerHTML = `
      <img class="reprompt-btn__logo" src="${LOGO_URL}" alt="RePrompt" draggable="false" />
      <span class="reprompt-btn__status" aria-hidden="true"></span>
    `;
    enhanceButton.addEventListener("click", onEnhance);
    enhanceButton.addEventListener("pointerdown", onDragStart);
    document.body.appendChild(enhanceButton);

    intentBadge = document.createElement("div");
    intentBadge.className = "reprompt-badge";
    intentBadge.style.display = "none";
    document.body.appendChild(intentBadge);

    applyButtonPosition(savedButtonPosition || getDefaultButtonPosition());
  } else if (!savedButtonPosition && !dragState) {
    applyButtonPosition(getDefaultButtonPosition());
  } else if (savedButtonPosition && !dragState) {
    applyButtonPosition(savedButtonPosition);
  }
}

function removeButton() {
  if (enhanceButton?.parentElement) {
    enhanceButton.removeEventListener("click", onEnhance);
    enhanceButton.removeEventListener("pointerdown", onDragStart);
    enhanceButton.remove();
  }

  if (intentBadge?.parentElement) {
    intentBadge.remove();
  }

  enhanceButton = null;
  intentBadge = null;
}

function onDragStart(event) {
  if (!enhanceButton || event.button !== 0) return;
  event.preventDefault();

  const rect = enhanceButton.getBoundingClientRect();
  dragState = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    startLeft: rect.left,
    startTop: rect.top,
    moved: false,
  };

  enhanceButton.setPointerCapture(event.pointerId);
  enhanceButton.addEventListener("pointermove", onDragMove);
  enhanceButton.addEventListener("pointerup", onDragEnd);
  enhanceButton.addEventListener("pointercancel", onDragEnd);
}

function onDragMove(event) {
  if (!dragState || event.pointerId !== dragState.pointerId) return;

  const deltaX = event.clientX - dragState.startX;
  const deltaY = event.clientY - dragState.startY;

  if (!dragState.moved && Math.hypot(deltaX, deltaY) >= DRAG_THRESHOLD) {
    dragState.moved = true;
    enhanceButton.classList.add("reprompt-btn--dragging");
  }

  if (!dragState.moved) return;

  event.preventDefault();
  applyButtonPosition({
    left: dragState.startLeft + deltaX,
    top: dragState.startTop + deltaY,
  });
}

function onDragEnd(event) {
  if (!dragState || event.pointerId !== dragState.pointerId) return;

  if (enhanceButton) {
    enhanceButton.releasePointerCapture?.(event.pointerId);
    enhanceButton.removeEventListener("pointermove", onDragMove);
    enhanceButton.removeEventListener("pointerup", onDragEnd);
    enhanceButton.removeEventListener("pointercancel", onDragEnd);
    enhanceButton.classList.remove("reprompt-btn--dragging");
  }

  if (dragState.moved && enhanceButton) {
    const rect = enhanceButton.getBoundingClientRect();
    saveButtonPosition({ left: rect.left, top: rect.top });
    suppressNextClick = true;
    setTimeout(() => {
      suppressNextClick = false;
    }, 0);
  }

  dragState = null;
}

function onViewportChange() {
  if (!enhanceButton) return;

  const rect = enhanceButton.getBoundingClientRect();
  const nextPosition = clampPosition({ left: rect.left, top: rect.top });
  applyButtonPosition(nextPosition);

  if (savedButtonPosition) {
    saveButtonPosition(nextPosition);
  }
}

function getSelectedText(element) {
  if (element.tagName === "TEXTAREA" || element.tagName === "INPUT") {
    if (element.selectionStart === element.selectionEnd) return "";
    return element.value.substring(element.selectionStart, element.selectionEnd);
  }

  const selection = window.getSelection();
  if (!selection.rangeCount || selection.isCollapsed) return "";
  if (!element.contains(selection.anchorNode) || !element.contains(selection.focusNode)) return "";

  return selection.toString();
}

function replaceSelectedText(element, replacement) {
  if (element.tagName === "TEXTAREA" || element.tagName === "INPUT") {
    const start = element.selectionStart;
    const end = element.selectionEnd;
    element.value = element.value.substring(0, start) + replacement + element.value.substring(end);
    element.selectionStart = start;
    element.selectionEnd = start + replacement.length;
  } else {
    const selection = window.getSelection();
    if (!selection.rangeCount) return;
    const range = selection.getRangeAt(0);
    range.deleteContents();
    range.insertNode(document.createTextNode(replacement));
  }

  element.dispatchEvent(new Event("input", { bubbles: true }));
}

async function onEnhance(event) {
  if (suppressNextClick) {
    event.preventDefault();
    return;
  }

  const textarea = findTextarea();
  if (!textarea) return;

  const fullText = getText(textarea);
  if (!fullText.trim()) return;

  const selectedText = getSelectedText(textarea);
  const query = selectedText || fullText;
  const isSelection = !!(selectedText && selectedText !== fullText);

  setButtonState("loading");

  try {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/enhance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const result = await response.json();
    const enhanced = result.enhanced || result.cleaned;

    if (isSelection) {
      replaceSelectedText(textarea, enhanced);
    } else {
      setText(textarea, enhanced);
    }

    setButtonState("done");
    showIntent(result.intent, result.confidence);
  } catch (error) {
    console.error("RePrompt: Enhancement failed", error);
    setButtonState("error");
    showToast(`RePrompt: ${error.message}`);
    setTimeout(() => setButtonState("ready"), 3000);
  }
}

function getText(element) {
  if (element.tagName === "TEXTAREA" || element.tagName === "INPUT") {
    return element.value;
  }

  return element.textContent || "";
}

function setText(element, text) {
  if (element.tagName === "TEXTAREA" || element.tagName === "INPUT") {
    element.value = text;
  } else {
    element.textContent = text;
  }

  element.dispatchEvent(new Event("input", { bubbles: true }));
}

function setButtonState(state) {
  if (!enhanceButton) return;

  enhanceButton.className = "reprompt-btn";
  enhanceButton.dataset.status = state;

  switch (state) {
    case "loading":
      enhanceButton.classList.add("reprompt-btn--loading");
      enhanceButton.disabled = true;
      break;
    case "done":
      enhanceButton.classList.add("reprompt-btn--done");
      enhanceButton.disabled = false;
      setTimeout(() => setButtonState("ready"), 1500);
      break;
    case "error":
      enhanceButton.classList.add("reprompt-btn--error");
      enhanceButton.disabled = false;
      break;
    default:
      enhanceButton.dataset.status = "ready";
      enhanceButton.disabled = false;
  }
}

function showIntent(intent, confidence) {
  if (!intentBadge) return;

  const labels = {
    general_qa: "General Q&A",
    coding: "Coding",
    creative_writing: "Creative Writing",
    email: "Email",
    summarization: "Summarization",
    learning: "Learning / Explanation",
    planning: "Planning",
  };

  intentBadge.textContent = `${labels[intent] || intent} - ${(confidence * 100).toFixed(0)}%`;
  intentBadge.style.display = "inline-block";
  intentBadge.className = "reprompt-badge reprompt-badge--visible";
  positionIntentBadge();

  setTimeout(() => {
    if (!intentBadge) return;
    intentBadge.classList.remove("reprompt-badge--visible");
    setTimeout(() => {
      if (intentBadge) intentBadge.style.display = "none";
    }, 300);
  }, 3000);
}

function showToast(message) {
  let toast = document.querySelector(".reprompt-toast");

  if (!toast) {
    toast = document.createElement("div");
    toast.className = "reprompt-toast";
    document.body.appendChild(toast);
  }

  toast.textContent = message;
  toast.classList.add("reprompt-toast--visible");

  setTimeout(() => {
    toast.classList.remove("reprompt-toast--visible");
  }, 4000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
