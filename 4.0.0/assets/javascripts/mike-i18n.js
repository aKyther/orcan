/* Keep Material language switcher inside the current mike version prefix.
 *
 * Nested pages already use relative hreflang links (OK under /latest/...).
 * Homepages often use absolute /orcan/ and /orcan/pl/ which skip the version.
 */
(function () {
  function versionRoot(pathname) {
    const match = pathname.match(/^(.*?)\/(latest|dev|\d+\.\d+\.\d+)(?=\/|$)/);
    if (!match) {
      return null;
    }
    return match[1] + "/" + match[2];
  }

  function rewrite(href, root) {
    if (!href || href.startsWith("#") || href.startsWith("mailto:")) {
      return href;
    }
    // Absolute site paths without a version segment.
    if (href === "/orcan" || href === "/orcan/") {
      return root + "/";
    }
    if (href.startsWith("/orcan/pl")) {
      return root + href.slice("/orcan".length);
    }
    if (
      href.startsWith("/orcan/") &&
      !/^\/orcan\/(latest|dev|\d+\.\d+\.\d+)(\/|$)/.test(href)
    ) {
      return root + href.slice("/orcan".length);
    }
    return href;
  }

  function fix() {
    const root = versionRoot(location.pathname);
    if (!root) {
      return;
    }
    document.querySelectorAll("a[hreflang], link[hreflang]").forEach(function (el) {
      const href = el.getAttribute("href");
      const next = rewrite(href, root);
      if (next && next !== href) {
        el.setAttribute("href", next);
      }
    });
  }

  if (typeof document$ !== "undefined" && document$.subscribe) {
    document$.subscribe(fix);
  } else {
    document.addEventListener("DOMContentLoaded", fix);
  }
})();
