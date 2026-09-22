UPDATE "pricing_options"
SET
  "currency" = 'KRW',
  "updated_at" = now()
WHERE "id" IN (
  'option-starter-monthly',
  'option-starter-yearly',
  'option-pro-monthly',
  'option-pro-yearly',
  'option-lifetime-onetime'
)
  AND "currency" = 'USD';
--> statement-breakpoint
UPDATE "pricing_catalog_settings"
SET "currency" = 'KRW', "updated_by" = 'toss-catalog-krw', "updated_at" = now()
WHERE "id" = 'platform' AND "currency" = 'USD';
