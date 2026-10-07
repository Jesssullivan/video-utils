# video-utils hosted deploy plan (reviewed files, not applied)

Lane `auth_hosting`, sprint `20261007-s3`, Linear TIN-5720. Contract:
[`docs/spec/sprints/AUTH_HOSTING_S3.md`](../docs/spec/sprints/AUTH_HOSTING_S3.md). Estate pattern:
[`docs/research/2026-10-07-estate-auth-hosting.md`](../docs/research/2026-10-07-estate-auth-hosting.md).

## Apply boundary

**Nothing in `deploy/` has been applied.** Every step below is an outward-facing action. Each one
needs a separate operator go, given for that step, before anyone runs it. Merging these files is
not that go. No agent lane creates a namespace, Secret, tunnel, tunnel route, DNS record, Access
application, IdP or service token, and none builds or pushes the image. Whether the RKE2 cluster
host counts as an operator-controlled host for real-take media (AGENTS.md) is part of the
operator's apply decision. This plan does not infer it.

## What is here

| File | Object | Notes |
| --- | --- | --- |
| `k8s/namespace.json` | Namespace `video-utils` | Pod Security `restricted` labels |
| `k8s/configmap.json` | ConfigMap `video-utils-web-config` | `VIDEO_UTILS_AUTH_MODE=tailnet`. The five tailnet variables are empty placeholders, so `serve.js` exits 2 until they are set. Non-secret |
| `k8s/pvc.json` | PersistentVolumeClaim `video-utils-artifacts` | `ReadWriteOnce`, 20Gi, `storageClassName` omitted |
| `k8s/deployment.json` | Deployment `video-utils-web` | 1 replica, `Recreate`, non-root 10001, read-only root FS, all capabilities dropped, no service-account token, cpu/memory/ephemeral-storage requests and limits, no GPU, tcpSocket probes, PVC at `/srv/video-utils/artifacts`, `emptyDir` `/tmp`. The image is pinned to the all-zero sentinel digest, so an apply before a build fails closed at pull |
| `k8s/service.json` | Service `video-utils-web` | `ClusterIP` only. No Ingress, NodePort, LoadBalancer, hostNetwork or hostPort anywhere: tunnel-only origin |
| `k8s/networkpolicy.json` | NetworkPolicy ×2 (a `v1` `List`) | Default-deny ingress, plus one allow on TCP 3000 from the cloudflared connector namespace. The placeholder label value `unset-cloudflared-namespace` matches nothing until the operator sets it |
| `k8s/kustomization.yaml` | Kustomization | Strict JSON, which is valid YAML |
| `cloudflare/video-utils-app-origin-routes.json` | Tunnel route contract | `tinyland.cloudflare-tunnel.app-origin.v1` shape. Hostname and tunnel are `null` |
| `cloudflare/video-utils-access-plan.json` | Access application and policies | Declarative plan, not tofu. Zone-bound exact hostname, all paths, 24h, HttpOnly, SameSite=Lax, exact-email allow, `allowed_idps` pinned to Google Workspace, One-Time-PIN and tsidp (ids `null`), no bypass application |

The image definition is [`web/Containerfile`](../web/Containerfile). It uses adapter-node, a
multi-stage build, the base `node:22.23.2-bookworm-slim` pinned by the digest observed on
2026-10-07, `USER 10001:10001`, and no media, fixtures, artifacts, `.env` or models.

## Apply order (each step is an operator act with its own go)

The xoruby order from tinyland-infra `tofu/stacks/xoxd-ai-edge` is gate first, then route, then
DNS. The cluster objects come before the route so the route has an origin to reach.

1. **Decide the unknowns**: the public hostname, the cluster and tunnel, the cloudflared
   namespace, the storage class, and whether that host may hold real-take media.
2. **Image**: build `web/Containerfile`, push it to the chosen registry, and replace the sentinel
   `image` in `k8s/deployment.json` with `<registry>/<name>@sha256:<pushed digest>` in a reviewed
   commit.
