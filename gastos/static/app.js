// Ang Gastos! The pages work without JavaScript; this file only adds extras.
"use strict";

// ---------- Light / dark theme ----------
// With no saved choice, the page follows the system setting (CSS does that).
// Pressing the button saves the opposite of what is showing now.

function currentTheme() {
  const saved = document.documentElement.dataset.theme;
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function updateThemeButton(button) {
  const next = currentTheme() === "dark" ? "light" : "dark";
  button.setAttribute("aria-label", `Switch to ${next} theme`);
}

function setUpThemeToggle() {
  const button = document.getElementById("theme-toggle");
  if (!button) return;
  updateThemeButton(button);
  button.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch (e) {
      // Private windows can block storage; the theme still changes for this page.
    }
    updateThemeButton(button);
    document.dispatchEvent(new Event("themechange"));
  });
}

// ---------- "Are you sure?" before deleting ----------
// A form with data-confirm="Question?" asks first. Without JavaScript it just sends.

function setUpConfirms() {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
}

// ---------- Charts ----------
// Each <figure class="chart" data-chart="columns|line"> holds a <canvas> and its
// data as JSON: {labels, titles, series: [{name, color (a CSS variable), values}]}.
// Values are centavos. The same numbers are in the figure's table, so nothing
// is lost if Chart.js doesn't load.

const pesoFull = new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" });
const pesoShort = new Intl.NumberFormat("en-PH", {
  style: "currency", currency: "PHP", notation: "compact", maximumFractionDigits: 1,
});
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const drawnCharts = [];

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// "#2a78d6" -> "rgba(42, 120, 214, 0.75)", for the lighter look of a hovered bar.
function withAlpha(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function chartTheme() {
  return {
    ink: cssVar("--ink"),
    soft: cssVar("--ink-soft"),
    grid: cssVar("--chart-grid"),
    axis: cssVar("--chart-axis"),
    surface: cssVar("--card"),
    font: getComputedStyle(document.body).fontFamily,
  };
}

// Chart.js has no crosshair, so this small plugin draws one: a thin
// vertical line at the hovered day, so you aim at a day, not at a 2px line.
const crosshairPlugin = {
  id: "crosshair",
  afterDatasetsDraw(chart, args, options) {
    const active = chart.tooltip ? chart.tooltip.getActiveElements() : [];
    if (!options.enabled || !active.length) return;
    const x = active[0].element.x;
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.lineWidth = 1;
    ctx.strokeStyle = options.color;
    ctx.stroke();
    ctx.restore();
  },
};

function lastValueIndex(values) {
  for (let i = values.length - 1; i >= 0; i -= 1) {
    if (values[i] !== null) return i;
  }
  return -1;
}

function chartConfig(kind, data, theme) {
  const isLine = kind === "line";
  const datasets = data.series.map((series, index) => {
    const color = cssVar(series.color);
    const values = series.values.map((v) => (v === null ? null : v / 100));
    if (isLine) {
      const last = lastValueIndex(values);
      return {
        label: series.name,
        data: values,
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        borderCapStyle: "round",
        borderJoinStyle: "round",
        // Only the end of each line gets a dot, with a ring in the card colour.
        pointRadius: (ctx) => (ctx.dataIndex === last ? 4 : 0),
        pointHoverRadius: 5,
        pointBackgroundColor: color,
        // The ring is only for the end dot. (Legend and tooltip keys use the
        // point border colour too, so elsewhere it must be the line's colour.)
        pointBorderColor: (ctx) => (ctx.dataIndex === last ? theme.surface : color),
        pointBorderWidth: 2,
        order: index, // the first series (this month) is drawn on top
      };
    }
    return {
      label: series.name,
      data: values,
      backgroundColor: color,
      hoverBackgroundColor: withAlpha(color, 0.75),
      borderRadius: 4,
      borderSkipped: "start", // round at the top, square at the zero line
      maxBarThickness: 24,
      categoryPercentage: 0.7,
      barPercentage: 0.88, // leaves a small gap between the two bars of a month
    };
  });

  return {
    type: isLine ? "line" : "bar",
    data: { labels: data.labels, datasets },
    plugins: [crosshairPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: reduceMotion.matches ? false : { duration: 250 },
      // One tooltip with every series for the hovered month or day.
      interaction: { mode: "index", intersect: false },
      plugins: {
        crosshair: { enabled: isLine, color: theme.axis },
        legend: {
          position: "top",
          align: "start",
          labels: {
            color: theme.ink,
            boxWidth: 12,
            boxHeight: 12,
            padding: 16,
            usePointStyle: isLine, // a short line for lines, a square for bars
            pointStyle: "line",
          },
        },
        tooltip: {
          backgroundColor: theme.surface,
          titleColor: theme.ink,
          bodyColor: theme.ink,
          borderColor: theme.axis,
          borderWidth: 1,
          padding: 10,
          usePointStyle: true,
          boxPadding: 6,
          filter: (item) => item.raw !== null,
          callbacks: {
            title: (items) => data.titles[items[0].dataIndex],
            // The value first, then the name.
            label: (item) => `${pesoFull.format(item.raw)}  ${item.dataset.label}`,
            labelPointStyle: () => ({ pointStyle: "line", rotation: 0 }),
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: theme.axis },
          ticks: { color: theme.soft, maxRotation: 0, autoSkipPadding: 10 },
        },
        y: {
          beginAtZero: true,
          grid: { color: theme.grid },
          border: { display: false },
          ticks: { color: theme.soft, maxTicksLimit: 6, callback: (value) => pesoShort.format(value) },
        },
      },
    },
  };
}

function drawCharts() {
  const figures = document.querySelectorAll("figure.chart");
  if (!figures.length) return;
  if (!window.Chart) {
    // Chart.js didn't load (offline, blocked): show the tables instead.
    figures.forEach((figure) => {
      figure.classList.add("chart-failed");
      figure.querySelector("details").open = true;
    });
    return;
  }
  drawnCharts.forEach((chart) => chart.destroy());
  drawnCharts.length = 0;
  const theme = chartTheme();
  window.Chart.defaults.font.family = theme.font;
  window.Chart.defaults.font.size = 13;
  figures.forEach((figure) => {
    const data = JSON.parse(figure.querySelector(".chart-data").textContent);
    const canvas = figure.querySelector("canvas");
    drawnCharts.push(new window.Chart(canvas, chartConfig(figure.dataset.chart, data, theme)));
  });
}

setUpThemeToggle();
setUpConfirms();
drawCharts();
// Charts take their colours from CSS, so draw them again when the theme changes.
document.addEventListener("themechange", drawCharts);
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawCharts);
