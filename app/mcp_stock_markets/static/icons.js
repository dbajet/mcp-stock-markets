"use strict";

// Inline SVG constants (no CDN). They follow the text color
// through currentColor, so both themes get them for free.
const SVG_OPEN = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" focusable="false">';
const SVG_CLOSE = "</svg>";

const ICONS = {
  logo: '<svg viewBox="0 0 64 64" width="28" height="28" focusable="false"><rect width="64" height="64" rx="14" fill="var(--accent)"/><path d="M14 44l12-12 9 8 15-17" fill="none" stroke="var(--accent-text)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><path d="M40 23h10v10" fill="none" stroke="var(--accent-text)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  trash: SVG_OPEN + '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/>' + SVG_CLOSE,
  sun: SVG_OPEN + '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>' + SVG_CLOSE,
  moon: SVG_OPEN + '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>' + SVG_CLOSE,
  gear: SVG_OPEN + '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>' + SVG_CLOSE,
  logout: SVG_OPEN + '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>' + SVG_CLOSE,
  plus: SVG_OPEN + '<path d="M12 5v14M5 12h14"/>' + SVG_CLOSE,
  tag: SVG_OPEN + '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1"/>' + SVG_CLOSE,
  search: SVG_OPEN + '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>' + SVG_CLOSE,
  pencil: SVG_OPEN + '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4z"/>' + SVG_CLOSE,
  mail: SVG_OPEN + '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 6-10 7L2 6"/>' + SVG_CLOSE,
  refresh: SVG_OPEN + '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>' + SVG_CLOSE,
  back: SVG_OPEN + '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>' + SVG_CLOSE,
  check: SVG_OPEN + '<path d="M20 6 9 17l-5-5"/>' + SVG_CLOSE,
  wallet: SVG_OPEN + '<path d="M20 7H5a2 2 0 0 1 0-4h13v4"/><path d="M3 5v14a2 2 0 0 0 2 2h15V7"/><circle cx="16" cy="14" r="1.5"/>' + SVG_CLOSE,
  chart: SVG_OPEN + '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 6-6"/>' + SVG_CLOSE,
  bot: SVG_OPEN + '<rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 4v4"/><circle cx="12" cy="3" r="1"/><path d="M9 13h.01M15 13h.01M9 17h6"/>' + SVG_CLOSE,
  list: SVG_OPEN + '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>' + SVG_CLOSE,
  play: SVG_OPEN + '<path d="m7 4 13 8-13 8z"/>' + SVG_CLOSE,
  alert: SVG_OPEN + '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>' + SVG_CLOSE,
};
