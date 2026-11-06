// Collects the license texts of the libraries in the built frontend (production
// dependencies) into one file, which the image serves next to the app: MIT and similar
// licenses require their text to go along with every copy.
//
//   node scripts/third-party-licenses.mjs <output file>
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const output = process.argv[2];
if (!output) {
  console.error("usage: node scripts/third-party-licenses.mjs <output file>");
  process.exit(2);
}

const dirs = execFileSync("npm", ["ls", "--omit=dev", "--all", "--parseable"], {
  encoding: "utf8",
})
  .trim()
  .split("\n")
  .slice(1); // the first line is the project itself

const seen = new Set();
const sections = [];
for (const dir of dirs) {
  const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
  const id = `${pkg.name}@${pkg.version}`;
  if (seen.has(id)) continue;
  seen.add(id);
  const file = readdirSync(dir).find((f) => /^(licen[cs]e|copying)(\.|$)/i.test(f));
  const text = file ? readFileSync(join(dir, file), "utf8").trim() : `License: ${pkg.license}`;
  sections.push(`${id} (${pkg.license ?? "unknown"})\n\n${text}`);
}
sections.sort();
writeFileSync(
  output,
  "Third-party software in the YAP frontend\n" +
    "=".repeat(56) +
    "\n\n" +
    sections.join(`\n\n${"-".repeat(72)}\n\n`) +
    "\n",
);
console.log(`${sections.length} packages -> ${output}`);
