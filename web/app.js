"use strict";

const byId = id => document.getElementById(id);
const data = JSON.parse(byId("data").textContent);
const contract = byId("contract");
const windowSelect = byId("window");
const costSelect = byId("cost");
const chart = byId("chart");
const series = [
  { key: "unhedged", label: "Unhedged", color: "#62747e", dash: "6 4" },
  { key: "full", label: "1:1 hedge", color: "#98681c", dash: "2 4" },
  { key: "rolling", label: "Rolling hedge", color: "#076c55", dash: "" },
];
const number = Intl.NumberFormat("en", { maximumFractionDigits: 1 });
const percent = Intl.NumberFormat("en", { style: "percent", maximumFractionDigits: 1 });
const fmt = value => number.format(Math.abs(value) < 0.05 ? 0 : value).replace("-", "−");
const pct = value => value === null ? "N/A" : percent.format(value).replace("-", "−");
const label = month => new Date(month + "-01T00:00:00Z").toLocaleDateString("en", {
  month: "short", year: "numeric", timeZone: "UTC",
});
let mode = "cumulative";
let chartState;

function setupSelect(select, values, labelFor, selected) {
  for (const value of values) {
    select.add(new Option(labelFor(value), value, false, value === selected));
  }
  select.addEventListener("change", render);
}

function tableRow(body, values) {
  const row = document.createElement("tr");
  values.forEach((value, index) => {
    const cell = document.createElement(index ? "td" : "th");
    if (!index) cell.scope = "row";
    cell.textContent = value;
    row.append(cell);
  });
  body.append(row);
}

function selectedCase() {
  return data.cases[[contract.value, windowSelect.value, costSelect.value].join("/")];
}

function render() {
  const { rows, metrics } = selectedCase();
  const rolling = metrics.rolling;
  byId("he").textContent = pct(rolling.effectiveness);
  byId("he").classList.toggle("negative", rolling.effectiveness < 0);
  byId("vol").textContent = fmt(rolling.volatility);
  byId("vol-detail").textContent = "MYR/t · " + fmt(metrics.unhedged.volatility) + " unhedged";
  byId("tail").textContent = fmt(rolling.tail);
  byId("added").textContent = rolling.added_loss + " / " + rows.length;

  const comparison = byId("comparison");
  comparison.replaceChildren();
  for (const strategy of series) {
    const item = metrics[strategy.key];
    tableRow(comparison, [strategy.label, pct(item.effectiveness), fmt(item.volatility), fmt(item.tail),
      fmt(item.worst), item.added_loss]);
  }

  const stress = rows.filter(row => row.rolling < Math.min(row.unhedged, 0) - 1e-9)
    .sort((a, b) => (b.unhedged - b.rolling) - (a.unhedged - a.rolling));
  const stressRows = byId("stress-rows");
  stressRows.replaceChildren();
  for (const row of stress.slice(0, 5)) {
    tableRow(stressRows, [label(row.month), fmt(row.spot), fmt(row.futures), pct(row.ratio),
      fmt(row.rolling), fmt(row.unhedged - row.rolling)]);
  }
  const worst = stress[0];
  const mechanism = worst && worst.futures > 0
    ? "The futures price rose and the short position lost money."
    : "The short position’s round-trip cost outweighed any gain on the futures leg.";
  byId("stress-note").textContent = worst
    ? label(worst.month) + " had the largest additional loss, " + fmt(worst.unhedged - worst.rolling)
      + " MYR/t. " + mechanism
    : "The rolling hedge did not increase losses in any evaluated month for these settings.";
  byId("stress-table").hidden = !worst;
  byId("stress-unit").hidden = !worst;
  drawChart(rows);
}

function svgElement(name, attributes, value) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, attr] of Object.entries(attributes)) element.setAttribute(key, attr);
  if (value !== undefined) element.textContent = value;
  chart.append(element);
  return element;
}

