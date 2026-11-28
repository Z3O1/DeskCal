# Licensing of the embedded Anki fork

## Original DeskCal

The original DeskCal code by HANSEIDON remains under the MIT license reproduced
in `LICENSE`. Its copyright and permission notice must be preserved. This fork
does not remove or replace those grants for the upstream code.

## Embedded integration and combined distribution

The new embedded Anki integration is licensed under GNU AGPL version 3 or later.
The combined application incorporating the official Anki core/reviewer is
redistributed under AGPL-3.0-or-later. The full text is in `COPYING`.

Anki's original copyright and component exceptions are reproduced in
`licenses/Anki-LICENSE.txt`; see also `THIRD_PARTY_NOTICES.md`. This fork is not
an official Anki release and does not claim endorsement by Anki Software, LLC.

The packaging scripts retain the original notices and include:

- This fork's application sources, dependency declaration and build scripts.
- The matching upstream `anki-26.09.2-source.tar.gz`, including the core/reviewer
  sources and upstream build recipes, plus the source URL and SHA-256 manifest.
- License/copyright files from the bundled Python dependency wheels.

When publishing a binary, provide its corresponding source with the binary or
through an AGPL-compliant distribution method, including any later modifications
and required build/dependency sources. Recheck the complete dependency notices
and source obligations for the actual build you distribute. Do not publish only
an opaque executable with an MIT label or strip the bundled source/license files.

No personal collection, card media, installed add-on configuration, API key, or
profile is part of the source or distribution package.
