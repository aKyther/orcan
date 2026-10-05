/*
 * Docs version switcher — works on mike-deployed Pages and on plain
 * `mkdocs serve` (fetches published versions.json when local has none).
 * Hides Material’s native .md-version (see CSS) so one control can jump
 * to e.g. 2.0.0 / latest / dev.
 */
(function () {
  var DOCS_ROOT = "https://akyther.github.io/orcan";
  var VERSION_RE = /^(latest|dev|\d+\.\d+\.\d+)$/;

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function currentAliasFromPath() {
    var parts = location.pathname.split("/").filter(Boolean);
    var i = parts.indexOf("orcan");
    if (i >= 0 && parts[i + 1] && VERSION_RE.test(parts[i + 1])) {
      return parts[i + 1];
    }
    return null;
  }

  function pageSuffix() {
    var parts = location.pathname.split("/").filter(Boolean);
    var i = parts.indexOf("orcan");
    if (i >= 0 && parts[i + 1] && VERSION_RE.test(parts[i + 1])) {
      return parts.slice(i + 2).join("/");
    }
    return parts.join("/");
  }

  function labelFor(entries, alias) {
    if (!alias) {
      return "latest";
    }
    if (alias === "latest" || alias === "dev") {
      return alias;
    }
    var hit = entries.find(function (e) {
      return e.version === alias || (e.aliases && e.aliases.indexOf(alias) !== -1);
    });
    return hit ? hit.title || hit.version : alias;
  }

  function hrefFor(version, suffix) {
    var path = suffix ? "/" + suffix.replace(/^\/+/, "") : "/";
    if (!path.endsWith("/")) {
      path += "/";
    }
    return DOCS_ROOT + "/" + version + path;
  }

  function close(root) {
    var btn = $(".orcan-version-select__current", root);
    var list = $(".orcan-version-select__list", root);
    if (!btn || !list) {
      return;
    }
    btn.setAttribute("aria-expanded", "false");
    list.hidden = true;
    root.classList.remove("orcan-version-select--open");
  }

  function open(root) {
    var btn = $(".orcan-version-select__current", root);
    var list = $(".orcan-version-select__list", root);
    if (!btn || !list) {
      return;
    }
    btn.setAttribute("aria-expanded", "true");
    list.hidden = false;
    root.classList.add("orcan-version-select--open");
  }

  function toggle(root) {
    var list = $(".orcan-version-select__list", root);
    if (!list) {
      return;
    }
    if (list.hidden) {
      open(root);
    } else {
      close(root);
    }
  }

  function render(root, entries) {
    var btn = $(".orcan-version-select__current", root);
    var label = $(".orcan-version-select__label", root);
    var list = $(".orcan-version-select__list", root);
    if (!btn || !label || !list) {
      return;
    }

    var alias = currentAliasFromPath();
    var suffix = pageSuffix();
    label.textContent = labelFor(entries, alias);

    list.innerHTML = "";

    function addItem(version, text, isActive) {
      var li = document.createElement("li");
      li.className = "orcan-version-select__item";
      li.setAttribute("role", "option");
      if (isActive) {
        li.setAttribute("aria-selected", "true");
      }
      var a = document.createElement("a");
      a.className = "orcan-version-select__link";
      if (isActive) {
        a.classList.add("orcan-version-select__link--active");
      }
      a.href = hrefFor(version, suffix);
      a.textContent = text;
      li.appendChild(a);
      list.appendChild(li);
    }

    var hasLatest = entries.some(function (e) {
      return e.aliases && e.aliases.indexOf("latest") !== -1;
    });
    if (hasLatest) {
      addItem("latest", "latest", alias === "latest" || alias === null);
    }

    entries.forEach(function (entry) {
      var active =
        entry.version === alias ||
        (entry.aliases && alias && entry.aliases.indexOf(alias) !== -1 && alias !== "latest");
      // When browsing /latest/, highlight SemVer row too if it owns the alias
      if (alias === "latest" && entry.aliases && entry.aliases.indexOf("latest") !== -1) {
        active = false;
      }
      addItem(entry.version, entry.title || entry.version, !!active);
    });

    btn.onclick = function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      toggle(root);
    };

    if (!root.dataset.orcanBound) {
      root.dataset.orcanBound = "1";
      document.addEventListener("click", function (ev) {
        if (!root.contains(ev.target)) {
          close(root);
        }
      });
      document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") {
          close(root);
        }
      });
    }
  }

  function fetchJson(url) {
    return fetch(url, { credentials: "omit" }).then(function (res) {
      if (!res.ok) {
        throw new Error(String(res.status));
      }
      return res.json();
    });
  }

  function loadEntries() {
    var candidates = [];
    try {
      candidates.push(new URL("../versions.json", location.href).href);
      candidates.push(new URL("../../versions.json", location.href).href);
    } catch (e) {
      /* ignore */
    }
    candidates.push(DOCS_ROOT + "/versions.json");

    var chain = Promise.reject(new Error("start"));
    candidates.forEach(function (url) {
      chain = chain.catch(function () {
        return fetchJson(url);
      });
    });
    return chain;
  }

  function mount() {
    var root = $(".orcan-version-select");
    if (!root) {
      return;
    }
    document.documentElement.classList.add("orcan-owns-version-select");
    loadEntries()
      .then(function (entries) {
        if (!Array.isArray(entries) || !entries.length) {
          throw new Error("empty");
        }
        render(root, entries);
        root.hidden = false;
      })
      .catch(function () {
        var label = $(".orcan-version-select__label", root);
        if (label) {
          label.textContent = "versions";
        }
        root.hidden = false;
        var list = $(".orcan-version-select__list", root);
        var btn = $(".orcan-version-select__current", root);
        if (list) {
          list.innerHTML =
            '<li class="orcan-version-select__item"><a class="orcan-version-select__link" href="' +
            DOCS_ROOT +
            '/latest/">latest (Pages)</a></li>' +
            '<li class="orcan-version-select__item"><a class="orcan-version-select__link" href="' +
            DOCS_ROOT +
            '/2.0.0/">2.0.0</a></li>';
        }
        if (btn) {
          btn.onclick = function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            toggle(root);
          };
        }
      });
  }

  if (typeof document$ !== "undefined" && document$.subscribe) {
    document$.subscribe(mount);
  } else {
    document.addEventListener("DOMContentLoaded", mount);
  }
})();
