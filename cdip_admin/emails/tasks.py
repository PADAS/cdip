import logging
from .utils import send_invite_email
from cdip_admin.celery import app
from django.contrib.auth import get_user_model
from organizations.models import Organization


logger = logging.getLogger(__name__)
User = get_user_model()


@app.task(autoretry_for=(Exception,), retry_backoff=True)
def send_invite_email_task(user_id, org_id, is_new_user):
    try:
        user = User.objects.get(id=user_id)
        organization = Organization.objects.get(id=org_id)
        return send_invite_email(user, organization, is_new_user)
    except Exception as e:
        logger.error(
            f"Error sending invitation email to {user.email}: {e}.",
            extra={
                "user_id": user_id,
                "org_id": org_id,
                "is_new_user": is_new_user,
            }
        )
        raise e  # Raise and let celery retry
