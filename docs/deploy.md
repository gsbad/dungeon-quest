# Deploy

Dungeon Quest runs on a single Oracle Cloud Free Tier VM (Ubuntu 22.04,
`VM.Standard.E2.1.Micro`): Caddy terminates HTTPS and serves the static
pygbag web build, reverse-proxying `/health`, `/auth/*`, `/me`, `/save`,
`/balance`, `/admin*` and `/leaderboard` to the FastAPI backend
(`127.0.0.1:8090`, managed by systemd, loopback-only).

## Automatic deploy (GitHub Actions)

`.github/workflows/deploy.yml` runs on every push to `main` (i.e. every
merged PR) on a **self-hosted runner installed directly on the production
VM** - not a hosted GitHub runner reaching out over SSH. That was a
deliberate choice: no SSH private key or server address ever has to be
stored as a GitHub secret, since the runner already lives where the
deploy needs to happen. The tradeoff is that the runner itself needs to
be registered once, by hand, on the VM (below), and the workflow needs
narrow passwordless `sudo` for exactly the commands it runs (also below).

The workflow: builds `build/web` with `pygbag --build` using the VM's own
`python3` (not `actions/setup-python`, to avoid ever building against a
different Python than what runs the backend in production), copies it to
`/srv/dungeonquest-web`, copies the backend's `app/` files into
`~/backend/app/`, restarts `dungeonquest-backend`, reloads Caddy, and
curls `/health` as a smoke test. It mirrors the manual steps below exactly
- if you ever need to deploy by hand again (runner down, etc.), those
still work unchanged.

### One-time runner setup on the VM

**Done as of 2026-07-14**: registered, running as a systemd service
(`actions.runner.gsbad-dungeon-quest.dungeon-quest-vm.service`), and
confirmed end-to-end with a real deploy run. The first run did surface
two real bugs, both already fixed in the workflow: it deploys with
`rsync --delete` now, not `cp -r` (a plain `cp` never removes files a
previous build doesn't produce anymore - concretely, an `.apk` named
after a different checkout folder than the runner's own left behind and
un-served, but not cleaned up), and the health check retries a few times
instead of one `sleep 2; curl -f` (that one-shot version flaked once on
this VM's modest specs, right after a restart competing with the
`pygbag --build` that had just run).

For reference, this is the one-time setup that already happened here -
only useful again if the runner ever needs re-registering from scratch
(token expired mid-setup, moved to a different VM, etc.):

```bash
ssh -i ~/.ssh/dungeonquest_vm ubuntu@129.80.222.127
cd ~/actions-runner
# Registration token: GitHub repo -> Settings -> Actions -> Runners ->
# New self-hosted runner (short-lived, generate a fresh one if this is
# stale). Give it the "dungeonquest-vm" label - the workflow's
# runs-on: [self-hosted, dungeonquest-vm] targets that label specifically,
# not just any self-hosted runner, in case more are ever added for other
# projects on the same account.
./config.sh --url https://github.com/gsbad/dungeon-quest --token <TOKEN> --labels dungeonquest-vm
sudo ./svc.sh install
sudo ./svc.sh start
```

To set this up from scratch on a different VM: download
`https://github.com/actions/runner/releases/latest`'s
`actions-runner-linux-x64-<version>.tar.gz`, `tar xzf` it into a fresh
`~/actions-runner`, `python3 -m pip install --user --upgrade pip` (Ubuntu's
default python3 has no pip preinstalled), then the `config.sh`/`svc.sh`
steps above.

### Passwordless sudo for the workflow's exact commands

The runner (runs as `ubuntu`) needs to run a handful of root-only commands
without an interactive password prompt. **On this VM, `ubuntu` already has
unrestricted `(ALL) NOPASSWD: ALL` from Oracle's own cloud-init default**
- discovered while setting this up, not something this project configured
- so the workflow already works without anything further. The narrower
rule below is added anyway as defense-in-depth/documentation of exactly
what the workflow actually needs, in case the broad grant is ever tightened
later; it's redundant, not required, on the VM as currently provisioned.

`/etc/sudoers.d/dungeonquest-deploy` (mode 440, validated with `visudo -c`):

```
ubuntu ALL=(root) NOPASSWD: /usr/bin/rsync -a --delete /home/ubuntu/actions-runner/_work/dungeon-quest/dungeon-quest/build/web/. /srv/dungeonquest-web/
ubuntu ALL=(root) NOPASSWD: /usr/bin/chown -R root\:root /srv/dungeonquest-web
ubuntu ALL=(root) NOPASSWD: /usr/bin/chmod -R a+rX /srv/dungeonquest-web
ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart dungeonquest-backend
ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl reload caddy
```

