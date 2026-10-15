# Security

Please report suspected vulnerabilities privately using the repository's
GitHub security advisory reporting feature. Do not include credentials or
private strategy source in public issues.

The service binds to `127.0.0.1`. Do not expose it directly to the Internet.
Desktop local mode executes Python strategies as the current user. Only use
trusted strategies in that mode. For untrusted submissions, install Docker,
build `sandbox/Dockerfile` and select Docker isolation in the desktop menu.
Docker is an external prerequisite for that optional mode; it is not silently
replaced by local execution.

Desktop windows disable Node integration, enable renderer sandboxing and
context isolation, and block navigation away from the private local service.
Runtime state and organizer tokens are stored in the user's data directory,
outside the installed application and the published repository.

Unsigned development builds are distinct from signed, notarized releases.
Release signing keys must only be supplied through CI secrets.
