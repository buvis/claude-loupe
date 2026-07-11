function renderStatic(el) {
  el.innerHTML = "<p>static</p>";
}

function renderSafe(el, text) {
  el.textContent = text;
}
