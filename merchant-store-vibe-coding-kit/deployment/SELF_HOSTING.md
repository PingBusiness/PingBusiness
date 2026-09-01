# Self-hosted deployment on your own server

This is the merchant-owned path: the same stack as the managed platforms, but on
a machine you control. It uses the Compose adapter in `deployment/compose/`, with
a real public hostname rather than the `--local` preview mode.

Choose this if you already run a server, want the data on infrastructure you own,
or cannot use a hosted platform. Choose Railway or Northflank instead if you do
not want to be responsible for the items in "What you take on" below.

## What you take on

Railway and Northflank handle these for you. Self-hosting does not:

- server uptime, operating-system patching, and Docker upgrades;
- taking, storing, and testing database backups;
- keeping ports 80/443 reachable so certificates keep renewing;
- responding when something breaks at 2am.

Nothing here is exotic, but it is ongoing work. The kit ships scripts for the
backup and deployment parts; it cannot run them for you.

## Before you start

Collect all of these before generating anything.

| Requirement | Detail |
| --- | --- |
| A server | Public IPv4 address and root/sudo access. A VPS from any provider is fine. |
| Size | Minimum 2 vCPU / 4 GB RAM / 20 GB disk. Use 4 vCPU / 8 GB if you build the UI on the same machine — the Angular production build is the heaviest step and will fail on a 2 GB box. |
| Docker | Docker Engine 24 or newer with the Compose v2 plugin. |
| `git` and `python3` | Used to fetch the kit and generate the deployment values. Python needs no third-party packages. |
| A domain | A hostname you control, such as `shop.example.com`, plus the ability to edit its DNS records. |
| Open ports | Inbound `80/tcp` and `443/tcp`, in both the OS firewall and any cloud provider security group. |
| PingBusiness credentials | Your merchant identifier, store identifier, and merchant API key, issued by PingBusiness. |
| An email address | Used as the certificate-authority contact for expiry warnings. |

## Prepare the server

Run these on the server and fix anything that fails before going further.

```bash
docker compose version              # expect v2.x
git --version
python3 --version                   # expect 3.10 or newer
ss -lntp | grep -E ':(80|443) '     # expect NO output
```

If Docker is missing, install Docker Engine and the Compose plugin from
<https://docs.docker.com/engine/install/>. The `docker.io` package on some
distributions ships without Compose v2. Either add your user to the `docker`
group (`sudo usermod -aG docker "$USER"`, then log out and back in) or run every
`docker` command below with `sudo` — but do not mix the two, because a stack
brought up under `sudo` is invisible to the same commands run without it.

If the port check prints anything, another service already owns the port, usually
nginx or Apache. Stop and disable it; the edge cannot bind otherwise.

Open the ports in the OS firewall *and* in your provider's security group, which
is a separate setting that is easy to miss:

```bash
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp   # ufw; use firewall-cmd on RHEL-family
```

On a 4 GB machine that also builds the UI, add swap first. The Angular build is
the step that runs out of memory, and it fails confusingly when it does:

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
```

## DNS

Create one record pointing your store hostname at the server:

```text
Type   Name                 Value
A      shop.example.com     <server public IPv4>
AAAA   shop.example.com     <server public IPv6>     (only if the server has one)
```

Confirm it resolves to the server *before* deploying:

```bash
dig +short shop.example.com
```

If that prints nothing, or prints an address that is not your server, certificate
issuance will fail. Wait for propagation and check again.

Only this one hostname is needed. The store, its API, and its login service all
live on it — there are no separate `api.` or `auth.` records.

**If you use a proxying CDN** (for example Cloudflare's orange cloud): leave it
off — DNS-only, grey cloud — until the first certificate is issued and the smoke
test passes. Once it works, you may enable proxying, but set the CDN's SSL mode
to **Full (strict)** so it validates the origin certificate, and keep port 80
reachable so renewals continue to succeed.

## Certificates

There is nothing to buy, download, or install. The edge service runs Caddy, which
requests a Let's Encrypt certificate on first start and renews it automatically
for as long as the deployment runs. You do not need certbot, a cron job, or
manual certificate files.

Two things make issuance fail, and both are in the list above: the hostname not
resolving to this server, and port 80 not being reachable from the internet. Port
80 is not optional even though the store is HTTPS-only — it carries the ACME
challenge and the HTTP-to-HTTPS redirect.

Certificates are stored in the `caddy-data` Docker volume. Do not delete that
volume casually; Let's Encrypt applies rate limits to repeated issuance for the
same hostname.

## Deploy

```bash
# 1. Get the kit
git clone https://github.com/PingBusiness/PingBusiness
cd PingBusiness/merchant-store-vibe-coding-kit

