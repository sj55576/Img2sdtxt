# Vendored third-party assets

## `axe.min.js`

- Source: [axe-core](https://github.com/dequelabs/axe-core) v4.13.0, downloaded from
  `https://registry.npmjs.org/axe-core/-/axe-core-4.13.0.tgz` (`package/axe.min.js`).
- License: Mozilla Public License 2.0 (Deque Systems, Inc.) — see `axe-core-LICENSE`.
- SHA-256: `c24f097bd2f451d4f933e8bc7d8d539f8672a2ebcb5cc9f9f3eec8ca9470a0c1`
- Why vendored instead of installed via a package manager: this project has no
  Node.js/npm toolchain (the frontend is plain HTML/CSS/JS), and CI runs without
  outbound access to arbitrary CDNs. Vendoring a pinned, hash-verified copy avoids
  adding either dependency for a single test file (`tests/test_a11y.py`).
- To update: fetch a newer `axe-core-X.Y.Z.tgz` from the npm registry, replace this
  file with `package/axe.min.js` from the tarball, update the version/hash above, and
  re-run `tests/test_a11y.py` to confirm the new ruleset still passes (or triage any
  newly detected violations).
