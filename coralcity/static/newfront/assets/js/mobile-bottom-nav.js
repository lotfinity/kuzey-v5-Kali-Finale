(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var nav = document.getElementById("mobileBottomNav");
    var trigger = document.getElementById("mobileBottomNavTrigger");

    if (!nav || !trigger) {
      return;
    }

    var AUTO_CLOSE_DELAY = 5000;
    var autoCloseTimer = null;

    document.body.classList.add("has-mobile-bottom-nav");

    function setExpanded(expanded) {
      nav.classList.toggle("is-expanded", expanded);
      trigger.setAttribute("aria-expanded", expanded ? "true" : "false");

      window.clearTimeout(autoCloseTimer);
      autoCloseTimer = null;

      if (expanded) {
        autoCloseTimer = window.setTimeout(function () {
          setExpanded(false);
        }, AUTO_CLOSE_DELAY);
      }
    }

    function refreshAutoClose() {
      if (!nav.classList.contains("is-expanded")) {
        return;
      }

      window.clearTimeout(autoCloseTimer);
      autoCloseTimer = window.setTimeout(function () {
        setExpanded(false);
      }, AUTO_CLOSE_DELAY);
    }

    trigger.addEventListener("click", function (event) {
      event.stopPropagation();
      setExpanded(!nav.classList.contains("is-expanded"));
    });

    nav.addEventListener("pointerdown", refreshAutoClose);
    nav.addEventListener("keydown", refreshAutoClose);

    nav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        setExpanded(false);
      });
    });

    document.addEventListener("click", function (event) {
      if (!nav.contains(event.target)) {
        setExpanded(false);
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("is-expanded")) {
        setExpanded(false);
        trigger.focus();
      }
    });

    window.addEventListener("pagehide", function () {
      window.clearTimeout(autoCloseTimer);
    });
  });
})();
