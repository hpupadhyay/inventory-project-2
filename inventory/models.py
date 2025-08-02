from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

# AbstractUser is the built-in User model. We extend it to add our custom fields.
class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('user', 'User'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    can_edit = models.BooleanField(default=True)
    can_delete = models.BooleanField(default=False)

class GroupMaster(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class WarehouseMaster(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # This allows for hierarchical warehouses (e.g., Floor 1 is a child of Main Building)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')

    def __str__(self):
        return self.name

class Contact(models.Model):
    TYPE_CHOICES = (
        ('Supplier', 'Supplier'),
        ('Customer', 'Customer'),
    )
    name = models.CharField(max_length=150, unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    def __str__(self):
        return f"{self.name} ({self.type})"

class ItemMaster(models.Model):
    name = models.CharField(max_length=150, unique=True, help_text="The name of the item.")
    code = models.CharField(max_length=50, unique=True, null=True, blank=True, help_text="Unique code or SKU for the item.")
    unit = models.CharField(max_length=20, help_text="e.g., KG, PCS, LTR")
    group = models.ForeignKey(GroupMaster, on_delete=models.PROTECT, related_name='items')

    def __str__(self):
        return f"{self.name} ({self.code or 'No Code'})"

class OpeningStock(models.Model):
    """Represents the current stock balance of an item in a specific warehouse."""
    item = models.ForeignKey(ItemMaster, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(WarehouseMaster, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        # Ensures that you can't have two stock entries for the same item in the same warehouse.
        unique_together = ('item', 'warehouse')

    def __str__(self):
        return f"{self.item.name} in {self.warehouse.name}: {self.quantity}"

class InwardHeader(models.Model):
    """The main record for an inward transaction."""
    date = models.DateField()
    invoice_no = models.CharField(max_length=50, unique=True)
    supplier = models.ForeignKey(Contact, on_delete=models.PROTECT, limit_choices_to={'type': 'Supplier'})
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='inward_entries')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Inward INV-{self.invoice_no} on {self.date}"

class InwardItem(models.Model):
    """An individual line item within an inward transaction."""
    header = models.ForeignKey(InwardHeader, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(WarehouseMaster, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} x {self.item.name} for INV-{self.header.invoice_no}"
        
class OutwardHeader(models.Model):
    """The main record for an outward transaction."""
    date = models.DateField()
    invoice_no = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Contact, on_delete=models.PROTECT, limit_choices_to={'type': 'Customer'})
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='outward_entries')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Outward INV-{self.invoice_no} on {self.date}"

class OutwardItem(models.Model):
    """An individual line item within an outward transaction."""
    header = models.ForeignKey(OutwardHeader, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(WarehouseMaster, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} x {self.item.name} for INV-{self.header.invoice_no}"
class ProductionHeader(models.Model):
    date = models.DateField()
    reference_no = models.CharField(max_length=50, unique=True)
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='productions')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Production Ref-{self.reference_no} on {self.date}"

class ProductionItem(models.Model):
    TYPE_CHOICES = (
        ('Produced', 'Produced'),
        ('Consumed', 'Consumed'),
    )
    header = models.ForeignKey(ProductionHeader, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(WarehouseMaster, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    def __str__(self):
        return f"{self.quantity} x {self.item.name} ({self.type})"
        

class WarehouseTransferHeader(models.Model):
    date = models.DateField()
    reference_no = models.CharField(max_length=50, unique=True)
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='transfers')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transfer Ref-{self.reference_no} on {self.date}"

class WarehouseTransferItem(models.Model):
    header = models.ForeignKey(WarehouseTransferHeader, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    from_warehouse = models.ForeignKey(WarehouseMaster, on_delete=models.PROTECT, related_name='transfers_from')
    to_warehouse = models.ForeignKey(WarehouseMaster, on_delete=models.PROTECT, related_name='transfers_to')

    def __str__(self):
        return f"{self.quantity} x {self.item.name} from {self.from_warehouse.name}"
        
class DeliveryOutHeader(models.Model):
    date = models.DateField()
    reference_no = models.CharField(max_length=50, unique=True)
    to_person = models.ForeignKey(Contact, on_delete=models.PROTECT, related_name='deliveries_to')
    vehicle_number = models.CharField(max_length=20, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='deliveries_out')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Material Out Ref-{self.reference_no} to {self.to_person}"

class DeliveryOutItem(models.Model):
    header = models.ForeignKey(DeliveryOutHeader, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    from_warehouse = models.ForeignKey(WarehouseMaster, on_delete=models.PROTECT)
    issued_quantity = models.PositiveIntegerField()
    returned_quantity = models.PositiveIntegerField(default=0)

    @property
    def pending_quantity(self):
        return self.issued_quantity - self.returned_quantity

    def __str__(self):
        return f"{self.issued_quantity} x {self.item.name} from {self.header}"

class DeliveryInHeader(models.Model):
    date = models.DateField()
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='deliveries_in')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Material In on {self.date} (ID: {self.pk})"

class DeliveryInItem(models.Model):
    header = models.ForeignKey(DeliveryInHeader, on_delete=models.CASCADE, related_name='items')
    # Link back to the original item that was sent out
    original_delivery_item = models.ForeignKey(DeliveryOutItem, on_delete=models.PROTECT)
    returned_quantity = models.PositiveIntegerField()
    to_warehouse = models.ForeignKey(WarehouseMaster, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.returned_quantity} x {self.original_delivery_item.item.name} returned"


class StockAdjustmentHeader(models.Model):
    date = models.DateField()
    reason = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Adjustment on {self.date} (Reason: {self.reason[:20]}...)"

class StockAdjustmentItem(models.Model):
    ADJUSTMENT_TYPE_CHOICES = (('ADD', 'Increase'), ('SUB', 'Decrease'))
    header = models.ForeignKey(StockAdjustmentHeader, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(WarehouseMaster, on_delete=models.PROTECT)
    adjustment_type = models.CharField(max_length=3, choices=ADJUSTMENT_TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.get_adjustment_type_display()} {self.quantity} of {self.item.name}"

class BillOfMaterial(models.Model):
    item = models.OneToOneField(ItemMaster, on_delete=models.CASCADE, related_name='bom')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"BOM for {self.item.name}"

class BOMItem(models.Model):
    bom = models.ForeignKey(BillOfMaterial, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} of {self.item.name}"