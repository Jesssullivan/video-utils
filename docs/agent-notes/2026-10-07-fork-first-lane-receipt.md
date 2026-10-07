# Fork-first contributions rule: video-utils lane preserved (2026-10-07)

```
actor: /root video-utils-d6 (Claude, neo)
target: Jesssullivan/video-utils main (private, operator-owned; no upstream, no fork relationship)
reason: the estate fork-first rule prefers a signed fork branch plus a reviewed upstream PR, and
        preserves a lane that was already authorized when it carries a dated receipt
ruling: R-HOOK-CONVERGENCE-20261004 (TIN-3692 comment 98cf680c-7299-4949-bfb2-60079053ad43), R-N13;
        repo-local AGENTS.md ("Contributors own named files; root integrates and publishes") wins
prior_state: operator prompt 2026-10-06 authorized admin merging by root; S2 and S3 used signed
        root merge commits to main (card subkey D34D0D8F65EE5C88), one hosted CI run per merge
result: lane preserved as already authorized. Signed --no-ff root merges to main continue for
        this repository. Changes to CI or the flake are proven on a pushed branch first.
        Contributions to any sibling or third-party repository are out of scope here and would
        follow fork-first.
```

Not a new authorization: this records the existing one against the new rule.
