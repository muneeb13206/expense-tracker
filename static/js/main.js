/* main.js - behaviour shared by every page: dark mode, mobile menu, confirm dialogs */
(function () {
  var root = document.documentElement;
  var themeBtn = document.getElementById("themeBtn");
  var menuBtn = document.getElementById("menuBtn");
  var sidebar = document.getElementById("sidebar");

  function updateThemeIcon() {
    var dark = root.getAttribute("data-theme") === "dark";
    themeBtn.innerHTML = dark
      ? '<i class="fa-solid fa-sun"></i>'
      : '<i class="fa-solid fa-moon"></i>';
  }

  themeBtn.addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
    updateThemeIcon();
  });

  menuBtn.addEventListener("click", function () {
    sidebar.classList.toggle("open");
  });

  /* Any <form data-confirm="Are you sure?"> asks before submitting */
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  updateThemeIcon();
})();