# 2. Describe the deployment
cp deployment/deployment-input.example.json my-deployment.json
chmod 600 my-deployment.json
#    Edit it: set "platform" to "compose", "storeDomain" to your hostname,
#    "pingbusinessEnvironment" to staging or production, "acmeEmail" to a real
#    address you read, and your merchant and store identifiers. Leave
#    "merchantApiKey" alone for now — step 3 handles it.

# 3. Add the merchant API key without it appearing anywhere it should not
read -rsp 'Merchant API key: ' PB_KEY; echo
PB_KEY="$PB_KEY" python3 -c "import json,os; p='my-deployment.json'; d=json.load(open(p)); d['merchantApiKey']=os.environ['PB_KEY']; json.dump(d,open(p,'w'),indent=2)"
unset PB_KEY

# 4. Generate secrets and the private environment file
python3 scripts/prepare-deployment.py --input my-deployment.json --output-dir .generated

# 5. Bring the stack up
deployment/compose/deploy.sh .generated/compose.env
```

Step 3 is written that way on purpose: `read -rs` does not echo the key and does
not record it in shell history, and the key never appears in a command line. Run
it yourself. **If an AI agent is helping you, this is the one step it must not do
for you** — anything an agent types passes through a chat transcript. The agent
should prepare everything else, hand you these three lines, and wait.

Step 4 needs only Python 3 and the standard library. It generates the database
password, the Keycloak admin password, and the Keycloak client secret, and writes
them to `.generated/` with mode `0600`. It never prints them. Do not commit
`.generated/`, and do not paste `my-deployment.json` or anything under
`.generated/` into a chat window — both hold live secrets. Keep
`my-deployment.json` at mode `600`, or delete it once the stack is up.

Step 5 builds the images on the server the first time, which takes several
minutes. Watch for the certificate being issued:

```bash
docker compose --env-file .generated/compose.env \
  -f deployment/compose/compose.yaml logs -f edge
```

## Your customized UI

Every deployment builds a UI you supply. The kit's `source/merchant-store` tree is
the reference implementation your customization starts from — it carries
demonstration branding and is not a storefront to put in front of customers.
`uiSource` has no mode that builds it, and the generator refuses an input that
points back at it. Complete the customize step first.

Set one of these in `my-deployment.json`:

```jsonc
// A customized UI repository
"uiSource": { "mode": "git", "repositoryUrl": "https://github.com/you/your-store-ui",
              "branch": "main", "rootPath": "/", "dockerfilePath": "Dockerfile" }

// A customized UI tree already on this server
"uiSource": { "mode": "local", "path": "/home/you/customized-ui" }
```

`local` is compose-only and the path must be absolute — a managed platform builds
from Git and cannot see your disk. For a ZIP produced by a design agent, copy it
up and unpack it first:

```bash
scp customized-merchant-store.zip you@your-server:~/          # from your laptop
unzip customized-merchant-store.zip -d ~/customized-ui        # on the server
```

Then use that directory as `uiSource.path`. The generator writes it into
`MERCHANT_STORE_BUILD_CONTEXT` for you, so there is no file to hand-edit
afterwards.

## Verify

```bash
python3 scripts/public-smoke-test.py --store-url https://shop.example.com
```

Then check by hand that `https://shop.example.com/` shows the storefront, that
registration and login work, and that the certificate in the browser is valid and
issued to your hostname. Confirm the private services are not reachable from
outside: nothing should answer on ports 5432, 5000, 8080, or 9000.

## After it is running

**Back up.** The Keycloak database holds your customer accounts. Losing it means
every customer must register again.

```bash
deployment/compose/backup-keycloak-db.sh .generated/compose.env
```

Run it on a schedule, copy the output off the server, and restore one backup into
a throwaway environment at least once so you know the procedure works. A restore
is destructive — see `deployment/compose/README.md`.

**Update.** Pull the kit, then re-run the deploy script; it rebuilds and restarts
in place.

**Do not regenerate the environment file casually.** Every
`prepare-deployment.py` run mints a new `KEYCLOAK_DB_PASSWORD`. If you regenerate
`compose.env` while the existing `keycloak-postgres-data` volume is still around,
Keycloak fails to start with `password authentication failed for user "keycloak"`.
Carry the previous `KEYCLOAK_DB_*` values forward, or drop the volume and accept
that you are starting from an empty user database.

## Related files

- `deployment/compose/README.md` — the adapter itself, including local preview,
  customized-UI build contexts, and backup/restore detail.
- `deployment/DNS_AND_TLS.md` — DNS and certificate behaviour across all targets.
- `deployment/DEPLOYMENT_ACCEPTANCE_CHECKLIST.md` — what to verify before calling
  a store live.
