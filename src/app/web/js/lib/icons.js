// Hand-drawn 24x24 stroke icons. One weight, one style.
import { html } from "./html.js";

const P = {
  briefing: '<rect x="3.5" y="3.5" width="7.5" height="8.5" rx="1.5"/><rect x="13" y="3.5" width="7.5" height="5" rx="1.5"/><rect x="13" y="11" width="7.5" height="9.5" rx="1.5"/><rect x="3.5" y="14.5" width="7.5" height="6" rx="1.5"/>',
  table: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M3.5 14.5h17M9 4.5v15"/>',
  users: '<circle cx="9" cy="8.5" r="3.2"/><path d="M3 19.5c.4-3.2 3-5 6-5s5.6 1.8 6 5"/><circle cx="17.2" cy="9.4" r="2.5"/><path d="M16.4 14.6c2.6-.1 4.3 1.5 4.6 4.4"/>',
  search: '<circle cx="10.8" cy="10.8" r="6.2"/><path d="m20 20-4.7-4.7"/>',
  scout: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/>',
  compare: '<path d="M5.5 20V11M12 20V4M18.5 20v-6.5"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  star: '<path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9 6.8 19.7l1-5.9L3.5 9.7l5.9-.8z"/>',
  database: '<ellipse cx="12" cy="6" rx="7.5" ry="3"/><path d="M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6M4.5 12v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6"/>',
  book: '<path d="M12 6.5C10.5 5 8 4.5 4 4.5v13c4 0 6.5.5 8 2 1.5-1.5 4-2 8-2v-13c-4 0-6.5.5-8 2zM12 6.5v13"/>',
  sun: '<circle cx="12" cy="12" r="3.8"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6"/>',
  moon: '<path d="M20 14.2A8 8 0 0 1 9.8 4a8 8 0 1 0 10.2 10.2z"/>',
  monitor: '<rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M8.5 20h7M12 16.5V20"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  chevronLeft: '<path d="m15 6-6 6 6 6"/>',
  arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  arrowUpRight: '<path d="M7 17 17 7M8 7h9v9"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.6v.1"/>',
  alert: '<path d="M12 4 21 19.5H3z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  trendUp: '<path d="M3.5 16.5 9 11l3.5 3.5 6-6.5M14.5 8h4.5v4.5"/>',
  trendDown: '<path d="M3.5 7.5 9 13l3.5-3.5 6 6.5M14.5 16h4.5v-4.5"/>',
  minus: '<path d="M6 12h12"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  sliders: '<path d="M5 7h9M18 7h1M5 17h1M10 17h9"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  download: '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"/>',
  refresh: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4.2h-4.2"/>',
  external: '<path d="M14 4.5h5.5V10M19.5 4.5 11 13M9.5 6H6a1.5 1.5 0 0 0-1.5 1.5V18A1.5 1.5 0 0 0 6 19.5h10.5A1.5 1.5 0 0 0 18 18v-3.5"/>',
  scatter: '<path d="M4 4v16h16"/><circle cx="9" cy="14" r="1.4"/><circle cx="13" cy="9.5" r="1.4"/><circle cx="17" cy="12.5" r="1.4"/><circle cx="8.5" cy="8" r="1.4"/>',
  list: '<path d="M8.5 6.5H20M8.5 12H20M8.5 17.5H20M4.5 6.5h.1M4.5 12h.1M4.5 17.5h.1"/>',
  grid: '<rect x="4" y="4" width="6.5" height="6.5" rx="1.2"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.2"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.2"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.2"/>',
  ball: '<circle cx="12" cy="12" r="8.5"/><path d="m12 8.2 3.3 2.4-1.3 3.9h-4l-1.3-3.9zM12 8.2V3.6M15.3 10.6l4.3-1.4M14 14.5l2.6 3.6M10 14.5l-2.6 3.6M8.7 10.6 4.4 9.2"/>',
  flag: '<path d="M5.5 21V4M5.5 5h11l-2 3.5 2 3.5h-11"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  pitch: '<rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="M12 5v14"/><circle cx="12" cy="12" r="2.8"/>',
  bolt: '<path d="M13 3 5.5 13.5H11L10 21l7.5-10.5H12z"/>',
  edit: '<path d="M5 19l.7-3.6L16 5.1a1.8 1.8 0 0 1 2.5 0l.4.4a1.8 1.8 0 0 1 0 2.5L8.6 18.3z"/>',
  trash: '<path d="M5 7h14M9.5 7V4.5h5V7M7 7l.8 12.5h8.4L17 7"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  shield: '<path d="M12 3.5 5 6v5.5c0 4.3 2.9 7.4 7 9 4.1-1.6 7-4.7 7-9V6z"/>',
  map: '<path d="M9 5 3.5 7v12L9 17l6 2 5.5-2V5L15 7z"/><path d="M9 5v12M15 7v12"/>',
  layers: '<path d="m12 4 8.5 4.5L12 13 3.5 8.5z"/><path d="m3.5 12.5 8.5 4.5 8.5-4.5"/>',
  play: '<path d="M8 5.5v13l10-6.5z"/>',
  pause: '<path d="M8.5 5.5v13M15.5 5.5v13"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  dictionary: '<path d="M6 4.5h10.5A1.5 1.5 0 0 1 18 6v13.5H7.5A1.5 1.5 0 0 1 6 18z"/><path d="M6 18a1.5 1.5 0 0 0 1.5 1.5M9.5 8.5h5M9.5 11.5h5"/>',
};

export function Icon({ name, size, class: klass = "", title }) {
  const inner = P[name] || P.info;
  return html`<svg class=${"icon " + (size || "") + " " + klass} viewBox="0 0 24 24" aria-hidden=${title ? undefined : "true"} role=${title ? "img" : undefined}
    dangerouslySetInnerHTML=${{ __html: (title ? `<title>${title}</title>` : "") + inner }}></svg>`;
}

