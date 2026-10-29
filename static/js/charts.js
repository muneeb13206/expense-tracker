/* charts.js - draws every <canvas data-chart="..." data-url="..."> on the page.
   The data comes from the Flask JSON routes (/api/charts/...), which read the database.
   Supported types: doughnut, bar, line. Charts are redrawn when the theme changes. */
(function () {
  var canvases = document.querySelectorAll("canvas[data-chart]");
  if (!canvases.length) { return; }

  var RUPEE = "\u20B9";
  var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
  var compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

  // The same colour for the same category on every chart
  var CATEGORY_COLORS = {
    Food: "#f59e0b", Transport: "#3b82f6", Education: "#8b5cf6", Shopping: "#ec4899",
    Healthcare: "#ef4444", Entertainment: "#14b8a6", Bills: "#64748b", Other: "#a3a3a3"
  };

  var items = [];   // { canvas, kind, data, chart }

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function showMessage(canvas, text) {
    var box = canvas.parentNode;
    box.innerHTML = "";
    var p = document.createElement("p");
    p.className = "chart-empty";
    p.textContent = text;
    box.appendChild(p);
  }

  function baseOptions() {
    return { responsive: true, maintainAspectRatio: false };
  }

  function axisOptions() {
    return {
      x: { ticks: { color: css("--muted") }, grid: { display: false } },
      y: {
        beginAtZero: true,
        ticks: { color: css("--muted"), callback: function (v) { return RUPEE + compact.format(v); } },
        grid: { color: css("--border") }
      }
    };
  }

  function moneyTooltip() {
    return {
      callbacks: {
        label: function (ctx) { return " " + ctx.dataset.label + ": " + money.format(ctx.parsed.y); }
      }
    };
  }

  function buildConfig(kind, d) {
    var text = css("--text");

    if (kind === "doughnut") {
      return {
        type: "doughnut",
        data: {
          labels: d.labels,
          datasets: [{
            data: d.values,
            backgroundColor: d.labels.map(function (l) { return CATEGORY_COLORS[l] || "#94a3b8"; }),
            borderColor: css("--surface"),
            borderWidth: 2
          }]
        },
        options: Object.assign(baseOptions(), {
          cutout: "62%",
          plugins: {
            legend: { position: "bottom", labels: { color: text, boxWidth: 12 } },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  return " " + ctx.label + ": " + money.format(ctx.parsed) +
                         " (" + d.percents[ctx.dataIndex] + "%)";
                }
              }
            }
          }
        })
      };
    }

    if (kind === "bar") {
      return {
        type: "bar",
        data: {
          labels: d.labels,
          datasets: [
            { label: "Income", data: d.income, backgroundColor: "#16a34a", borderRadius: 6 },
            { label: "Expenses", data: d.expense, backgroundColor: "#dc2626", borderRadius: 6 }
          ]
        },
        options: Object.assign(baseOptions(), {
          scales: axisOptions(),
          plugins: { legend: { labels: { color: text } }, tooltip: moneyTooltip() }
        })
      };
    }

    // line
    return {
      type: "line",
      data: {
        labels: d.labels,
        datasets: [{
          label: "Expenses", data: d.expense, borderColor: "#4f46e5",
          backgroundColor: "rgba(79,70,229,.15)", fill: true, tension: 0.3,
          pointRadius: 4, pointBackgroundColor: "#4f46e5"
        }]
      },
      options: Object.assign(baseOptions(), {
        scales: axisOptions(),
        plugins: { legend: { display: false }, tooltip: moneyTooltip() }
      })
    };
  }

  function isEmpty(kind, d) {
    if (kind === "doughnut") { return !d.values.length; }
    var all = (d.income || []).concat(d.expense || []);
    return !all.some(function (v) { return v > 0; });
  }

  function emptyText(kind) {
    return kind === "doughnut" ? "No expenses in this period yet." : "No transactions in these months yet.";
  }

  function draw(item) {
    if (item.chart) { item.chart.destroy(); }
    item.chart = new Chart(item.canvas, buildConfig(item.kind, item.data));
  }

  // If the Chart.js library could not load (for example, no internet), say so
  if (typeof Chart === "undefined") {
    canvases.forEach(function (c) {
      showMessage(c, "Charts could not load. Check your internet connection and refresh.");
    });
    return;
  }

  canvases.forEach(function (canvas) {
    var kind = canvas.getAttribute("data-chart");
    fetch(canvas.getAttribute("data-url"), { headers: { "Accept": "application/json" } })
      .then(function (r) {
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
      })
      .then(function (data) {
        if (isEmpty(kind, data)) { showMessage(canvas, emptyText(kind)); return; }
        var item = { canvas: canvas, kind: kind, data: data, chart: null };
        items.push(item);
        draw(item);
      })
      .catch(function () { showMessage(canvas, "Could not load chart data."); });
  });

  // main.js announces theme changes: redraw so colours match light/dark mode
  document.addEventListener("themechange", function () {
    items.forEach(draw);
  });
})();