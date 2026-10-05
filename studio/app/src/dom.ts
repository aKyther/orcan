export function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> = {}, ...children: (Node | string)[]): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

export function radioValue(name: string): string {
  return document.querySelector<HTMLInputElement>(`input[name="${name}"]:checked`)!.value;
}

export function setRadio(name: string, value: string): void {
  for (const input of document.querySelectorAll<HTMLInputElement>(`input[name="${name}"]`)) input.checked = input.value === value;
}

export function actionButton(text: string, onClick: () => void, className = "secondary"): HTMLButtonElement {
  const button = el("button", { type: "button", className, textContent: text });
  button.addEventListener("click", onClick);
  return button;
}

export function emptyState(text: string, action: string, onClick: () => void): HTMLElement {
  return el("div", { className: "empty-state" }, el("p", { textContent: text }), actionButton(action, onClick, ""));
}

export function listItem(title: string, detail: string, ...actions: HTMLElement[]): HTMLElement {
  return el("div", { className: "list-item" }, el("div", {}, el("strong", { textContent: title }), el("span", { textContent: detail })), ...actions);
}
