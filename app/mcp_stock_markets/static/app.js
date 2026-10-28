"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const STORAGE_PREFIX = "mcp_stock_markets-";
const STORAGE_VIEW = "mcp_stock_markets-view";
const STORAGE_RUN = "mcp_stock_markets-run";

const CONNECTION_DEFAULTS = {
  claude: { model: "claude-opus-5-5" },
  openai: { model: "" },
};
const KIND_LABELS = { claude: "Cloud · Claude", openai: "OpenAI-compatible" };

const VIEWS = ["portfolio", "market", "agent", "run", "trades", "settings"];
const DEFAULT_VIEW = "portfolio";
const LINK_PATH = "/auth/link";
// A running agent run is followed closely; the portfolio only while the market
// is open, and no faster than a price is read again (60 s, QuoteCommand).
const RUN_POLL_MILLISECONDS = 5000;
const PORTFOLIO_POLL_MILLISECONDS = 60000;
const LIVE_VIEWS = ["portfolio", "agent", "run"];
const GENERIC_ERROR = "Something went wrong. Try again.";
const RUN_LABELS = {
  running: "Running…",
  completed: "Completed",
  exhausted: "Stopped: out of rounds",
  failed: "Failed",
};
const TRIGGER_LABELS = { schedule: "Scheduled", manual: "Run now" };
const SOURCE_LABELS = { google_finance: "Google Finance", alpaca: "Alpaca (IEX)", alpha_vantage: "Alpha Vantage" };
const STEP_LABELS = { thinking: "Thinking", model: "The model" };
// labelGap: the least vertical distance between two axis labels (12 px text).
const CHART = { width: 640, height: 220, padding: 24, left: 76, labelGap: 16 };

// The one module-scope mutable object.
const state = {
  view: "loading",
  user: null,
  modal: null,
  pollTimer: null,
  runId: null,
  // The runs unfolded in the list, kept while the list is drawn again.
  runsOpen: new Set(),
  // The whole S&P 500, read once and filtered here; null until read.
  companies: null,
  universe: [],
  universeFull: false,
  llm: null,
};

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// --- small helpers -------------------------------------------------------------

function stored(key) {
  try {
    return localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function store(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    // Private windows may refuse storage: the choice still holds for this page.
  }
}

function forgetStored() {
  try {
    Object.keys(localStorage)
      .filter((key) => key.startsWith(STORAGE_PREFIX))
      .forEach((key) => localStorage.removeItem(key));
  } catch (error) {
    // Nothing stored, nothing to forget.
  }
}

// Text set through textContent, never innerHTML: company names, reasons and
// the models' words come from outside. Icons are the one innerHTML, from constants.
function element(tag, attributes, children) {
  const result = document.createElement(tag);
  Object.entries(attributes).forEach(([name, value]) => {
    if (value === false || value === null || value === undefined) {
      return;
    }
    if (name === "text") {
      result.textContent = String(value);
    } else if (name === "icon") {
      result.innerHTML = ICONS[value] || "";
      result.setAttribute("aria-hidden", "true");
    } else if (value === true) {
      result.setAttribute(name, "");
    } else {
      result.setAttribute(name, String(value));
    }
  });
  children.forEach((child) => result.append(child));
  return result;
}

function iconLabelled(icon, label) {
  return [element("span", { icon }, []), element("span", { text: label }, [])];
}

function renderIcons(root) {
  $$("[data-icon]", root).forEach((target) => {
    // Constants from icons.js only, never user input.
    target.innerHTML = ICONS[target.dataset.icon] || "";
  });
}

function dateText(iso) {
  const date = new Date(String(iso));
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function status(message, kind) {
  const target = $("#status");
  target.textContent = message;
  target.dataset.kind = kind;
  target.hidden = message === "";
}

function failed(error) {
  status(error instanceof ApiError ? error.message : GENERIC_ERROR, "error");
}

// --- the API -------------------------------------------------------------------

function detailOf(data, fallback) {
  return data !== null && typeof data === "object" && typeof data.detail === "string" ? data.detail : fallback;
}

// The single fetch wrapper: JSON in and out, the server's
// `detail` as the error, 401 back to the sign-in, and the button that sent the
// request disabled until it answers, so a double click submits once.
async function api(path, options) {
  const button = options.button || null;
  if (button !== null) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }
  try {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    let body;
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.json);
    }
    let response;
    try {
      response = await fetch(path, { method: options.method || "GET", headers, body, credentials: "same-origin" });
    } catch (error) {
      throw new ApiError("The server could not be reached. Check your connection.", 0);
    }
    const text = await response.text();
    let data = null;
    try {
      data = text === "" ? null : JSON.parse(text);
    } catch (error) {
      data = null;
    }
    if (response.status === 401 && options.isSignInCheck !== true && path.startsWith("/api/auth/") === false) {
      signedOutLocally();
    }
    if (response.ok === false) {
      throw new ApiError(detailOf(data, GENERIC_ERROR), response.status);
    }
    return data;
  } finally {
    if (button !== null) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }
}

// --- views ---------------------------------------------------------------------

function storedView() {
  const saved = stored(STORAGE_VIEW);
  if (saved === "run") {
    const runId = Number(stored(STORAGE_RUN));
    if (Number.isInteger(runId) === false || runId <= 0) {
      return DEFAULT_VIEW;
    }
    state.runId = runId;
  }
  return VIEWS.includes(saved) ? saved : DEFAULT_VIEW;
}

function shown(view) {
  state.view = view;
  $$("[data-view]").forEach((section) => {
    section.hidden = section.dataset.view !== view;
  });
  // A run is part of the agent's page.
  const navView = view === "run" ? "agent" : view;
  $$("[data-nav]").forEach((button) => {
    if (button.dataset.nav === navView) {
      button.setAttribute("aria-current", "page");
    } else {
      button.removeAttribute("aria-current");
    }
  });
}

