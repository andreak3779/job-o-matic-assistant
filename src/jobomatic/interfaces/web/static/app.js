// Shows a failed partial update instead of leaving the page looking unchanged (ADR 0025).
// htmx swaps a 2xx or 3xx reply and a 400 (the row with its message); any other error, and a request
// that never reached the server, comes here. Text only (textContent), never markup.
(function () {
  "use strict";

  function show(text) {
    var box = document.getElementById("request-error");
    if (!box) { return; }
    box.textContent = text;
    box.hidden = false;
    box.scrollIntoView({ block: "nearest" });
  }

  // The server's own error page says why in its first heading and paragraph; use them.
  function reasonFrom(xhr) {
    try {
      var doc = new DOMParser().parseFromString(xhr.responseText || "", "text/html");
      var title = doc.querySelector("main h1");
      var text = doc.querySelector("main h1 + p");
      if (title && text) { return title.textContent + ". " + text.textContent; }
    } catch (ignored) { /* fall through to the generic text */ }
    return "";
  }

  document.addEventListener("htmx:responseError", function (event) {
    var xhr = event.detail.xhr;
    show(reasonFrom(xhr) || "That did not work (the server answered " + xhr.status + "). Reload the page and try again.");
  });

  document.addEventListener("htmx:sendError", function () {
    show("Could not reach the server. Is jobo web still running in the terminal?");
  });

  document.addEventListener("htmx:beforeRequest", function () {
    var box = document.getElementById("request-error");
    if (box) { box.hidden = true; }
  });
})();
