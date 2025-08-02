# inventory/forms.py

from django import forms
from .models import (
    ItemMaster, GroupMaster, WarehouseMaster, Contact, 
    InwardHeader, InwardItem, OutwardHeader, OutwardItem, 
    ProductionHeader, ProductionItem, WarehouseTransferHeader, 
    WarehouseTransferItem, DeliveryOutHeader, DeliveryOutItem, 
    DeliveryInHeader, StockAdjustmentHeader, StockAdjustmentItem,
    BillOfMaterial, BOMItem,
)


class ItemMasterForm(forms.ModelForm):
    class Meta:
        model = ItemMaster
        # These are the fields that will be shown in the form
        fields = ['name', 'code', 'group', 'unit']

class GroupMasterForm(forms.ModelForm):
    class Meta:
        model = GroupMaster
        fields = ['name']
        
class WarehouseMasterForm(forms.ModelForm):
    class Meta:
        model = WarehouseMaster
        fields = ['name', 'parent']    
        
class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'type']

class InwardHeaderForm(forms.ModelForm):
    class Meta:
        model = InwardHeader
        fields = ['date', 'invoice_no', 'supplier', 'remarks']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.TextInput(),
        }

class InwardItemForm(forms.ModelForm):
    group = forms.ModelChoiceField(queryset=GroupMaster.objects.all(), required=True)

    class Meta:
        model = InwardItem
        fields = ['group', 'item', 'warehouse', 'quantity']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMaster.objects.none()

        # This logic now correctly finds the prefixed field name (e.g., 'items-0-group')
        if self.data:
            try:
                group_id = int(self.data.get(f'{self.prefix}-group'))
                self.fields['item'].queryset = ItemMaster.objects.filter(group_id=group_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.item:
            self.fields['item'].queryset = ItemMaster.objects.filter(group=self.instance.item.group).order_by('name')
        
class OutwardHeaderForm(forms.ModelForm):
    class Meta:
        model = OutwardHeader
        fields = ['date', 'invoice_no', 'customer', 'remarks']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.TextInput(), # <-- Change remarks to a single line input
        }

class OutwardItemForm(forms.ModelForm):
    group = forms.ModelChoiceField(queryset=GroupMaster.objects.all(), required=True)

    class Meta:
        model = OutwardItem
        fields = ['group', 'item', 'warehouse', 'quantity']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMaster.objects.none()

        if self.data:
            try:
                group_id = int(self.data.get(f'{self.prefix}-group'))
                self.fields['item'].queryset = ItemMaster.objects.filter(group_id=group_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.item:
            self.fields['item'].queryset = ItemMaster.objects.filter(group=self.instance.item.group).order_by('name')
        
class ProductionHeaderForm(forms.ModelForm):
    class Meta:
        model = ProductionHeader
        fields = ['date', 'reference_no', 'remarks']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.TextInput(),
        }


class ProductionItemForm(forms.ModelForm):
    group = forms.ModelChoiceField(queryset=GroupMaster.objects.all(), required=True)

    class Meta:
        model = ProductionItem
        fields = ['group', 'item', 'warehouse', 'quantity']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMaster.objects.none()

        if self.data:
            try:
                group_id = int(self.data.get(f'{self.prefix}-group'))
                self.fields['item'].queryset = ItemMaster.objects.filter(group_id=group_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.item:
            self.fields['item'].queryset = ItemMaster.objects.filter(group=self.instance.item.group).order_by('name')
        
class WarehouseTransferHeaderForm(forms.ModelForm):
    class Meta:
        model = WarehouseTransferHeader
        fields = ['date', 'reference_no', 'remarks']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.TextInput(),
        }

class WarehouseTransferItemForm(forms.ModelForm):
    group = forms.ModelChoiceField(queryset=GroupMaster.objects.all(), required=True)

    class Meta:
        model = WarehouseTransferItem
        fields = ['group', 'item', 'from_warehouse', 'to_warehouse', 'quantity']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMaster.objects.none()

        if self.data:
            try:
                group_id = int(self.data.get(f'{self.prefix}-group'))
                self.fields['item'].queryset = ItemMaster.objects.filter(group_id=group_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.item:
            self.fields['item'].queryset = ItemMaster.objects.filter(group=self.instance.item.group).order_by('name')

        
class DeliveryOutHeaderForm(forms.ModelForm):
    class Meta:
        model = DeliveryOutHeader
        fields = ['date', 'reference_no', 'to_person', 'vehicle_number', 'remarks']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

class DeliveryOutItemForm(forms.ModelForm):
    class Meta:
        model = DeliveryOutItem
        fields = ['item', 'from_warehouse', 'issued_quantity']

class DeliveryInHeaderForm(forms.ModelForm):
    class Meta:
        model = DeliveryInHeader
        fields = ['date', 'remarks']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}


class StockAdjustmentHeaderForm(forms.ModelForm):
    class Meta:
        model = StockAdjustmentHeader
        fields = ['date', 'reason']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.TextInput()
        }

class StockAdjustmentItemForm(forms.ModelForm):
    group = forms.ModelChoiceField(queryset=GroupMaster.objects.all(), required=True)
    class Meta:
        model = StockAdjustmentItem
        fields = ['group', 'item', 'warehouse', 'adjustment_type', 'quantity']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMaster.objects.none()
        if self.data:
            try:
                group_id = int(self.data.get(f'{self.prefix}-group'))
                self.fields['item'].queryset = ItemMaster.objects.filter(group_id=group_id).order_by('name')
            except (ValueError, TypeError): pass
        elif self.instance.pk and self.instance.item:
            self.fields['item'].queryset = ItemMaster.objects.filter(group=self.instance.item.group).order_by('name')

class BOMForm(forms.ModelForm):
    group = forms.ModelChoiceField(queryset=GroupMaster.objects.all(), required=True)

    class Meta:
        model = BillOfMaterial
        fields = ['group', 'item']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMaster.objects.none()

class BOMItemForm(forms.ModelForm):
    group = forms.ModelChoiceField(queryset=GroupMaster.objects.all(), required=True)

    class Meta:
        model = BOMItem
        fields = ['group', 'item', 'quantity']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMaster.objects.none()

        if self.data:
            try:
                group_id = int(self.data.get(f'{self.prefix}-group'))
                self.fields['item'].queryset = ItemMaster.objects.filter(group_id=group_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.item:
            self.fields['item'].queryset = ItemMaster.objects.filter(group=self.instance.item.group).order_by('name')