import requests
import responses
import pytest
import base64
from datetime import datetime, timezone, timedelta

from roomdoo_locks_salto import SaltoProvider
from roomdoo_locks_base.exceptions import (
    LockAuthError,
    LockConnectionError,
    LockNotFoundError,
    LockOperationError,
)

# ── Constantes de prueba ─────────────────────────────────────────────────────

CLIENT_ID     = "fake_client_id"
CLIENT_SECRET = "fake_client_secret"
USERNAME      = "fake_user"
PASSWORD      = "fake_pass"
SITE_ID       = "fake_site_id"
LOCK_ID       = "fake_lock_id"
SITE_USER_ID  = "fake_site_user_id"
USER_ID       = "fake_user_id"
ACCESS_GROUP_ID   = "fake_access_group_id"
TIME_SCHEDULE_ID  = "fake_time_schedule_id"
ROLE_ID = "fake_role_id"

IDENTITY_URL = "https://identity-acc.eu.my-clay.com/connect/token"
API_BASE     = "https://clp-accept-user.my-clay.com"

# ── Helpers ──────────────────────────────────────────────────────────────────

def mock_auth():
    """Mock de autenticación reutilizable."""
    responses.post(
        IDENTITY_URL,
        json={
            "access_token": "fake_access_token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "user_api.full_access"
        }
    )

def make_provider():
    """Instancia el provider (requiere mock_auth activo)."""
    return SaltoProvider(CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD, SITE_ID)

@pytest.fixture
def time_range():
    starts_at = datetime.now(timezone.utc)
    ends_at   = starts_at + timedelta(hours=24)
    return starts_at, ends_at

def mock_add_user_to_site():
    responses.post(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users",
        json={
            "id": SITE_USER_ID,
            "user": {
                "id": USER_ID,
                "email": "prueba@gmail.com",
                "first_name": "Prueba",
                "last_name": "API"
            },
            "roles": [
                ROLE_ID
            ],
            "alias": "Prueba API",
            "subscription_state": "subscribed",
            "use_pin": True
        }
    )

def mock_add_access_group():
    responses.post(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/access_groups",
        json={"id": ACCESS_GROUP_ID, "customer_reference": "Grupo de Acceso"}
    )

def mock_add_time_schedule(start_date, end_date):
    responses.post(
        f"{API_BASE}/v1.1/sites/{SITE_ID}/access_groups/{ACCESS_GROUP_ID}/time_schedules",
        json={
            "id": TIME_SCHEDULE_ID,
            "start_date": start_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date": end_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True, "saturday": True, "sunday": True,
            "start_time": "00:00:00",
            "end_time": "23:59:59"
        }
    )

def mock_add_user_to_access_group():
    responses.post(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/access_groups/{ACCESS_GROUP_ID}/users",
        json={"id": USER_ID, "first_name": "Prueba", "last_name": "API"}
    )

def mock_add_lock_to_access_group():
    responses.post(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/access_groups/{ACCESS_GROUP_ID}/locks",
        json={"id": LOCK_ID, "customer_reference": "Cerradura"}
    )

def mock_create_pin():
    responses.put(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users/{SITE_USER_ID}/pin",
        body="123456"
    )

# ── Tests de autenticación ────────────────────────────────────────────────────

@responses.activate
def test_authentication_success():
    mock_auth()
    provider = make_provider()
    assert provider.accessToken == "fake_access_token"


@responses.activate
def test_authentication_invalid_credentials():
    responses.post(
        IDENTITY_URL,
        json={"error": "invalid_client"},
        status=401
    )
    with pytest.raises(LockAuthError):
        make_provider()


@responses.activate
def test_authentication_missing_token():
    responses.post(
        IDENTITY_URL,
        json={"error": "invalid_grant"},
        status=400
    )
    with pytest.raises(LockAuthError):
        make_provider()


# ── Tests de test_connection ──────────────────────────────────────────────────

@responses.activate
def test_connection_success():
    mock_auth()
    provider = make_provider()
    mock_auth()  # test_connection vuelve a autenticar
    assert provider.test_connection() is True


