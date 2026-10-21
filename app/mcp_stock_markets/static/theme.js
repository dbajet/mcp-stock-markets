"use strict";

// A file of its own because the CSP allows no inline script.
// Loaded in <head> without defer, before the stylesheet: data-theme is on <html>
// before the first paint, so a dark theme never shows a light first frame.
(function themed() {
  const key = "mcp_stock_markets-theme";
  const choices = ["system", "light", "dark"];
  const colors = { light: "#f6f7f9", dark: "#11151b" };
  const media = window.matchMedia("(prefers-color-scheme: dark)");

  function choice() {
    let saved = null;
    try {
      saved = localStorage.getItem(key);
    } catch (error) {
      saved = null;
    }
    return choices.includes(saved) ? saved : "system";
  }

  function applied() {
    const chosenTheme = choice();
    const theme = chosenTheme === "system" ? (media.matches ? "dark" : "light") : chosenTheme;
    document.documentElement.setAttribute("data-theme", theme);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta !== null) {
      meta.setAttribute("content", colors[theme]);
    }
    return theme;
  }

  function chosen(value) {
    try {
      if (value === "system") {
        localStorage.removeItem(key);
      } else {
        localStorage.setItem(key, value);
      }
    } catch (error) {
      // Private windows may refuse storage: the theme still applies to this page.
    }
    applied();
    document.dispatchEvent(new CustomEvent("themechange"));
  }

  applied();
  media.addEventListener("change", () => {
    if (choice() === "system") {
      applied();
      document.dispatchEvent(new CustomEvent("themechange"));
    }
  });
  window.Theme = { applied };

  document.addEventListener("DOMContentLoaded", () => {
    const button = document.querySelector("#theme-toggle");
    if (button === null) {
      return;
    }
    button.addEventListener("click", () => {
      chosen(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });
  });
})();
