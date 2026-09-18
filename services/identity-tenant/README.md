# identity-tenant

Owns users, organizations, memberships, RBAC, and OAuth/session policy. The
Python implementation is in `services/identity_tenant/`; the hyphenated
directory remains the deployable service ownership marker.

The boundary consumes server-resolved Better Auth sessions, validates Google
callback transactions exactly once, and denies missing or cross-tenant scope.

