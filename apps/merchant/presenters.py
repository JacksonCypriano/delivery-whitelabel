"""Explicit JSON allowlists for existing financial and WhatsApp view contexts.

Never serialize model __dict__: payment credentials must stay on the server.
"""

from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from .schema import value


def pick(obj, names):
    if obj is None:
        return None
    return {key: value(getattr(obj, key, None)) for key in names.split()}


def note_json(note):
    data = pick(note, "pk invoice_id number status created_at pdf_sha256 xml_sha256")
    if data:
        data["status_label"] = note.get_status_display()
        data["pdf"] = bool(data.pop("pdf_sha256"))
        data["xml"] = bool(data.pop("xml_sha256"))
    return data


def invoice_json(bill):
    data = pick(
        bill,
        "pk plan_name months amount method environment checkout_url status created_at paid_at due_date additional_service_id",
    )
    if data:
        data.update(
            status_label=bill.get_status_display(),
            method_label=bill.get_method_display(),
        )
        try:
            data["note"] = note_json(bill.fiscal_note)
        except ObjectDoesNotExist:
            data["note"] = None
    return data


def billing_json(template, ctx):
    data = {"title": ctx["title"]}
    if template == "billing/setup_required.html":
        data["missing"] = ctx["billing_profile_missing"]
    elif template == "billing/dashboard.html":
        data.update(
            subscription=pick(
                ctx["subscription"],
                "situation valid_until days_remaining manually_blocked payment_review",
            ),
            ready=ctx["ready"],
            sandbox=ctx["sandbox"],
            fiscal_count=ctx["fiscal_count"],
            customer=pick(ctx["customer"], "name document email"),
            invoices=[invoice_json(x) for x in ctx["invoices"]],
            latest_invoice=invoice_json(ctx["latest_invoice"]),
            page=ctx["history_page"].number,
            pages=ctx["history_page"].paginator.num_pages,
        )
        for key, field in [("plans", "plan"), ("services", "service")]:
            data[key] = [
                {
                    "item": pick(x[field], "pk name description months discount"),
                    "options": [
                        {k: value(v) for k, v in o.items()} for o in x["options"]
                    ],
                }
                for x in ctx[key]
            ]
    elif template == "billing/invoice.html":
        data["invoice"] = invoice_json(ctx["invoice"])
    elif template == "billing/fiscal_list.html":
        data.update(
            notes=[note_json(x) for x in ctx["notes"]],
            page=ctx["notes_page"].number,
            pages=ctx["notes_page"].paginator.num_pages,
            total=ctx["total_notes"],
            authorized=ctx["authorized_notes"],
            processing=ctx["processing_notes"],
        )
    elif template == "billing/online_fees.html":
        data.update(
            account=pick(ctx["payment_account"], "status provider_account_id"),
            fee_summary=ctx["fee_summary"],
            card_fee_rows=ctx["card_fee_rows"],
            fee_error=ctx["fee_error"],
        )
    else:
        raise ValueError("Unsupported merchant presentation")
    return JsonResponse(data)


def whatsapp_json(ctx):
    agent = ctx["agent"]
    data = {
        "agent": pick(
            agent,
            "status ai_enabled requires_pairing checked_at webhook_at connected_at disconnected_at last_error instance_name instance_created reconnect_attempts next_reconnect_at",
        ),
        "feature_enabled": ctx["feature_enabled"],
        "stale": ctx["stale"],
        "qr": ctx["qr"],
        "context_timeout_minutes": ctx["context_timeout_minutes"],
        "events": [pick(e, "created_at kind description") for e in ctx["events"]],
    }
    data["agent"]["status_label"] = agent.get_status_display()
    from .api import notices

    data["messages"] = notices(ctx["request"]) if "request" in ctx else []
    return JsonResponse(data)
