# Security and deployment history

## Security boundary

A later audit found that the original service exposed private API/tool surfaces without a
sufficient application authentication boundary and did not bind sessions strongly enough
to an authenticated owner.

The repair changed the service boundary rather than only adding endpoint checks:

- bearer authentication is required for protected API/tool access;
- sessions are partitioned by authenticated owner;
- the default server bind is loopback;
- public binding fails closed unless application authentication is configured;
- deployment helpers preserve the application authentication requirement;
- regressions cover missing auth, cross-owner session access, and public-bind behavior.

The relevant audit/fix history is visible in
`fix: close public API and session ownership P0 (#2)`.

Local inference can keep model requests on the Ollama host. That does **not** mean every
optional adapter is offline: external business/WhatsApp integrations may transmit data to
their configured services.


[Current guide](../README.md)
