function render(el, userContent) {
  el.innerHTML = userContent;
}

function renderTemplate(el, name) {
  el.innerHTML = `<b>${name}</b>`;
}
