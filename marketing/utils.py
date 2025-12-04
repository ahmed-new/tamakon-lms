# marketing/utils.py
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.urls import reverse
from django.conf import settings
from django.template import Template, Context

signer = TimestampSigner(salt="visitor-unsub")

def build_unsubscribe_url(email: str) -> str:
    token = signer.sign(email)
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    path = reverse("marketing:visitor_unsubscribe") + f"?t={token}"
    return f"{base}{path}"

def verify_unsubscribe_token(token: str, max_age_days: int = 3650):
    try:
        email = signer.unsign(token, max_age=max_age_days * 24 * 3600)
        return email
    except (BadSignature, SignatureExpired):
        return None

def render_personalized(html: str, txt: str | None, ctx: dict) -> tuple[str, str]:
    # نسمح بـ {{ name }} {{ email }} {{ site_name }} {{ unsubscribe_url }} وغيرها
    html_out = Template(html).render(Context(ctx))
    txt_out  = Template(txt or "").render(Context(ctx)) if txt else ""
    return html_out, txt_out