function opened(view) {
  status("", "");
  pollStopped();
  shown(view);
  if (VIEWS.includes(view)) {
    store(STORAGE_VIEW, view);
  }
  const heading = $(`[data-view="${view}"] h1`);
  if (heading !== null) {
    heading.setAttribute("tabindex", "-1");
    heading.focus({ preventScroll: true });
  }
  viewLoaded(view);
}

function viewLoaded(view) {
  const loaders = {
    portfolio: loadPortfolio,
    market: loadMarket,
    agent: loadRuns,
    run: loadRun,
    trades: loadTrades,
    settings: loadConnections,
  };
  if (loaders[view] !== undefined) {
    loaders[view]();
  }
}

// --- numbers -----------------------------------------------------------------------

function money(value) {
  return Number(value).toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function signedMoney(value) {
  const amount = Number(value);
  return `${amount > 0 ? "+" : ""}${money(amount)}`;
}

function percent(part, whole) {
  const ratio = Number(whole) === 0 ? 0 : (Number(part) / Number(whole)) * 100;
  return `${ratio > 0 ? "+" : ""}${ratio.toFixed(2)} %`;
}

function trend(value) {
  const amount = Number(value);
  return amount > 0 ? "is-up" : amount < 0 ? "is-down" : "";
}

function momentText(iso) {
  const date = new Date(String(iso));
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// --- polling ------------------------------------------------------------------------

// A hidden tab is not polled: it is loaded again when it shows.
function pollScheduled(action, milliseconds) {
  pollStopped();
  if (!document.hidden) {
    state.pollTimer = window.setTimeout(action, milliseconds);
  }
}

// Only the views that refresh themselves load again: Settings, say, would test
// every model connection each time the tab shows.
function visibilityChanged() {
  pollStopped();
  if (!document.hidden && LIVE_VIEWS.includes(state.view)) {
    viewLoaded(state.view);
  }
}

function pollStopped() {
  if (state.pollTimer !== null) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function renderChrome() {
  const isSignedIn = state.user !== null;
  $("#app-nav").hidden = isSignedIn === false;
  $("#sign-out").hidden = isSignedIn === false;
  $("#settings-open").hidden = isSignedIn === false;
}

// --- signing in ----------------------------------------------------------------

async function loadAccount() {
  shown("loading");
  try {
    state.user = await api("/api/account", { isSignInCheck: true });
  } catch (error) {
    state.user = null;
    renderChrome();
    shown("sign-in");
    if (error instanceof ApiError && error.status !== 401) {
      failed(error);
    }
    return;
  }
  renderChrome();
  opened(storedView());
}

function signedOutLocally() {
  // The next person on this device sees none of the previous one's data.
  state.user = null;
  state.runId = null;
  state.runsOpen = new Set();
  $("#runs-from").value = "";
  $("#runs-to").value = "";
  state.companies = null;
  state.universe = [];
  state.universeFull = false;
  state.llm = null;
  ["#llm-connection-list", "#portfolio-stats", "#portfolio-chart", "#positions-body", "#universe-list", "#company-list", "#company-found",
    "#run-list", "#step-list", "#server-list", "#trades-body"].forEach((selector) => $(selector).replaceChildren());
  $("#company-query").value = "";
  $("#mcp-servers").open = false;
  pollStopped();
  forgetStored();
  Theme.applied();
  closeModal();
  renderChrome();
  shown("sign-in");
}

async function signOut(event) {
  try {
    await api("/api/auth/sign-out", { method: "POST", button: event.currentTarget });
  } catch (error) {
    // The session is forgotten here either way; the server drops it at expiry.
  }
  signedOutLocally();
  status("You are signed out.", "success");
}

async function linkRequested(event) {
  event.preventDefault();
  const input = $("#sign-in-email");
  const email = input.value.trim();
  if (email === "" || input.checkValidity() === false) {
    status("Enter your email address.", "error");
    input.focus();
    return;
  }
  status("", "");
  try {
    const answer = await api("/api/auth/link-request", { method: "POST", json: { email }, button: $("#link-submit") });
    const notice = $("#link-sent");
    notice.textContent = `${answer.message} Check your inbox.`;
    notice.hidden = false;
  } catch (error) {
    failed(error);
  }
}

async function linkConfirmed(event) {
  const token = new URLSearchParams(window.location.search).get("token") || "";
  try {
    await api("/api/auth/link", { method: "POST", json: { token }, button: event.currentTarget });
  } catch (error) {
    failed(error);
    $("#link-confirm").hidden = true;
    $("#link-back").hidden = false;
    return;
  }
  // The token is spent: it leaves the address bar and the history.
  window.history.replaceState(null, "", "/");
  await loadAccount();
}

function linkAbandoned() {
  window.history.replaceState(null, "", "/");
  status("", "");
  shown("sign-in");
  $("#sign-in-email").focus();
}

// --- portfolio -----------------------------------------------------------------------
// Cash, positions at their latest price, and the chart of the recorded valuations.

async function loadPortfolio() {
  let view;
  let history;
  let market;
  try {
    [view, history, market] = await Promise.all([api("/api/portfolio", {}), api("/api/valuations", {}), api("/api/market", {})]);
  } catch (error) {
    failed(error);
    return;
  }
  renderPortfolio(view, market.status);
  renderChart(history);
  if (state.view === "portfolio" && market.status.is_open) {
    pollScheduled(loadPortfolio, PORTFOLIO_POLL_MILLISECONDS);
  }
}

function renderPortfolio(view, marketStatus) {
  const start = Number(view.portfolio.starting_budget);
  const gain = Number(view.total_value) - start;
  marketChip($("#portfolio-market"), marketStatus);
  $("#portfolio-stats").replaceChildren(
    stat("Total value", money(view.total_value), `${signedMoney(gain)} (${percent(gain, start)})`, trend(gain)),
    stat("Cash", money(view.portfolio.cash), "never below $0", ""),
    stat("In shares", money(view.holdings_value), `${view.positions.length} ${view.positions.length === 1 ? "position" : "positions"}`, ""),
    stat("Started with", money(start), `on ${momentText(view.portfolio.created_at)}`, ""),
  );
  $("#positions-empty").hidden = view.positions.length > 0;
  $("#positions-table").hidden = view.positions.length === 0;
  $("#positions-body").replaceChildren(...view.positions.map(positionRow));
}

function stat(label, value, detail, kind) {
  return element("li", { class: "stat" }, [
    element("span", { class: "stat-label", text: label }, []),
    element("strong", { class: "stat-value", text: value }, []),
    element("span", { class: `stat-detail ${kind}`, text: detail }, []),
  ]);
}

function positionRow(position) {
  const holding = position.holding;
  const gain = Number(position.value) - Number(holding.cost);
  const price = position.quote === null ? "—" : money(position.quote.price);
  return element("tr", {}, [
    element("th", { scope: "row", text: holding.symbol }, []),
    element("td", { class: "number", text: String(holding.quantity) }, []),
    element("td", { class: "number", text: money(holding.cost) }, []),
    element("td", { class: "number", text: price, title: position.quote === null ? "No price read yet" : quoteTitle(position.quote) }, []),
    element("td", { class: "number", text: money(position.value) }, []),
    element("td", { class: `number ${trend(gain)}`, text: `${signedMoney(gain)} (${percent(gain, holding.cost)})` }, []),
  ]);
}

function quoteTitle(quote) {
  return `${SOURCE_LABELS[quote.source] || quote.source}, trade of ${momentText(quote.as_of)}`;
}

function marketChip(chip, marketStatus) {
  chip.textContent = marketStatus.is_open
    ? `Market open until ${momentText(marketStatus.closes_at)}`
    : `Market closed · opens ${momentText(marketStatus.next_open)}`;
  chip.className = `chip ${marketStatus.is_open ? "is-up" : ""}`;
}

// A hand-rolled SVG line (no chart library): the total value at each valuation,
// against a dashed line at the starting budget.
function renderChart(history) {
  const points = history.valuations;
  const target = $("#portfolio-chart");
  $("#chart-empty").hidden = points.length > 0;
  if (points.length === 0) {
    target.replaceChildren();
    return;
  }
  const start = Number(history.starting_budget);
  const values = points.map((point) => Number(point.total_value));
  // A flat line sits in the middle: a range of 1 % around the budget.
  const margin = start / 100;
  const low = Math.min(start - margin, ...values);
  const high = Math.max(start + margin, ...values);
  const span = high - low;
  const x = (index) => CHART.left + (points.length === 1 ? 0 : (index / (points.length - 1)) * (CHART.width - CHART.left - CHART.padding));
  const y = (value) => CHART.height - CHART.padding - ((value - low) / span) * (CHART.height - 2 * CHART.padding);
  const svgNs = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNs, "svg");
  svg.setAttribute("viewBox", `0 0 ${CHART.width} ${CHART.height}`);
  svg.setAttribute("role", "img");
  const last = values[values.length - 1];
  svg.setAttribute("aria-label", `Value from ${money(values[0])} to ${money(last)} over ${points.length} valuations`);
  const shape = (tag, attributes) => {
    const node = document.createElementNS(svgNs, tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
    svg.append(node);
    return node;
  };
  shape("line", { x1: CHART.left, x2: CHART.width - CHART.padding, y1: y(start), y2: y(start), class: "chart-base" });
  // The budget's label first; the top and bottom ones only where they do not
  // overlap a label already drawn.
  const labelled = [];
  [start, high, low].forEach((value) => {
    if (labelled.every((other) => Math.abs(y(other) - y(value)) >= CHART.labelGap)) {
      shape("text", { x: CHART.left - 8, y: y(value) + 4, class: "chart-label end" }).textContent = money(value);
      labelled.push(value);
    }
  });
  shape("polyline", { points: values.map((value, index) => `${x(index)},${y(value)}`).join(" "), class: `chart-line ${trend(last - start)}` });
  values.forEach((value, index) => {
    const dot = shape("circle", { cx: x(index), cy: y(value), r: 3, class: "chart-dot" });
    const title = document.createElementNS(svgNs, "title");
    title.textContent = `${momentText(points[index].taken_at)}: ${money(value)}`;
    dot.append(title);
  });
  shape("text", { x: CHART.left, y: CHART.height - 4, class: "chart-label" }).textContent = momentText(points[0].taken_at);
  shape("text", { x: CHART.width - CHART.padding, y: CHART.height - 4, class: "chart-label end" }).textContent = momentText(points[points.length - 1].taken_at);
  target.replaceChildren(svg);
}

// --- market --------------------------------------------------------------------------
// The companies the agent may buy, priced, and the S&P 500 to choose them from.

async function loadMarket() {
  let market;
  try {
    market = await api("/api/market", {});
  } catch (error) {
    failed(error);
    return;
  }
  renderMarket(market);
  if (state.companies === null) {
    await companiesLoaded();
  } else {
    companiesFiltered();
  }
}

function renderMarket(market) {
  marketChip($("#market-status"), market.status);
  $("#market-hint").textContent = market.status.is_open
    ? "The agent runs on its own while the market is open."
    : "Orders are refused while the market is closed; prices are those of the last trade.";
  $("#universe-count").textContent = `${market.universe.length} of at most ${market.limit} companies. The agent may buy only these, and sell whatever the portfolio holds.`;
  $("#universe-empty").hidden = market.universe.length > 0;
  $("#universe-list").replaceChildren(...market.universe.map(universeItem));
  $("#sp500-summary").textContent = market.sp500_companies === 0
    ? "The list is being read from Wikipedia…"
    : `${market.sp500_companies} companies, from Wikipedia's "List of S&P 500 companies", read again every day.`;
  state.universeFull = market.universe.length >= market.limit;
  state.universe = market.universe.map((company) => company.symbol);
}

function universeItem(company) {
  const remove = element("button", { type: "button", class: "button small quiet danger-text", "aria-label": `Remove ${company.symbol}` }, iconLabelled("trash", "Remove"));
  remove.addEventListener("click", () => universeRemovalAsked(company));
  const price = company.quote === null
    ? element("span", { class: "muted small", text: company.quote_error || "No price" }, [])
    : element("span", { class: "price", title: quoteTitle(company.quote), text: money(company.quote.price) }, []);
  return element("li", { class: "company" }, [
    element("div", { class: "company-body" }, [
      element("p", {}, [element("strong", { text: company.symbol }, []), document.createTextNode(` ${company.name}`)]),
      element("p", { class: "muted small", text: [company.sector, company.sub_industry, company.exchange].filter((part) => part !== "").join(" · ") }, []),
    ]),
    price,
    remove,
  ]);
}

async function companiesLoaded() {
  let found;
  try {
    found = await api("/api/companies", {});
  } catch (error) {
    failed(error);
    return;
  }
  const sector = $("#company-sector").value;
  $("#company-sector").replaceChildren(
    element("option", { value: "", text: "Every sector" }, []),
    ...found.sectors.map((item) => element("option", { value: item.sector, text: `${item.sector} (${item.companies})` }, [])),
  );
  // The sector chosen before a new reading stays chosen while it still exists.
  $("#company-sector").value = found.sectors.some((item) => item.sector === sector) ? sector : "";
  state.companies = found.companies;
  companiesFiltered();
}

// By symbol or name, within the sector chosen; a symbol that starts with the
// query first, then by symbol, as the agent's search_companies orders them.
function companiesFiltered() {
  const query = $("#company-query").value.trim().toLowerCase();
  const sector = $("#company-sector").value;
  const starts = (company) => company.symbol.toLowerCase().startsWith(query);
  const found = (state.companies || [])
    .filter((company) => sector === "" || company.sector === sector)
    .filter((company) => company.symbol.toLowerCase().includes(query) || company.name.toLowerCase().includes(query))
    .sort((one, other) => Number(starts(other)) - Number(starts(one)) || (one.symbol < other.symbol ? -1 : 1));
  $("#company-found").textContent = `${found.length} of ${(state.companies || []).length} companies`;
  $("#company-list").replaceChildren(...found.map(companyItem));
}

function companyItem(company) {
  const isChosen = (state.universe || []).includes(company.symbol);
  const add = element("button", {
    type: "button",
    class: "button small",
    disabled: isChosen || state.universeFull === true,
    "aria-label": `Add ${company.symbol} to the agent's market`,
  }, iconLabelled(isChosen ? "check" : "plus", isChosen ? "Added" : "Add"));
  add.addEventListener("click", async () => {
    try {
      await api("/api/universe", { method: "POST", json: { symbol: company.symbol }, button: add });
    } catch (error) {
      failed(error);
      return;
    }
    status(`${company.symbol} is in the agent's market.`, "success");
    await loadMarket();
  });
  return element("li", { class: "company" }, [
    element("div", { class: "company-body" }, [
      element("p", {}, [element("strong", { text: company.symbol }, []), document.createTextNode(` ${company.name}`)]),
      element("p", { class: "muted small", text: `${company.sector} · ${company.sub_industry} · ${company.exchange}` }, []),
    ]),
    add,
  ]);
}

function universeRemovalAsked(company) {
  openModal({
    title: `Remove ${company.symbol}?`,
    content: [element("p", { text: "The agent will no longer buy it. Shares already held stay, and it may still sell them." }, [])],
    actions: [
      { label: "Cancel", kind: "button", onClick: closeModal },
      {
        label: "Remove",
        kind: "button danger",
        onClick: async (button) => {
          await api(`/api/universe/${encodeURIComponent(company.symbol)}`, { method: "DELETE", button });
          closeModal();
          status(`${company.symbol} is out of the agent's market.`, "success");
          await loadMarket();
        },
      },
    ],
  });
}

async function sp500Refreshed(event) {
  try {
    const answer = await api("/api/companies/refresh", { method: "POST", button: event.currentTarget });
    status(`The list holds ${answer.companies} companies.`, "success");
  } catch (error) {
    failed(error);
    return;
  }
  state.companies = null;
  await loadMarket();
}

// --- the agent --------------------------------------------------------------------------
// Its runs, each with its transcript, and the MCP servers' tools.

// A day as a date input writes it, in the browser's time zone.
function dayValue(moment) {
  const pad = (number) => String(number).padStart(2, "0");
  return `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}`;
}

// From the first day's midnight to the midnight after the last, in the
// owner's time zone; today when no day is chosen.
function runsRange() {
  const today = dayValue(new Date());
  if ($("#runs-from").value === "") {
    $("#runs-from").value = today;
  }
  if ($("#runs-to").value === "" || $("#runs-to").value < $("#runs-from").value) {
    $("#runs-to").value = $("#runs-from").value;
  }
  const [fromYear, fromMonth, fromDay] = $("#runs-from").value.split("-").map(Number);
  const [toYear, toMonth, toDay] = $("#runs-to").value.split("-").map(Number);
  return {
    start: new Date(fromYear, fromMonth - 1, fromDay).toISOString(),
    end: new Date(toYear, toMonth - 1, toDay + 1).toISOString(),
  };
}

async function loadRuns() {
  let answer;
  try {
    answer = await api(`/api/agent/runs?${new URLSearchParams(runsRange())}`, {});
  } catch (error) {
    failed(error);
    return;
  }
  $("#runs-empty").hidden = answer.runs.length > 0;
  $("#runs-found").textContent = answer.runs.length >= answer.limit
    ? `The latest ${answer.limit} runs of these days.`
    : answer.runs.length === 0 ? "" : `${answer.runs.length} ${answer.runs.length === 1 ? "run" : "runs"}.`;
  $("#run-list").replaceChildren(...answer.runs.map(runItem));
  if (state.view === "agent" && answer.runs.some((run) => run.status === "running")) {
    pollScheduled(loadRuns, RUN_POLL_MILLISECONDS);
  }
}

// Folded to its title and the summary's first line; unfolded, the whole
// summary and the way to its transcript.
function runItem(run) {
  const text = run.summary || run.error || "";
  const transcript = element("button", { type: "button", class: "button small" }, iconLabelled("list", "Transcript"));
  transcript.addEventListener("click", () => {
    state.runId = run.run_id;
    store(STORAGE_RUN, String(run.run_id));
    opened("run");
  });
  const folded = element("details", { class: "run", open: state.runsOpen.has(run.run_id) }, [
    element("summary", { class: "run-head" }, [
      element("span", { class: `chip run-${run.status}`, text: RUN_LABELS[run.status] || run.status }, []),
      element("span", { class: "run-when", text: `${momentText(run.started_at)} · ${TRIGGER_LABELS[run.trigger] || run.trigger}` }, []),
      element("span", { class: "muted small", text: `${run.model} · ${run.turns} ${run.turns === 1 ? "round" : "rounds"}` }, []),
      element("span", { class: "run-preview muted", text: text.split("\n")[0] }, []),
    ]),
    element("div", { class: "run-body" }, [element("p", { class: "run-summary", text }, []), transcript]),
  ]);
  folded.addEventListener("toggle", () => {
    if (folded.open) {
      state.runsOpen.add(run.run_id);
    } else {
      state.runsOpen.delete(run.run_id);
    }
  });
  return element("li", { "data-run": run.run_id }, [folded]);
}

function runsFolded(open) {
  $$("#run-list details.run").forEach((folded) => {
    folded.open = open;
  });
}

async function agentStarted(event) {
  try {
    const answer = await api("/api/agent/runs", { method: "POST", button: event.currentTarget });
    status(answer.detail, "success");
  } catch (error) {
    failed(error);
    return;
  }
  // The run starts on the server's agent thread a moment later.
  window.setTimeout(loadRuns, 1500);
}

async function loadServers() {
  const target = $("#server-list");
  target.replaceChildren(element("p", { class: "muted", text: "Asking the MCP servers…" }, []));
  let answer;
  try {
    answer = await api("/api/agent/servers", {});
  } catch (error) {
    target.replaceChildren(element("p", { class: "notice error", text: error.message }, []));
    return;
  }
  target.replaceChildren(...answer.servers.map(serverShown));
}

function serverShown(server) {
  const body = server.error !== undefined
    ? [element("p", { class: "notice error", text: server.error }, [])]
    : server.tools.map((tool) => element("details", { class: "tool" }, [
      element("summary", {}, [element("code", { text: tool.name }, []), document.createTextNode(` ${tool.description.split("\n")[0]}`)]),
      element("p", { class: "small", text: tool.description }, []),
      element("pre", { class: "code", text: JSON.stringify(tool.input_schema, null, 2) }, []),
    ]));
  return element("section", { class: "server" }, [
    element("h3", {}, [element("span", { class: "server-badge", "data-server": server.server, text: server.server }, []), document.createTextNode(` ${server.url}`)]),
    ...body,
  ]);
}

async function loadRun() {
  if (state.runId === null) {
    opened("agent");
    return;
  }
  let answer;
  try {
    answer = await api(`/api/agent/runs/${Number(state.runId)}`, {});
  } catch (error) {
    failed(error);
    return;
  }
  renderRun(answer.run, answer.steps);
  if (state.view === "run" && answer.run.status === "running") {
    pollScheduled(loadRun, RUN_POLL_MILLISECONDS);
  }
}

function renderRun(run, steps) {
  $("#run-title").textContent = `Run ${run.run_id}`;
  const chip = $("#run-status");
  chip.textContent = RUN_LABELS[run.status] || run.status;
  chip.className = `chip run-${run.status}`;
  $("#run-meta").textContent = [
    momentText(run.started_at),
    TRIGGER_LABELS[run.trigger] || run.trigger,
    `${run.connection_name} (${run.model})`,
    `${run.turns} ${run.turns === 1 ? "round" : "rounds"}`,
    `${steps.filter((step) => step.kind === "tool").length} MCP calls`,
  ].join(" · ");
  $("#run-error").textContent = run.error;
  $("#run-error").hidden = run.error === "";
  $("#step-list").replaceChildren(...steps.map(stepShown));
}

function stepShown(step) {
  if (step.kind !== "tool") {
    return element("li", { class: `step step-${step.kind}` }, [
      element("p", { class: "step-head", text: STEP_LABELS[step.kind] || step.kind }, []),
      element("p", { class: "step-text", text: step.content }, []),
    ]);
  }
  const head = element("p", { class: "step-head" }, [
    element("span", { class: "server-badge", "data-server": step.server || "none", text: step.server || "?" }, []),
    element("code", { text: `${step.tool}(${argumentsText(step.arguments)})` }, []),
    element("span", { class: "muted small", text: `${Math.round(step.elapsed_ms)} ms` }, []),
  ]);
  if (step.is_error) {
    head.append(element("span", { class: "chip run-failed", text: "error" }, []));
  }
  // An error is shown at once: it is what the model read and acted on.
  const said = step.is_error ? [element("p", { class: "step-text is-down", text: step.content }, [])] : [];
  return element("li", { class: `step step-tool ${step.is_error ? "is-error" : ""}` }, [
    head,
    ...said,
    element("details", {}, [
      element("summary", { text: "tools/call arguments and answer" }, []),
      element("pre", { class: "code", text: JSON.stringify(step.arguments, null, 2) }, []),
      element("pre", { class: "code", text: prettyJson(step.content) }, []),
    ]),
  ]);
}

function argumentsText(argumentsObject) {
  if (argumentsObject === null) {
    return "…";
  }
  return Object.entries(argumentsObject).map(([name, value]) => `${name}=${JSON.stringify(value)}`).join(", ");
}

function prettyJson(text) {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch (error) {
    return text;
  }
}

// --- transactions ----------------------------------------------------------------------

async function loadTrades() {
  let answer;
  try {
    answer = await api("/api/trades", {});
  } catch (error) {
    failed(error);
    return;
  }
  $("#trades-empty").hidden = answer.trades.length > 0;
  $("#trades-table").hidden = answer.trades.length === 0;
  $("#trades-body").replaceChildren(...answer.trades.map(tradeRow));
}

function tradeRow(trade) {
  return element("tr", {}, [
    element("td", { text: momentText(trade.executed_at) }, []),
    element("th", { scope: "row", text: trade.symbol }, []),
    element("td", {}, [element("span", { class: `chip side-${trade.side}`, text: trade.side === "buy" ? "Buy" : "Sell" }, [])]),
    element("td", { class: "number", text: String(trade.quantity) }, []),
    element("td", { class: "number", text: money(trade.price), title: `${SOURCE_LABELS[trade.quote_source] || trade.quote_source}, trade of ${momentText(trade.quote_as_of)}` }, []),
    element("td", { class: "number", text: money(trade.amount) }, []),
    element("td", { class: "number", text: money(trade.cash_after) }, []),
    element("td", { class: "small", text: trade.reason }, []),
  ]);
}

// --- language models ---------------------------------------------------------
// Connections to Claude or to any OpenAI-compatible endpoint, each with a light that
// says whether it answers now, and the connection the agent trades with.

async function loadConnections() {
  try {
    state.llm = await api("/api/llm/connections", {});
  } catch (error) {
    failed(error);
    return;
  }
  renderConnections();
  state.llm.connections.forEach((connection) => connectionChecked(connection.connection_id));
}

function renderConnections() {
  const connections = state.llm.connections;
  $("#llm-empty").hidden = connections.length > 0;
  $("#llm-connection-list").replaceChildren(...connections.map(connectionShown));
  const chosen = state.llm.routing.agent;
  $("#llm-route-agent").replaceChildren(
    element("option", { value: "", text: "None: the agent is off", selected: chosen === null }, []),
    ...connections.map((connection) =>
      element("option", { value: connection.connection_id, text: connection.name, selected: connection.connection_id === chosen }, []),
    ),
  );
}

function connectionShown(connection) {
  const test = element("button", { type: "button", class: "button small quiet" }, iconLabelled("refresh", "Test"));
  test.addEventListener("click", () => connectionChecked(connection.connection_id));
  const edit = element("button", { type: "button", class: "button small quiet" }, iconLabelled("pencil", "Edit"));
  edit.addEventListener("click", () => connectionAsked(connection));
  const remove = element("button", { type: "button", class: "button small quiet danger-text" }, iconLabelled("trash", "Delete"));
  remove.addEventListener("click", () => connectionRemovalAsked(connection));
  const facts = [`Model: ${connection.model}`];
  if (connection.key_hint !== "") {
    facts.push(`Key ${connection.key_hint}`);
  }
  if (connection.kind === "openai") {
    facts.unshift(connection.base_url);
  }
  return element("li", { class: "connection", "data-connection": connection.connection_id }, [
    element("span", { class: "light is-checking", role: "img", "aria-label": "Checking…", title: "Checking…" }, []),
    element("div", { class: "connection-body" }, [
      element("p", { class: "connection-name" }, [
        element("strong", { text: connection.name }, []),
        document.createTextNode(" "),
        element("span", { class: "chip", text: KIND_LABELS[connection.kind] || connection.kind }, []),
      ]),
      element("p", { class: "muted small", text: facts.join(" · ") }, []),
      element("p", { class: "small connection-detail", text: "Checking…" }, []),
      element("div", { class: "connection-actions" }, [test, edit, remove]),
    ]),
  ]);
}

async function connectionChecked(connectionId) {
  const item = $(`[data-connection="${Number(connectionId)}"]`);
  if (item === null) {
    return;
  }
  lightShown(item, "is-checking", "Checking…");
  let health;
  try {
    health = await api(`/api/llm/connections/${Number(connectionId)}/health`, {});
  } catch (error) {
    lightShown(item, "is-down", error.message);
    return;
  }
  lightShown(item, health.is_ok ? "is-up" : "is-down", `${health.detail} (${Math.round(health.elapsed_ms)} ms)`);
}

function lightShown(item, kind, detail) {
  const light = $(".light", item);
  light.className = `light ${kind}`;
  const label = kind === "is-up" ? "Connected" : kind === "is-down" ? "Not connected" : "Checking…";
  light.setAttribute("aria-label", label);
  light.setAttribute("title", detail);
  $(".connection-detail", item).textContent = detail;
}

// Two tabs: the endpoint first (kind, address, key), then its model, chosen from the
// list the endpoint answered with rather than typed.
function connectionAsked(connection) {
  const isNew = connection === null;
  const kind = isNew ? "claude" : connection.kind;
  const values = isNew ? { name: "", base_url: "", ...CONNECTION_DEFAULTS.claude, disable_thinking: true } : connection;
  const kindSelect = element("select", { name: "kind" }, [
    element("option", { value: "claude", text: "Claude (cloud)", selected: kind === "claude" }, []),
    element("option", { value: "openai", text: "OpenAI-compatible (vLLM, or hosted)", selected: kind === "openai" }, []),
  ]);
  const urlInput = element("input", { type: "url", name: "base_url", value: values.base_url, placeholder: "https://llm.example.com/v1" }, []);
  const urlField = element("div", { class: "kind-openai" }, field("Address of the API, ending in /v1", urlInput));
  const stored = !isNew && connection.key_hint !== "" ? `, ${connection.key_hint}` : "";
  const keyHint = isNew || connection.has_key === false ? "API key" : `API key (leave empty to keep the stored one${stored})`;
  const keyInput = element("input", { type: "password", name: "api_key", autocomplete: "off" }, []);
  const thinking = element("div", { class: "kind-openai" }, [
    checkbox("Ask the model not to think first (faster; vLLM reasoning models)", "disable_thinking", values.disable_thinking),
  ]);
  const modelSelect = element("select", { name: "model" }, []);
  const offered = element("p", { class: "muted small" }, []);
  const tabs = {
    endpoint: element("button", { type: "button", role: "tab", id: "connection-tab-endpoint", "aria-controls": "connection-panel-endpoint", text: "1. Connection" }, []),
    models: element("button", { type: "button", role: "tab", id: "connection-tab-models", "aria-controls": "connection-panel-models", text: "2. Model" }, []),
  };
  const panels = {
    endpoint: element("div", { role: "tabpanel", id: "connection-panel-endpoint", "aria-labelledby": "connection-tab-endpoint" }, [
      ...field("Kind", kindSelect),
      ...field("Name", element("input", { type: "text", name: "name", maxlength: 80, value: values.name }, [])),
      urlField,
      ...field(keyHint, keyInput),
      element("p", { class: "muted small", text: "Connect to fetch the models this key can use." }, []),
    ]),
    models: element("div", { role: "tabpanel", id: "connection-panel-models", "aria-labelledby": "connection-tab-models" }, [
      offered,
      ...field("Model", modelSelect),
      thinking,
    ]),
  };
  const dialog = { tab: "endpoint", models: null };
  const tabShown = (tab) => {
    dialog.tab = tab;
    Object.entries(tabs).forEach(([name, button]) => {
      const isChosen = name === tab;
      button.setAttribute("aria-selected", String(isChosen));
      button.tabIndex = isChosen ? 0 : -1;
      panels[name].hidden = isChosen === false;
    });
    state.modal.submit.button.textContent = tab === "endpoint" ? "Connect" : isNew ? "Add" : "Save";
  };
  // A changed endpoint may offer other models: they are fetched again.
  const endpointChanged = () => {
    dialog.models = null;
    tabs.models.disabled = true;
    const isOpenai = kindSelect.value === "openai";
    urlField.hidden = isOpenai === false;
    // Disabled while hidden: an address left from another kind must not block the form.
    urlInput.disabled = isOpenai === false;
    thinking.hidden = isOpenai === false;
  };
  const connected = async (button) => {
    const listed = await api("/api/llm/models", {
      method: "POST",
      json: {
        connection_id: isNew ? 0 : Number(connection.connection_id),
        kind: kindSelect.value,
        base_url: urlInput.value,
        api_key: keyInput.value,
      },
      button,
    });
    if (listed.models.length === 0) {
      throw new ApiError("Connected, but the endpoint offers no model.", 0);
    }
    const preferred = kindSelect.value === kind ? values : CONNECTION_DEFAULTS[kindSelect.value];
    modelOptions(modelSelect, listed.models, preferred.model);
    offered.textContent = `Connected: ${listed.models.length} ${listed.models.length === 1 ? "model is" : "models are"} offered.`;
    dialog.models = listed.models;
    tabs.models.disabled = false;
    tabShown("models");
    tabs.models.focus();
  };
  const saved = async (button) => {
    const form = $("#modal-form");
    const json = {
      kind: kindSelect.value,
      name: form.elements.name.value,
      base_url: urlInput.value,
      api_key: keyInput.value,
      model: modelSelect.value,
      disable_thinking: form.elements.disable_thinking.checked,
    };
    const path = isNew ? "/api/llm/connections" : `/api/llm/connections/${Number(connection.connection_id)}`;
    const answer = await api(path, { method: isNew ? "POST" : "PUT", json, button });
    closeModal();
    status(`${answer.name} is saved.`, "success");
    await loadConnections();
  };
  [kindSelect, urlInput, keyInput].forEach((input) => input.addEventListener("input", endpointChanged));
  Object.entries(tabs).forEach(([name, button]) => {
    button.addEventListener("click", () => tabShown(name));
    // Arrow keys move between the tabs, as a tablist is expected to behave.
    button.addEventListener("keydown", (event) => {
      const other = name === "endpoint" ? "models" : "endpoint";
      if ((event.key === "ArrowRight" || event.key === "ArrowLeft") && tabs[other].disabled === false) {
        event.preventDefault();
        tabShown(other);
        tabs[other].focus();
      }
    });
  });
  openModal({
    title: isNew ? "Add a connection" : `Edit ${connection.name}`,
    isTall: true,
    content: [element("div", { class: "tabs", role: "tablist", "aria-label": "Connection steps" }, [tabs.endpoint, tabs.models]), panels.endpoint, panels.models],
    actions: [
      { label: "Cancel", kind: "button", onClick: closeModal },
      {
        label: "Connect",
        kind: "button primary",
        isSubmit: true,
        onClick: (button) => (dialog.tab === "endpoint" ? connected(button) : saved(button)),
      },
    ],
  });
  endpointChanged();
  tabShown("endpoint");
  kindSelect.focus();
}

// The endpoint's models as options; the one preferred is chosen when offered.
function modelOptions(select, models, preferred) {
  const chosen = models.includes(preferred) ? preferred : models[0];
  select.replaceChildren(...models.map((model) => element("option", { value: model, text: model, selected: model === chosen }, [])));
}

function connectionRemovalAsked(connection) {
  openModal({
    title: "Delete this connection?",
    content: [
      element("p", { class: "document-name", text: connection.name }, []),
      element("p", { class: "muted", text: "If the agent trades with it, the agent is off until you choose another." }, []),
    ],
    actions: [
      { label: "Cancel", kind: "button", onClick: closeModal },
      {
        label: "Delete",
        kind: "button danger",
        onClick: async (button) => {
          await api(`/api/llm/connections/${Number(connection.connection_id)}`, { method: "DELETE", button });
          closeModal();
          status(`${connection.name} was deleted.`, "success");
          await loadConnections();
        },
      },
    ],
  });
}

async function routingSaved(event) {
  event.preventDefault();
  const value = $("#llm-route-agent").value;
  try {
    await api("/api/llm/routing", {
      method: "PUT",
      json: { agent: value === "" ? null : Number(value) },
      button: $("#llm-routing-save"),
    });
  } catch (error) {
    failed(error);
    return;
  }
  status("The connection the agent trades with is saved.", "success");
}

// --- form fields -----------------------------------------------------------------

function field(label, input) {
  const id = `modal-field-${input.getAttribute("name")}`;
  input.setAttribute("id", id);
  return [element("label", { for: id, text: label }, []), input];
}

function checkbox(label, name, isChecked) {
  return element("label", { class: "check" }, [
    element("input", { type: "checkbox", name, checked: isChecked }, []),
    element("span", { text: label }, []),
  ]);
}

// --- the modal -----------------------------------------------------------------

// One in-app dialog for every question (never alert/confirm/prompt).
// Its frame is fixed by the stylesheet; showModal() keeps focus inside and Escape
// closes it; focus returns to whatever opened it.
function openModal(spec) {
  const dialog = $("#modal");
  state.modal = { returnFocus: document.activeElement, submit: null };
  $("#modal-title").textContent = spec.title;
  // A taller frame for a form that would otherwise scroll on a laptop screen.
  dialog.classList.toggle("is-tall", spec.isTall === true);
  $("#modal-body").replaceChildren(...spec.content);
  $("#modal-error").hidden = true;
  $("#modal-actions").replaceChildren(
    ...spec.actions.map((action) => {
      const button = element("button", { type: action.isSubmit === true ? "submit" : "button", class: action.kind, text: action.label }, []);
      const run = async () => {
        $("#modal-error").hidden = true;
        try {
          await action.onClick(button);
        } catch (error) {
          const message = $("#modal-error");
          message.textContent = error instanceof ApiError ? error.message : GENERIC_ERROR;
          message.hidden = false;
        }
      };
      if (action.isSubmit === true) {
        state.modal.submit = { run, button };
      } else {
        button.addEventListener("click", run);
      }
      return button;
    }),
  );
  dialog.showModal();
  const first = $("#modal-body input") || $("#modal-actions button");
  if (first !== null) {
    first.focus();
  }
}

function closeModal() {
  const dialog = $("#modal");
  if (dialog.open) {
    dialog.close();
  }
}

function modalSubmitted(event) {
  event.preventDefault();
  if (state.modal === null || state.modal.submit === null) {
    return;
  }
  const form = $("#modal-form");
  if (form.reportValidity() === false) {
    return;
  }
  state.modal.submit.run();
}

function modalClosed() {
  // The close event arrives a task after close(): a dialog re-opened in between
  // already holds new content, which this late event must not clear.
  if ($("#modal").open) {
    return;
  }
  const returnFocus = state.modal === null ? null : state.modal.returnFocus;
  state.modal = null;
  $("#modal-body").replaceChildren();
  $("#modal-actions").replaceChildren();
  if (returnFocus !== null && typeof returnFocus.focus === "function" && document.contains(returnFocus)) {
    returnFocus.focus();
  }
}

// --- wiring --------------------------------------------------------------------

function bound() {
  $$("[data-nav]").forEach((button) => {
    button.addEventListener("click", () => opened(button.dataset.nav));
  });
  $("#sign-out").addEventListener("click", signOut);
  $("#runs-from").addEventListener("change", loadRuns);
  $("#runs-to").addEventListener("change", loadRuns);
  $("#runs-range").addEventListener("submit", (event) => {
    event.preventDefault();
    loadRuns();
  });
  $("#runs-expand").addEventListener("click", () => runsFolded(true));
  $("#runs-collapse").addEventListener("click", () => runsFolded(false));
  document.addEventListener("visibilitychange", visibilityChanged);
  $("#link-form").addEventListener("submit", linkRequested);
  $("#link-confirm").addEventListener("click", linkConfirmed);
  $("#link-back").addEventListener("click", linkAbandoned);
  $("#llm-add").addEventListener("click", () => connectionAsked(null));
  $("#llm-routing-form").addEventListener("submit", routingSaved);
  $("#agent-run").addEventListener("click", agentStarted);
  $("#run-back").addEventListener("click", () => opened("agent"));
  $("#mcp-servers").addEventListener("toggle", (event) => {
    if (event.currentTarget.open) {
      loadServers();
    }
  });
  $("#sp500-refresh").addEventListener("click", sp500Refreshed);
  $("#company-search").addEventListener("submit", (event) => {
    event.preventDefault();
    companiesFiltered();
  });
  // Filtered as the owner types: the list is already here.
  $("#company-query").addEventListener("input", companiesFiltered);
  $("#company-sector").addEventListener("change", companiesFiltered);
  $("#modal-form").addEventListener("submit", modalSubmitted);
  $("#modal").addEventListener("close", modalClosed);
  $("#version-button").addEventListener("click", (event) => {
    const button = event.currentTarget;
    button.setAttribute("aria-expanded", button.getAttribute("aria-expanded") === "true" ? "false" : "true");
  });
}

function workerRegistered() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Without a worker the app still works; it just cannot be installed.
    });
  }
}

async function booted() {
  renderIcons(document);
  bound();
  workerRegistered();
  if (window.location.pathname === LINK_PATH) {
    shown("link");
    return;
  }
  await loadAccount();
}

document.addEventListener("DOMContentLoaded", booted);