function drawChart(rows) {
  const cumulative = mode === "cumulative";
  const displayed = rows.map(row => ({ ...row }));
  if (cumulative) {
    const [year, month] = data.start.split("-").map(Number);
    const baseline = new Date(Date.UTC(2000, month - 2, 1));
    baseline.setUTCFullYear(month === 1 ? year - 1 : year);
    displayed.unshift({ month: baseline.toISOString().slice(0, 7), unhedged: 0, full: 0, rolling: 0 });
    for (let i = 1; i < displayed.length; i++) {
      for (const { key } of series) displayed[i][key] += displayed[i - 1][key];
    }
  }
  const width = Math.max(260, chart.clientWidth);
  const height = chart.clientHeight || 255;
  const margin = { left: 56, right: 15, top: 10, bottom: 27 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const values = displayed.flatMap(row => series.map(({ key }) => row[key]));
  const rawLow = Math.min(0, ...values);
  const rawHigh = Math.max(0, ...values);
  const range = rawHigh - rawLow || 1;
  const unit = 10 ** Math.floor(Math.log10(range / 4));
  const step = [1, 2, 2.5, 5, 10].map(k => k * unit).find(tick => tick >= range / 4);
  const low = Math.floor(rawLow / step) * step;
  const high = Math.max(low + step, Math.ceil(rawHigh / step) * step);
  const x = index => margin.left + plotW * index / (displayed.length - 1);
  const y = value => margin.top + (high - value) * plotH / (high - low);
  chart.replaceChildren();
  chart.setAttribute("viewBox", "0 0 " + width + " " + height);
  byId("chart-title").textContent = (cumulative ? "Cumulative" : "Monthly") + " inventory P&L";

  for (let tick = 0; tick <= Math.round((high - low) / step); tick++) {
    const value = low + tick * step;
    const position = y(value);
    svgElement("line", { x1: margin.left, x2: width - margin.right, y1: position, y2: position,
      stroke: Math.abs(value) < step / 100 ? "#a4b7a9" : "#e2eae3" });
    svgElement("text", { x: margin.left - 8, y: position + 4, "text-anchor": "end",
      fill: "#465a55", "font-size": 11 }, fmt(value));
  }
  const tickCount = Math.min(width < 450 ? 3 : 6, displayed.length);
  for (let i = 0; i < tickCount; i++) {
    const index = Math.round(i * (displayed.length - 1) / (tickCount - 1));
    svgElement("text", { x: x(index), y: height - 6, fill: "#465a55",
      "text-anchor": i === 0 ? "start" : i === tickCount - 1 ? "end" : "middle",
      "font-size": 11 }, label(displayed[index].month));
  }
  for (const strategy of series) {
    const points = displayed.map((row, index) => x(index) + "," + y(row[strategy.key])).join(" ");
    svgElement("polyline", { points, fill: "none", stroke: strategy.color, "stroke-dasharray": strategy.dash,
      "stroke-width": strategy.key === "rolling" ? 2.8 : 1.8, "stroke-linejoin": "round" });
  }
  const cursor = svgElement("line", { stroke: "#71897c", "stroke-dasharray": "3 3",
    y1: margin.top, y2: margin.top + plotH, visibility: "hidden" });
  chartState = { displayed, cursor, x, plotW, margin };
  showPoint(displayed.length - 1, false);
}

function showPoint(index, showCursor) {
  const { displayed, cursor, x } = chartState;
  const row = displayed[index];
  chartState.index = index;
  cursor.setAttribute("visibility", showCursor ? "visible" : "hidden");
  cursor.setAttribute("x1", x(index));
  cursor.setAttribute("x2", x(index));
  const details = series.map(({ key, label: name }) => name + " " + fmt(row[key]));
  byId("chart-readout").textContent = label(row.month) + " · " + details.join(" · ") + " MYR/t";
}

function downloadCsv() {
  const fields = ["month", "spot", "futures", "ratio", "unhedged", "full", "rolling"];
  const header = ["month", "spot_change_myr_t", "futures_change_myr_t", "short_hedge_ratio",
    "unhedged_pnl_myr_t", "one_to_one_pnl_myr_t", "rolling_pnl_myr_t"];
  const lines = selectedCase().rows.map(row => fields.map(field => row[field]).join(","));
  const url = URL.createObjectURL(new Blob([[header.join(","), ...lines].join("\n") + "\n"], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "fcpo-" + (data.demo ? "synthetic-" : "") + contract.value.toLowerCase() + "-"
    + windowSelect.value + "m-cost" + costSelect.value + ".csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 500);
}

setupSelect(contract, data.contracts, value => "FCPO " + value, "C1");
setupSelect(windowSelect, data.windows, value => value + " months", 24);
setupSelect(costSelect, data.costs, value => value + " MYR/t", 2);
byId("data-badge").textContent = data.demo ? "Synthetic demo" : "User-supplied dataset";
byId("source-label").textContent = data.provenance;
byId("period").textContent = label(data.start) + " – " + label(data.end);
byId("method-data").textContent = data.demo
  ? "Spot and futures changes are generated from a seeded scenario. C1 and C2 simulate nearby and next contract exposures. Calendar labels represent hypothetical intervals."
  : "The source label is supplied by the operator. Consult the accompanying data documentation for price timing and futures roll rules.";
for (const choice of ["cumulative", "monthly"]) {
  byId(choice).addEventListener("click", () => {
    mode = choice;
    for (const name of ["cumulative", "monthly"]) byId(name).setAttribute("aria-pressed", name === choice);
    drawChart(selectedCase().rows);
  });
}
byId("download").addEventListener("click", downloadCsv);
chart.addEventListener("pointermove", event => {
  const { displayed, margin, plotW } = chartState;
  const relative = (event.clientX - chart.getBoundingClientRect().left - margin.left) / plotW;
  const index = Math.max(0, Math.min(displayed.length - 1, Math.round(relative * (displayed.length - 1))));
  showPoint(index, true);
});
chart.addEventListener("pointerleave", () => showPoint(chartState.displayed.length - 1, false));
chart.addEventListener("keydown", event => {
  const last = chartState.displayed.length - 1;
  const targets = { ArrowLeft: chartState.index - 1, ArrowRight: chartState.index + 1, Home: 0, End: last };
  if (!Object.hasOwn(targets, event.key)) return;
  event.preventDefault();
  byId("chart-readout").setAttribute("aria-live", "polite");
  showPoint(Math.min(last, Math.max(0, targets[event.key])), true);
});
new ResizeObserver(() => drawChart(selectedCase().rows)).observe(chart);
render();
