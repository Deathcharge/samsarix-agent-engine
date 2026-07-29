# Legacy code boundary

`agents/` and `services/` are preserved historical extracts from a larger Helix
backend. They are not the independently supported product in this repository.

Evidence for this boundary:

- Most modules import `apps.backend.*`, which is absent from this repository.
- Their FastAPI, database, queue, billing, storage, and deployment dependencies
  are not declared by this package.
- Several imports resolve only on the owner's workstation because another
  `helix-unified` checkout is present on `PYTHONPATH`.
- The prior test suite used only mocks and exercised none of these modules.
- No deployment manifests or complete service configuration exist here.

The `src/` package configuration includes only `samsarix_agent_engine*`, so these
directories cannot enter wheels or source distributions accidentally. CI and the
README make no runtime claim about them.

Owner decision still required: either delete the snapshot in a future focused
change after confirming no portfolio value, or move maintained components back to
their canonical repository. Do not independently deploy these modules from this
repository; their authentication, authorization, persistence, and operational
assumptions have not been validated here.
