import json
import uuid

import pydantic
from integrations.models import (
    DeviceGroup,
    InboundIntegrationConfiguration,
    InboundIntegrationType,
    Organization,
    OutboundIntegrationConfiguration,
    OutboundIntegrationType,
)


class ERConfig(pydantic.BaseModel):
    name: str
    status: bool
    username: str
    password: str
    subscription_token: str
    provider_key: str
    domain: str

    @pydantic.validator("status", pre=True)
    def coerce_status(cls, val):
        return val == "enabled"


# Magic value for staging organization
ORGANIZATION_ID = "b394b478-61d0-46f8-b878-9b2644b0dc11"


def ensure_inbound_type():
    itype, created = InboundIntegrationType.objects.get_or_create(
        slug="awt_staging",
        defaults=dict(
            name="AWT-staging", description="Holding type for AWT configurations"
        ),
    )
    if created:
        print(f"Created Inbound Type: {itype}")
    return itype


def get_outbound_type():
    otype = OutboundIntegrationType.objects.get(slug="earth_ranger")
    return otype


def ensure_stage_organization():
    org, created = Organization.objects.get_or_create(
        id=uuid.UUID(ORGANIZATION_ID),
        defaults=dict(
            name="AWT Migration Stage",
            description="Placeholder Organization for holding pre-populated AWT configurations.",
        ),
    )
    if created:
        print(f"Created Organization: {org}")
    return org


def ensure_inbound_config(er_config, org, itype):

    ioc, created = InboundIntegrationConfiguration.objects.get_or_create(
        name=er_config.name,
        owner=org,
        type=itype,
        defaults=dict(
            login=er_config.username,
            password=er_config.password,
            endpoint="https://api.africawildlifetracking.com",
            provider=er_config.provider_key,
            token=er_config.subscription_token,
            enabled=False,
            state={"staged": True},
        ),
    )
    if created:
        print(f"Created Inbound Configuration: {ioc}")

    return ioc


def ensure_device_group(ioc):
    dg, created = DeviceGroup.objects.get_or_create(
        name=f"{ioc.name} - Default Group", owner=ioc.owner
    )
    if created:
        print(f"Created Device Group: {dg}")

    return dg


def run(input_filename, *args):

    with open(input_filename, "r") as fi:
        configs = json.load(fi)

    otype = get_outbound_type()
    if not otype:
        print("Outbound type is not present. Stubbornly insisting on having an 'earth_ranger' Outbound Type.")
        exit()

    itype = ensure_inbound_type()
    org = ensure_stage_organization()
    for domain, configs in configs.items():
        for config in configs:
            erconfig = ERConfig.parse_obj(dict(domain=domain, **config))
            if not erconfig.status:
                print(f"Skipping disabled configuration: {erconfig.name}")

            ioc = ensure_inbound_config(erconfig, org, itype)

            dg = ensure_device_group(ioc)
            ioc.default_devicegroup = dg
            ioc.save()

            oic, created = OutboundIntegrationConfiguration.objects.get_or_create(
                endpoint=f"https://{erconfig.domain}/api/v1.0",
                defaults=dict(
                    name=erconfig.domain, owner=org, type=otype, token="change-me"
                ),
            )

            oic.devicegroups.add(dg)
