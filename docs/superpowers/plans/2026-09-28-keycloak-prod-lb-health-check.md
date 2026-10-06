# Keycloak prod: faster load balancer health check, graceful pod swap, credentials in a Secret

Cluster `cdip-prod01` (kube context `cdip-prod`), namespace `cdip-auth`, GCP project `cdip-78ca`.
gcloud account: `chrisdo@earthranger.com`.

## Why

Prod runs one Keycloak replica. The swap to `11.0.2-gundi-a4fe4ac` on 2026-09-28 had a short outage because:

- The readiness probe and the load balancer health check both poll `/auth/realms/master` every 20 s. GKE built the load balancer check from the readiness probe.
- Kubernetes stopped the old pod as soon as the new one passed readiness. GKE marked the new pod's load-balancer
  readiness true without waiting for a health check (`LoadBalancerNegWithoutHealthCheck` event), so the rollout did not wait for the load balancer to see the new pod as healthy.
- Connection draining is 0 and there is no preStop hook, so the old pod stopped serving before the load balancer deregistered it.

Separately, the Deployment may carry credentials as plain env values. Moving them into a Secret keeps them out of the manifest, so the manifest can live in git.

## Status (2026-09-29)

Steps 1 to 4 are done, and step 5 is applied except for the readiness probe. A `kubectl diff --server-side -f manifests/` on 2026-09-29 showed the BackendConfig, Service and Deployment matching prod apart from the `last-applied-configuration`
annotation, which is harmless bookkeeping from a client-side apply. Prod runs image `11.0.2-gundi-438715d`, built from the newer main commits that centre the login card and fix the screenshot cleanup trap.

**Remaining:** the readiness probe still polls every 20 s in both the manifest and the cluster. Step 5 edits were
made without it. Do the probe change in **step 5b**, then step 6.

| Setting | Original (2026-09-28) | Target | Done |
|---|---|---|---|
| Load balancer check interval | 20 s | 5 s | yes |
| Load balancer check timeout | 4 s | 3 s | yes |
| Connection draining | 0 s | 30 s | yes |
| Readiness probe period | 20 s | 5 s | **no, still 20 s** |
| preStop hook | none | `sleep 20` | yes |
| terminationGracePeriodSeconds | 30 | 60 | yes |
| Credential env vars | plain `value:` | `secretKeyRef` to Secret `keycloak-credentials` | yes |

Liveness probe stays as it is (120 s initial delay, 20 s period).

Load balancer objects: backend service and health check are both named
`k8s1-29c9a6d8-cdip-auth-keycloak-8080-218e32e7`.

## Approach

Export the live Deployment and Service to YAML with `kubectl neat`, edit those files, check the change with
`kubectl diff`, and apply with server-side apply. The files become the record of what prod runs.

