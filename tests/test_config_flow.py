import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from myqcommunity import MyQAuthError, MyQOtpError, MyQRequestError, Token

from custom_components.myq_community.const import CONF_CODE, CONF_EMAIL, CONF_PASSWORD, CONF_TOKEN, DOMAIN

from .conftest import EMAIL, PASSWORD, TOKEN


async def start_flow(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def submit_credentials(hass, flow_id, email=EMAIL, password=PASSWORD):
    return await hass.config_entries.flow.async_configure(flow_id, {CONF_EMAIL: email, CONF_PASSWORD: password})


async def test_user_then_otp_creates_entry_without_password(hass, mock_auth):
    result = await start_flow(hass)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

    result = await submit_credentials(hass, result["flow_id"], email=f" {EMAIL} ")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "otp"
    assert result["description_placeholders"] == {"method": "text message", "destination": "(XXX) XXX-3392"}
    mock_auth.start_login.assert_awaited_once_with(EMAIL, PASSWORD)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "123456"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == EMAIL
    assert result["data"] == {CONF_EMAIL: EMAIL, CONF_TOKEN: TOKEN}  # no password stored
    assert result["result"].unique_id == EMAIL
    mock_auth.finish_login.assert_awaited_once_with(mock_auth.pending, "123456")
    assert mock_auth.init_kwargs["http"] is not None  # HA's shared httpx client


async def test_wrong_code_can_be_retried(hass, mock_auth):
    result = await start_flow(hass)
    result = await submit_credentials(hass, result["flow_id"])

    mock_auth.finish_login.side_effect = MyQOtpError("rejected")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "000000"})
    assert result["step_id"] == "otp" and result["errors"] == {"base": "invalid_code"}

    mock_auth.finish_login.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "123456"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_auth.start_login.await_count == 1  # same pending login, no new code sent


async def test_account_without_mfa_skips_code_step(hass, mock_auth):
    mock_auth.start_login.return_value = Token.from_dict(TOKEN)
    result = await start_flow(hass)
    result = await submit_credentials(hass, result["flow_id"])
    assert result["type"] is FlowResultType.CREATE_ENTRY
    mock_auth.finish_login.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (MyQAuthError("bad"), "invalid_auth"),
        (MyQRequestError("down"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_credential_errors_then_recovers(hass, mock_auth, error, key):
    mock_auth.start_login.side_effect = error
    result = await start_flow(hass)
    result = await submit_credentials(hass, result["flow_id"], password="wrong")
    assert result["step_id"] == "user" and result["errors"] == {"base": key}

    mock_auth.start_login.side_effect = None
    result = await submit_credentials(hass, result["flow_id"])
    assert result["step_id"] == "otp"


async def test_broken_login_at_code_step_restarts(hass, mock_auth):
    result = await start_flow(hass)
    result = await submit_credentials(hass, result["flow_id"])

    mock_auth.finish_login.side_effect = MyQRequestError("session gone")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "123456"})
    assert result["step_id"] == "user" and result["errors"] == {"base": "login_expired"}

    mock_auth.finish_login.side_effect = None
    result = await submit_credentials(hass, result["flow_id"])
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "654321"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_auth.start_login.await_count == 2


async def test_abandoned_flow_closes_pending_login(hass, mock_auth):
    result = await start_flow(hass)
    result = await submit_credentials(hass, result["flow_id"])
    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()
    mock_auth.pending.aclose.assert_awaited_once()


async def test_duplicate_account_aborts(hass, mock_auth, config_entry):
    result = await start_flow(hass)
    result = await submit_credentials(hass, result["flow_id"], email=EMAIL.upper())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_auth.start_login.assert_not_awaited()


async def test_reauth_asks_password_then_code(hass, setup_integration, mock_auth):
    entry = setup_integration
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["email"] == EMAIL

    mock_auth.start_login.side_effect = MyQAuthError("bad")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "still-wrong"})
    assert result["step_id"] == "reauth_confirm" and result["errors"] == {"base": "invalid_auth"}

    mock_auth.start_login.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "new-password"})
    assert result["step_id"] == "otp"
    mock_auth.start_login.assert_awaited_with(EMAIL, "new-password")

    new = {**TOKEN, "refresh_token": "fresh"}
    mock_auth.finish_login.return_value = Token.from_dict(new)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CODE: "123456"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == new
    assert CONF_PASSWORD not in entry.data
