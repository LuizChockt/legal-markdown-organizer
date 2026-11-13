# Security

This is a small local CLI in the 0.2 development series. Fixes are prepared against
the latest default branch; there is no commitment to maintain older versions.

Do not put credentials, private notes, legal documents, personal paths or real
client/case data in public issues, attachments or pull requests. Use a minimal
synthetic reproduction.

For a vulnerability that needs private disclosure, use **Security → Advisories →
Report a vulnerability** if that option is enabled. If it is unavailable, open an
issue containing only a request to establish a private reporting channel; withhold
the exploit and sensitive details until the maintainer provides one.

Document processing is local. Review the scope and filesystem limitations in the
[reference guide](docs/reference.md) before using the tool on important originals.

Execution manifests in `.legal-organizer/` contain private filenames, file
identities, hashes and error messages. They are local recovery records, not
backups or authenticated evidence. Keep them private and do not edit them.
The tool rejects unsafe paths, symlinks, Windows reparse points, overwritten
original paths and changed file fingerprints. POSIX access uses no-follow
directory descriptors; Windows uses identity/reparse checks. Local filesystem
identities, locking and atomic replacement are required. Close editors and sync
clients before moving documents. These checks cannot defend against a malicious
process with the same filesystem permissions or guarantee recovery after power
loss on every filesystem. See [recovery details](docs/history.md).

The release workflow has repository-content write permission only in its release
job, after the entire Tests workflow succeeds for a push to this repository's
`main`. It checks out that exact tested SHA, refuses to replace an existing tag
and publishes only version 0.2.0. Pull-request and fork runs cannot publish.