# ── Tests de add_user_to_site ─────────────────────────────────────────────────

@responses.activate
def test_add_user_to_site_success():
    mock_auth()
    provider = make_provider()
    mock_add_user_to_site()
    result = provider._add_user_to_site("Prueba", "API", ROLE_ID, "prueba@gmail.com")
    assert result["site_user_id"] == SITE_USER_ID
    assert result["user_id"] == USER_ID


@responses.activate
def test_add_user_to_site_not_found():
    mock_auth()
    provider = make_provider()
    responses.post(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users",
        json={"ErrorCode": "1100", "Message": "Site not found"},
        status=404
    )
    with pytest.raises(LockNotFoundError):
        provider._add_user_to_site("Prueba", "API", ROLE_ID, "prueba@gmail.com")


# ── Tests de access groups ────────────────────────────────────────────────────

@responses.activate
def test_add_access_group_success():
    mock_auth()
    provider = make_provider()
    mock_add_access_group()
    access_group_id = provider._add_access_group_to_site("Grupo de Acceso")
    assert access_group_id == ACCESS_GROUP_ID


@responses.activate
def test_delete_access_group_success():
    mock_auth()
    provider = make_provider()
    responses.delete(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/access_groups/{ACCESS_GROUP_ID}",
        status=204
    )
    assert provider._delete_access_group_from_site(ACCESS_GROUP_ID) is True


# ── Tests de time schedules ───────────────────────────────────────────────────

@responses.activate
def test_add_time_schedule_success(time_range):
    mock_auth()
    provider = make_provider()
    starts_at, ends_at = time_range
    mock_add_time_schedule(starts_at, ends_at)
    result = provider._add_time_schedule_to_access_group(ACCESS_GROUP_ID, starts_at, ends_at)
    assert result["time_schedule_id"] == TIME_SCHEDULE_ID
    assert "start_date" in result
    assert "end_date" in result


@responses.activate
def test_modify_time_schedule_success(time_range):
    mock_auth()
    provider = make_provider()
    starts_at, ends_at = time_range
    new_ends_at = ends_at + timedelta(hours=12)
    responses.patch(
        f"{API_BASE}/v1.1/sites/{SITE_ID}/access_groups/{ACCESS_GROUP_ID}/time_schedules/{TIME_SCHEDULE_ID}",
        json={
            "id": TIME_SCHEDULE_ID,
            "start_date": starts_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date": new_ends_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True, "saturday": True, "sunday": True,
            "start_time": "00:00:00",
            "end_time": "23:59:59"
        }
    )
    result = provider._modify_time_schedule_in_access_group(ACCESS_GROUP_ID, TIME_SCHEDULE_ID, starts_at, new_ends_at)
    assert result["time_schedule_id"] == TIME_SCHEDULE_ID


@responses.activate
def test_delete_time_schedule_success():
    mock_auth()
    provider = make_provider()
    responses.delete(
        f"{API_BASE}/v1.1/sites/{SITE_ID}/access_groups/{ACCESS_GROUP_ID}/time_schedules/{TIME_SCHEDULE_ID}",
        status=204
    )
    assert provider._delete_time_schedule_from_access_group(ACCESS_GROUP_ID, TIME_SCHEDULE_ID) is True


# ── Tests de suscripción de usuario ──────────────────────────────────────────

@responses.activate
def test_unsubscribe_user_success():
    mock_auth()
    provider = make_provider()
    responses.patch(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users/{SITE_USER_ID}/subscription",
        status=204
    )
    assert provider._unsubscribe_user_from_site(SITE_USER_ID) is True


@responses.activate
def test_subscribe_user_success():
    mock_auth()
    provider = make_provider()
    responses.patch(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users/{SITE_USER_ID}/subscription",
        status=204
    )
    assert provider._subscribe_user_to_site(SITE_USER_ID) is True


# ── Tests de delete_user_from_site ────────────────────────────────────────────

@responses.activate
def test_delete_user_from_site_success():
    mock_auth()
    provider = make_provider()
    responses.delete(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users/{SITE_USER_ID}",
        status=204
    )
    assert provider._delete_user_from_site(SITE_USER_ID) is True


