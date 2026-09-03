/*
 * Mermaid theme aligned with Orcan navy/cyan palette.
 * Only adjusts themeVariables; does not change securityLevel or re-parse
 * diagrams Material already rendered.
 */
(function () {
  function scheme() {
    return document.body.getAttribute("data-md-color-scheme") || "default";
  }

  function themeVariables(isDark) {
    if (isDark) {
      return {
        darkMode: true,
        background: "#0d1520",
        primaryColor: "#164e63",
        primaryTextColor: "#c8d3e0",
        primaryBorderColor: "#5eead4",
        secondaryColor: "#111827",
        tertiaryColor: "#152033",
        lineColor: "#64748b",
        textColor: "#c8d3e0",
        mainBkg: "#111827",
        nodeBorder: "#5eead4",
        clusterBkg: "#0d1520",
        clusterBorder: "#334155",
        titleColor: "#67e8f9",
        edgeLabelBackground: "#0a0e17",
      };
    }
    return {
      darkMode: false,
      background: "#ffffff",
      primaryColor: "#ccfbf1",
      primaryTextColor: "#0f172a",
      primaryBorderColor: "#0f766e",
      secondaryColor: "#eef2f7",
      tertiaryColor: "#f8fafc",
      lineColor: "#64748b",
      textColor: "#0f172a",
      mainBkg: "#eef6f5",
      nodeBorder: "#0f766e",
      clusterBkg: "#f8fafc",
      clusterBorder: "#cbd5e1",
      titleColor: "#0f766e",
      edgeLabelBackground: "#ffffff",
    };
  }

  function apply() {
    if (typeof mermaid === "undefined" || typeof mermaid.initialize !== "function") {
      return;
    }
    var dark = scheme() === "slate";
    try {
      mermaid.initialize({
        startOnLoad: false,
        theme: dark ? "dark" : "default",
        themeVariables: themeVariables(dark),
      });
    } catch (e) {
      /* Material may lock config after first paint — ignore. */
    }
  }

  if (typeof document$ !== "undefined" && document$.subscribe) {
    document$.subscribe(apply);
  } else {
    document.addEventListener("DOMContentLoaded", apply);
  }
})();
