# Prod Keycloak 11 manifests (`cdip-prod01`, namespace `cdip-auth`)

These files are the record of what prod runs. Prod is not managed by ArgoCD; changes are made by editing a file
here, checking the diff, and applying with server-side apply. Rollout steps are in `../RUNBOOK.md`.

| File | Object | Restart on change? |
|---|---|---|
| `deployment.yaml` | Deployment `keycloak` | Yes, if anything under `spec.template` changes |
| `service.yaml` | Service `keycloak` (ClusterIP; the ingress reaches pods via NEGs) | No |
| `backendconfig.yaml` | BackendConfig `keycloak` (load balancer health check, draining) | No |
| `ingress.yaml` | Ingress `keycloak` (GCE LB for `cdip-auth.pamdas.org`; TLS secret name rotates with cert renewals) | No |
| `nightly-restart.yaml` | Suspended emergency-restart CronJob and its RBAC | No |

Not in git: Secret `keycloak-credentials` (`KEYCLOAK_USER`, `KEYCLOAK_PASSWORD`, `DB_USER`, `DB_PASSWORD`). The
Deployment references it by key. To recreate it from scratch: `kubectl -n cdip-auth create secret generic
keycloak-credentials --from-literal=KEYCLOAK_USER=... --from-literal=KEYCLOAK_PASSWORD=...
--from-literal=DB_USER=... --from-literal=DB_PASSWORD=...`.
To rotate a value, update the Secret and run `kubectl rollout restart deploy/keycloak`.
`KEYCLOAK_USER` / `KEYCLOAK_PASSWORD` only seed the admin user on an empty database; changing them does not change
the existing admin password.

## Workflow

```bash
kubectl --context cdip-prod diff --server-side -f keycloak/prod/     # empty before you edit; only your edit after
kubectl --context cdip-prod apply --server-side -f keycloak/prod/
kubectl --context cdip-prod -n cdip-auth rollout status deploy/keycloak --timeout=5m
```

Commit the edit in the same change as the apply, so the files never lag prod.

- **Always diff first.** A non-empty diff before editing means someone changed prod by hand. Re-export with
  `kubectl get ... -o yaml | kubectl neat`, reconcile, and commit that before making your change.
- **Conflicts.** Server-side apply refuses to change a field last set by another tool (`kubectl set image`,
  `rollout restart`, a client-side apply). Read the field names it reports. If they are exactly the fields you
  edited, rerun with `--force-conflicts`. Anything else means the file has drifted: stop and re-export.
- **Do not use `kubectl set image`, `kubectl edit` or `kubectl patch` on these objects.** They work, but the files
  here stop matching prod and the next apply becomes a surprise.
- **`kubectl.kubernetes.io/restartedAt`** in the pod template is left over from a `rollout restart`. Leave it alone:
  removing or changing it restarts the pod.
- **Fields the cluster owns** are deliberately absent (`status`, `resourceVersion`, `clusterIP`, the NEG status
  annotation, the last-applied annotation). Do not add them back when re-exporting.

## What the values are for

- `readinessProbe.periodSeconds: 5`, `lifecycle.preStop` (`sleep 20`), `terminationGracePeriodSeconds: 60`, and the
  BackendConfig's 5 s health check with 30 s draining together keep the load balancer pointed at a serving pod
  during an image swap. Prod has one replica, so a swap still restarts Keycloak; these limit the gap to a few
  seconds. Background: `docs/superpowers/plans/2026-09-28-keycloak-prod-lb-health-check.md`.
- `-Dkeycloak.theme.staticMaxAge=3600` in `JAVA_OPTS` caps browser caching of theme files at one hour. Keycloak's
  default is 30 days with no ETag, and the resource URLs only change with the Keycloak version, so without this a
  theme change can take a month to reach returning users.
- `-Dkeycloak.profile.feature.upload_scripts=enabled` was already set before these files existed. Keep it unless
  you have confirmed nothing depends on it.
- `DB_ADDR` is the Cloud SQL instance's private IP. It is internal-only, which is why it is acceptable in git.
- The Service is `ClusterIP` because the ingress reaches the pods through NEGs; a Service-level load balancer is
  redundant with the ingress. Admin console access that must not go through the public hostname works with
  `kubectl -n cdip-auth port-forward deploy/keycloak 8080:8080` → `http://localhost:8080/auth/admin/`.
