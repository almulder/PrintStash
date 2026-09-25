# App-store catalogues

Source manifests for the stores that list PrintStash. Each one runs the
single-container image described by the root [`docker-compose.yml`](../docker-compose.yml)
and is submitted to that store's own repository. The Unraid template lives in
[`templates/printstash.xml`](../templates/printstash.xml), which Community
Applications reads directly.

| Store | Files | First administrator |
| --- | --- | --- |
| Unraid | `templates/printstash.xml` | Optional username/password fields; blank fields register in the browser |
| Runtipi | `runtipi/printstash/` | Required install-form fields, so the owner exists before the app serves a request |
| Umbrel | `umbrel/printstash/` | Umbrel's per-app credentials (`defaultUsername`, `deterministicPassword`), shown on the app's page |
| CasaOS / ZimaOS | `casaos/PrintStash/` | Optional variables in the install dialog; blank fields register in the browser |

All of them map the store's form or credentials to `VAULT_SETUP_ADMIN_*`, which
creates the administrator once at first start (see
[first use](../docs/first-run.md#an-administrator-from-the-deployment)). The
administrator then signs in and chooses storage in the browser.

`backend/tests/repo/test_catalogue_manifests.py` checks that every manifest runs
the unified image at the current app version, persists `/data`, enables
`trusted_network`, never passes `VAULT_JWT_SECRET`, and wires the administrator
settings.

## Releasing

The release commit bumps every manifest to the new version (the test above fails
until it does), then each store is updated with its own pull request:

- **Runtipi:** copy `runtipi/printstash/` to `apps/printstash/` in
  [runtipi-appstore](https://github.com/runtipi/runtipi-appstore), add
  `metadata/logo.jpg` exported from [`icon.svg`](../icon.svg), increment
  `tipi_version`, and set `updated_at`.
- **Umbrel:** copy `umbrel/printstash/` to
  [umbrel-apps](https://github.com/getumbrel/umbrel-apps), pin `image` by digest
  (`…:X.Y.Z@sha256:…`), add the gallery images, and fill in `submission`.
- **CasaOS / ZimaOS:** copy `casaos/PrintStash/` to `Apps/PrintStash/` in
  [CasaOS-AppStore](https://github.com/IceWhaleTech/CasaOS-AppStore) with the
  icon and screenshots.
- **Unraid:** nothing to submit; Community Applications re-reads the template.
  It deliberately tracks `:latest`, the Community Applications convention, so it
  is the one manifest the version test does not pin.

The ports in `config.json` (Runtipi), `umbrel-app.yml` (Umbrel) and the
published port in the CasaOS compose file are host ports that must be unique
within each store; a store reviewer may assign different ones.

The Umbrel service uses `restart: unless-stopped` where that store usually uses
`on-failure`: a restart requested from Settings is a graceful exit that can
return status 0, which `on-failure` would not relaunch. Mention this in the
submission.
