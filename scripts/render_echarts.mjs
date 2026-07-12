import fs from "node:fs/promises";
import * as echarts from "echarts";

function readArg(flag) {
  const index = process.argv.indexOf(flag);
  if (index === -1 || index + 1 >= process.argv.length) {
    return null;
  }
  return process.argv[index + 1];
}

const inputPath = readArg("--input");
const outputPath = readArg("--output");
const widthArg = readArg("--width");
const heightArg = readArg("--height");

if (!inputPath || !outputPath) {
  console.error("Usage: node render_echarts.mjs --input spec.json --output chart.svg [--width 1200] [--height 675]");
  process.exit(1);
}

const width = Number(widthArg || 1200);
const height = Number(heightArg || 675);

const raw = await fs.readFile(inputPath, "utf8");
const payload = JSON.parse(raw);
const option = payload.echarts_option;

if (!option) {
  console.error("Input payload must include an 'echarts_option' field.");
  process.exit(1);
}

const chart = echarts.init(null, null, {
  renderer: "svg",
  ssr: true,
  width,
  height,
});

chart.setOption(option);
const svg = chart.renderToSVGString();
chart.dispose();

await fs.writeFile(outputPath, svg, "utf8");
