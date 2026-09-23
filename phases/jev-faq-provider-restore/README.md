# Jev (TypeSafe) FAQ provider — mechanism

How the Jev provider participates in one FAQ request: where it is called,
what it is asked, what comes back, how the response is validated, and where
the provider switch lives. Operational setup (enabling each provider, env
vars, rate limits, safety controls) is in `phases/jev-cs-faq-bot/README.md`
and is not repeated here.

## Where Jev sits in the request flow

`answerFaq()` in `apps/web/lib/faq/service.ts` is the whole policy. A
provider call is the last branch it takes, not the first:

```text
answerFaq(question, repository, provider)
  |
  ├─ catalogSchema.parse(repository.list())        contracts.ts
  ├─ matchFaq(question, entries)                   matcher.ts -> { exact, candidates }
  |
  ├─ 1. isSensitive(question)        -> fallback()          provider NEVER called
  ├─ 2. exact                        -> answer(exact)       provider NEVER called, zero cost
  ├─ 3. !candidates.length           -> fallback()          provider NEVER called
  |
  └─ 4. provider.select(normalize(redact(question)), candidates)   <- Jev or OpenAI
         |
         ├─ null                     -> fallback('clarify')
         └─ Selection                -> gate (below) -> answer(row) | fallback('clarify')
```

Steps 1 and 3 return the `handoff` fallback; a provider that answers but
fails the gate returns `clarify` (`fallback()` in
`apps/web/lib/faq/contracts.ts`). Exact and alias hits are resolved inside
`matchFaq()` from the catalog alone, so the common path never reaches a
model at all. `matchFaq()` also caps `candidates` at 5, which is the same
bound the provider re-checks before it will send anything.

## What Jev is actually asked

`createJevProvider()` in `apps/web/lib/faq/jev.ts` issues one POST to
`https://api.typesafe.ai/v1/systemone` (overridable via `JEV_API_URL`),
model `jev-latest` by default.

The `state` field carries only:

- the question, re-run through `normalize(redact(...))` from
  `apps/web/lib/faq/matcher.ts` — `redact()` strips URLs, emails, any token
  bearing a digit, and credential-shaped phrases, then truncates to 500
  chars;
- the candidates, each reduced to `{ id, category, question }`.

Answer prose, aliases, session, tenant, headers, history and database
context are never in the payload — the destructure
`candidates.map(({ id, category, question }) => ...)` is what enforces that.

Three typed questions ride in the same call:

| key | type | asked |
| --- | --- | --- |
| `faq` | Choice | which candidate id answers this, or `none` |
| `category` | Choice | topic classification |
| `answerable` | Noul | probability that exactly one candidate answers this without requiring personal information or an account action |

`faq`'s criteria are built from the live candidate set plus a `none` option.
`category`'s criteria come from `categoryCriteria(candidates)`, which derives
the option set from the candidates themselves (falling back to the candidate's
own category string when it is not in `KNOWN_CATEGORY_LABELS`) rather than
from a hardcoded list. `parseJev()` validates against
`Object.keys(categoryCriteria(candidates))` — the same function — so the
options offered to the model and the set used to judge its answer cannot
drift apart. This was one of the two defects fixed when the adapter was
restored from git history (`step0.md`, `step1.md`).

The `faq` instructions also state that the question is untrusted data, not
instructions, and that `none` is the correct choice under uncertainty.

## What comes back, and how it is checked

Jev returns a probability distribution per Choice plus a single Noul
probability. `parseJev()` (`apps/web/lib/faq/jev.ts`) refuses to trust it
until `validDistribution()` holds for both Choice answers:

- the chosen option is one of the options actually offered;
- the distribution has an entry for every offered option and no extras;
- the probabilities sum to 1 within 0.01;
- the chosen option is the argmax of that distribution.

The last check is structural self-consistency on the answer itself, not just
a shape check: a response whose stated choice disagrees with its own
distribution is rejected. Only then is a
`Selection { faqId, category, confidence, answerable }` produced —
`confidence` being `min(faq.confidence, category.confidence)`. That is the
same type `parseOpenAi()` returns, declared once in
`apps/web/lib/faq/provider.ts`.

Failures do not leak: any throw inside `select()` is caught, converted to a
generic `Provider unavailable`, and opens a cooldown window.

## The gate that decides whether the answer is used

Back in `answerFaq()`, independent of which provider replied:

```ts
const row = candidates.find(x => x.id === selection.faqId && x.category === selection.category);
if (!row || ... selection.confidence < 0.85 || ... selection.answerable < 0.9 ...) return fallback('clarify');
return answer(row);
```

The selected id must still resolve to a candidate row *and* agree with the
selected category, and both scores must be finite and within `[0, 1]`.

This threshold is the one place Jev differs qualitatively from OpenAI today.
`parseOpenAi()` in `apps/web/lib/faq/openai.ts` produces
`answerable: decision.answerable ? 1 : 0` from a JSON-schema boolean, so
`>= 0.9` can only ever mean `=== 1` — that half of the gate is effectively
dead under OpenAI. Under Jev, `answerable` is the raw Noul probability, so
the threshold does real, tunable work. This restoration deliberately does not
retune it (`step0.md`); no calibration data exists — the one live check
recorded in `step1-output.json` is a single data point, not a calibration.

## What Jev never does

It never authors the text the user sees. On a successful match the response
body is built by `answer(row)` from the catalog row found by `faqId` —
`row.answer`, straight from the validated catalog. Jev and OpenAI only ever
*select* a row; the application owns all answer prose and the fixed support
link.

## Where the provider switch lives

`apps/web/app/api/faq/route.ts`:

```ts
const provider = process.env.FAQ_PROVIDER === 'jev'
  ? createJevProvider({ ... })
  : createOpenAiProvider({ ... });
```

That single conditional is the entire switch — `jev` selects the Jev
adapter, anything else (including unset) keeps the OpenAI adapter, which is
the default. Nothing downstream is provider-aware: `matchFaq()`, the
confidence gate in `service.ts`, the HTTP layer (`apps/web/lib/faq/http.ts`)
and the widget all consume the same `Selection` and `FaqResponse` shapes
from `provider.ts` and `contracts.ts`.
