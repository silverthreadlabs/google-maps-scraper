# TDD Test Quality Rules

> These are project-global TDD rules vendored into this repo so collaborators
> get them on clone. The canonical source is `~/.claude/rules/tdd-rules.md`
> in the maintainer's environment; keep the two in sync when either changes.
>
> Examples below use TypeScript/React (Vitest, Testing Library) because that's
> where the rules were originally distilled. The **principles are
> framework-agnostic** — they map directly to Python (pytest, unittest), Go
> (`testing`), and any other test framework. Read past the syntax for the
> intent: assert contracts not implementation, falsifiable assertions, every
> error path tested same cycle, etc.

#### 1. Never mock the module under test

Mock **dependencies** (fetch, browser APIs, background messaging), not the module being tested. If a test mocks `lib/constants` and then asserts on the mocked values, it is self-fulfilling — it validates its own mock, not the real code. If there is nothing meaningful to mock, the module may not need a dedicated test; its consumers will cover it.

#### 2. Query elements the way a user finds them

Use semantic queries in this order of preference:

- `getByRole('button', { name: /send/i })` — accessible name
- `getByLabelText(...)` — form labels
- `getByText(...)` — visible text
- `getByPlaceholderText(...)` — input hints

Never use:

- `getAllByRole('button').at(-1)` — positional selection
- `container.querySelector('.some-tailwind-class')` — CSS class coupling
- `button.querySelector('.lucide-check')` — icon implementation detail
- `container.querySelectorAll('span')` — raw element counting (breaks on harmless refactors)

If no semantic query exists, **add accessibility attributes to the source** (`aria-label`, `role="status"`). This is not test-driven bloat — it is an accessibility improvement that also makes tests resilient. For example, `LoadingDots` uses `role="status" aria-label="Loading"` so tests query `getByRole('status', { name: 'Loading' })` instead of counting `<span>` elements.

#### 3. Assert the contract, not the implementation

Ask: "if this assertion fails, does a user-visible behavior break?" If the answer is "no, just styling changed", the assertion is too coupled.

Good — behavior:

- `expect(onSend).toHaveBeenCalledWith('Hello', 'context')`
- `expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()`
- `expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()`

Bad — implementation:

- `expect(button.className).toContain('bg-brand')`
- `expect(wrapper?.className).toContain('items-end')`
- `expect(container.querySelectorAll('span.animate-bounce')).toHaveLength(3)`

#### 4. Assert the intended state, not just the absence of other states

A test that only proves "X is not there" does not prove "Y is there." A blank screen satisfies every negative assertion. In TDD, the test must force you to write the intended behavior.

Bad — absence only:

```ts
// Loading test that a blank screen would pass
expect(screen.queryByTestId('chat-view')).not.toBeInTheDocument();
expect(screen.queryByTestId('auth-prompt')).not.toBeInTheDocument();
```

Good — presence + absence:

```ts
// Proves the loader IS rendered, then confirms other views are not
expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
expect(screen.queryByTestId('chat-view')).not.toBeInTheDocument();
expect(screen.queryByTestId('auth-prompt')).not.toBeInTheDocument();
```

**Rule of thumb:** Every `expect(...).not.toBeInTheDocument()` should be accompanied by at least one positive assertion about what _should_ be rendered in that state.

#### 5. Every assertion must be falsifiable

Before writing an assertion, mentally delete the feature from the source and verify the test would turn red. Patterns that produce unfalsifiable assertions:

- **Always-true:** `expect(container).toBeInTheDocument()` — render never returns a detached container
- **Wrong role:** `queryByRole('paragraph')` — `<p>` has no implicit ARIA role, so this always returns null
- **Too loose:** `buttons.length > 0` — passes even with unexpected extra buttons
- **True before the action:** asserting the button exists _after_ a click, when it already existed _before_ the click — the click changes nothing about the assertion. Before writing a post-action assertion, ask: "Would this pass if I deleted the action line?" If yes, it is vacuous.

#### 6. In variant/loop tests, assert the discriminating property

When iterating over variants, sizes, or cases, each iteration must assert something **unique to that variant** — the thing that distinguishes it from the others. An assertion that is true for every variant is decorative.

Bad — trivially true for all variants:

```ts
for (const variant of variants) {
    const button = screen.getByRole('button', { name: variant });
    expect(button.className.length).toBeGreaterThan(0); // base classes always present
}
```

Good — discriminating class per variant:

```ts
const variantClasses = {
    default: 'bg-primary',
    destructive: 'bg-destructive',
    ghost: 'hover:bg-accent',
};
for (const [variant, expectedClass] of Object.entries(variantClasses)) {
    const button = screen.getByRole('button', { name: variant });
    expect(button.className).toContain(expectedClass);
}
```

#### 7. Assert exact values at boundaries

At message-passing and URL-composition boundaries (background messages, API calls, events, navigation), assert the **complete value**, not a fragment.

Bad — loose fragment:

```ts
expect(sendToBackground).toHaveBeenCalledWith(expect.objectContaining({ type: 'OPEN_URL' }));
// or
expect(sendToBackground).toHaveBeenCalledWith({
    type: 'OPEN_URL',
    url: expect.stringContaining('/chat/abc'),
});
```

Good — exact composed value:

```ts
import { WEBAPP_BASE_URL, WEBAPP_CHAT_PATH } from '../../../lib/constants';
expect(sendToBackground).toHaveBeenCalledWith({
    type: 'OPEN_URL',
    url: `${WEBAPP_BASE_URL}${WEBAPP_CHAT_PATH}/abc`,
});
```

