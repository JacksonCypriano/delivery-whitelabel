from django.urls import path
from .api import (
    Session, Password, Dashboard, ResourceList, ResourceDetail, ResourceAction, History,
)
from .integrations import Finance, Whatsapp
from .api import ListEdit
from .orders import (
    OrdersBoard, OrderOperationsDetail, OrderTransition, OrderEstimate, OrderSettings,
    ManualOrderCatalog, ManualOrderQuote, ManualOrderCreate,
)
from .kitchen import Kitchen, KitchenAction
from .sales import Sales
from .conversations import Conversations
from .crm import CRM
from .logistics import Logistics, DeliveryPhoto
from apps.channels.views import Integrations, CancellationReasons, IntegrationEvents
from .api import Selection, Relationships, Activity
from .food99_review import Food99ReviewList, Food99ReviewDetail
from .food99_workflow_api import (
    Food99ReviewSummary, Food99ReviewAcknowledge,
    Food99ReviewRefresh, Food99ReviewCompare,
)

from .food99_operational_api import (
    Food99OperationalReadiness, Food99OperationalPreview,
    Food99SandboxStage, Food99SandboxBatchRefresh, Food99IntegrityAudit,
    Food99OperationalDryRun, Food99OperationalBatchDryRun,
    Food99SimulatedImport, Food99SimulationAvailability, Food99SimulatedEvent, Food99Telemetry, Food99BacklogPreview,
)

urlpatterns = [
    path("activity/", Activity.as_view()),
    path("resources/<slug:resource>/selection/", Selection.as_view()),
    path("resources/<slug:resource>/<str:pk>/relationships/", Relationships.as_view()),
    path("integrations/", Integrations.as_view()),
    path("integrations/events/", IntegrationEvents.as_view()),
    path("integrations/99food/telemetry/", Food99Telemetry.as_view()),
    path("integrations/99food/backlog/", Food99BacklogPreview.as_view()),
    path("integrations/99food/simulation-availability/", Food99SimulationAvailability.as_view()),
    path("integrations/99food/simulated-import/", Food99SimulatedImport.as_view()),
    path("integrations/99food/simulated-event/", Food99SimulatedEvent.as_view()),
    path("integrations/99food/integrity-audit/", Food99IntegrityAudit.as_view()),
    path("integrations/99food/operational-readiness/", Food99OperationalReadiness.as_view()),
    path("integrations/99food/operational-preview/<int:pk>/", Food99OperationalPreview.as_view()),
    path("integrations/99food/operational-dryrun/<int:pk>/", Food99OperationalDryRun.as_view()),
    path("integrations/99food/operational-dryrun-batch/", Food99OperationalBatchDryRun.as_view()),
    path("integrations/99food/sandbox-stage/", Food99SandboxStage.as_view()),
    path("integrations/99food/sandbox-refresh-batch/", Food99SandboxBatchRefresh.as_view()),
    path("integrations/99food/review/", Food99ReviewList.as_view()),
    path("integrations/99food/review/summary/", Food99ReviewSummary.as_view()),
    path("integrations/99food/review/<int:pk>/", Food99ReviewDetail.as_view()),
    path("integrations/99food/review/<int:pk>/acknowledge/", Food99ReviewAcknowledge.as_view()),
    path("integrations/99food/review/<int:pk>/refresh/", Food99ReviewRefresh.as_view()),
    path("integrations/99food/review/<int:pk>/compare/", Food99ReviewCompare.as_view()),
    path("orders/<int:pk>/cancellation-reasons/", CancellationReasons.as_view()),
    path("logistics/", Logistics.as_view()),
    path("logistics/<int:pk>/photo/", DeliveryPhoto.as_view()),
    path("crm/", CRM.as_view()),
    path("conversations/", Conversations.as_view()),
    path("sales/", Sales.as_view()),
    path("kitchen/", Kitchen.as_view()),
    path("kitchen/<int:pk>/", KitchenAction.as_view()),
    path("session/", Session.as_view()),
    path("password/", Password.as_view()),
    path("dashboard/", Dashboard.as_view()),
    path("orders/", OrdersBoard.as_view()),
    path("orders/settings/", OrderSettings.as_view()),
    path("orders/manual/catalog/", ManualOrderCatalog.as_view()),
    path("orders/manual/quote/", ManualOrderQuote.as_view()),
    path("orders/manual/", ManualOrderCreate.as_view()),
    path("orders/<int:pk>/", OrderOperationsDetail.as_view()),
    path("orders/<int:pk>/transition/", OrderTransition.as_view()),
    path("orders/<int:pk>/estimate/", OrderEstimate.as_view()),
    path("resources/<slug:resource>/", ResourceList.as_view()),
    path("resources/<slug:resource>/new/", ResourceDetail.as_view()),
    path("resources/<slug:resource>/list-edit/", ListEdit.as_view()),
    path("resources/<slug:resource>/actions/", ResourceAction.as_view()),
    path("resources/<slug:resource>/<int:pk>/history/", History.as_view()),
    path("resources/<slug:resource>/<int:pk>/", ResourceDetail.as_view()),
    path("finance/", Finance.as_view()),
    path("finance/purchase/", Finance.as_view(), {"action": "purchase"}),
    path("finance/notes/", Finance.as_view(), {"action": "notes"}),
    path("finance/fees/", Finance.as_view(), {"action": "fees"}),
    path("finance/invoices/<uuid:invoice_id>/", Finance.as_view(), {"action": "invoice"}),
    path("finance/invoices/<uuid:invoice_id>/refresh/", Finance.as_view(), {"action": "refresh"}),
    path("finance/invoices/<uuid:invoice_id>/notes/<str:kind>/", Finance.as_view(), {"action": "download"}),
    path("whatsapp/", Whatsapp.as_view()),
]
