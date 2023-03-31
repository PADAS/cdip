from django.template.loader import render_to_string
from django.conf import settings
from django.core.mail import send_mail
from accounts.utils import get_password_reset_link


def send_invite_email(user, organization, is_new_user):
    subject = f"Gundi - You has been invited to {organization.name}"
    context = {
        "name": user.first_name,
        "organization": organization.name,
        "action_url": settings.EMAIL_INVITE_REDIRECT_URL,
        "is_new_user": is_new_user
    }
    email_html_message = render_to_string('invite_email.html', context)
    email_plaintext_message = render_to_string('invite_email.txt', context)
    to_email = user.email or user.username  # Fallback to username if email field isn't set
    return send_mail(
        subject=subject,
        message=email_plaintext_message,
        html_message=email_html_message,
        from_email=settings.EMAIL_FROM_DEFAULT,
        recipient_list=[to_email],
        fail_silently=False
    )
