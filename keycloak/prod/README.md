# Prod Keycloak manifests (`cdip-auth` namespace, `cdip-prod` cluster)

Desired-state manifests for the prod Keycloak behind `https://cdip-auth.pamdas.org`,
captured from the live cluster 2026-10-06 and sanitized. Credentials live in the
`keycloak-credentials` Secret (already present in the cluster, never committed —
`secret.yaml.example` documents its shape).

Not ArgoCD/Terraform-managed: changes are reviewed here, then applied with
`kubectl apply -f` against context `cdip-prod`. The Terraform Keycloak in
`gundi-tf-base-infra` is the newer helm-based one and is disabled in prod
(`keycloak_enabled = false`).

## Files

| File | Notes |
|---|---|
| `deployment.yaml` | Image tag is owned by the theme-image rollout in `../RUNBOOK.md` (`kubectl set image`); re-sync the tag here after each rollout. |
| `service.yaml` | ClusterIP + NEG. **Differs from live** — see below. |
| `ingress.yaml` | GCE LB; the TLS secret name rotates with cert renewals. |
| `backendconfig.yaml` | LB health check; Cloud Armor attachment point (commented until the policy exists). |
| `nightly-restart.yaml` | Suspended emergency restart CronJob + its RBAC. |
| `secret.yaml.example` | Shape of `keycloak-credentials`; real values out of band. |

## Drift from live (as of 2026-10-06)

`service.yaml` is the one intentional difference: it is `ClusterIP`, while the
live Service is still `type: LoadBalancer`. Applying it is step 1 of the parked
hardening plan in `docs/ideation/2026-09-30-keycloak-master-realm-lockdown.md`
(the ingress reaches pods via NEGs, so it is unaffected; in-cluster DNS keeps
working). Diff before applying anything:

```bash
kubectl --context cdip-prod diff -f keycloak/prod/
```

## Realm admin access without the public console

```bash
kubectl --context cdip-prod -n cdip-auth port-forward deploy/keycloak 8080:8080
# then http://localhost:8080/auth/admin/
```
