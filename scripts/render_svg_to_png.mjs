import { readFile } from "node:fs/promises";
import sharp from "sharp";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key ?? ""}`);
    }
    args[key.slice(2)] = value;
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));

if (!args.input || !args.output) {
  throw new Error("Usage: node render_svg_to_png.mjs --input input.svg --output output.png");
}

const svg = await readFile(args.input);
await sharp(svg, { density: Number(args.density || 144) })
  .png({ compressionLevel: 9, adaptiveFiltering: true })
  .toFile(args.output);