@responses.activate
def test_delete_user_from_site_not_found():
    mock_auth()
    provider = make_provider()
    responses.delete(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users/{SITE_USER_ID}",
        status=404,
        json={"ErrorCode": "1100", "Message": "User not found"}
    )
    with pytest.raises(LockNotFoundError):
        provider._delete_user_from_site(SITE_USER_ID)


# ── Tests de create_modify_user_pin ──────────────────────────────────────────

@responses.activate
def test_create_modify_user_pin_success(time_range):
    mock_auth()
    provider = make_provider()
    starts_at, ends_at = time_range
    mock_create_pin()
    result = provider._create_modify_user_pin(ACCESS_GROUP_ID, SITE_USER_ID, LOCK_ID, starts_at, ends_at)
    assert result.pin == "123456"
    assert result.code_id == ACCESS_GROUP_ID
    assert result.lock_id == LOCK_ID


@responses.activate
def test_create_modify_user_pin_error(time_range):
    mock_auth()
    provider = make_provider()
    starts_at, ends_at = time_range
    responses.put(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users/{SITE_USER_ID}/pin",
        json={"ErrorCode": "1100", "Message": "Invalid parameter"},
        status=400
    )
    with pytest.raises(LockAuthError):
        provider._create_modify_user_pin(ACCESS_GROUP_ID, SITE_USER_ID, LOCK_ID, starts_at, ends_at)


# ── Tests de create_code (flujo completo) ─────────────────────────────────────

@responses.activate
def test_create_code_full_flow(time_range):
    mock_auth()
    provider = make_provider()
    starts_at, ends_at = time_range

    mock_add_user_to_site()
    mock_add_access_group()
    mock_add_time_schedule(starts_at, ends_at)
    mock_add_user_to_access_group()
    mock_add_lock_to_access_group()
    mock_create_pin()

    result = provider._do_create_code(LOCK_ID, starts_at, ends_at, "Prueba", "API", ROLE_ID, "prueba@gmail.com", "Grupo de Acceso")
    assert result.pin == "123456"
    assert result.code_id == ACCESS_GROUP_ID
    assert result.lock_id == LOCK_ID


# ── Tests de invalidate_code ──────────────────────────────────────────────────

@responses.activate
def test_invalidate_code_success():
    mock_auth()
    provider = make_provider()
    responses.delete(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/access_groups/{ACCESS_GROUP_ID}",
        status=204
    )
    responses.patch(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users/{SITE_USER_ID}/subscription",
        status=204
    )
    assert provider._do_invalidate_code(ACCESS_GROUP_ID, SITE_USER_ID) is True


# ── Tests de validación de fechas ─────────────────────────────────────────────

@responses.activate
def test_invalid_time_range(time_range):
    mock_auth()
    provider = make_provider()
    starts_at, ends_at = time_range
    with pytest.raises(ValueError):
        provider.create_code(LOCK_ID, ends_at, starts_at, "Prueba", "API", ROLE_ID)


@responses.activate
def test_naive_datetime(time_range):
    mock_auth()
    provider = make_provider()
    starts_at, ends_at = time_range
    with pytest.raises(ValueError):
        provider.create_code(LOCK_ID, datetime.now(), ends_at, "Prueba", "API", ROLE_ID)


# ── Tests de errores de conexión ──────────────────────────────────────────────

@responses.activate
def test_connection_error_on_auth():
    responses.post(
        IDENTITY_URL,
        body=requests.exceptions.ConnectionError("Connection refused")
    )
    with pytest.raises(LockConnectionError):
        make_provider()


@responses.activate
def test_server_error_on_add_user():
    mock_auth()
    provider = make_provider()
    responses.post(
        f"{API_BASE}/v1.2/sites/{SITE_ID}/users",
        status=500,
        json={"ErrorCode": "9999", "Message": "Internal server error"}
    )
    with pytest.raises(LockConnectionError):
        provider._add_user_to_site("Prueba", "API", "fake_role_id", "prueba@gmail.com")
