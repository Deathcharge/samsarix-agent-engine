# Historical code boundary

The current checkout contains only the standalone Samsarix Agent Engine product.

On 2026-08-08, 160 tracked files under `agents/` and `services/` were removed after
verification showed they were non-distributed extracts from a larger Helix/Samsarix
application and that the related repositories still exist. Keeping those copies in
this SDK created ownership, security-audit, licensing, and contributor ambiguity.

## Recovery and ownership

- The exact removed path ledger and regression analysis are recorded in
  [Historical snapshot disposition](SNAPSHOT_DISPOSITION.md).
- Git commit `c709e2b` is the last branch commit before removal, so repository
  archaeology remains possible without keeping duplicate code in the working tree.
- Canonical application behavior belongs in its owning repository, not in a restored
  snapshot here.
- Do not copy or restore the removed directories into this package. Use a public,
  versioned dependency or adapter if a future integration is required.

## Enforced boundary

- Packaging includes only `src/samsarix_agent_engine*`.
- Wheel and sdist checks reject `agents/`, `services/`, and the historical import
  namespace.
- Manifest pruning remains as defense in depth if those names are accidentally
  reintroduced.
- Security and release claims cover the current package and CLI, not historical
  revisions or another repository's deployment.
