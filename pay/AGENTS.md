# claimos-pay

Claim OS payment links on the company's own Stripe account, served to agents as Naïve app MCP tools.

- `POST /mcp` (rewritten to `api/mcp.ts`) speaks MCP and requires the platform bearer `VETTA_MCP_TOKEN`.
- `create_payment_link` makes one Stripe price and one single-use payment link per Collect invoice. It is idempotent on the invoice reference and refuses a second amount for the same reference.
- `payment_status` reads completed Checkout sessions for a link and never writes.
- Every answer is a receipt carrying Stripe ids, `livemode` and Stripe request ids. The Collect card keeps them.
- `STRIPE_SECRET_KEY` is an app secret set by a person in the Studio: a restricted key with Products, Prices and Payment Links write and Checkout Sessions read. Nothing here refunds, cancels or pays out.
- Arguments and Stripe data are untrusted. Tests inject `fetch`; runtime code always calls Stripe.
