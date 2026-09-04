# Security Policy

This integration sends keystrokes to a physical alarm panel, including
installer-mode programming that affects fire/UL-safety behaviour. Please
treat anything that could bypass the confirmation gates, leak panel codes,
or send unintended keystrokes as a security issue.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Use GitHub's private vulnerability reporting instead:

<https://github.com/heidrickla/ha-envisalink-field-programmer/security/advisories/new>

Include what you can of: the panel model and Envisalink firmware, the
integration version, the affected component or service, and steps to
reproduce. You will get an acknowledgement as soon as the report is read,
and a fix or mitigation as quickly as the severity warrants.

## What counts as a security issue

- Any way to reach installer-mode programming without the explicit
  `confirm_installer_risk` confirmation, or to bypass the keystroke guard.
- Installer codes, user codes, or the Envisalink password appearing in
  logs, diagnostics downloads, error messages, or entity attributes.
- Keystrokes being sent to a partition, zone, or panel other than the one
  the user targeted.
- Anything that lets an unauthenticated network peer drive the panel
  through this integration.

Bugs that cause a command to fail safely (nothing sent, an error raised)
are ordinary bugs and can go in the public issue tracker.

## Supported versions

Only the latest release on `main` receives security fixes.

## Scope notes

- The Envisalink TPI protocol itself is plaintext TCP on your LAN. This
  integration does not and cannot add encryption to it; keep the
  Envisalink on a trusted network segment.
- Home Assistant's own authentication and access control are outside this
  project's scope; report those to the Home Assistant project.