3. **Access application** (Cloudflare, operator-owned stack): create the application and allow
   policy from `cloudflare/video-utils-access-plan.json`, giving the exact operator email(s) at
   apply. Read back the application AUD tag and the team domain. Signed out, `GET /` must return
   302 to `*.cloudflareaccess.com` before anything else is exposed.
4. **Namespace**, then the **ConfigMap** values: `VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN`,
   `VIDEO_UTILS_CF_ACCESS_AUDS` (the AUD from step 3), `VIDEO_UTILS_OPERATOR_ALLOWLIST` (the same
   exact emails as the allow policy), `VIDEO_UTILS_PUBLIC_HOSTS` and `ORIGIN=https://<host>`. These
   values are configuration, not credentials, but they are set at apply and not committed.
5. **PersistentVolumeClaim**, **Deployment**, **Service**, **NetworkPolicy** (with the real
   cloudflared namespace label), for example `kubectl apply -k deploy/k8s` after review. The pod
   must reach `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs` for JWKS. No egress policy
   is declared here.
6. **Tunnel route**: add the rule from `cloudflare/video-utils-app-origin-routes.json` to the
   chosen tunnel out of band (TR1 GET/merge/PUT or console), then read it back.
7. **DNS**: a proxied CNAME to the tunnel, only after the route answers.
8. **Served proof** (operator): signed out gets 302 to Access. Signed in as an allowlisted
   operator gets 200. A request straight to the Service without an Access JWT gets 403
   `bff_identity_refused`. A wrong Host gets 421.

## Rollback

Reverse order: DNS record, tunnel route, Deployment/Service/NetworkPolicy/PVC (the PVC holds
artifacts, so export them before deleting it), ConfigMap, Namespace, Access application. To end
Access sessions that were already issued, use **Revoke existing tokens** on the application. The
gftb runbook notes that deleting an IdP does not end issued sessions.

## Secrets

This plan contains no secrets and needs none to apply. By estate pattern, credential values
(Cloudflare API tokens, tsidp client id and secret, Access service-token id and secret) stay in
operator custody: lab sops, or GitHub environment secrets set by stdin. Only their **names** ever
appear in git. The control-API bearer token (`VIDEO_UTILS_CONTROL_API_TOKEN`) is not deployed by
this plan, because the control API is not containerised here.

## Unknowns (explicit, never omitted)

| Field | Value | Meaning |
| --- | --- | --- |
| `public_hostname` | `null` | No hostname chosen |
| `cloudflare_tunnel_id` | `null` | Estate dynamic apps use the shared `honey-ingress` tunnel. Not decided for video-utils |
| `access_application_aud` | `null` | Exists only after step 3 |
| `access_idp_ids` | `null` | Google Workspace, One-Time-PIN and tsidp IdP ids for the account |
| `cluster_target` | `"unknown"` | Which RKE2 cluster |
| `namespace_exists` | `"unknown"` | Not checked. This lane makes no cluster reads |
| `storage_class` | `"unknown"` | PVC uses the cluster default when applied unchanged |
| `cloudflared_namespace` | `"unknown"` | Placeholder label in the NetworkPolicy |
| `container_base_digest` | `sha256:48e4b67d…f0f9` (observed 2026-10-07) | Multi-arch index for `node:22.23.2-bookworm-slim` |
| `container_image_digest` | `null` | Image not built |
| `container_built` | `false` | |
| `control_api_colocation` | `"unresolved"` | The BFF renders `control_api_unconfigured` without it. A same-pod loopback sidecar is one option and needs its own contract |
| `tsidp_claims_in_access_jwt` | `"unknown"` | The sources do not establish whether Access forwards tsidp OIDC claims into the app token |
| `assertion_idp_visible_to_app` | `"unknown"` | Whether the app token tells the origin which IdP was used |
| `tailscale_serve_identity` | `"not_accepted"` | `Tailscale-User-*` headers are never read. The pod model gives no same-node Serve guarantee |
| `applied` | `false` | |
| `served_proof` | `"not_run"` | |
