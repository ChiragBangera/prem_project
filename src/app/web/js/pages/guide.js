// Guide: where every chart and feature lives, and how to read the colours.
import { html } from "../lib/html.js";
import { href } from "../lib/router.js";
import { FEATURES } from "../lib/help.js";
import { Card, PageHead, useDocumentTitle } from "../ui/common.js";

export default function Guide() {
  useDocumentTitle("Guide");
  return html`<div class="stack" style=${{ "--gap": "24px" }}>
    <${PageHead} eyebrow="Guide" title="Where to find things" sub="Every chart and feature, where it lives, and what it is for. Look for the (i) button next to a chart title for what it shows, what good looks like and what to watch for." />
    <${Card} title="How to read the colours">
      <div class="stack" style=${{ "--gap": "8px" }}>
        <p><b>Blue</b> means above expectation and <b>orange</b> means below. Neither is good or bad on its own: a team with far more points than its chances deserve is blue, and that is usually luck that fades.</p>
        <p><b>Percentile bars</b> always read higher is better. 50 is average, 90 is better than nine in ten comparable players or teams.</p>
        <p><b>Small sample</b> means few minutes or games. Treat those numbers as a hint, not a verdict.</p>
      </div>
    </${Card}>
    <${Card} title="Pitch drawings in this version">
      <p>There are two: the <b>player shot map</b> and the <b>match shot map</b>. There are no team shot maps, heat maps or pass maps yet.</p>
    </${Card}>
    <${Card} title="Find a chart or feature" flush>
      <div class="guide-list" style=${{ padding: "4px 20px 12px" }}>
        ${FEATURES.map((f) => html`<div class="guide-item" key=${f.name}>
          <div><a class="link" href=${href(f.href)}><b>${f.name}</b></a><div class="where">${f.where}</div></div>
          <div>${f.what}</div>
        </div>`)}
      </div>
    </${Card}>
  </div>`;
}
