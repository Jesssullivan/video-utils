# xoxd public chrome

A shared Svelte 5 navigation, footer, and theme picker exported from
site.scaffold. Bazel module `xoxd_public_chrome` supplies `//:pkg`; link it
as `@xoxd/public-chrome` with `npm_link_package`. This package metadata
supports the Bazel link only; no npm registry publication is required.

Import components from `@xoxd/public-chrome`, and import its `styles.css`
after Tailwind and Skeleton. Import `@xoxd/theme/theme/theme-xoxd.css`,
`fonts.css`, `tailwind.css`, and `base.css` from `xoxd_theme`. Copy the
licensed theme font files to the site's `static/fonts/`.

Navigation accepts `identity`, `pathname`, `navLinks`, optional `quickLinks`
and `externalLinks`, an optional `action` (`label`, `onselect`), and `brand`,
`trailing`, and `mobileSection` Svelte snippets. Mobile sections receive a
close callback. Footer accepts `identity`, `tagline`, `description`,
`sections`, and `provenance`/`accent`/`contact` snippets. Sites own their words,
authentication dialogs, provenance, and routes.

The singleton `theme` store powers every picker placement. `FOUC_SCRIPT`
from the `/fouc` export applies the same six themes and dark default before
paint; inject the escaped script at build time rather than maintaining a
second list in an application.
