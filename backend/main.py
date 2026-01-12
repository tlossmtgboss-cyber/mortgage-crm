import hmac
import hashlib
import base64
def _environment() -> str:
    return os.getenv("ENVIRONMENT", "development")


def _require_shared_secret(request: Request, header_name: str, expected_secret: str, service: str) -> None:
    if _environment() == "development":
        return

    if not expected_secret:
        logger.warning(f"{service} webhook secret not configured")
        raise HTTPException(status_code=503, detail=f"{service} webhook secret not configured")

    provided = request.headers.get(header_name)
    if not provided:
        raise HTTPException(status_code=401, detail=f"Missing {service} webhook secret")

    if not hmac.compare_digest(provided, expected_secret):
        raise HTTPException(status_code=401, detail=f"Invalid {service} webhook secret")


def _twilio_request_url(request: Request) -> str:
    override_base = os.getenv("TWILIO_WEBHOOK_BASE_URL", "").strip()
    if override_base:
        base = override_base.rstrip("/")
        url = f"{base}{request.url.path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        return url

    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        url = f"{forwarded_proto}://{forwarded_host}{request.url.path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        return url

    return str(request.url)


def _is_valid_twilio_signature(auth_token: str, signature: str, url: str, params: Dict[str, Any]) -> bool:
    if not signature:
        return False
    sorted_items = sorted((key, str(value)) for key, value in params.items())
    payload = url + "".join(f"{key}{value}" for key, value in sorted_items)
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


        vapi_secret = os.getenv("VAPI_WEBHOOK_SECRET", "")
        _require_shared_secret(request, "X-Webhook-Secret", vapi_secret, "Vapi")

        twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        signature = request.headers.get("X-Twilio-Signature", "")
        if _environment() != "development":
            if not twilio_auth_token:
                raise HTTPException(status_code=503, detail="Twilio auth token not configured")
            request_url = _twilio_request_url(request)
            params = {key: str(value) for key, value in form_data.items()}
            if not _is_valid_twilio_signature(twilio_auth_token, signature, request_url, params):
                raise HTTPException(status_code=401, detail="Invalid Twilio signature")
        elif twilio_auth_token and signature:
            request_url = _twilio_request_url(request)
            params = {key: str(value) for key, value in form_data.items()}
            if not _is_valid_twilio_signature(twilio_auth_token, signature, request_url, params):
                raise HTTPException(status_code=401, detail="Invalid Twilio signature")

        sendgrid_secret = os.getenv("SENDGRID_INBOUND_WEBHOOK_SECRET", "")
        _require_shared_secret(request, "X-Webhook-Secret", sendgrid_secret, "SendGrid inbound")

