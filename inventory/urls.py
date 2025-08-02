from django.urls import path
from django.contrib.auth.views import LogoutView

# Add InwardDeleteView to your imports
from .views import (
    DashboardView, 
    CustomLoginView, 
    ItemMasterView, 
    GroupMasterView, 
    WarehouseMasterView, 
    ContactMasterView,
    GroupUpdateView, GroupDeleteView,
    OpeningStockView,
    InwardView, InwardUpdateView, InwardDeleteView,
    OutwardView,
    ProductionView,
    WarehouseTransferView,
    DeliveryOutView,
    DeliveryInView,
    get_pending_items_for_person,
    StockReportView,
    StockReportDetailView,
    InwardReportView,
    PendingDeliveryReportView,
    get_items_api,
    OutwardReportView,
    ProductionReportView,
    StockAdjustmentView, 
    WarehouseTransferReportView,
    WarehouseTransferUpdateView, WarehouseTransferDeleteView,
    StockAdjustmentReportView, 
    StockAdjustmentUpdateView, StockAdjustmentDeleteView, 
    get_stock_api,
    get_item_stock_details_api,
    ImportView,ItemUpdateView, ItemDeleteView,
    OutwardUpdateView, OutwardDeleteView,
    ProductionUpdateView, ProductionDeleteView,
    BOMView,
)

urlpatterns = [
    # Authentication
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),

    # Main Pages
    path('', DashboardView.as_view(), name='dashboard'),
    
    # Master Data
    path('items/', ItemMasterView.as_view(), name='item_master'),
    path('items/<int:pk>/edit/', ItemUpdateView.as_view(), name='item_edit'),
    path('items/<int:pk>/delete/', ItemDeleteView.as_view(), name='item_delete'),
    path('groups/', GroupMasterView.as_view(), name='group_master'),
    path('groups/<int:pk>/edit/', GroupUpdateView.as_view(), name='group_edit'),
    path('groups/<int:pk>/delete/', GroupDeleteView.as_view(), name='group_delete'),
    path('warehouses/', WarehouseMasterView.as_view(), name='warehouse_master'),
    path('contacts/', ContactMasterView.as_view(), name='contact_master'),
    path('opening-stock/', OpeningStockView.as_view(), name='opening_stock'),

    # Transactions
    path('inward/', InwardView.as_view(), name='inward'),
    path('inward/<int:pk>/edit/', InwardUpdateView.as_view(), name='inward_edit'),
    path('inward/<int:pk>/delete/', InwardDeleteView.as_view(), name='inward_delete'), # <-- This was the missing line
    path('outward/', OutwardView.as_view(), name='outward'),
    path('outward/<int:pk>/edit/', OutwardUpdateView.as_view(), name='outward_edit'),
    path('outward/<int:pk>/delete/', OutwardDeleteView.as_view(), name='outward_delete'),
    path('production/', ProductionView.as_view(), name='production'),
    path('transfer/', WarehouseTransferView.as_view(), name='warehouse_transfer'),
    path('adjustment/', StockAdjustmentView.as_view(), name='stock_adjustment'),

    # Delivery Notes
    path('delivery-out/', DeliveryOutView.as_view(), name='delivery_out'),
    path('delivery-in/', DeliveryInView.as_view(), name='delivery_in'),
    path('api/get-pending-items/', get_pending_items_for_person, name='get_pending_items'),
    
    # Reports
    path('report/', StockReportView.as_view(), name='stock_report'),
    path('report/detail/', StockReportDetailView.as_view(), name='stock_report_detail'),
    path('report/pending-delivery/', PendingDeliveryReportView.as_view(), name='pending_delivery_report'),
    path('report/inward/', InwardReportView.as_view(), name='inward_report'),
    path('report/outward/', OutwardReportView.as_view(), name='outward_report'),
    path('report/production/', ProductionReportView.as_view(), name='production_report'),
    path('production/<int:pk>/edit/', ProductionUpdateView.as_view(), name='production_edit'),
    path('production/<int:pk>/delete/', ProductionDeleteView.as_view(), name='production_delete'),
    path('report/transfer/', WarehouseTransferReportView.as_view(), name='warehouse_transfer_report'),
    path('transfer/<int:pk>/edit/', WarehouseTransferUpdateView.as_view(), name='warehouse_transfer_edit'),
    path('transfer/<int:pk>/delete/', WarehouseTransferDeleteView.as_view(), name='warehouse_transfer_delete'),
    path('report/adjustment/', StockAdjustmentReportView.as_view(), name='stock_adjustment_report'),
    path('adjustment/<int:pk>/edit/', StockAdjustmentUpdateView.as_view(), name='stock_adjustment_edit'),
    path('adjustment/<int:pk>/delete/', StockAdjustmentDeleteView.as_view(), name='stock_adjustment_delete'),
    
    path('settings/bom/', BOMView.as_view(), name='bom_create'),
    
    
    # API
    path('api/get-stock/', get_stock_api, name='get_stock_api'),
    path('api/get-item-stock-details/', get_item_stock_details_api, name='get_item_stock_details_api'),
    
    #import
    path('import/', ImportView.as_view(), name='import_page'),
    
    # Better User options
    path('api/get-items/', get_items_api, name='get_items_api'),
]