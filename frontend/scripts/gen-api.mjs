// Generates src/api/schema.d.ts from the backend's OpenAPI description, and
// src/api/messages.json from the backend's message catalog (NFR-10).
// CI regenerates both and fails if the committed files differ (API drift check).
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const backend = resolve(here, "../../backend");
const openapiFile = resolve(here, "../src/api/openapi.json");

const python = process.env.PYTHON ?? "python";
const spec = execFileSync(
  python,
  [
    "-c",
    [
      "import json",
      "from yap.api.app import create_app",
      "from yap.api.settings import Settings",
      "app = create_app(Settings(database_url='sqlite://', migrate_on_startup=False))",
      "print(json.dumps(app.openapi(), indent=2, sort_keys=True))",
    ].join("; "),
  ],
  {
    cwd: backend,
    encoding: "utf8",
    env: { ...process.env, APP_VERSION: "0.0.0", APP_COMMIT: "-" },
  },
);
writeFileSync(openapiFile, spec);
const messages = execFileSync(
  python,
  [
    "-c",
    [
      "import json",
      "from yap.messages import CATALOG",
      "print(json.dumps(CATALOG, indent=2, sort_keys=True, ensure_ascii=False))",
    ].join("; "),
  ],
  { cwd: backend, encoding: "utf8" },
);
writeFileSync(resolve(here, "../src/api/messages.json"), messages);
execFileSync(
  resolve(here, "../node_modules/.bin/openapi-typescript"),
  // fields with a default value stay optional in request bodies
  [openapiFile, "--default-non-nullable", "false", "-o", resolve(here, "../src/api/schema.d.ts")],
  { stdio: "inherit" },
);
