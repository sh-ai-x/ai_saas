Status: completed
Name: sandbox-checkout-handoff

## Objective

Close the provider-specific sandbox handoff gap without weakening the common
adapter contract. Toss must launch its browser SDK from a server-created order
context; Lemon Squeezy must create a hosted checkout against explicit store and
variant IDs. Redirects remain UX signals, while signed provider events remain
the entitlement and credit authority.

## Plan

1. Extend the provider-neutral checkout response with an opaque,
   browser-safe `checkout_context`.
2. Add Toss client-key/order/amount/redirect context and browser SDK launch.
3. Add Lemon Squeezy store/variant JSON:API relationships and custom order
   correlation, with configured resource checks on webhooks.
4. Add safe Toss success/fail and Lemon redirect routes.
5. Add fixture tests for checkout shape, secret exclusion, relationships, and
   mismatched variant rejection.
6. Update provider examples, setup guides, SOT, PRD, and release evidence.

## Acceptance criteria

- No server secret is present in a checkout response or browser context.
- Toss context contains only the client key, immutable order/amount data, and
  configured redirect URLs; the browser invokes the SDK.
- Lemon checkout requests contain explicit store and variant relationships and
  internal order correlation in `checkout_data.custom`.
- Provider redirects never grant credits directly.
- 93 Python tests, local verification, and the Next.js lint/build pass.
