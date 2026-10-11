/** Connection geometry owns its frame scheduling; selection never rebuilds cards. */
export function createMapConnections(canvas: HTMLElement, sources: HTMLElement, targets: HTMLElement,
  background: SVGSVGElement, foreground: SVGSVGElement,
  selection: () => { path?: string; workspace?: string },
  measure: <T>(name: string, operation: () => T) => T = (_name, operation) => operation()) {
  let frame: number | undefined;
  let edges: Array<{ line: SVGPathElement; path: string; workspace?: string; state: string }> = [];
  let lines = new Map<string, SVGPathElement>();

  function highlight() {
    measure("map-selection", highlightContents);
  }

  function highlightContents() {
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
    measure("map-geometry", drawContents);
  }

  function drawContents() {
    const bounds = canvas.getBoundingClientRect();
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
    const next = new Map<string, SVGPathElement>();
    const occurrences = new Map<string, number>();
    const updates: Array<{ line: SVGPathElement; path: string; workspace: string; geometry: string }> = [];
    for (const source of sources.querySelectorAll<HTMLElement>(".project-chip[data-project-path]")) {
      const sourceBox = source.querySelector<HTMLElement>(".connection-anchor")?.getBoundingClientRect();
      if (!sourceBox?.width || !sourceBox.height) continue;
      const path = source.dataset.projectPath!;
      for (const target of byPath.get(path) ?? []) {
        const targetBox = target.querySelector<HTMLElement>(".connection-anchor")?.getBoundingClientRect();
        if (!targetBox?.width || !targetBox.height) continue;
        const identity = JSON.stringify([path, target.dataset.workspace ?? ""]);
        const occurrence = occurrences.get(identity) ?? 0;
        occurrences.set(identity, occurrence + 1);
        const key = `${identity}:${occurrence}`;
        const line = lines.get(key) ?? document.createElementNS("http://www.w3.org/2000/svg", "path");
        next.set(key, line);
        const startX = sourceBox.left - bounds.left + sourceBox.width / 2;
        const startY = sourceBox.top - bounds.top + sourceBox.height / 2;
        const endX = targetBox.left - bounds.left + targetBox.width / 2;
        const endY = targetBox.top - bounds.top + targetBox.height / 2;
        const middleX = (startX + endX) / 2, middleY = (startY + endY) / 2;
        const geometry = horizontal
          ? `M ${startX} ${startY} C ${middleX} ${startY}, ${middleX} ${endY}, ${endX} ${endY}`
          : `M ${startX} ${startY} C ${startX} ${middleY}, ${endX} ${middleY}, ${endX} ${endY}`;
        updates.push({ line, path, workspace: target.dataset.workspace ?? "", geometry });
        edges.push({ line, path, workspace: target.dataset.workspace, state: target.dataset.connectionState ?? "current" });
      }
    }
    // Measure every anchor before changing live SVG geometry.
    for (const { line, path, workspace, geometry } of updates) {
      line.setAttribute("data-project-path", path);
      line.setAttribute("data-workspace", workspace);
      line.setAttribute("d", geometry);
    }
    for (const [key, line] of lines) if (!next.has(key)) line.remove();
    lines = next;
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