Server-side apply is used because these objects were never managed with client-side `kubectl apply` (the Service's `last-applied-configuration` annotation is empty). It tracks field ownership on the server, so fields left out of a file are not removed, and changing a field another tool last set shows up as a conflict instead of passing silently.

The Secret is created with `kubectl create` from the live values and is never written to `manifests/`. Only the references to it go in the Deployment file.

## Before you start

- **Timing.** Steps 3 and 4 need no restart. Steps 5 and 5b restart the pod, so do them in the 02:00 UTC window or another agreed off-hours slot.
- **Tools.** `kubectl neat` (`kubectl krew install neat`), `yq` (v4), and gcloud with the account above.
- **Old manifests.** The only Keycloak manifests found locally (`padas/keycloak.yaml`,
  `cdip/.worktrees/main/keycloak.yaml`) are from 2021, use `jboss/keycloak:11.0.2`, and do not match the live Deployment. Do not apply them. The files exported below replace them.
- **Credential handling.** Commands below never print a credential. Don't `cat` the export or the backup, and don't paste either into chat or a ticket, until step 5 is done.

## Step 1: back up and export

Raw backups keep everything the server holds, for rollback and comparison. The backup holds credentials, so the
directory is private:

```bash
WORK=~/keycloak-prod-2026-09-28
mkdir -p -m 700 "$WORK" && mkdir -p "$WORK/backup" "$WORK/manifests" && cd "$WORK"

kubectl --context cdip-prod -n cdip-auth get deploy keycloak -o yaml > backup/deploy-keycloak.yaml
kubectl --context cdip-prod -n cdip-auth get svc keycloak -o yaml > backup/svc-keycloak.yaml
kubectl --context cdip-prod -n cdip-auth rollout history deploy/keycloak | tail -3 > backup/rollout-history.txt
gcloud compute health-checks describe k8s1-29c9a6d8-cdip-auth-keycloak-8080-218e32e7 \
  --account=chrisdo@earthranger.com --project=cdip-78ca > backup/health-check.yaml
```

Clean exports to edit:

```bash
kubectl --context cdip-prod -n cdip-auth get deploy keycloak -o yaml | kubectl neat > manifests/deployment.yaml
kubectl --context cdip-prod -n cdip-auth get svc keycloak -o yaml | kubectl neat > manifests/service.yaml
```

## Step 2: review the exports

**Credentials.** List the env vars in the `keycloak` container that are set as plain values, without printing the
values themselves:

```bash
yq '.spec.template.spec.containers[] | select(.name == "keycloak") | .env[]
    | select(has("value")) | .name' manifests/deployment.yaml
```

Write down the names in that list that are credentials. From the 2021 manifest, expect `KEYCLOAK_USER`,
`KEYCLOAK_PASSWORD`, `DB_USER` and `DB_PASSWORD`. `DB_ADDR`, `DB_DATABASE`, `DB_SCHEMA`, `DB_VENDOR` and
`PROXY_ADDRESS_FORWARDING` are configuration and stay as plain values. If no credential is in the list, skip step 4 and the env edit in step 5.

**Fields the cluster owns.** Delete these if present, so the apply does not take ownership of them:

- `service.yaml`: `spec.clusterIP`, `spec.clusterIPs`, and the annotations `cloud.google.com/neg-status`,
  `networking.gke.io/target-pool` and `kubectl.kubernetes.io/last-applied-configuration`.
- `deployment.yaml`: the annotations `deployment.kubernetes.io/revision` and
  `kubectl.kubernetes.io/last-applied-configuration`.

Keep `cloud.google.com/neg: '{"ingress":true}'` on the Service. The ingress depends on it.

**Baseline.** Before editing, the diff must be empty. Anything it shows is a field the export got wrong:

```bash
kubectl --context cdip-prod diff --server-side -f manifests/deployment.yaml -f manifests/service.yaml
```

## Step 3: faster load balancer check and connection draining (no restart)

Create `manifests/backendconfig.yaml`:

```yaml
apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: keycloak
  namespace: cdip-auth
spec:
  healthCheck:
    type: HTTP
    requestPath: /auth/realms/master
    port: 8080
    checkIntervalSec: 5
    timeoutSec: 3
    healthyThreshold: 1
    unhealthyThreshold: 2
  connectionDraining:
    drainingTimeoutSec: 30
```

In `manifests/service.yaml`, add under `metadata.annotations`:

```yaml
    cloud.google.com/backend-config: '{"default":"keycloak"}'
```

Diff, then apply. The diff should show the new BackendConfig and that one annotation, nothing else:

```bash
kubectl --context cdip-prod diff --server-side -f manifests/backendconfig.yaml -f manifests/service.yaml
kubectl --context cdip-prod apply --server-side -f manifests/backendconfig.yaml -f manifests/service.yaml
```

The ingress controller reconciles within a few minutes. Verify:

```bash
gcloud compute health-checks describe k8s1-29c9a6d8-cdip-auth-keycloak-8080-218e32e7 \
  --account=chrisdo@earthranger.com --project=cdip-78ca \
  --format="value(checkIntervalSec,timeoutSec,httpHealthCheck.requestPath)"
# expect: 5  3  /auth/realms/master

gcloud compute backend-services describe k8s1-29c9a6d8-cdip-auth-keycloak-8080-218e32e7 --global \
  --account=chrisdo@earthranger.com --project=cdip-78ca \
  --format="value(connectionDraining.drainingTimeoutSec)"
# expect: 30

kubectl --context cdip-prod -n cdip-auth get ingress keycloak \
  -o jsonpath='{.metadata.annotations.ingress\.kubernetes\.io/backends}{"\n"}'
# expect every backend HEALTHY
```

If the backend is not HEALTHY after 5 minutes, roll back step 3 (below) before going further.

## Step 4: create the credentials Secret (no restart)

Set `VARS` to the credential names you wrote down in step 2. The loop writes each current value to a private temp file, the Secret is created from those files with the env var names as keys, and the files are removed. Nothing is printed and nothing lands in shell history:

```bash
VARS="KEYCLOAK_USER KEYCLOAK_PASSWORD DB_USER DB_PASSWORD"

tmp=$(mktemp -d) && chmod 700 "$tmp"
for v in $VARS; do
  printf '%s' "$(V="$v" yq '.spec.template.spec.containers[] | select(.name == "keycloak") | .env[]
                             | select(.name == strenv(V)) | .value' manifests/deployment.yaml)" > "$tmp/$v"
  [ -s "$tmp/$v" ] || echo "EMPTY: $v"
done
kubectl --context cdip-prod -n cdip-auth create secret generic keycloak-credentials --from-file="$tmp"
rm -rf "$tmp"
```

Stop if any line printed `EMPTY:`. Delete the Secret, fix `VARS`, and run it again.

`printf '%s'` drops the newline yq adds, so the Secret holds exactly what the env var holds today.

Verify the keys, not the values. `describe` shows each key with its size and never the value:

```bash
kubectl --context cdip-prod -n cdip-auth describe secret keycloak-credentials
# one key per name in VARS, each with a non-zero byte count
```

The running pod is unaffected until step 5.

## Step 5: readiness probe, graceful shutdown, credential references (restarts the pod)

Done on 2026-09-29, except the readiness probe, which is now step 5b. Kept for the record.

In `manifests/deployment.yaml`, under `spec.template.spec`:

- set `terminationGracePeriodSeconds: 60`
- in the `keycloak` container's `readinessProbe`, set `periodSeconds: 5` and leave the other probe fields as they are
- add to the `keycloak` container:

```yaml
        lifecycle:
          preStop:
            exec:
              command: ["sleep", "20"]
```

- for each name in `VARS`, replace its `value:` line with a reference, keeping the entry in its current position. For example:

```yaml
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: keycloak-credentials
              key: DB_PASSWORD
```

Replace, don't add: an entry with both `value:` and `valueFrom:` is rejected by the API server with
`valueFrom: Invalid value: "": may not be specified when value is not empty`. Confirm no credential value is left in the file. This should print nothing:

```bash
for v in $VARS; do
  V="$v" yq '.spec.template.spec.containers[] | select(.name == "keycloak") | .env[]
             | select(.name == strenv(V)) | select(has("value")) | .name' manifests/deployment.yaml
done
```

Diff. It should show the grace period, probe period and lifecycle changes, and each credential's `value` replaced by a `valueFrom`. The diff masks nothing in a Deployment, so the removed lines contain the old values: read it yourself, don't share it.

```bash
kubectl --context cdip-prod diff --server-side -f manifests/deployment.yaml
```

Start a downtime monitor in a second terminal:

```bash
while true; do
  printf '%s %s\n' "$(date -u +%T)" \
    "$(curl -s -o /dev/null -m 3 -w '%{http_code}' https://cdip-auth.pamdas.org/auth/realms/master)"
  sleep 1
done | tee ~/keycloak-prod-2026-09-28/swap-monitor.log
```

Apply and wait:

```bash
kubectl --context cdip-prod apply --server-side -f manifests/deployment.yaml
kubectl --context cdip-prod -n cdip-auth rollout status deploy/keycloak --timeout=5m
```

If the apply reports conflicts, read which fields it names. Conflicts on only the grace period, readiness probe
period, lifecycle or the credential env entries are expected, because those were last set by another tool. Rerun  with `--force-conflicts`. A conflict on any other field means the file differs from prod: stop and compare it with backup/deploy-keycloak.yaml`.

If a secret reference is wrong, the new pod fails with `CreateContainerConfigError` or Keycloak cannot reach the database, and never becomes ready. With one replica the rollout keeps the old pod serving in that case, so
`rollout status` times out instead of causing an outage. Roll back step 5 (below).

This rollout's old pod has no preStop hook yet, so it can still blink. The next swap is the first one that gets
the full benefit.

Verify:

```bash
kubectl --context cdip-prod -n cdip-auth get deploy keycloak -o jsonpath=\
'image={.spec.template.spec.containers[0].image}{"\n"}readiness={.spec.template.spec.containers[0].readinessProbe}{"\n"}preStop={.spec.template.spec.containers[0].lifecycle.preStop}{"\n"}grace={.spec.template.spec.terminationGracePeriodSeconds}{"\n"}'
# image must still be the Gundi image that was running before the apply (11.0.2-gundi-438715d as of 2026-09-29)

kubectl --context cdip-prod -n cdip-auth logs deploy/keycloak --since=10m | grep -E 'WFLYSRV0025|ERROR' | tail -5
# expect the "Keycloak 11.0.2 ... started" line and no database errors

curl -s -o /dev/null -w '%{http_code}\n' https://cdip-auth.pamdas.org/auth/realms/master
# expect 200

grep -v ' 200$' ~/keycloak-prod-2026-09-28/swap-monitor.log
# lists every second the endpoint was not answering 200

kubectl --context cdip-prod diff --server-side -f manifests/
# expect no output: the files now match prod
```

Stop the monitor. Log in through the prod portal once, and once to the admin console at
`https://cdip-auth.pamdas.org/auth/admin/`.

## Step 5b: readiness probe period and theme cache lifetime (restarts the pod)

Two edits, one restart. Both are already made in `manifests/deployment.yaml` as of 2026-09-30. Confirm before applying, with no values printed:

```bash
yq '.spec.template.spec.containers[] | select(.name == "keycloak") | .readinessProbe.periodSeconds' manifests/deployment.yaml
# expect 5
yq '.spec.template.spec.containers[] | select(.name == "keycloak") | .env[] | select(.name == "JAVA_OPTS") | .value' manifests/deployment.yaml
# expect the existing flags followed by -Dkeycloak.theme.staticMaxAge=3600
```

- **Readiness probe:** in the `keycloak` container's `readinessProbe`, `periodSeconds: 5`. `failureThreshold`, `httpGet`, `successThreshold` and `timeoutSeconds` stay as they are.
- **Theme cache:** `-Dkeycloak.theme.staticMaxAge=3600` appended to `JAVA_OPTS`. Keycloak 11 serves theme files with `Cache-Control: max-age=2592000` (30 days) and no ETag, and the `/auth/resources/<token>/` URL token changes only with the Keycloak version, so browsers keep old CSS for up to a month after a theme change. One hour bounds that. Verified on prod 2026-09-30: `curl -sI` on `login/gundi/css/gundi.css` returned `cache-control: max-age=2592000`.

Diff. It should show exactly two changed lines: `periodSeconds: 20` to `5` inside `readinessProbe`, and the `JAVA_OPTS` value gaining the new flag. A change to the `last-applied-configuration` annotation may appear as well and is fine. Anything else means the file has drifted from prod: stop and re-export.

```bash
kubectl --context cdip-prod diff --server-side -f manifests/deployment.yaml
```

This changes the pod template, so it restarts Keycloak. Start the downtime monitor from step 5 in a second terminal, then apply and wait:

```bash
kubectl --context cdip-prod apply --server-side -f manifests/deployment.yaml
kubectl --context cdip-prod -n cdip-auth rollout status deploy/keycloak --timeout=5m
```

Conflicts on `readinessProbe.periodSeconds` and the `JAVA_OPTS` env entry are expected; rerun with `--force-conflicts`. Any other conflict means stop.

This is the first swap where the old pod has the preStop hook and the load balancer check is 5 s, so the monitor log is the first real measurement of the fix. Verify with the same commands as step 5. Expect the probe to show `"periodSeconds":5`, the image unchanged, and an empty diff for `manifests/`. Note how many non-200 seconds the monitor logged; on 2026-09-28 the swap without these changes lost roughly 20 to 30 seconds.

Check the new cache lifetime once the pod is up:

```bash
curl -s 'https://cdip-auth.pamdas.org/auth/realms/cdip-dev/protocol/openid-connect/auth?client_id=cdip-admin-portal&response_type=code&scope=openid&redirect_uri=https%3A%2F%2Fexample.invalid%2F' \
  | grep -o '/auth/resources/[^"]*login/gundi/css/gundi.css' | head -1 \
  | xargs -I{} curl -sI 'https://cdip-auth.pamdas.org{}' | grep -i cache-control
# expect: cache-control: max-age=3600
```

Users who loaded the login page before this change still hold the 30-day copy of the old CSS; the shorter lifetime only applies to files fetched from now on.

## Step 6: keep the manifests, remove the backups

`manifests/` now describes what prod runs and holds no credentials. It is committed as `keycloak/prod/` in the cdip repo (branch `docs/keycloak-prod-lb-health-check`), with a README describing the diff-then-apply workflow. The runbook's image-swap step now edits `keycloak/prod/deployment.yaml` instead of using `kubectl set image`, so the files stop drifting. Delete `~/keycloak-prod-2026-09-28/manifests/` once the branch is merged, and work from the repo copy.

Once prod has run cleanly for a day, delete the raw backup, which still holds the old plain values:

```bash
rm -rf ~/keycloak-prod-2026-09-28/backup
```

The Secret is not in git. It lives only in the cluster. To rotate a credential, update the Secret and restart the
pod with `kubectl rollout restart deploy/keycloak`. For `DB_PASSWORD`, change it in Cloud SQL first.
`KEYCLOAK_USER` and `KEYCLOAK_PASSWORD` only create the admin user on an empty database, so changing them does not change the existing admin password.

## Rollback

**Step 5b:** `rollout undo` returns to the revision with the 20 s probe, the old `JAVA_OPTS` and everything else from step 5 intact. Then set `periodSeconds` back to 20 and remove the `staticMaxAge` flag in `manifests/deployment.yaml`.

**Step 5:** return to the previous revision, which is the Gundi image with the old probe, no preStop hook and the plain env values. Then revert the same edits in `manifests/deployment.yaml` so the file matches prod again. Leave the Secret in place; nothing reads it after the rollback.

```bash
kubectl --context cdip-prod -n cdip-auth rollout undo deploy/keycloak
kubectl --context cdip-prod -n cdip-auth rollout status deploy/keycloak --timeout=5m
```

**Step 4:** nothing reads the Secret until step 5, so deleting it is safe as long as step 5 is not applied.

```bash
kubectl --context cdip-prod -n cdip-auth delete secret keycloak-credentials
```

**Step 3:** remove the annotation from `manifests/service.yaml` and re-apply it, which drops the annotation because this apply owns it. Then delete the BackendConfig. GKE re-infers the health check from the readiness probe.

```bash
kubectl --context cdip-prod apply --server-side -f manifests/service.yaml
kubectl --context cdip-prod delete -f manifests/backendconfig.yaml
```

## Not in scope

A second replica would make swaps seamless, but Keycloak 11 needs cluster-aware session caching for that. It fits better with the Keycloak 26 upgrade.
