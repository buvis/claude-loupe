function renderStatic(el: HTMLElement): void {
  el.innerHTML = "<p>static</p>";
}

function renderSafe(el: HTMLElement, text: string): void {
  el.textContent = text;
}
