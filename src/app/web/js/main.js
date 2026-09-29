import { html, render } from "./lib/html.js";
import { App } from "./app.js";

render(html`<${App} />`, document.getElementById("root"));