(Adjust the `rsync` source path if the runner's work directory ends up
different from the default `_work/<repo>/<repo>` layout - `pwd` inside a
running job, or the first workflow run's log, will show the real path.)

### Concurrency

`concurrency: { group: deploy-production, cancel-in-progress: false }` in
the workflow queues deploys instead of overlapping them - two merges in
quick succession run one after another, never two `pygbag --build`s
racing over the same `build/web` directory.

## Manual redeploy (fallback, or for anything the workflow doesn't cover)

```bash
# backend (code only, not the venv or the sqlite db):
scp -i ~/.ssh/dungeonquest_vm backend/app/main.py backend/app/models.py ubuntu@129.80.222.127:~/backend/app/
ssh -i ~/.ssh/dungeonquest_vm ubuntu@129.80.222.127 "rm -rf ~/backend/app/__pycache__ && sudo systemctl restart dungeonquest-backend"

# game (after rebuilding build/web locally with pygbag):
scp -i ~/.ssh/dungeonquest_vm -r build/web/. ubuntu@129.80.222.127:~/web/
ssh -i ~/.ssh/dungeonquest_vm ubuntu@129.80.222.127 "sudo cp -r ~/web/. /srv/dungeonquest-web/ && sudo chown -R root:root /srv/dungeonquest-web && sudo chmod -R a+rX /srv/dungeonquest-web"
```

`/srv/dungeonquest-web` is what Caddy actually serves (`root:root`,
`a+rX`) - **not** `/home/ubuntu/web`, which is just a staging copy; Caddy
runs as the `caddy` user, which can't traverse `/home/ubuntu` (mode `750`).

**Adding a new backend route?** Add a matching
`handle /your-route { reverse_proxy 127.0.0.1:8090 }` block to
`/etc/caddy/Caddyfile` on the VM, then `sudo systemctl reload caddy`. Caddy
only forwards paths it's explicitly told to - a route that only exists in
FastAPI 404s through Caddy's static-file fallback otherwise.

## Admin balance panel on localhost (Stage K19 confirmed)

No VM needed to test `/admin` - it's a plain FastAPI route, identical in
local dev and production:

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt  # first time only
ADMIN_PASSWORD=whatever .venv/bin/uvicorn app.main:app --port 8090
```

Open `http://127.0.0.1:8090/admin`, log in with whatever password you set
`ADMIN_PASSWORD` to. `JWT_SECRET` doesn't need to be set - if absent, the
backend generates one and persists it to `backend/.jwt_secret_dev`
(gitignored) so it survives a restart. `GOOGLE_CLIENT_ID` isn't needed
either unless you're also testing Google login - the balance/appearance
panel doesn't touch it. The game itself doesn't need to be running at all
to test the panel in isolation; point a local pygbag dev server's
`ALLOWED_ORIGINS` entry at it (already listed in `backend/app/main.py`)
only if you want the game to actually pick up overrides live.

## Caddy route fixed: /appearance was never proxied at all (Stage K23)

Checked directly on the VM (2026-07-14): `/etc/caddy/Caddyfile` had no
`/appearance` block whatsoever, going all the way back to Stage K18 -
every `GET /appearance` (both the game's own boot-time fetch in
game/net.py and the admin panel's override list) silently 404'd through
the catch-all `file_server`, not just Stage K23's new
`/appearance/defaults`. This is very likely the actual root cause behind
"editar aparencia abre vazio" being reported as still-broken even after
the SPRITE_DEFAULTS fallback shipped - the override-fetch path itself was
dead in production the whole time, defaults or not.

Fixed by adding a `handle /appearance* { reverse_proxy 127.0.0.1:8090 }`
block (covers both `/appearance` and `/appearance/defaults` with one
entry) and `sudo systemctl reload caddy`. Verified both routes live:
`curl https://129.80.222.127.sslip.io/appearance` -> `{}`,
`/appearance/defaults` -> the 45-entry dict. The Caddyfile itself isn't
tracked in git (VM-only, edited directly over SSH) - this note is the
only record of the change outside the VM's own file.

## Caddy route fixed: /leaderboard had the exact same bug

Same class of bug, same session it was found in: `/leaderboard` (Stage
J8-J10) was also never in the Caddyfile - "o rank ainda nao esta
funcionando" traced straight to this, not any code bug in
game/leaderboard.py or the `/leaderboard` endpoint itself. Every `GET
/leaderboard` 404'd through the catch-all `file_server` in production,
even though the underlying data was there the whole time (players' saves
sync fine via `/save`, which *was* proxied - only the leaderboard READ
path was dead). Fixed the same way: added its own `handle /leaderboard`
block, reloaded Caddy, verified `curl
https://129.80.222.127.sslip.io/leaderboard` returns real entries.

**Lesson for next time a new backend route is added**: don't just check
it works against `127.0.0.1:8090` locally - verify it through the actual
public domain too, or add it to the Caddyfile in the same breath as
adding the FastAPI route. Both this and /appearance sat broken in
production for a while specifically because local testing (`docs/deploy.md`'s own "Admin balance panel on localhost" section) never
touches Caddy at all, so it never would have caught either.

## Login gate (Stage K23)

`pygbag_template.tmpl` now blocks the game behind a forced Google login
on first visit - `dq-login-gate`, a fullscreen overlay covering the whole
page until a JWT exists in `localStorage`. Bypassed entirely (never even
flashes) for local/LAN hosts - `dqIsLocalOrLan()` matches `localhost`,
`127.0.0.1`, and the `192.168.*`/`10.*`/`172.16-31.*` ranges the PC+mobile
same-LAN dev setup already uses - so neither of the two local dev flows
above (this admin panel, or the game itself via a local pygbag server)
ever need to log in to test. `/admin` is untouched - it keeps its own
separate password-based admin login, the gate has no opinion on it either
way since it only guards the game's own landing page.

## VM access

- SSH: `ssh -i ~/.ssh/dungeonquest_vm ubuntu@129.80.222.127`
- OCI CLI configured in `~/.oci/config`, region `us-ashburn-1`.

## Secrets on the VM

`/etc/dungeonquest-backend.env` (mode 600, root:root): `JWT_SECRET`,
`GOOGLE_CLIENT_ID`, `ADMIN_PASSWORD` - referenced via `EnvironmentFile=`
in the `dungeonquest-backend` systemd unit. Never committed, never copied
off the VM.
