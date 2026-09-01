from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.customers.models import Customer
from .audit import record_event
from .models import PendingContactChange, PendingRegistration, User


@receiver(user_logged_in, dispatch_uid="security.login.success")
def login_success(sender, request, user, **kwargs):
    record_event("login_succeeded", user_id=user.pk, request=request)


@receiver(user_logged_out, dispatch_uid="security.logout")
def logout_success(sender, request, user, **kwargs):
    if user is not None:
        record_event("logout", user_id=user.pk, request=request)


@receiver(user_login_failed, dispatch_uid="security.login.failed")
def login_failure(sender, credentials, request, **kwargs):
    # Read only the login identifier; never copy the credentials dictionary.
    record_event("login_failed", request=request, reason="invalid_credentials",
                 identifier=credentials.get("username") or credentials.get("email") or "")
    if request is not None:
        request._security_login_failure_recorded = True


@receiver(pre_save, sender=User, dispatch_uid="security.user.before")
def user_before(sender, instance, raw=False, update_fields=None, **kwargs):
    instance._audit_previous_user = None
    if raw or not instance.pk:
        return
    tracked = {"email", "password"}
    if update_fields is not None and not tracked.intersection(update_fields):
        return
    instance._audit_previous_user = sender.objects.filter(pk=instance.pk).values("email", "password").first()


@receiver(post_save, sender=User, dispatch_uid="security.user.after")
def user_after(sender, instance, created, raw=False, update_fields=None, **kwargs):
    previous = instance.__dict__.pop("_audit_previous_user", None)
    if raw:
        return
    if created:
        record_event("account_created", scope="account", user_id=instance.pk)
    elif previous:
        if (update_fields is None or "email" in update_fields) and previous["email"] != instance.email:
            record_event("email_changed", scope="account", user_id=instance.pk, channel="email", identifier=instance.email)
        if (update_fields is None or "password" in update_fields) and previous["password"] != instance.password:
            record_event("password_changed", scope="account", user_id=instance.pk)


@receiver(pre_save, sender=Customer, dispatch_uid="security.customer.before")
def customer_before(sender, instance, raw=False, update_fields=None, **kwargs):
    instance._audit_previous_phone = None
    if raw or not instance.pk or (update_fields is not None and "phone" not in update_fields):
        return
    instance._audit_previous_phone = sender.objects.filter(pk=instance.pk).values_list("phone", flat=True).first()


@receiver(post_save, sender=Customer, dispatch_uid="security.customer.after")
def customer_after(sender, instance, created, raw=False, **kwargs):
    previous = instance.__dict__.pop("_audit_previous_phone", None)
    if not raw and not created and previous is not None and previous != instance.phone:
        record_event("phone_changed", scope="account", user_id=instance.user_id, channel="whatsapp", identifier=instance.phone)


@receiver(post_save, sender=PendingRegistration, dispatch_uid="security.registration.started")
def registration_started(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        record_event("registration_started", scope="registration", reference=instance.pk, identifier=instance.email)


@receiver(post_save, sender=PendingContactChange, dispatch_uid="security.contact.requested")
def contact_requested(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        record_event("contact_requested", scope="contact", reference=instance.pk,
                     user_id=instance.user_id, channel=instance.channel, identifier=instance.destination)
