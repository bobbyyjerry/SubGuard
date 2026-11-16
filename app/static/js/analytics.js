function renderSpendingCharts() {
  const dataElement = document.getElementById("spending-chart-data");
  if (!dataElement || !window.Chart) return;

  const { currency, categories } = JSON.parse(dataElement.textContent);
  const currencyFormat = new Intl.NumberFormat(document.documentElement.lang, { style: "currency", currency });
  const tickFormat = new Intl.NumberFormat(document.documentElement.lang, {
    style: "currency", currency, notation: "compact",
  });
  const theme = getComputedStyle(document.documentElement);
  const themeColor = (name) => theme.getPropertyValue(name).trim();
  const textColor = themeColor("--sg-text");
  const categoryColors = {
    streaming: themeColor("--sg-primary"),
    music: "#a78bfa",
    software: "#60a5fa",
    cloud: "#2dd4bf",
    gaming: "#fb7185",
    news: "#fbbf24",
    fitness: "#a3e635",
    education: "#fb923c",
    other: "#94a3b8",
  };
  const labels = categories.map(({ label }) => label);
  const backgroundColor = categories.map(({ key }) => categoryColors[key]);
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 450 },
  };

  const charts = document.getElementById("spending-charts");
  charts.hidden = false;
  new window.Chart(document.getElementById("monthly-category-chart"), {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: categories.map(({ monthly }) => Number(monthly)),
        backgroundColor,
        borderColor: themeColor("--sg-surface"),
        borderWidth: 2,
        hoverOffset: 4,
      }],
    },
    options: {
      ...chartOptions,
      cutout: "66%",
      plugins: {
        legend: { position: "bottom", labels: { color: textColor, usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: (item) => `${item.label} · ${currencyFormat.format(item.raw)}` } },
      },
    },
  });

  new window.Chart(document.getElementById("annual-category-chart"), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: categories.map(({ annual }) => Number(annual)),
        backgroundColor,
        borderRadius: 4,
        maxBarThickness: 28,
      }],
    },
    options: {
      ...chartOptions,
      indexAxis: "y",
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: themeColor("--sg-border") },
          ticks: { color: textColor, maxTicksLimit: 5, callback: (value) => tickFormat.format(value) },
        },
        y: { grid: { display: false }, ticks: { color: textColor } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (item) => currencyFormat.format(item.raw) } },
      },
    },
  });
}

renderSpendingCharts();
