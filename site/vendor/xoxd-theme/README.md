# xoxd-theme

The public xoxd.ai design tokens as the Bazel module `xoxd_theme`.
Version0.1.1 is a narrow public export; source repository history remains
private. `//:pkg` contains the licensed theme, palette, prepaint script,
fonts, and package metadata for a Bazel `npm_link_package` consumer.

The existing xoxd-ai/bazel-registry carries its immutable public release
archive with an integrity checksum. No parallel npm registry is involved.
The font faces require serving `fonts/*.woff2` at `/fonts/` in the site.
