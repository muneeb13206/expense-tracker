/* transaction_form.js - shows the Category field for expenses
   and the Source field for income. */
(function () {
  var radios = document.querySelectorAll('input[name="type"]');
  var groups = document.querySelectorAll("[data-show-for]");

  function update() {
    var checked = document.querySelector('input[name="type"]:checked');
    var type = checked ? checked.value : "expense";

    groups.forEach(function (group) {
      var hide = group.getAttribute("data-show-for") !== type;
      group.classList.toggle("hidden", hide);
      // Hidden fields are disabled (not submitted, not validated)
      group.querySelectorAll("input, select").forEach(function (el) {
        el.disabled = hide;
        el.required = !hide;
      });
    });
  }

  radios.forEach(function (r) { r.addEventListener("change", update); });
  update();
})();