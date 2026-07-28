// Material's own automatic Mermaid initialization (via its bundled mermaid.run())
// was found to fail silently for diagrams on this site - the library itself
// works fine (confirmed via mermaid.render() directly), but Material's
// auto-init clears the source text and never inserts the rendered SVG.
// This renders diagrams explicitly instead, using the same direct API,
// and re-runs on every Material "instant navigation" page swap.

function waitForMermaid(callback, attempts) {
  attempts = attempts || 0;
  if (window.mermaid && window.mermaid.render) {
    callback();
  } else if (attempts < 40) {
    setTimeout(() => waitForMermaid(callback, attempts + 1), 250);
  }
}

let mermaidInitialized = false;
let renderCounter = 0;

function renderMermaidDiagrams() {
  const nodes = document.querySelectorAll(".mermaid-diagram:not([data-rendered])");
  if (!nodes.length) return;

  waitForMermaid(() => {
    if (!mermaidInitialized) {
      const isDark = document.body.getAttribute("data-md-color-scheme") === "slate";
      window.mermaid.initialize({
        startOnLoad: false,
        theme: isDark ? "dark" : "default",
        themeVariables: { primaryColor: "#6C5CE7" },
      });
      mermaidInitialized = true;
    }

    nodes.forEach((node) => {
      const source = node.textContent;
      node.setAttribute("data-rendered", "true");
      const id = "mermaid-diagram-" + renderCounter++;
      window.mermaid
        .render(id, source)
        .then(({ svg }) => {
          node.innerHTML = svg;
        })
        .catch((err) => {
          node.innerHTML =
            '<p style="color:#c0392b">Diagram failed to render: ' +
            String(err) +
            "</p>";
        });
    });
  });
}

if (window.document$) {
  // Material's RxJS observable that fires on every page view, including
  // instant-navigation swaps that don't trigger a full page load.
  document$.subscribe(renderMermaidDiagrams);
} else {
  document.addEventListener("DOMContentLoaded", renderMermaidDiagrams);
}
