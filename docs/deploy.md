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

## VM access

- SSH: `ssh -i ~/.ssh/dungeonquest_vm ubuntu@129.80.222.127`
- OCI CLI configured in `~/.oci/config`, region `us-ashburn-1`.

## Secrets on the VM

`/etc/dungeonquest-backend.env` (mode 600, root:root): `JWT_SECRET`,
`GOOGLE_CLIENT_ID`, `ADMIN_PASSWORD` - referenced via `EnvironmentFile=`
in the `dungeonquest-backend` systemd unit. Never committed, never copied
off the VM.
