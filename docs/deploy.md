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

```bash
ssh -i ~/.ssh/dungeonquest_vm ubuntu@129.80.222.127
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64.tar.gz -L \
  https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64-<version>.tar.gz
tar xzf ./actions-runner-linux-x64.tar.gz
# Registration token: GitHub repo -> Settings -> Actions -> Runners ->
# New self-hosted runner (short-lived, generate a fresh one if this is
# stale). Give it the "dungeonquest-vm" label when prompted - the
# workflow's runs-on: [self-hosted, dungeonquest-vm] targets that label
# specifically, not just any self-hosted runner, in case more are ever
# added for other projects on the same account.
./config.sh --url https://github.com/gsbad/dungeon-quest --token <TOKEN> --labels dungeonquest-vm
sudo ./svc.sh install
sudo ./svc.sh start
```

### Passwordless sudo for the workflow's exact commands

The runner (registered above, runs as `ubuntu`) needs to run a handful of
root-only commands without an interactive password prompt - broad
`ubuntu ALL=(ALL) NOPASSWD: ALL` would work but is far more than this
needs. Add this instead via `sudo visudo -f /etc/sudoers.d/dungeonquest-deploy`:

```
ubuntu ALL=(root) NOPASSWD: /usr/bin/cp -r /home/ubuntu/actions-runner/_work/dungeon-quest/dungeon-quest/build/web/. /srv/dungeonquest-web/
ubuntu ALL=(root) NOPASSWD: /usr/bin/chown -R root\:root /srv/dungeonquest-web
ubuntu ALL=(root) NOPASSWD: /usr/bin/chmod -R a+rX /srv/dungeonquest-web
ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart dungeonquest-backend
ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl reload caddy
```

(Adjust the `cp` source path if the runner's work directory ends up
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
