# JNS v5.5.0 Production Upgrade

## Safety rule

Keep the currently working v5.4 management PC authorized throughout the upgrade. Do not revoke it until the replacement PC has completed v5.5 enrollment and the signed commissioning deploy+rollback test.

## Upgrade integration

Update `custom_components/jns_deployment` to v5.5.0 using an already-authorized administrative path (HACS when the v5.5 repository is published, or the signed JNS platform-update workflow). Restart Home Assistant if required by the chosen update method.

## Enroll replacement PC

In Home Assistant:

```text
Settings → Devices & services → JNS Deployment Platform → Configure
→ Enrol a new management PC
```

Generate the one-time code. On Windows Manager v5.5 click **ENROLL THIS PC** and enter the code.

Home Assistant retains existing legacy SFTP keys and the old `jns-config-production` publisher while adding the new PC's independent public keys.

## Commission

Click **COMMISSION THIS PC**. It must pass:

```text
per-PC signing
→ strict SFTP key authentication
→ package validation
→ plan
→ dry-run / HA config check
→ transactional install
→ rollback
→ mark commissioned
```

## Revoke legacy access

Only after commissioning succeeds:

```text
JNS Deployment Platform → Configure → Manage JNS management PCs
→ Revoke legacy pre-v5.5 PC credentials
```

Then revoke the old PC itself when no longer required.

## Privilege separation

Enrolled per-PC publisher keys have `config` scope only. Platform updates remain separately privileged and must not be authorized by a normal management-PC config key.