Import the same constants the source uses so the test stays in sync without hardcoding. A malformed base URL or missing field would pass the loose assertion silently.

#### 8. Write the assertion before the implementation

In TDD, write `expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()` **before** the button exists. This forces you to define the accessibility contract upfront, think about behavior (disabled vs enabled) rather than structure (last button in the tree), and keep the test independent of implementation you haven't written yet.

#### 9. Test every error path alongside the happy path

When you implement a `try/catch`, the test for the `catch` must be written in the same TDD cycle — not deferred to a "hardening pass" later. The same applies to `else` branches, early-return guards, and promise rejections. In practice this means each feature has _at least_ three tests:

1. **Happy path** — success response, valid input, expected state
2. **Failure path** — error response, rejected promise, thrown exception
3. **Boundary/guard path** — retry limit reached, stale-generation discard, cancelled flag

Bad — deferred:

```ts
// "I'll add error tests later"
it('saves chat on success', async () => {
    /* ... */
});
// ...months pass, catch block is never tested
```

Good — same cycle:

```ts
it('saves chat on success', async () => {
    /* ... */
});
it('shows error when save returns non-success', async () => {
    /* ... */
});
it('shows error when save throws', async () => {
    /* ... */
});
it('discards save result when conversation changed during save', async () => {
    /* ... */
});
```

If you write a `catch` without a test that enters it, or a guard like `if (attempts >= 3) return` without a test at the boundary, the TDD cycle is incomplete.

#### 10. Test state transitions, not static snapshots

A component test that renders and immediately asserts props on mocked children is a _wiring check_, not a _behavior test_. These tests are low-confidence because they can still pass after a meaningful user-facing break.

A good component test has an **action** between the render and the assertion — a click, an async resolution, a prop change, a timer advance.

Bad — static snapshot:

```ts
render(<Panel conversationUrl={url} />);
expect(capturedChatViewProps.conversationUrl).toBe(url);
```

Good — transition:

```ts
render(<Panel conversationUrl={url} />);
const scrapeButton = await screen.findByRole('button', { name: 'Pull chat from active tab' });
await user.click(scrapeButton);
await waitFor(() => {
    expect(capturedChatViewProps.scrapedMessage).toBe('scraped text');
});
```

If your test has no action between `render()` and `expect()`, ask: "Am I testing React's rendering, or my code's behavior?"

#### 11. Excessive mocking is a design signal

If testing a component requires 5+ `vi.mock()` calls just to render it, the component likely has too many responsibilities. Heavy mocking produces tests that validate mock wiring rather than real behavior.

When you hit this, extract before testing:

- **Pure logic** → standalone functions (testable with zero mocks)
- **Side-effectful logic** → custom hooks (testable with `renderHook`)
- **The component itself** → thin wiring layer that connects hooks to JSX

Example: `toChatMessages()` and `toUIMessages()` are already extracted from `ChatView` as pure functions — they're trivially testable without mocking React, transport, storage, or background messaging. Apply the same pattern to new stateful logic.

#### 12. One test per distinct behavior

Each `it()` block should test a behavior that can independently pass or fail. Don't split one logical check across multiple test blocks — this inflates test count without adding protection.

Bad — split:

```ts
it('returns loading: true initially', () => {
    const { result } = renderHook(() => useQuickReplies());
    expect(result.current.loading).toBe(true);
});
it('returns an empty quickReplies array initially', () => {
    const { result } = renderHook(() => useQuickReplies());
    expect(result.current.quickReplies).toEqual([]);
});
```

Good — one behavior:

```ts
it('returns loading: true and empty quickReplies initially', () => {
    const { result } = renderHook(() => useQuickReplies());
    expect(result.current.loading).toBe(true);
    expect(result.current.quickReplies).toEqual([]);
});
```

If two tests always pass or fail together, they describe one behavior and should be one test.

#### 13. Pre-commit checklist

Before considering a test done:

1. Does it fail if I break the feature?
2. Does it stay green if I refactor without changing behavior?
3. Am I querying by role/label/text, not by position/class/structure?
4. Am I asserting the outcome (callback args, visible text, disabled state), not the implementation (CSS classes, DOM shape, icon SVG)?
5. Do I have at least one positive assertion (`getBy*`) for every state I'm testing, not just negative ones (`queryBy*.not`)?
6. Would every assertion fail if I deleted the action or feature it claims to test? (Was it already true before the action?)
7. If looping over variants/cases, does each iteration assert something unique to that variant?
8. If testing a message/API call, did I assert the full payload with exact values?
9. Is the riskiest logic actually executing, or am I only testing prop wiring through mocked children? If a function is passed to a mocked API (e.g. `executeScript`, `setTimeout` callback), the function itself is untested — extract it and test it directly.
10. Does every defensive guard (`if (cancelled)`, stale check, retry limit) have a test that would fail without it?
11. For async/stateful components, am I testing state transitions (loading -> loaded, empty -> populated, streaming -> ready), not just static renders?
12. Does every `try/catch` have a test that exercises the `catch`? Does every async call (promise, `sendToBackground`) have a rejection test?
13. If I needed 5+ mocks just to render this component, should I extract logic into a testable function or hook instead?
14. Does each `it()` block test a distinct user-visible behavior, or am I inflating test count by splitting one check across multiple blocks?
