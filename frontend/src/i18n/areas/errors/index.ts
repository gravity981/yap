import catalog from "../../../api/messages.json" with { type: "json" };
import { de as accounts } from "./accounts";
import { de as general } from "./general";
import { de as investments } from "./investments";
import { de as prices } from "./prices";
import { de as reviews } from "./reviews";

// Messages of the backend by code (NFR-10). The English texts are the backend's own
// templates (src/api/messages.json, from npm run gen:api); the German ones are written per
// group, like the backend's catalogs. A missing German text fails tsc.

export type MessageCode = keyof typeof catalog;

/** "{name}" in the backend's templates is "{{name}}" for i18next. */
function toI18next(template: string): string {
  return template.replace(/\{(\w+)\}/g, "{{$1}}");
}

export const en = Object.fromEntries(
  Object.entries(catalog).map(([code, template]) => [code, toI18next(template)]),
) as Record<MessageCode, string>;

export const de: Record<MessageCode, string> = {
  ...general,
  ...accounts,
  ...investments,
  ...reviews,
  ...prices,
};
