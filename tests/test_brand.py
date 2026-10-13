from homeassistant.setup import async_setup_component

from custom_components.myq_community.const import DOMAIN


async def test_brand_images_served_locally(hass, hass_client, setup_integration):
    """HA 2026.3+ serves custom integration icons from the brand/ folder."""
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client()
    for name in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png"):
        resp = await client.get(f"/api/brands/integration/{DOMAIN}/{name}")
        assert resp.status == 200, name
        assert (await resp.read()).startswith(b"\x89PNG"), name
