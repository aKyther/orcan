/** Connection geometry owns its frame scheduling; selection never rebuilds cards. */
export function createMapConnections(canvas: HTMLElement, sources: HTMLElement, targets: HTMLElement,
  background: SVGSVGElement, foreground: SVGSVGElement,
  selection: () => { path?: string; workspace?: string }) {
  let frame: number | undefined;
  let edges: Array<{ line: SVGPathElement; path: string; workspace?: string; state: string }> = [];

  function highlight() {
    const selected = selection();
    for (const chip of canvas.querySelectorAll<HTMLElement>(".project-chip[data-project-path]")) {
      chip.classList.toggle("traced", selected.path === chip.dataset.projectPath);
      chip.classList.toggle("dimmed", Boolean(selected.path) && selected.path !== chip.dataset.projectPath);
    }
    for (const edge of edges) {
      const active = selected.path === edge.path || (Boolean(selected.workspace) && selected.workspace === edge.workspace);
      edge.line.setAttribute("class", `context-link ${edge.state} ${active ? "highlight" : "muted"}`);
      const layer = active ? foreground : background;
      if (edge.line.parentNode !== layer) layer.append(edge.line);
    }
  }

  function draw() {
    const bounds = canvas.getBoundingClientRect();
    background.replaceChildren();
    foreground.replaceChildren();
    edges = [];
    for (const layer of [background, foreground]) layer.setAttribute("viewBox", `0 0 ${bounds.width} ${bounds.height}`);
    const byPath = new Map<string, HTMLElement[]>();
    for (const target of targets.querySelectorAll<HTMLElement>(".project-chip[data-project-path]")) {
      const path = target.dataset.projectPath!;
      const entries = byPath.get(path) ?? [];
      entries.push(target);
      byPath.set(path, entries);
    }
    const horizontal = window.matchMedia("(min-width: 761px)").matches;
    for (const source of sources.querySelectorAll<HTMLElement>(".project-chip[data-project-path]")) {
      const sourceBox = source.querySelector<HTMLElement>(".connection-anchor")?.getBoundingClientRect();
      if (!sourceBox?.width || !sourceBox.height) continue;
      const path = source.dataset.projectPath!;
      for (const target of byPath.get(path) ?? []) {
        const targetBox = target.querySelector<HTMLElement>(".connection-anchor")?.getBoundingClientRect();
        if (!targetBox?.width || !targetBox.height) continue;
        const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
        line.setAttribute("data-project-path", path);
        line.setAttribute("data-workspace", target.dataset.workspace ?? "");
        const startX = sourceBox.left - bounds.left + sourceBox.width / 2;
        const startY = sourceBox.top - bounds.top + sourceBox.height / 2;
        const endX = targetBox.left - bounds.left + targetBox.width / 2;
        const endY = targetBox.top - bounds.top + targetBox.height / 2;
        const middleX = (startX + endX) / 2, middleY = (startY + endY) / 2;
        line.setAttribute("d", horizontal
          ? `M ${startX} ${startY} C ${middleX} ${startY}, ${middleX} ${endY}, ${endX} ${endY}`
          : `M ${startX} ${startY} C ${startX} ${middleY}, ${endX} ${middleY}, ${endX} ${endY}`);
        edges.push({ line, path, workspace: target.dataset.workspace, state: target.dataset.connectionState ?? "current" });
      }
    }
    highlight();
  }

  function schedule() {
    if (frame !== undefined) return;
    frame = requestAnimationFrame(() => { frame = undefined; draw(); });
  }
  // Collapsing groups changes anchors without a window resize.
  canvas.addEventListener("toggle", schedule, true);
  return { schedule, highlight };
}
