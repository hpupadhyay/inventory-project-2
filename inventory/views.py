import csv
import io

from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.db.models import Sum, Count, Q, F, Value, CharField
from django.forms import inlineformset_factory
from django.db import transaction
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.db import models
from django.views.generic.edit import UpdateView, DeleteView
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from datetime import datetime
from django.db.models import Sum
from django.utils import timezone
from datetime import datetime

# Import your models
from .models import (
    User, ItemMaster, InwardHeader, GroupMaster, WarehouseMaster, Contact, OpeningStock, 
    InwardItem, OutwardHeader, OutwardItem, ProductionHeader, ProductionItem, 
    WarehouseTransferHeader, WarehouseTransferItem, DeliveryOutHeader, 
    DeliveryOutItem, DeliveryInHeader, DeliveryInItem, StockAdjustmentHeader, StockAdjustmentItem, BillOfMaterial, BOMItem, SystemSetting,
)

# Import your forms
from .forms import (
    CustomUserCreationForm, CustomUserChangeForm, ItemMasterForm, GroupMasterForm, WarehouseMasterForm, ContactForm, InwardHeaderForm, 
    InwardItemForm, OutwardHeaderForm, OutwardItemForm, ProductionHeaderForm, ProductionItemForm,
    WarehouseTransferHeaderForm, WarehouseTransferItemForm, DeliveryOutHeaderForm, 
    DeliveryOutItemForm, DeliveryInHeaderForm, DeliveryInItemForm, StockAdjustmentHeaderForm, StockAdjustmentItemForm, BOMForm, BOMItemForm, SystemSettingForm, OpeningStockForm,
)
# We need a new form for the item rows that allows the user to select the specific "Material Out" item they are returning.

def get_pending_delivery_items_api(request):
    person_id = request.GET.get('person_id')
    search_term = request.GET.get('term', '')

    if not person_id:
        return JsonResponse({'results': []})

    pending_items = DeliveryOutItem.objects.select_related('item').filter(
        header__to_person_id=person_id,
        issued_quantity__gt=models.F('returned_quantity')
    )

    if search_term:
        pending_items = pending_items.filter(item__name__icontains=search_term)

    results = [{
        'id': item.id,
        'text': f"{item.item.name} (Ref: {item.header.reference_no}, Pending: {item.pending_quantity})"
    } for item in pending_items]
    
    return JsonResponse({'results': results})
def get_pending_items_for_person(request):
    """An API-like view to fetch pending items for the selected person."""
    person_name = request.GET.get('person')
    pending_items = DeliveryOutItem.objects.filter(
        header__to_person__name=person_name,
        issued_quantity__gt=models.F('returned_quantity')
    ).select_related('item', 'from_warehouse')

    data = [{
        'id': item.id,
        'item_name': item.item.name,
        'from_warehouse': item.from_warehouse.name,
        'pending_quantity': item.pending_quantity
    } for item in pending_items]
    
    return JsonResponse({'items': data})
    
# for better search option on dropdown 

def get_items_api(request):
    group_id = request.GET.get('group_id')
    search_term = request.GET.get('term', '') # 'term' is the default search parameter for Select2
    
    items = ItemMaster.objects.filter(group_id=group_id).order_by('name')
    
    if search_term:
        items = items.filter(
            Q(name__icontains=search_term) | Q(code__icontains=search_term)
        )
        
    results = [{'id': item.id, 'text': f"{item.name} ({item.code or 'No Code'})"} for item in items]
    
    return JsonResponse({'results': results})

# for inward Stock details extract
def get_stock_api(request):
    try:
        item_id = request.GET.get('item_id')
        warehouse_id = request.GET.get('warehouse_id')
        stock = OpeningStock.objects.get(item_id=item_id, warehouse_id=warehouse_id)
        return JsonResponse({'stock_quantity': stock.quantity})
    except OpeningStock.DoesNotExist:
        return JsonResponse({'stock_quantity': 0})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# for outward stock details extract
def get_item_stock_details_api(request):
    item_id = request.GET.get('item_id')
    try:
        stock_details = OpeningStock.objects.filter(item_id=item_id).select_related('warehouse')
        data = [
            {'warehouse': stock.warehouse.name, 'quantity': stock.quantity} 
            for stock in stock_details
        ]
        return JsonResponse({'stock_details': data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# --- AUTH & DASHBOARD ---
class CustomLoginView(LoginView):
    template_name = 'inventory/login.html'
    redirect_authenticated_user = True


# inventory/views.py

class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        # --- Get User Filters ---
        warehouse_filter = request.GET.get('warehouse_filter')
        group_filter = request.GET.get('group_filter')

        # --- Base Querysets (using the correct OpeningStock model) ---
        stock_queryset = OpeningStock.objects.all()
        item_queryset = ItemMaster.objects.all()

        # Apply user filters if they are selected
        if warehouse_filter:
            stock_queryset = stock_queryset.filter(warehouse_id=warehouse_filter)
        if group_filter:
            stock_queryset = stock_queryset.filter(item__group_id=group_filter)
            item_queryset = item_queryset.filter(group_id=group_filter)
            
        # --- Calculate Stats using the filtered querysets ---
        total_stock_quantity = stock_queryset.aggregate(total=Sum('quantity'))['total'] or 0
        
        # FIX: Using a fixed value of 10 for low stock, as reorder_level doesn't exist
        low_stock_items = stock_queryset.select_related('item').filter(quantity__lte=10)

        top_items_by_stock = stock_queryset.select_related('item').order_by('-quantity')[:5]

        # --- Latest Transactions (No date filter) ---
        latest_inwards = InwardHeader.objects.annotate(type=Value('Inward', CharField()), name=F('contact__name')).values('date', 'type', 'name', 'pk', 'invoice_no')
        latest_outwards = OutwardHeader.objects.annotate(type=Value('Outward', CharField()), name=F('contact__name')).values('date', 'type', 'name', 'pk', 'invoice_no')
        latest_transactions = sorted(list(latest_inwards) + list(latest_outwards), key=lambda x: x['date'], reverse=True)[:5]
        
        context = {
            'total_stock_quantity': total_stock_quantity,
            'low_stock_items_count': low_stock_items.count(),
            'total_items_count': item_queryset.count(),
            'latest_transactions': latest_transactions,
            'chart_labels': [stock.item.name for stock in top_items_by_stock],
            'chart_data': [float(stock.quantity) for stock in top_items_by_stock],
            
            # Pass filter options and current values to the template
            'warehouses': WarehouseMaster.objects.all(),
            'groups': GroupMaster.objects.all(),
            'warehouse_filter': int(warehouse_filter) if warehouse_filter else None,
            'group_filter': int(group_filter) if group_filter else None,
        }
        return render(request, 'inventory/dashboard.html', context)
        
class ItemMasterView(LoginRequiredMixin, View):
    def get(self, request):
        form = ItemMasterForm()
        items_list = ItemMaster.objects.select_related('group').all().order_by('name')
        search_query = request.GET.get('search_query', '')
        group_filter = request.GET.get('group_filter')
        per_page = request.GET.get('per_page', 10)
        if search_query:
            items_list = items_list.filter(Q(name__icontains=search_query) | Q(code__icontains=search_query))
        if group_filter and group_filter.isnumeric():
            items_list = items_list.filter(group_id=group_filter)
        
        paginator = Paginator(items_list, per_page)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        context = {
            'form': form, 'items': page_obj, 'groups': GroupMaster.objects.all(),
            'search_query': search_query, 
            'group_filter': int(group_filter) if (group_filter and group_filter.isnumeric()) else None,
            'per_page': per_page,
        }
        return render(request, 'inventory/item_master.html', context)


    @transaction.atomic
    def post(self, request):
        # --- AJAX CSV Import Logic ---
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            csv_file = request.FILES.get('csv_file')
            if not csv_file:
                return JsonResponse({'status': 'error', 'message': 'No file was uploaded.'})

            try:
                decoded_file = csv_file.read().decode('utf-8-sig')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string)
                header = next(reader)
                original_rows = list(reader)

                report_rows = []
                successful_imports = 0
                
                existing_names = set(ItemMaster.objects.values_list('name', flat=True))
                existing_codes = set(ItemMaster.objects.filter(code__isnull=False).values_list('code', flat=True))

                # Loop through and process each row
                for i, row in enumerate(original_rows, start=2):
                    try:
                        item_name, item_code, group_name, unit = row
                        item_name = item_name.strip()
                        item_code = item_code.strip() or None

                        # Check for duplicates
                        if item_name in existing_names:
                            raise ValueError(f"Item name '{item_name}' already exists.")
                        if item_code and item_code in existing_codes:
                            raise ValueError(f"Item code '{item_code}' already exists.")

                        # If no errors, process the row
                        group, _ = GroupMaster.objects.get_or_create(name=group_name.strip())
                        ItemMaster.objects.create(name=item_name, code=item_code, group=group, unit=unit.strip())
                        
                        # Add to success report and update sets to prevent duplicates within the same file
                        report_rows.append(row + ['Imported Successfully'])
                        successful_imports += 1
                        existing_names.add(item_name)
                        if item_code: existing_codes.add(item_code)

                    except Exception as e:
                        report_rows.append(row + [f'Skipped - Error on line {i}: {e}'])
                
                # Generate the comprehensive report
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(header + ['Status'])
                writer.writerows(report_rows)
                
                message = f"Import complete. {successful_imports} items imported. {len(original_rows) - successful_imports} items failed."
                return JsonResponse({
                    'status': 'complete', 
                    'message': message,
                    'report_data': output.getvalue(), 
                    'filename': 'item_master_import_summary.csv'
                })

            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f'A critical error occurred: {e}'})


        # --- Standard Manual Form Submission Logic ---
        form = ItemMasterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item added successfully!')
            return redirect('item_master')
        
        # If manual form is invalid, re-render page with errors
        items_list = ItemMaster.objects.select_related('group').all().order_by('name')
        context = {'form': form, 'items': items_list, 'groups': GroupMaster.objects.all()}
        return render(request, 'inventory/item_master.html', context)
        
class ItemUpdateView(LoginRequiredMixin, UpdateView):
    model = ItemMaster
    form_class = ItemMasterForm
    template_name = 'inventory/item_master_edit.html' # We'll create this new template
    success_url = reverse_lazy('item_master')

class ItemDeleteView(LoginRequiredMixin, DeleteView):
    model = ItemMaster
    template_name = 'inventory/item_confirm_delete.html' # We'll create this new template
    success_url = reverse_lazy('item_master')
        
# Views for Group Master page (List/Create, Update, Delete)
class GroupMasterView(LoginRequiredMixin, View):
    def get(self, request):
        form = GroupMasterForm()
        groups = GroupMaster.objects.all().order_by('name')
        context = {'form': form, 'groups': groups}
        return render(request, 'inventory/group_master.html', context)

    def post(self, request):
        if 'download_template' in request.POST:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="group_master_template.csv"'
            writer = csv.writer(response)
            writer.writerow(['Group Name'])
            return response

        if 'import_csv' in request.POST:
            csv_file = request.FILES.get('csv_file')
            if not csv_file or not csv_file.name.endswith('.csv'):
                messages.error(request, 'Please upload a valid .csv file.')
                return redirect('group_master')
            try:
                decoded_file = csv_file.read().decode('utf-8')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string)
                next(reader)
                
                groups_created_count = 0
                for row in reader:
                    group_name = row[0]
                    _, created = GroupMaster.objects.get_or_create(name=group_name.strip())
                    if created:
                        groups_created_count += 1
                messages.success(request, f'Successfully imported {groups_created_count} new groups.')
            except Exception as e:
                messages.error(request, f'An error occurred during import: {e}')
            return redirect('group_master')

        form = GroupMasterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Group added successfully!')
            return redirect('group_master')
        
        groups = GroupMaster.objects.all().order_by('name')
        context = {'form': form, 'groups': groups}
        return render(request, 'inventory/group_master.html', context)

class GroupUpdateView(LoginRequiredMixin, UpdateView):
    model = GroupMaster
    form_class = GroupMasterForm
    template_name = 'inventory/group_master.html'
    success_url = reverse_lazy('group_master')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groups'] = GroupMaster.objects.all().order_by('name')
        return context

class GroupDeleteView(LoginRequiredMixin, DeleteView):
    model = GroupMaster
    template_name = 'inventory/group_confirm_delete.html'
    success_url = reverse_lazy('group_master')

class OpeningStockView(LoginRequiredMixin, View):
    def get(self, request):
        form = OpeningStockForm()
        stock_records = OpeningStock.objects.select_related('item', 'warehouse').all().order_by('-date', 'item__name')
        context = {'form': form, 'stock_records': stock_records}
        return render(request, 'inventory/opening_stock.html', context)

    def post(self, request):
        # We don't validate the form immediately. First, we get the key data.
        date = request.POST.get('date')
        item_id = request.POST.get('item')
        warehouse_id = request.POST.get('warehouse')

        # Try to find an existing instance based on the submitted data
        instance = OpeningStock.objects.filter(date=date, item_id=item_id, warehouse_id=warehouse_id).first()

        # Now, create the form. If an instance was found, this will be an update.
        # If no instance was found, this will be a create.
        form = OpeningStockForm(request.POST, instance=instance)

        if form.is_valid():
            form.save() # The .save() method correctly handles both creating and updating.
            
            # Provide a clearer success message
            message = "updated" if instance else "created"
            messages.success(request, f"Opening Stock record was {message} successfully.")
            
            return redirect('opening_stock')

        # If the form is not valid for other reasons (e.g., bad date format), re-render with errors.
        stock_records = OpeningStock.objects.select_related('item', 'warehouse').all().order_by('-date', 'item__name')
        context = {'form': form, 'stock_records': stock_records}
        return render(request, 'inventory/opening_stock.html', context)

        
# View for Warehouse Master page
class WarehouseMasterView(LoginRequiredMixin, View):
    def get(self, request):
        form = WarehouseMasterForm()
        warehouses = WarehouseMaster.objects.all().order_by('name')
        context = {'form': form, 'warehouses': warehouses}
        return render(request, 'inventory/warehouse_master.html', context)

    def post(self, request):
        form = WarehouseMasterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Warehouse added successfully!')
            return redirect('warehouse_master')
        warehouses = WarehouseMaster.objects.all().order_by('name')
        context = {'form': form, 'warehouses': warehouses}
        return render(request, 'inventory/warehouse_master.html', context)

class ContactMasterView(LoginRequiredMixin, View):
    def get(self, request):
        form = ContactForm()
        contacts = Contact.objects.all().order_by('type', 'name')
        context = {'form': form, 'contacts': contacts}
        return render(request, 'inventory/contact_master.html', context)

    def post(self, request):
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contact added successfully!')
            return redirect('contact_master')
        
        contacts = Contact.objects.all().order_by('type', 'name')
        context = {'form': form, 'contacts': contacts}
        return render(request, 'inventory/contact_master.html', context)

class InwardView(LoginRequiredMixin, View):
    InwardItemFormSet = inlineformset_factory(
        InwardHeader, InwardItem, form=InwardItemForm, 
        extra=1, can_delete=True,
    )

    def get(self, request):
        header_form = InwardHeaderForm()
        item_formset = self.InwardItemFormSet()
        context = {'header_form': header_form, 'item_formset': item_formset}
        return render(request, 'inventory/inward.html', context)

    @transaction.atomic
    def post(self, request):
        post_data = request.POST.copy()
        contact_id_or_name = post_data.get('contact')
        if contact_id_or_name and not contact_id_or_name.isnumeric():
            trans_type = post_data.get('transaction_type')
            contact_type = 'Customer' if trans_type == 'Sales Return' else 'Supplier'
            new_contact, _ = Contact.objects.get_or_create(
                name=contact_id_or_name.strip(), defaults={'type': contact_type}
            )
            post_data['contact'] = new_contact.id
        
        header_form = InwardHeaderForm(post_data)
        item_formset = self.InwardItemFormSet(post_data)
        
        if header_form.is_valid() and item_formset.is_valid():
            has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE') for form in item_formset)
            if not has_items:
                messages.error(request, "Cannot save a transaction with no items.")
            else:
                header = header_form.save(commit=False)
                header.created_by = request.user
                header.save()
                item_formset.instance = header
                item_formset.save()
                for form in item_formset.cleaned_data:
                    if form and not form.get('DELETE'):
                        stock, _ = OpeningStock.objects.get_or_create(item=form['item'], warehouse=form['warehouse'])
                        stock.quantity += form['quantity']
                        stock.save()
                messages.success(request, 'Inward transaction saved successfully!')
                return redirect('inward')

        context = {'header_form': header_form, 'item_formset': item_formset}
        return render(request, 'inventory/inward.html', context)
        
class OutwardView(LoginRequiredMixin, View):
    OutwardItemFormSet = inlineformset_factory(
        OutwardHeader, 
        OutwardItem, 
        form=OutwardItemForm, 
        extra=1, 
        can_delete=True, 
    )

    def get(self, request):
        header_form = OutwardHeaderForm()
        item_formset = self.OutwardItemFormSet()
        context = {
            'header_form': header_form, 
            'item_formset': item_formset,
        }
        return render(request, 'inventory/outward.html', context)

    @transaction.atomic
    def post(self, request):
        # (The logic for handling on-the-fly contact creation remains the same)
        post_data = request.POST.copy()
        contact_id_or_name = post_data.get('contact')
        if contact_id_or_name and not contact_id_or_name.isnumeric():
            trans_type = post_data.get('transaction_type')
            contact_type = 'Supplier' if trans_type == 'Purchase Return' else 'Customer'
            new_contact, _ = Contact.objects.get_or_create(
                name=contact_id_or_name.strip(),
                defaults={'type': contact_type}
            )
            post_data['contact'] = new_contact.id
        
        header_form = OutwardHeaderForm(post_data)
        item_formset = self.OutwardItemFormSet(post_data)
        
        if header_form.is_valid() and item_formset.is_valid():
            
            # --- NEGATIVE STOCK VALIDATION ---
            can_save = True
            for form in item_formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    item = form.cleaned_data['item']
                    warehouse = form.cleaned_data['warehouse']
                    quantity = form.cleaned_data['quantity']
                    
                    try:
                        stock = OpeningStock.objects.get(item=item, warehouse=warehouse)
                        if stock.quantity < quantity:
                            messages.error(request, f"Cannot save: Not enough stock for '{item.name}' in '{warehouse.name}'. Available: {stock.quantity}, Required: {quantity}.")
                            can_save = False
                    except OpeningStock.DoesNotExist:
                        messages.error(request, f"Cannot save: No stock record exists for '{item.name}' in '{warehouse.name}'. Available: 0, Required: {quantity}.")
                        can_save = False
            
            if not can_save:
                # If any stock check fails, re-render the page with the errors
                return render(request, 'inventory/outward.html', {'header_form': header_form, 'item_formset': item_formset})

            # --- Validation for empty transaction ---
            has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE') for form in item_formset)
            if not has_items:
                messages.error(request, "Cannot save a transaction with no items.")
            else:
                # If all checks pass, proceed with saving
                header = header_form.save(commit=False)
                header.created_by = request.user
                header.save()
                
                item_formset.instance = header
                item_formset.save()

                for form in item_formset.cleaned_data:
                    if form and not form.get('DELETE'):
                        stock = OpeningStock.objects.get(item=form['item'], warehouse=form['warehouse'])
                        stock.quantity -= form['quantity']
                        stock.save()
                
                messages.success(request, 'Outward transaction saved successfully!')
                return redirect('outward')

        context = { 'header_form': header_form, 'item_formset': item_formset }
        return render(request, 'inventory/outward.html', context)
        


class ProductionView(LoginRequiredMixin, View):
    ProducedItemFormSet = inlineformset_factory(
        ProductionHeader, 
        ProductionItem, 
        form=ProductionItemForm,
        extra=1, 
        can_delete=True, 
    )
    ConsumedItemFormSet = inlineformset_factory(
        ProductionHeader, 
        ProductionItem, 
        form=ProductionItemForm,
        extra=1, 
        can_delete=True, 
    )

    def get(self, request):
        header_form = ProductionHeaderForm()
        produced_formset = self.ProducedItemFormSet()
        consumed_formset = self.ConsumedItemFormSet()
        context = {
            'header_form': header_form,
            'produced_formset': produced_formset,
            'consumed_formset': consumed_formset,
        }
        return render(request, 'inventory/production.html', context)

    @transaction.atomic
    def post(self, request):
        header_form = ProductionHeaderForm(request.POST)
        produced_formset = self.ProducedItemFormSet(request.POST, prefix='produced')
        consumed_formset = self.ConsumedItemFormSet(request.POST, prefix='consumed')

        if header_form.is_valid() and produced_formset.is_valid() and consumed_formset.is_valid():
            
            # --- THIS IS THE NEW VALIDATION ---
            produced_items_exist = any(form.cleaned_data and not form.cleaned_data.get('DELETE') for form in produced_formset)
            consumed_items_exist = any(form.cleaned_data and not form.cleaned_data.get('DELETE') for form in consumed_formset)

            if not produced_items_exist and not consumed_items_exist:
                messages.error(request, "Cannot save a production entry with no items. Please add at least one produced or consumed item.")
            else:
                # If there are items, proceed with saving
                production_header = header_form.save(commit=False)
                production_header.created_by = request.user
                production_header.save()

                # Save produced items
                produced_formset.instance = production_header
                produced_formset.save()
                for form in produced_formset.cleaned_data:
                    if form and not form.get('DELETE'):
                        item_instance = form.instance
                        item_instance.type = 'Produced'
                        item_instance.save()
                        stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.warehouse)
                        stock.quantity += item_instance.quantity
                        stock.save()

                # Save consumed items
                consumed_formset.instance = production_header
                consumed_formset.save()
                for form in consumed_formset.cleaned_data:
                    if form and not form.get('DELETE'):
                        item_instance = form.instance
                        item_instance.type = 'Consumed'
                        item_instance.save()
                        stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.warehouse)
                        stock.quantity -= item_instance.quantity
                        stock.save()

                messages.success(request, 'Production entry successful!')
                return redirect('production')

        # If any form is invalid or the item check fails, re-render the page
        context = {
            'header_form': header_form,
            'produced_formset': produced_formset,
            'consumed_formset': consumed_formset,
            'groups': GroupMaster.objects.all(),
        }
        return render(request, 'inventory/production.html', context)
        
class WarehouseTransferView(LoginRequiredMixin, View):
    TransferItemFormSet = inlineformset_factory(
        WarehouseTransferHeader, 
        WarehouseTransferItem, 
        form=WarehouseTransferItemForm, 
        extra=1,
        can_delete=True,
    )

    def get(self, request):
        header_form = WarehouseTransferHeaderForm()
        item_formset = self.TransferItemFormSet()
        recent_transfers = WarehouseTransferHeader.objects.order_by('-date', '-created_at')[:10]
        context = {
            'header_form': header_form,
            'item_formset': item_formset,
            'recent_transfers': recent_transfers,
            'groups': GroupMaster.objects.all()
        }
        return render(request, 'inventory/warehouse_transfer.html', context)

    @transaction.atomic
    def post(self, request):
        header_form = WarehouseTransferHeaderForm(request.POST)
        item_formset = self.TransferItemFormSet(request.POST)

        if header_form.is_valid() and item_formset.is_valid():
            
            # --- NEGATIVE STOCK VALIDATION ---
            can_save = True
            for form in item_formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    item = form.cleaned_data['item']
                    from_warehouse = form.cleaned_data['from_warehouse']
                    quantity = form.cleaned_data['quantity']
                    
                    try:
                        stock = OpeningStock.objects.get(item=item, warehouse=from_warehouse)
                        if stock.quantity < quantity:
                            messages.error(request, f"Cannot transfer: Not enough stock for '{item.name}' in '{from_warehouse.name}'. Available: {stock.quantity}, Required: {quantity}.")
                            can_save = False
                    except OpeningStock.DoesNotExist:
                        messages.error(request, f"Cannot transfer: No stock record exists for '{item.name}' in '{from_warehouse.name}'. Available: 0, Required: {quantity}.")
                        can_save = False
            
            if not can_save:
                # If any stock check fails, re-render the page with the errors
                context = {
                    'header_form': header_form,
                    'item_formset': item_formset,
                    'groups': GroupMaster.objects.all(),
                }
                return render(request, 'inventory/warehouse_transfer.html', context)

            # --- Validation for empty transaction ---
            has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE') for form in item_formset)
            if not has_items:
                messages.error(request, "Cannot save a transfer with no items.")
            else:
                # If all checks pass, proceed with saving
                transfer_header = header_form.save(commit=False)
                transfer_header.created_by = request.user
                transfer_header.save()

                item_formset.instance = transfer_header
                item_formset.save()

                for form in item_formset.cleaned_data:
                    if form and not form.cleaned_data.get('DELETE'):
                        # Decrease stock from the 'from' warehouse
                        from_stock = OpeningStock.objects.get(item=form['item'], warehouse=form['from_warehouse'])
                        from_stock.quantity -= form['quantity']
                        from_stock.save()

                        # Increase stock in the 'to' warehouse
                        to_stock, _ = OpeningStock.objects.get_or_create(
                            item=form['item'], warehouse=form['to_warehouse'],
                            defaults={'quantity': 0}
                        )
                        to_stock.quantity += form['quantity']
                        to_stock.save()
                
                messages.success(request, 'Warehouse transfer successful!')
                return redirect('warehouse_transfer')

        # If any form is invalid, re-render the page
        context = {
            'header_form': header_form,
            'item_formset': item_formset,
            'groups': GroupMaster.objects.all(),
        }
        return render(request, 'inventory/warehouse_transfer.html', context)

class DeliveryOutView(LoginRequiredMixin, View):
    DeliveryOutItemFormSet = inlineformset_factory(
        DeliveryOutHeader, DeliveryOutItem, form=DeliveryOutItemForm, 
        extra=1, can_delete=True, 
    )

    def get(self, request):
        header_form = DeliveryOutHeaderForm()
        item_formset = self.DeliveryOutItemFormSet()
        context = {
            'header_form': header_form,
            'item_formset': item_formset,
        }
        return render(request, 'inventory/delivery_out.html', context)

    @transaction.atomic
    def post(self, request):
        post_data = request.POST.copy()
        to_person_id_or_name = post_data.get('to_person')

        if to_person_id_or_name and not to_person_id_or_name.isnumeric():
            contact, _ = Contact.objects.get_or_create(
                name=to_person_id_or_name.strip(), 
                defaults={'type': 'Customer'}
            )
            post_data['to_person'] = contact.id
        
        header_form = DeliveryOutHeaderForm(post_data)
        item_formset = self.DeliveryOutItemFormSet(post_data)

        if header_form.is_valid() and item_formset.is_valid():
            
            # --- NEGATIVE STOCK VALIDATION ---
            can_save = True
            for form in item_formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    item = form.cleaned_data['item']
                    from_warehouse = form.cleaned_data['from_warehouse']
                    quantity = form.cleaned_data['issued_quantity']
                    
                    try:
                        stock = OpeningStock.objects.get(item=item, warehouse=from_warehouse)
                        if stock.quantity < quantity:
                            messages.error(request, f"Cannot save: Not enough stock for '{item.name}' in '{from_warehouse.name}'. Available: {stock.quantity}, Required: {quantity}.")
                            can_save = False
                    except OpeningStock.DoesNotExist:
                        messages.error(request, f"Cannot save: No stock record exists for '{item.name}' in '{from_warehouse.name}'. Available: 0, Required: {quantity}.")
                        can_save = False
            
            if not can_save:
                return render(request, 'inventory/delivery_out.html', {'header_form': header_form, 'item_formset': item_formset})

            # --- Validation for empty transaction ---
            has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE') for form in item_formset)
            if not has_items:
                messages.error(request, "Cannot save a transaction with no items.")
            else:
                delivery_header = header_form.save(commit=False)
                delivery_header.created_by = request.user
                delivery_header.save()

                for form in item_formset:
                    if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                        item_instance = form.save(commit=False)
                        item_instance.header = delivery_header
                        item_instance.save()
                        stock = OpeningStock.objects.get(item=item_instance.item, warehouse=item_instance.from_warehouse)
                        stock.quantity -= item_instance.issued_quantity
                        stock.save()

                messages.success(request, 'Material Out entry successful!')
                return redirect('delivery_out')

        context = {
            'header_form': header_form, 
            'item_formset': item_formset
        }
        return render(request, 'inventory/delivery_out.html', context)

class DeliveryInView(LoginRequiredMixin, View):
    DeliveryInItemFormSet = inlineformset_factory(
        DeliveryInHeader, DeliveryInItem, form=DeliveryInItemForm,
        extra=1, can_delete=True,
    )

    def get(self, request):
        header_form = DeliveryInHeaderForm()
        item_formset = self.DeliveryInItemFormSet()
        # Get contacts who have pending items
        pending_contacts = Contact.objects.filter(
            deliveries_to__items__isnull=False,
            deliveries_to__items__issued_quantity__gt=models.F('deliveries_to__items__returned_quantity')
        ).distinct()
        
        context = {
            'header_form': header_form,
            'item_formset': item_formset,
            'pending_contacts': pending_contacts
        }
        return render(request, 'inventory/delivery_in.html', context)
    
    @transaction.atomic
    def post(self, request):
        header_form = DeliveryInHeaderForm(request.POST)
        item_formset = self.DeliveryInItemFormSet(request.POST)

        if header_form.is_valid() and item_formset.is_valid():
            
            # --- THIS IS THE NEW VALIDATION ---
            # Check if any forms in the formset have data and are not marked for deletion.
            has_items = False
            for form in item_formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    has_items = True
                    break # Exit the loop as soon as we find one valid item
            
            if not has_items:
                messages.error(request, "Cannot save a return with no items. Please add at least one item.")
            else:
                # If there are items, proceed with saving
                delivery_header = header_form.save(commit=False)
                delivery_header.created_by = request.user
                delivery_header.save()

                for form in item_formset:
                    if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                        item_instance = form.save(commit=False)
                        item_instance.header = delivery_header
                        
                        original_item = item_instance.original_delivery_item
                        if item_instance.returned_quantity > original_item.pending_quantity:
                            messages.error(request, f"Cannot return {item_instance.returned_quantity} of {original_item.item.name}, only {original_item.pending_quantity} is pending.")
                            # This will now correctly roll back the transaction
                            raise Exception("Return quantity exceeds pending quantity.")
                        
                        item_instance.save()
                        original_item.returned_quantity += item_instance.returned_quantity
                        original_item.save()
                        
                        stock, _ = OpeningStock.objects.get_or_create(item=original_item.item, warehouse=item_instance.to_warehouse)
                        stock.quantity += item_instance.returned_quantity
                        stock.save()

                messages.success(request, 'Material In entry successful!')
                return redirect('delivery_in')
        
        # If any form is invalid or the item check fails, re-render the page
        pending_contacts = Contact.objects.filter(
            deliveries_to__items__isnull=False,
            deliveries_to__items__issued_quantity__gt=models.F('deliveries_to__items__returned_quantity')
        ).distinct()
        context = {
            'header_form': header_form, 
            'item_formset': item_formset, 
            'pending_contacts': pending_contacts
        }
        return render(request, 'inventory/delivery_in.html', context)    

# inventory/views.py

class StockReportView(LoginRequiredMixin, View):
    def get(self, request):
        # --- Get ALL Filter & Pagination Parameters ---
        warehouse_filter = request.GET.get('warehouse_filter')
        group_filter = request.GET.get('group_filter')
        item_filter = request.GET.get('item_filter')
        sort_by = request.GET.get('sort_by', 'item_name')
        per_page = request.GET.get('per_page', 10)
        hide_zero = request.GET.get('hide_zero')

        # --- Base Querysets ---
        warehouses_query = WarehouseMaster.objects.order_by('name')
        items_query = ItemMaster.objects.select_related('group').all()

        # Apply filters to the item and warehouse lists
        if warehouse_filter:
            warehouses_query = warehouses_query.filter(pk=warehouse_filter)
        if group_filter:
            items_query = items_query.filter(group_id=group_filter)
        if item_filter:
            items_query = items_query.filter(pk=item_filter)

        # Apply Sorting
        if sort_by == 'item_group':
            items_query = items_query.order_by('group__name', 'name')
        else:
            items_query = items_query.order_by('name')
        
        # --- Perform Calculations on CURRENT stock ---
        stock_map = {(s.item_id, s.warehouse_id): s.quantity for s in OpeningStock.objects.all()}
        pending_map = {p['item_id']: p['total_pending'] for p in DeliveryOutItem.objects.filter(issued_quantity__gt=F('returned_quantity')).values('item_id').annotate(total_pending=Sum(F('issued_quantity') - F('returned_quantity')))}

        # --- THIS IS THE CORRECTED DATA STRUCTURE ---
        full_report_data = []
        for item in items_query:
            row = {
                'item_name': item.name, 
                'item_code': item.code, 
                'item_group': item.group.name, 
                'stock_by_warehouse': [], 
                'total_stock': 0, 
                'pending': pending_map.get(item.id, 0)
            }
            for wh in warehouses_query:
                quantity = stock_map.get((item.id, wh.id), 0)
                row['stock_by_warehouse'].append(quantity)
                row['total_stock'] += quantity
            full_report_data.append(row)

        display_data = full_report_data
        if hide_zero:
            display_data = [row for row in full_report_data if row['total_stock'] != 0 or row['pending'] != 0]

        column_totals = [sum(stock_map.get((item.id, wh.id), 0) for item in items_query) for wh in warehouses_query]
        grand_total_stock = sum(column_totals)
        grand_total_pending = sum(pending_map.get(item.id, 0) for item in items_query)
        
        paginator = Paginator(display_data, per_page)
        page_number = request.GET.get('page')
        report_page = paginator.get_page(page_number)

        context = {
            'report_page': report_page,
            'warehouses': warehouses_query,
            'all_warehouses': WarehouseMaster.objects.all(),
            'all_groups': GroupMaster.objects.all(),
            'all_items': ItemMaster.objects.all(),
            'sort_by': sort_by,
            'column_totals': column_totals,
            'grand_total_stock': grand_total_stock,
            'grand_total_pending': grand_total_pending,
            'per_page': str(per_page),
            'hide_zero': hide_zero,
            'warehouse_filter': int(warehouse_filter) if warehouse_filter else None,
            'group_filter': int(group_filter) if group_filter else None,
            'item_filter': int(item_filter) if item_filter else None,
        }
        return render(request, 'inventory/stock_report.html', context)
       
class StockReportDetailView(LoginRequiredMixin, View):
    def get(self, request):
        # Get the filter parameters from the URL
        group_by = request.GET.get('group_by')
        group_name = request.GET.get('group_name')
        category = request.GET.get('category')

        title = f"{category.replace('_', ' ').title()} Stock in {group_by.replace('_', ' ').title()}: {group_name}"
        
        items = []
        
        # Build the correct query based on the category
        filter_kwargs = {}
        if group_by == 'warehouse':
            filter_kwargs['warehouse__name'] = group_name
        else: # group_by == 'item_group'
            filter_kwargs['item__group__name'] = group_name

        if category == 'positive':
            items = OpeningStock.objects.filter(quantity__gt=0, **filter_kwargs)
        elif category == 'negative':
            items = OpeningStock.objects.filter(quantity__lt=0, **filter_kwargs)
        elif category == 'zero':
            items = OpeningStock.objects.filter(quantity=0, **filter_kwargs)
        
        # Handle pending deliveries
        if category == 'pending':
            if group_by == 'warehouse':
                filter_kwargs = {'from_warehouse__name': group_name}
            else:
                filter_kwargs = {'item__group__name': group_name}
            items = DeliveryOutItem.objects.filter(
                issued_quantity__gt=models.F('returned_quantity'), **filter_kwargs
            )

        context = {
            'title': title,
            'items': items,
            'category': category
        }
        return render(request, 'inventory/stock_report_detail.html', context)
        


class PendingDeliveryReportView(LoginRequiredMixin, View):
    def get(self, request):
        # Get pagination parameter
        per_page = request.GET.get('per_page', 10)

        # Get the full list of items
        pending_items_list = DeliveryOutItem.objects.select_related(
            'header', 'item', 'header__to_person' # Updated to include to_person
        ).filter(
            issued_quantity__gt=models.F('returned_quantity')
        ).order_by('-header__date')

        # Handle Export Request (uses the full, unpaginated list)
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="pending_delivery_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'To Person', 'Ref No.', 'Item', 'Issued', 'Returned', 'Pending'])
            for item in pending_items_list:
                writer.writerow([
                    item.header.date,
                    item.header.to_person.name,
                    item.header.reference_no,
                    item.item.name,
                    item.issued_quantity,
                    item.returned_quantity,
                    item.pending_quantity
                ])
            return response

        # Apply Pagination
        paginator = Paginator(pending_items_list, per_page)
        page_number = request.GET.get('page')
        pending_items_page = paginator.get_page(page_number)
        
        context = {
            'pending_items': pending_items_page,
            'per_page': per_page
        }
        return render(request, 'inventory/pending_delivery_report.html', context)
        
class InwardReportView(LoginRequiredMixin, View):
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        type_filter = request.GET.get('type_filter')
        per_page = request.GET.get('per_page', 10)

        # If no date is provided in the filter, use the active period dates as default
        if not start_date or not end_date:
            active_period = SystemSetting.objects.get(name="Active Period")
            start_date = active_period.start_date.strftime('%Y-%m-%d')
            end_date = active_period.end_date.strftime('%Y-%m-%d')

        # The main query is now on the transaction header
        inward_headers = InwardHeader.objects.select_related(
            'contact', 'created_by'
        ).prefetch_related(
            'items', 'items__item', 'items__warehouse' # Pre-fetches all related items for efficiency
        ).all().order_by('-date')
        
        if start_date:
            inward_headers = inward_headers.filter(date__gte=start_date)
        if end_date:
            inward_headers = inward_headers.filter(date__lte=end_date)
        if type_filter:
            inward_headers = inward_headers.filter(transaction_type=type_filter)
        
        # Handle Export Request
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="inward_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Invoice No.', 'Supplier', 'Item', 'Warehouse', 'Quantity'])
            for header in inward_headers:
                for item in header.items.all():
                    writer.writerow([header.date, header.invoice_no, header.supplier.name, item.item.name, item.warehouse.name, item.quantity])
            return response

        # Apply Pagination to the headers
        paginator = Paginator(inward_headers, per_page)
        page_number = request.GET.get('page')
        inward_page = paginator.get_page(page_number)
        
        context = {
            'transactions': inward_page,
            'per_page': per_page,
            'start_date': start_date,
            'end_date': end_date,
            'type_filter': type_filter,
        }
        return render(request, 'inventory/inward_report.html', context)
        

# inventory/views.py

class InwardUpdateView(LoginRequiredMixin, View):
    InwardItemFormSet = inlineformset_factory(
        InwardHeader, 
        InwardItem, 
        form=InwardItemForm, 
        extra=0,  # <-- THIS IS THE FIX: Don't show an extra blank row on edit
        can_delete=True,

    )

    def get(self, request, pk):
        inward_header = InwardHeader.objects.get(pk=pk)
        header_form = InwardHeaderForm(instance=inward_header)
        item_formset = self.InwardItemFormSet(instance=inward_header)
        
        for form in item_formset:
            if form.instance.pk and form.instance.item:
                form.fields['group'].initial = form.instance.item.group
        
        context = {
            'header_form': header_form, 
            'item_formset': item_formset, 
            'object': inward_header
        }
        return render(request, 'inventory/inward_edit.html', context)

    @transaction.atomic
    def post(self, request, pk):
        inward_header = InwardHeader.objects.get(pk=pk)
        
        header_form = InwardHeaderForm(request.POST, instance=inward_header)
        item_formset = self.InwardItemFormSet(request.POST, instance=inward_header)

        if header_form.is_valid() and item_formset.is_valid():
            
            # --- THIS IS THE FINAL, CORRECTED LOGIC ---
            # Manually check if any data has truly been modified.
            data_has_changed = False
            if header_form.has_changed():
                data_has_changed = True
            
            for form in item_formset:
                if form.has_changed():
                    data_has_changed = True
                    break

            if not data_has_changed:
                messages.info(request, 'No changes were detected.')
                return redirect('inward_report')

            # If changes were made, proceed with validation and saving.
            has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE', False) for form in item_formset)
            
            if not has_items:
                messages.error(request, "Cannot save a transaction with no items. Please add at least one item or delete the entire transaction.")
            else:
                # Store the state of items *before* any changes are made
                old_items = {item.id: {
                    'item_id': item.item_id, 'quantity': item.quantity, 'warehouse_id': item.warehouse_id
                } for item in inward_header.items.all()}
                
                # 1. Reverse original stock
                for item_id, old_data in old_items.items():
                    stock, _ = OpeningStock.objects.get_or_create(item_id=old_data['item_id'], warehouse_id=old_data['warehouse_id'])
                    stock.quantity -= old_data['quantity']
                    stock.save()

                # 2. Save form changes
                header_form.save()
                item_formset.save()

                # 3. Apply new stock for all current items
                for item_instance in inward_header.items.all():
                    stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.warehouse)
                    stock.quantity += item_instance.quantity
                    stock.save()
                
                messages.success(request, 'Inward transaction updated successfully!')
                return redirect('inward_report')
        
        # If any form is invalid, re-render the page
        context = {'header_form': header_form, 'item_formset': item_formset, 'object': inward_header}
        return render(request, 'inventory/inward_edit.html', context)

        
class InwardDeleteView(LoginRequiredMixin, DeleteView):
    model = InwardHeader
    template_name = 'inventory/inward_confirm_delete.html' # Create this template for confirmation
    success_url = reverse_lazy('inward_report') # Redirect to the inward report after deletion
    

    

class OutwardReportView(LoginRequiredMixin, View):
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        type_filter = request.GET.get('type_filter')
        per_page = request.GET.get('per_page', 10)
       
       # If no date is provided in the filter, use the active period dates as default
        if not start_date or not end_date:
            active_period = SystemSetting.objects.get(name="Active Period")
            start_date = active_period.start_date.strftime('%Y-%m-%d')
            end_date = active_period.end_date.strftime('%Y-%m-%d')

        # The main query is now on the transaction header
        outward_headers = OutwardHeader.objects.select_related(
            'contact', 'created_by'
        ).prefetch_related(
            'items', 'items__item', 'items__warehouse'
        ).all().order_by('-date')
        
        if start_date:
            outward_headers = outward_headers.filter(date__gte=start_date)
        if end_date:
            outward_headers = outward_headers.filter(date__lte=end_date)
        if type_filter: #<-- Add this block
            outward_headers = outward_headers.filter(transaction_type=type_filter)
        
        # Handle Export Request
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="outward_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Invoice No.', 'Customer', 'Item', 'Warehouse', 'Quantity'])
            for header in outward_headers:
                for item in header.items.all():
                    writer.writerow([header.date, header.invoice_no, header.customer.name, item.item.name, item.warehouse.name, item.quantity])
            return response

        # Apply Pagination to the headers
        paginator = Paginator(outward_headers, per_page)
        page_number = request.GET.get('page')
        outward_page = paginator.get_page(page_number)
        
        context = {
            'transactions': outward_page,
            'per_page': per_page,
            'start_date': start_date,
            'end_date': end_date,
            'type_filter': type_filter,
        }
        return render(request, 'inventory/outward_report.html', context)

class ProductionReportView(LoginRequiredMixin, View):
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        per_page = request.GET.get('per_page', 10)

        # If no date is provided in the filter, use the active period dates as default
        if not start_date or not end_date:
            active_period = SystemSetting.objects.get(name="Active Period")
            start_date = active_period.start_date.strftime('%Y-%m-%d')
            end_date = active_period.end_date.strftime('%Y-%m-%d')

        # Query and paginate the main ProductionHeader
        production_headers = ProductionHeader.objects.select_related(
            'created_by'
        ).prefetch_related(
            'items', 'items__item', 'items__warehouse'
        ).all().order_by('-date')
        
        if start_date:
            production_headers = production_headers.filter(date__gte=start_date)
        if end_date:
            production_headers = production_headers.filter(date__lte=end_date)
        
        # Handle Export Request
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="production_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Ref No.', 'Type', 'Item', 'Warehouse', 'Quantity'])
            for header in production_headers:
                for item in header.items.all():
                    writer.writerow([header.date, header.reference_no, item.type, item.item.name, item.warehouse.name, item.quantity])
            return response

        paginator = Paginator(production_headers, per_page)
        page_number = request.GET.get('page')
        production_page = paginator.get_page(page_number)
        
        context = {
            'transactions': production_page,
            'per_page': per_page,
            'start_date': start_date,
            'end_date': end_date
        }
        return render(request, 'inventory/production_report.html', context)

class StockAdjustmentView(LoginRequiredMixin, View):
    AdjustmentItemFormSet = inlineformset_factory(
        StockAdjustmentHeader, StockAdjustmentItem, form=StockAdjustmentItemForm,
        extra=1, can_delete=True,
    )

    def get(self, request):
        header_form = StockAdjustmentHeaderForm()
        item_formset = self.AdjustmentItemFormSet()
        recent_adjustments = StockAdjustmentHeader.objects.order_by('-date', '-created_at')[:5]
        context = {
            'header_form': header_form,
            'item_formset': item_formset,
            'recent_adjustments': recent_adjustments,
            'groups': GroupMaster.objects.all(), # <-- Add groups to context
        }
        return render(request, 'inventory/stock_adjustment.html', context)

    @transaction.atomic
    def post(self, request):
        header_form = StockAdjustmentHeaderForm(request.POST)
        item_formset = self.AdjustmentItemFormSet(request.POST)

        if header_form.is_valid() and item_formset.is_valid():
            
            # --- NEGATIVE STOCK VALIDATION ---
            can_save = True
            for form in item_formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    # We only need to check stock for 'Decrease' adjustments
                    if form.cleaned_data['adjustment_type'] == 'SUB':
                        item = form.cleaned_data['item']
                        warehouse = form.cleaned_data['warehouse']
                        quantity = form.cleaned_data['quantity']
                        
                        try:
                            stock = OpeningStock.objects.get(item=item, warehouse=warehouse)
                            if stock.quantity < quantity:
                                messages.error(request, f"Cannot adjust: Not enough stock for '{item.name}' in '{warehouse.name}'. Available: {stock.quantity}, Required: {quantity}.")
                                can_save = False
                        except OpeningStock.DoesNotExist:
                            messages.error(request, f"Cannot adjust: No stock record exists for '{item.name}' in '{warehouse.name}'. Available: 0, Required: {quantity}.")
                            can_save = False
            
            if not can_save:
                # If any stock check fails, re-render the page with the errors
                context = {
                    'header_form': header_form,
                    'item_formset': item_formset,
                    'groups': GroupMaster.objects.all(),
                }
                return render(request, 'inventory/stock_adjustment.html', context)

            # --- Validation for empty transaction ---
            has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE') for form in item_formset)
            if not has_items:
                messages.error(request, "Cannot save an adjustment with no items.")
            else:
                # If all checks pass, proceed with saving
                adj_header = header_form.save(commit=False)
                adj_header.created_by = request.user
                adj_header.save()

                item_formset.instance = adj_header
                item_formset.save()

                for form in item_formset.cleaned_data:
                    if form and not form.get('DELETE'):
                        item_instance = form.instance
                        stock, _ = OpeningStock.objects.get_or_create(
                            item=item_instance.item, warehouse=item_instance.warehouse
                        )
                        if item_instance.adjustment_type == 'ADD':
                            stock.quantity += item_instance.quantity
                        elif item_instance.adjustment_type == 'SUB':
                            stock.quantity -= item_instance.quantity
                        stock.save()
                
                messages.success(request, 'Stock adjustment successful!')
                return redirect('stock_adjustment')

        # If any form is invalid, re-render the page
        context = {
            'header_form': header_form,
            'item_formset': item_formset,
            'groups': GroupMaster.objects.all(),
        }
        return render(request, 'inventory/stock_adjustment.html', context)
        
class WarehouseTransferReportView(LoginRequiredMixin, View):
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        per_page = request.GET.get('per_page', 10)

        # If no date is provided in the filter, use the active period dates as default
        if not start_date or not end_date:
            active_period = SystemSetting.objects.get(name="Active Period")
            start_date = active_period.start_date.strftime('%Y-%m-%d')
            end_date = active_period.end_date.strftime('%Y-%m-%d')

        # The main query is now on the transaction header
        transfer_headers = WarehouseTransferHeader.objects.select_related(
            'created_by'
        ).prefetch_related(
            'items', 'items__item', 'items__from_warehouse', 'items__to_warehouse'
        ).all().order_by('-date')
        
        if start_date:
            transfer_headers = transfer_headers.filter(date__gte=start_date)
        if end_date:
            transfer_headers = transfer_headers.filter(date__lte=end_date)
        
        # Handle Export Request
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="warehouse_transfer_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Ref No.', 'Item', 'From Warehouse', 'To Warehouse', 'Quantity'])
            for header in transfer_headers:
                for item in header.items.all():
                    writer.writerow([
                        header.date, header.reference_no, item.item.name,
                        item.from_warehouse.name, item.to_warehouse.name, item.quantity
                    ])
            return response

        # Apply Pagination to the headers
        paginator = Paginator(transfer_headers, per_page)
        page_number = request.GET.get('page')
        transfer_page = paginator.get_page(page_number)
        
        context = {
            'transactions': transfer_page,
            'per_page': per_page,
            'start_date': start_date,
            'end_date': end_date
        }
        return render(request, 'inventory/warehouse_transfer_report.html', context)


# inventory/views.py

class WarehouseTransferUpdateView(LoginRequiredMixin, View):
    TransferItemFormSet = inlineformset_factory(
        WarehouseTransferHeader, 
        WarehouseTransferItem, 
        form=WarehouseTransferItemForm,
        extra=0, 
        can_delete=True, 
    )

    def get(self, request, pk):
        transfer_header = WarehouseTransferHeader.objects.get(pk=pk)
        header_form = WarehouseTransferHeaderForm(instance=transfer_header)
        item_formset = self.TransferItemFormSet(instance=transfer_header)
        
        for form in item_formset:
            if form.instance.pk and form.instance.item:
                form.fields['group'].initial = form.instance.item.group
        
        context = {
            'header_form': header_form, 
            'item_formset': item_formset, 
            'object': transfer_header
        }
        return render(request, 'inventory/warehouse_transfer_edit.html', context)

    @transaction.atomic
    def post(self, request, pk):
        transfer_header = WarehouseTransferHeader.objects.get(pk=pk)
        old_items = {item.id: {
            'item_id': item.item_id, 
            'quantity': item.quantity, 
            'from_warehouse_id': item.from_warehouse_id, 
            'to_warehouse_id': item.to_warehouse_id
        } for item in transfer_header.items.all()}

        header_form = WarehouseTransferHeaderForm(request.POST, instance=transfer_header)
        item_formset = self.TransferItemFormSet(request.POST, instance=transfer_header)

        if header_form.is_valid() and item_formset.is_valid():
            
            if header_form.has_changed() or item_formset.has_changed():
                
                has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE', False) for form in item_formset)
                
                if not has_items:
                    messages.error(request, "Cannot save a transfer with no items.")
                else:
                    # 1. Reverse original stock movements
                    for item_id, old_data in old_items.items():
                        from_stock, _ = OpeningStock.objects.get_or_create(item_id=old_data['item_id'], warehouse_id=old_data['from_warehouse_id'])
                        from_stock.quantity += old_data['quantity']
                        from_stock.save()
                        to_stock, _ = OpeningStock.objects.get_or_create(item_id=old_data['item_id'], warehouse_id=old_data['to_warehouse_id'])
                        to_stock.quantity -= old_data['quantity']
                        to_stock.save()

                    # 2. Save form changes
                    header_form.save()
                    item_formset.save()

                    # 3. Apply new stock for all current items
                    for item_instance in transfer_header.items.all():
                        from_stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.from_warehouse)
                        from_stock.quantity -= item_instance.quantity
                        from_stock.save()
                        to_stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.to_warehouse)
                        to_stock.quantity += item_instance.quantity
                        to_stock.save()
                    
                    messages.success(request, 'Warehouse transfer updated successfully!')
            else:
                messages.info(request, 'No changes were detected.')

            return redirect('warehouse_transfer_report')
        
        context = {'header_form': header_form, 'item_formset': item_formset, 'object': transfer_header}
        return render(request, 'inventory/warehouse_transfer_edit.html', context)

class WarehouseTransferDeleteView(LoginRequiredMixin, DeleteView):
    model = WarehouseTransferHeader
    template_name = 'inventory/transfer_confirm_delete.html'
    success_url = reverse_lazy('warehouse_transfer_report')

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        for item in self.object.items.all():
            # Add stock back to the 'from' warehouse
            from_stock, _ = OpeningStock.objects.get_or_create(item=item.item, warehouse=item.from_warehouse)
            from_stock.quantity += item.quantity
            from_stock.save()
            # Remove stock from the 'to' warehouse
            to_stock, _ = OpeningStock.objects.get_or_create(item=item.item, warehouse=item.to_warehouse)
            to_stock.quantity -= item.quantity
            to_stock.save()
        messages.success(request, f"Transfer {self.object.reference_no} has been deleted and stock updated.")
        # super().post() will delete the header and all its items
        return super().post(request, *args, **kwargs)

class StockAdjustmentReportView(LoginRequiredMixin, View):
    def get(self, request):
        # Get filter and pagination parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        per_page = request.GET.get('per_page', 10)
        type_filter = request.GET.get('type_filter')
        
        # If no date is provided in the filter, use the active period dates as default
        if not start_date or not end_date:
            active_period = SystemSetting.objects.get(name="Active Period")
            start_date = active_period.start_date.strftime('%Y-%m-%d')
            end_date = active_period.end_date.strftime('%Y-%m-%d')        

        # Start with the base query
        adjustment_items_list = StockAdjustmentItem.objects.select_related(
            'header', 'item', 'warehouse'
        ).all().order_by('-header__date')
        
        # Apply filters
        if start_date:
            adjustment_items_list = adjustment_items_list.filter(header__date__gte=start_date)
        if end_date:
            adjustment_items_list = adjustment_items_list.filter(header__date__lte=end_date)
        if type_filter:
            adjustment_items_list = adjustment_items_list.filter(adjustment_type=type_filter)
        
        # Handle Export Request
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="stock_adjustment_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Item', 'Warehouse', 'Type', 'Quantity', 'Reason'])
            for item in adjustment_items_list:
                writer.writerow([
                    item.header.date, item.item.name, item.warehouse.name,
                    item.get_adjustment_type_display(), item.quantity, item.header.reason
                ])
            return response

        # Apply Pagination
        paginator = Paginator(adjustment_items_list, per_page)
        page_number = request.GET.get('page')
        adjustment_items_page = paginator.get_page(page_number)
        
        context = {
            'adjustment_items': adjustment_items_page,
            'per_page': per_page,
            'start_date': start_date,
            'end_date': end_date,
            'type_filter': type_filter,
        }
        return render(request, 'inventory/stock_adjustment_report.html', context)

# inventory/views.py

class StockAdjustmentUpdateView(LoginRequiredMixin, View):
    AdjustmentItemFormSet = inlineformset_factory(
        StockAdjustmentHeader, 
        StockAdjustmentItem, 
        form=StockAdjustmentItemForm,
        extra=0, 
        can_delete=True, 
    )

    def get(self, request, pk):
        adj_header = StockAdjustmentHeader.objects.get(pk=pk)
        header_form = StockAdjustmentHeaderForm(instance=adj_header)
        item_formset = self.AdjustmentItemFormSet(instance=adj_header)
        
        for form in item_formset:
            if form.instance.pk and form.instance.item:
                form.fields['group'].initial = form.instance.item.group
        
        context = {
            'header_form': header_form, 
            'item_formset': item_formset, 
            'object': adj_header,
        }
        return render(request, 'inventory/stock_adjustment_edit.html', context)

    @transaction.atomic
    def post(self, request, pk):
        adj_header = StockAdjustmentHeader.objects.get(pk=pk)
        old_items = {item.id: {
            'item_id': item.item_id, 
            'quantity': item.quantity, 
            'warehouse_id': item.warehouse_id,
            'adjustment_type': item.adjustment_type
        } for item in adj_header.items.all()}

        header_form = StockAdjustmentHeaderForm(request.POST, instance=adj_header)
        item_formset = self.AdjustmentItemFormSet(request.POST, instance=adj_header)

        if header_form.is_valid() and item_formset.is_valid():
            
            if header_form.has_changed() or item_formset.has_changed():
                
                has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE', False) for form in item_formset)
                
                if not has_items:
                    messages.error(request, "Cannot save an adjustment with no items. Please add at least one item or delete the entire transaction.")
                else:
                    # 1. Reverse all original stock movements
                    for item_id, old_data in old_items.items():
                        stock, _ = OpeningStock.objects.get_or_create(item_id=old_data['item_id'], warehouse_id=old_data['warehouse_id'])
                        if old_data['adjustment_type'] == 'ADD':
                            stock.quantity -= old_data['quantity']
                        elif old_data['adjustment_type'] == 'SUB':
                            stock.quantity += old_data['quantity']
                        stock.save()

                    # 2. Save form changes
                    header_form.save()
                    item_formset.save()

                    # 3. Apply new stock for all current items
                    for item_instance in adj_header.items.all():
                        stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.warehouse)
                        if item_instance.adjustment_type == 'ADD':
                            stock.quantity += item_instance.quantity
                        elif item_instance.adjustment_type == 'SUB':
                            stock.quantity -= item_instance.quantity
                        stock.save()
                    
                    messages.success(request, 'Stock adjustment updated successfully!')
            else:
                messages.info(request, 'No changes were detected.')

            return redirect('stock_adjustment_report')
        
        # If form is invalid, re-render the page with errors
        context = {
            'header_form': header_form, 
            'item_formset': item_formset, 
            'object': adj_header
        }
        return render(request, 'inventory/stock_adjustment_edit.html', context)
        
        
class StockAdjustmentDeleteView(LoginRequiredMixin, DeleteView):
    model = StockAdjustmentHeader
    template_name = 'inventory/adjustment_confirm_delete.html'
    success_url = reverse_lazy('stock_adjustment_report')

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        for item in self.object.items.all():
            stock, _ = OpeningStock.objects.get_or_create(item=item.item, warehouse=item.warehouse)
            if item.adjustment_type == 'ADD':
                stock.quantity -= item.quantity # Reverse the addition
            elif item.adjustment_type == 'SUB':
                stock.quantity += item.quantity # Reverse the subtraction
            stock.save()
        messages.success(request, f"Adjustment has been deleted and stock updated.")
        return super().post(request, *args, **kwargs)
        

class ImportView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'inventory/import.html')

    def _decode_csv_file(self, csv_file):
        """Helper method to decode the uploaded CSV file."""
        file_data = csv_file.read()
        for encoding in ['utf-8', 'latin-1', 'windows-1252']:
            try:
                decoded_file = file_data.decode(encoding)
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string)
                header = next(reader)
                original_rows = list(reader)
                return header, original_rows
            except UnicodeDecodeError:
                continue
        raise ValueError("File encoding not supported. Please save as UTF-8.")

    def _handle_inward_import(self, csv_header, original_rows, request):
        """Processes the logic for importing Inward transactions."""
        report_rows, groups_to_process, successful_imports = [], {}, 0
        for i, row in enumerate(original_rows, start=2):
            try:
                if len(row) != 7: raise ValueError("Incorrect number of columns.")
                date_str, inv_no, s_name, i_name, w_name, qty, remarks = row
                valid_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
                item = ItemMaster.objects.get(name=i_name.strip())
                warehouse = WarehouseMaster.objects.get(name=w_name.strip())
                if inv_no not in groups_to_process:
                    groups_to_process[inv_no] = {'header_info': {'date':valid_date, 's_name':s_name, 'remarks':remarks}, 'items': []}
                groups_to_process[inv_no]['items'].append({'item': item, 'warehouse': warehouse, 'quantity': int(qty), 'original_row': row})
            except Exception as e:
                report_rows.append(row + [f'Skipped - Error on line {i}: {e}'])
        
        for inv_no, data in groups_to_process.items():
            h_info = data['header_info']
            supplier, _ = Contact.objects.get_or_create(name=h_info['s_name'].strip(), defaults={'type': 'Supplier'})
            header_obj, created = InwardHeader.objects.get_or_create(invoice_no=inv_no.strip(), defaults={'date': h_info['date'], 'supplier': supplier, 'remarks': h_info['remarks'], 'created_by': request.user})
            if created:
                for item_data in data['items']:
                    InwardItem.objects.create(header=header_obj, item=item_data['item'], warehouse=item_data['warehouse'], quantity=item_data['quantity'])
                    stock, _ = OpeningStock.objects.get_or_create(item=item_data['item'], warehouse=item_data['warehouse'])
                    stock.quantity += item_data['quantity']
                    stock.save()
                    report_rows.append(item_data['original_row'] + ['Imported Successfully'])
                    successful_imports += 1
            else:
                for item_data in data['items']: report_rows.append(item_data['original_row'] + [f'Skipped - Invoice No. {inv_no} already exists.'])
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(csv_header + ['Status'])
        writer.writerows(sorted(report_rows, key=lambda x: x[1]))
        message = f"Inward import complete. {successful_imports} records imported. {len(original_rows) - successful_imports} records failed."
        return {'status': 'complete', 'message': message, 'report_data': output.getvalue(), 'filename': 'inward_import_summary.csv'}

    def _handle_outward_import(self, csv_header, original_rows, request):
        """Processes the logic for importing Outward transactions."""
        report_rows, groups_to_process, successful_imports = [], {}, 0
        for i, row in enumerate(original_rows, start=2):
            try:
                date_str, inv_no, c_name, i_name, w_name, qty, remarks = row
                valid_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
                item = ItemMaster.objects.get(name=i_name.strip())
                warehouse = WarehouseMaster.objects.get(name=w_name.strip())
                if inv_no not in groups_to_process:
                    groups_to_process[inv_no] = {'header_info': {'date':valid_date, 'c_name':c_name, 'remarks':remarks}, 'items': []}
                groups_to_process[inv_no]['items'].append({'item': item, 'warehouse': warehouse, 'quantity': int(qty), 'original_row': row})
            except Exception as e:
                report_rows.append(row + [f'Skipped - Error on line {i}: {e}'])

        for inv_no, data in groups_to_process.items():
            h_info = data['header_info']
            customer, _ = Contact.objects.get_or_create(name=h_info['c_name'].strip(), defaults={'type': 'Customer'})
            header_obj, created = OutwardHeader.objects.get_or_create(invoice_no=inv_no.strip(), defaults={'date': h_info['date'], 'customer': customer, 'remarks': h_info['remarks'], 'created_by': request.user})
            if created:
                for item_data in data['items']:
                    OutwardItem.objects.create(header=header_obj, item=item_data['item'], warehouse=item_data['warehouse'], quantity=item_data['quantity'])
                    stock, _ = OpeningStock.objects.get_or_create(item=item_data['item'], warehouse=item_data['warehouse'])
                    stock.quantity -= item_data['quantity']
                    stock.save()
                    report_rows.append(item_data['original_row'] + ['Imported Successfully'])
                    successful_imports += 1
            else:
                for item_data in data['items']: report_rows.append(item_data['original_row'] + [f'Skipped - Invoice No. {inv_no} already exists.'])
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(csv_header + ['Status'])
        writer.writerows(sorted(report_rows, key=lambda x: x[1]))
        message = f"Outward import complete. {successful_imports} records imported. {len(original_rows) - successful_imports} records failed."
        return {'status': 'complete', 'message': message, 'report_data': output.getvalue(), 'filename': 'outward_import_summary.csv'}

    def _handle_adjustment_import(self, csv_header, original_rows, request):
        """Processes the logic for importing Stock Adjustments."""
        report_rows, groups_to_process, successful_imports = [], {}, 0
        
        for i, row in enumerate(original_rows, start=2):
            try:
                if len(row) != 6: raise ValueError("Incorrect number of columns.")
                date_str, reason, item_name, wh_name, adj_type, qty = row
                
                valid_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
                item = ItemMaster.objects.get(name=item_name.strip())
                warehouse = WarehouseMaster.objects.get(name=wh_name.strip())
                qty_dec = float(qty.strip())
                adj_type_clean = adj_type.strip().upper()
                if adj_type_clean not in ['ADD', 'SUB']:
                    raise ValueError("Type must be 'ADD' or 'SUB'.")

                # Group by date and reason
                group_key = (valid_date, reason.strip())
                if group_key not in groups_to_process:
                    groups_to_process[group_key] = {'header_info': {'date': valid_date, 'reason': reason}, 'items': []}
                groups_to_process[group_key]['items'].append({'item': item, 'warehouse': warehouse, 'quantity': qty_dec, 'adjustment_type': adj_type_clean, 'original_row': row})
            
            except Exception as e:
                report_rows.append(row + [f'Skipped - Error on line {i}: {e}'])
        
        for key, data in groups_to_process.items():
            h_info = data['header_info']
            header, created = StockAdjustmentHeader.objects.get_or_create(
                date=h_info['date'], reason=h_info['reason'], created_by=request.user
            )
            
            for item_data in data['items']:
                StockAdjustmentItem.objects.create(
                    header=header, item=item_data['item'], warehouse=item_data['warehouse'],
                    adjustment_type=item_data['adjustment_type'], quantity=item_data['quantity']
                )
                stock, _ = OpeningStock.objects.get_or_create(item=item_data['item'], warehouse=item_data['warehouse'])
                if item_data['adjustment_type'] == 'ADD':
                    stock.quantity += item_data['quantity']
                else: # SUB
                    stock.quantity -= item_data['quantity']
                stock.save()
                report_rows.append(item_data['original_row'] + ['Imported Successfully'])
                successful_imports += 1
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(csv_header + ['Status'])
        writer.writerows(sorted(report_rows, key=lambda x: x[1]))
        message = f"Adjustment import complete. {successful_imports} records imported. {len(original_rows) - successful_imports} records failed."
        return {'status': 'complete', 'message': message, 'report_data': output.getvalue(), 'filename': 'adjustment_import_summary.csv'}  
        
    def _handle_opening_stock_import(self, csv_header, original_rows, request):
        """Processes the logic for importing HISTORICAL Opening Stock."""
        report_rows = []
        successful_imports = 0

        for i, row in enumerate(original_rows, start=2):
            try:
                # Expecting 4 columns now, including the date
                if len(row) != 4: raise ValueError("Incorrect number of columns. Expected: Date, Item Name, Warehouse Name, Quantity.")
                date_str, item_name, warehouse_name, quantity_str = row
                
                valid_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
                item = ItemMaster.objects.get(name=item_name.strip())
                warehouse = WarehouseMaster.objects.get(name=warehouse_name.strip())
                quantity = float(quantity_str.strip())
                
                OpeningStock.objects.update_or_create(
                    date=valid_date,
                    item=item, 
                    warehouse=warehouse,
                    defaults={'quantity': quantity}
                )
                report_rows.append(row + ['Imported Successfully'])
                successful_imports += 1

            except Exception as e:
                report_rows.append(row + [f'Skipped - Error on line {i}: {e}'])
        
        # (The rest of the reporting logic is correct)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(csv_header + ['Status'])
        writer.writerows(report_rows)
        message = f"Opening Stock import complete. {successful_imports} records processed. {len(original_rows) - successful_imports} records failed."
        return {'status': 'complete', 'message': message, 'report_data': output.getvalue(), 'filename': 'opening_stock_import_summary.csv'}

    def _handle_delivery_out_import(self, csv_header, original_rows, request):
        """Processes the logic for importing Delivery Out notes."""
        report_rows, groups_to_process, successful_imports = [], {}, 0
        
        for i, row in enumerate(original_rows, start=2):
            try:
                # Expecting: Date, Ref No, To Person, Vehicle No, Item Name, From Warehouse, Qty, Remarks
                if len(row) != 8: raise ValueError("Incorrect number of columns.")
                date_str, ref_no, person_name, vehicle_no, item_name, wh_name, qty, remarks = row
                
                valid_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
                item = ItemMaster.objects.get(name=item_name.strip())
                warehouse = WarehouseMaster.objects.get(name=wh_name.strip())
                
                if ref_no not in groups_to_process:
                    groups_to_process[ref_no] = {'header_info': {'date':valid_date, 'person_name':person_name, 'vehicle_no':vehicle_no, 'remarks':remarks}, 'items': []}
                groups_to_process[ref_no]['items'].append({'item': item, 'warehouse': warehouse, 'quantity': int(qty), 'original_row': row})
            except Exception as e:
                report_rows.append(row + [f'Skipped - Error on line {i}: {e}'])

        for ref_no, data in groups_to_process.items():
            h_info = data['header_info']
            # Assumes new contacts are Customers
            contact, _ = Contact.objects.get_or_create(name=h_info['person_name'].strip(), defaults={'type': 'Customer'})
            header_obj, created = DeliveryOutHeader.objects.get_or_create(
                reference_no=ref_no.strip(),
                defaults={'date': h_info['date'], 'to_person': contact, 'vehicle_number': h_info['vehicle_no'], 'remarks': h_info['remarks'], 'created_by': request.user}
            )
            if created:
                for item_data in data['items']:
                    DeliveryOutItem.objects.create(header=header_obj, item=item_data['item'], from_warehouse=item_data['warehouse'], issued_quantity=item_data['quantity'])
                    stock, _ = OpeningStock.objects.get_or_create(item=item_data['item'], warehouse=item_data['warehouse'])
                    stock.quantity -= item_data['quantity'] # DECREASE STOCK
                    stock.save()
                    report_rows.append(item_data['original_row'] + ['Imported Successfully'])
                    successful_imports += 1
            else:
                for item_data in data['items']: report_rows.append(item_data['original_row'] + [f'Skipped - Ref No. {ref_no} already exists.'])
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(csv_header + ['Status'])
        writer.writerows(sorted(report_rows, key=lambda x: x[1]))
        message = f"Delivery Out import complete. {successful_imports} records imported. {len(original_rows) - successful_imports} records failed."
        return {'status': 'complete', 'message': message, 'report_data': output.getvalue(), 'filename': 'delivery_out_import_summary.csv'}

    @transaction.atomic
    def post(self, request):
        action = request.POST.get('action')

        if 'download' in action:
            if action == 'download_inward_template':
                response = HttpResponse(content_type='text/csv'); response['Content-Disposition'] = 'attachment; filename="inward_template.csv"'
                writer = csv.writer(response); writer.writerow(['Date (YYYY-MM-DD)', 'Invoice No.', 'Supplier Name', 'Item Name', 'Warehouse Name', 'Quantity', 'Remarks']); return response
            elif action == 'download_outward_template':
                response = HttpResponse(content_type='text/csv'); response['Content-Disposition'] = 'attachment; filename="outward_template.csv"'
                writer = csv.writer(response); writer.writerow(['Date (YYYY-MM-DD)', 'Invoice No.', 'Customer Name', 'Item Name', 'Warehouse Name', 'Quantity', 'Remarks']); return response
            elif action == 'download_delivery_out_template':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="delivery_out_template.csv"'
                writer = csv.writer(response)
                writer.writerow(['Date (YYYY-MM-DD)', 'Ref No.', 'To Person', 'Vehicle Number', 'Item Name', 'From Warehouse', 'Quantity', 'Remarks'])
                return response
            elif action == 'download_opening_stock_template':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="opening_stock_template.csv"'
                writer = csv.writer(response)
                writer.writerow(['Date (YYYY-MM-DD)', 'Item Name', 'Warehouse Name', 'Quantity'])
                return response
                return response                
            elif action == 'download_adjustment_template':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="stock_adjustment_template.csv"'
                writer = csv.writer(response)
                writer.writerow(['Date (YYYY-MM-DD)', 'Reason', 'Item Name', 'Warehouse Name', 'Type (ADD/SUB)', 'Quantity'])
                writer.writerow(['2025-08-05', 'Annual stock count', 'Item A', 'Main Warehouse', 'ADD', '5'])
                writer.writerow(['2025-08-05', 'Annual stock count', 'Item B', 'Main Warehouse', 'SUB', '2'])
                return response                

        elif 'import' in action:
            csv_file = request.FILES.get('csv_file')
            if not csv_file: return JsonResponse({'status': 'error', 'message': 'No file uploaded.'})
            
            try:
                csv_header, original_rows = self._decode_csv_file(csv_file)
                if action == 'import_inward':
                    response_data = self._handle_inward_import(csv_header, original_rows, request)
                elif action == 'import_outward':
                    response_data = self._handle_outward_import(csv_header, original_rows, request)
                elif action == 'import_delivery_out':
                    response_data = self._handle_delivery_out_import(csv_header, original_rows, request)
                elif action == 'import_adjustment':
                    response_data = self._handle_adjustment_import(csv_header, original_rows, request)
                elif action == 'import_opening_stock':
                        response_data = self._handle_opening_stock_import(csv_header, original_rows, request)                 
                else:
                    response_data = {'status': 'error', 'message': 'Unknown import action.'}
                return JsonResponse(response_data)
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f'A critical error occurred: {e}'})
            
        return redirect('import_page')
# inventory/views.py

class OutwardUpdateView(LoginRequiredMixin, View):
    OutwardItemFormSet = inlineformset_factory(
        OutwardHeader, 
        OutwardItem, 
        form=OutwardItemForm,
        extra=0, 
        can_delete=True, 
    )

    def get(self, request, pk):
        outward_header = OutwardHeader.objects.get(pk=pk)
        header_form = OutwardHeaderForm(instance=outward_header)
        item_formset = self.OutwardItemFormSet(instance=outward_header)
        
        for form in item_formset:
            if form.instance.pk and form.instance.item:
                form.fields['group'].initial = form.instance.item.group
        
        context = {
            'header_form': header_form, 
            'item_formset': item_formset, 
            'object': outward_header
        }
        return render(request, 'inventory/outward_edit.html', context)

    @transaction.atomic
    def post(self, request, pk):
        outward_header = OutwardHeader.objects.get(pk=pk)
        old_items = {item.id: {
            'item_id': item.item_id, 'quantity': item.quantity, 'warehouse_id': item.warehouse_id
        } for item in outward_header.items.all()}

        header_form = OutwardHeaderForm(request.POST, instance=outward_header)
        item_formset = self.OutwardItemFormSet(request.POST, instance=outward_header)

        if header_form.is_valid() and item_formset.is_valid():
            
            # --- THIS IS THE NEW LOGIC ---
            # Check if any data has actually changed before processing.
            if header_form.has_changed() or item_formset.has_changed():
                
                has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE', False) for form in item_formset)
                
                if not has_items:
                    messages.error(request, "Cannot save a transaction with no items.")
                else:
                    # 1. Reverse original stock movements (add stock back)
                    for item_id, old_data in old_items.items():
                        stock, _ = OpeningStock.objects.get_or_create(item_id=old_data['item_id'], warehouse_id=old_data['warehouse_id'])
                        stock.quantity += old_data['quantity']
                        stock.save()

                    # 2. Save form changes
                    header_form.save()
                    item_formset.save()

                    # 3. Apply new stock for all current items (subtract stock)
                    for item_instance in outward_header.items.all():
                        stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.warehouse)
                        stock.quantity -= item_instance.quantity
                        stock.save()
                    
                    messages.success(request, 'Outward transaction updated successfully!')
            else:
                messages.info(request, 'No changes were detected.')

            return redirect('outward_report')
        
        context = {'header_form': header_form, 'item_formset': item_formset, 'object': outward_header}
        return render(request, 'inventory/outward_edit.html', context)


class OutwardDeleteView(LoginRequiredMixin, DeleteView):
    model = OutwardHeader
    template_name = 'inventory/outward_confirm_delete.html'
    success_url = reverse_lazy('outward_report')

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        # For each item, reverse the stock change (add it back)
        for item in self.object.items.all():
            stock, _ = OpeningStock.objects.get_or_create(item=item.item, warehouse=item.warehouse)
            stock.quantity += item.quantity
            stock.save()
        messages.success(request, f"Outward transaction {self.object.invoice_no} has been deleted and stock updated.")
        return super().post(request, *args, **kwargs)


class ProductionUpdateView(LoginRequiredMixin, View):
    ProducedItemFormSet = inlineformset_factory(
        ProductionHeader, ProductionItem, form=ProductionItemForm,
        extra=0, can_delete=True,
    )
    ConsumedItemFormSet = inlineformset_factory(
        ProductionHeader, ProductionItem, form=ProductionItemForm,
        extra=0, can_delete=True,
    )

    def get(self, request, pk):
        production_header = ProductionHeader.objects.get(pk=pk)
        header_form = ProductionHeaderForm(instance=production_header)
        
        produced_queryset = production_header.items.filter(type='Produced')
        consumed_queryset = production_header.items.filter(type='Consumed')

        produced_formset = self.ProducedItemFormSet(instance=production_header, queryset=produced_queryset)
        consumed_formset = self.ConsumedItemFormSet(instance=production_header, queryset=consumed_queryset)

        for form in produced_formset:
            if form.instance.pk: form.fields['group'].initial = form.instance.item.group
        for form in consumed_formset:
            if form.instance.pk: form.fields['group'].initial = form.instance.item.group

        context = {
            'header_form': header_form,
            'produced_formset': produced_formset,
            'consumed_formset': consumed_formset,
            'object': production_header
        }
        return render(request, 'inventory/production_edit.html', context)
        

    @transaction.atomic
    def post(self, request, pk):
        production_header = ProductionHeader.objects.get(pk=pk)
        
        # Reverse all original stock movements first
        for item in production_header.items.all():
            stock, _ = OpeningStock.objects.get_or_create(item=item.item, warehouse=item.warehouse)
            if item.type == 'Produced':
                stock.quantity -= item.quantity # Subtract produced quantity
            elif item.type == 'Consumed':
                stock.quantity += item.quantity # Add back consumed quantity
            stock.save()

        header_form = ProductionHeaderForm(request.POST, instance=production_header)
        produced_formset = self.ProducedItemFormSet(request.POST, instance=production_header)
        consumed_formset = self.ConsumedItemFormSet(request.POST, instance=production_header)

        if header_form.is_valid() and produced_formset.is_valid() and consumed_formset.is_valid():
            header_form.save()
            produced_formset.save()
            consumed_formset.save()

            messages.success(request, 'Production transaction updated successfully!')
            return redirect('production_report')

        context = {'header_form': header_form, 'produced_formset': produced_formset, 'consumed_formset': consumed_formset, 'object': production_header}
        return render(request, 'inventory/production_edit.html', context)


class ProductionDeleteView(LoginRequiredMixin, DeleteView):
    model = ProductionHeader
    template_name = 'inventory/production_confirm_delete.html'
    success_url = reverse_lazy('production_report')

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        # For each item, reverse the stock change
        for item in self.object.items.all():
            stock, _ = OpeningStock.objects.get_or_create(item=item.item, warehouse=item.warehouse)
            if item.type == 'Produced':
                stock.quantity -= item.quantity # Subtract what was produced
            elif item.type == 'Consumed':
                stock.quantity += item.quantity # Add back what was consumed
            stock.save()
        messages.success(request, f"Production entry {self.object.reference_no} has been deleted and stock updated.")
        return super().post(request, *args, **kwargs)

class BOMView(LoginRequiredMixin, View):
    BOMItemFormSet = inlineformset_factory(BillOfMaterial, BOMItem, form=BOMItemForm, extra=1, can_delete=True)

    def get(self, request):
        form = BOMForm()
        formset = self.BOMItemFormSet()
        boms = BillOfMaterial.objects.select_related('item').prefetch_related('items__item').all()
        context = {
            'form': form, 
            'formset': formset, 
            'boms': boms,
        }
        return render(request, 'inventory/bom_create.html', context)

    @transaction.atomic
    def post(self, request):
        form = BOMForm(request.POST)
        formset = self.BOMItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            if BillOfMaterial.objects.filter(item=form.cleaned_data['item']).exists():
                messages.error(request, f"A Bill of Material already exists for {form.cleaned_data['item']}.")
            else:
                bom_instance = form.save()
                formset.instance = bom_instance
                formset.save()
                messages.success(request, 'Bill of Material saved successfully!')
                return redirect('bom_create')
        
        boms = BillOfMaterial.objects.select_related('item').prefetch_related('items__item').all()
        context = {'form': form, 'formset': formset, 'boms': boms}
        return render(request, 'inventory/bom_create.html', context)
        
class DeliveryOutUpdateView(LoginRequiredMixin, View):
    DeliveryOutItemFormSet = inlineformset_factory(
        DeliveryOutHeader, DeliveryOutItem, form=DeliveryOutItemForm,
        extra=0, can_delete=True,
    )

    def dispatch(self, request, *args, **kwargs):
        # This check runs before the GET or POST method
        delivery_header = DeliveryOutHeader.objects.get(pk=kwargs['pk'])
        if DeliveryInItem.objects.filter(original_delivery_item__header=delivery_header).exists():
            messages.error(request, 'This transaction cannot be edited because returns have been recorded against it.')
            return redirect('delivery_note_report')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk):
        delivery_header = DeliveryOutHeader.objects.get(pk=pk)
        header_form = DeliveryOutHeaderForm(instance=delivery_header)
        item_formset = self.DeliveryOutItemFormSet(instance=delivery_header)
        
        for form in item_formset:
            if form.instance.pk and form.instance.item:
                form.fields['group'].initial = form.instance.item.group
        
        context = {
            'header_form': header_form, 
            'item_formset': item_formset, 
            'object': delivery_header
        }
        return render(request, 'inventory/delivery_out_edit.html', context)

    @transaction.atomic
    def post(self, request, pk):
        delivery_header = DeliveryOutHeader.objects.get(pk=pk)
        old_items = {item.id: {
            'item_id': item.item_id, 
            'quantity': item.issued_quantity, 
            'warehouse_id': item.from_warehouse_id
        } for item in delivery_header.items.all()}
        
        header_form = DeliveryOutHeaderForm(request.POST, instance=delivery_header)
        item_formset = self.DeliveryOutItemFormSet(request.POST, instance=delivery_header)

        if header_form.is_valid() and item_formset.is_valid():
            
            if header_form.has_changed() or item_formset.has_changed():
                
                # --- THIS IS THE NEW VALIDATION ---
                has_items = any(form.cleaned_data and not form.cleaned_data.get('DELETE', False) for form in item_formset)
                
                if not has_items:
                    messages.error(request, "Cannot save a transaction with no items. Please add at least one item or delete the entire transaction.")
                else:
                    # 1. Reverse original stock movements
                    for item_id, old_data in old_items.items():
                        stock, _ = OpeningStock.objects.get_or_create(item_id=old_data['item_id'], warehouse_id=old_data['warehouse_id'])
                        stock.quantity += old_data['quantity']
                        stock.save()
                    
                    # 2. Save form changes
                    header_form.save()
                    item_formset.save()

                    # 3. Apply new stock movements
                    for item_instance in delivery_header.items.all():
                        stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.from_warehouse)
                        stock.quantity -= item_instance.issued_quantity
                        stock.save()

                    messages.success(request, 'Material Out transaction updated successfully!')
            else:
                messages.info(request, 'No changes were detected.')

            return redirect('delivery_note_report')
        
        # If any form is invalid, re-render the page
        context = {'header_form': header_form, 'item_formset': item_formset, 'object': delivery_header}
        return render(request, 'inventory/delivery_out_edit.html', context)

class DeliveryOutDeleteView(LoginRequiredMixin, DeleteView):
    model = DeliveryOutHeader
    template_name = 'inventory/delivery_out_confirm_delete.html'
    success_url = reverse_lazy('delivery_note_report')

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if DeliveryInItem.objects.filter(original_delivery_item__header=self.object).exists():
            messages.error(request, 'This transaction cannot be deleted because returns have been recorded against it.')
            return redirect('delivery_note_report')
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        # Reverse the stock change for each item (add it back)
        for item in self.object.items.all():
            stock, _ = OpeningStock.objects.get_or_create(item=item.item, warehouse=item.from_warehouse)
            stock.quantity += item.issued_quantity
            stock.save()
            
        messages.success(request, f"Material Out {self.object.reference_no} deleted and stock updated.")
        # Let the original DeleteView handle the actual deletion and redirect
        return super().post(request, *args, **kwargs)

class DeliveryNoteReportView(LoginRequiredMixin, View):
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        per_page = request.GET.get('per_page', 10)
        type_filter = request.GET.get('type_filter')
        
        # If no date is provided in the filter, use the active period dates as default
        if not start_date or not end_date:
            active_period = SystemSetting.objects.get(name="Active Period")
            start_date = active_period.start_date.strftime('%Y-%m-%d')
            end_date = active_period.end_date.strftime('%Y-%m-%d')        

        material_out_list = DeliveryOutHeader.objects.prefetch_related('items__item', 'items__from_warehouse', 'items__deliveryinitem_set').select_related('to_person').all()
        material_in_list = DeliveryInHeader.objects.prefetch_related('items__original_delivery_item__item', 'items__to_warehouse', 'items__original_delivery_item__header__to_person').all()

        combined_list = []
        for do in material_out_list:
            combined_list.append({
                'obj': do, 'type': 'Material Out', 'date': do.date,
                'ref_no': do.reference_no, 'contact': do.to_person, 'items': do.items.all()
            })
        for di in material_in_list:
            combined_list.append({
                'obj': di, 'type': 'Material In', 'date': di.date,
                'ref_no': f"Return of {di.items.first().original_delivery_item.header.reference_no if di.items.first() else ''}",
                'contact': di.items.first().original_delivery_item.header.to_person if di.items.first() else None,
                'items': di.items.all()
            })
        
        if start_date:
            combined_list = [tx for tx in combined_list if tx['date'] >= datetime.strptime(start_date, '%Y-%m-%d').date()]
        if end_date:
            combined_list = [tx for tx in combined_list if tx['date'] <= datetime.strptime(end_date, '%Y-%m-%d').date()]
        if type_filter:
            combined_list = [tx for tx in combined_list if tx['type'] == type_filter]
        
        combined_list.sort(key=lambda x: x['date'], reverse=True)

        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="delivery_note_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Type', 'Ref No.', 'Contact', 'Item', 'Warehouse', 'Quantity'])
            for tx in combined_list:
                contact_name = tx['contact'].name if tx['contact'] else ''
                for item in tx['items']:
                    if tx['type'] == 'Material Out':
                        writer.writerow([tx['date'], tx['type'], tx['ref_no'], contact_name, item.item.name, item.from_warehouse.name, f"-{item.issued_quantity}"])
                    else: # Material In
                        writer.writerow([tx['date'], tx['type'], tx['ref_no'], contact_name, item.original_delivery_item.item.name, item.to_warehouse.name, f"+{item.returned_quantity}"])
            return response

        paginator = Paginator(combined_list, per_page)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'transactions': page_obj,
            'per_page': per_page,
            'start_date': start_date,
            'end_date': end_date,
            'type_filter': type_filter,
        }
        return render(request, 'inventory/delivery_note_report.html', context)

class DeliveryInUpdateView(LoginRequiredMixin, View):
    DeliveryInItemFormSet = inlineformset_factory(
        DeliveryInHeader, DeliveryInItem, form=DeliveryInItemForm,
        extra=0, can_delete=True,
    )

    def get(self, request, pk):
        delivery_header = DeliveryInHeader.objects.get(pk=pk)
        header_form = DeliveryInHeaderForm(instance=delivery_header)
        item_formset = self.DeliveryInItemFormSet(instance=delivery_header)
        
        context = {
            'header_form': header_form,
            'item_formset': item_formset,
            'object': delivery_header
        }
        return render(request, 'inventory/delivery_in_edit.html', context)

    @transaction.atomic
    def post(self, request, pk):
        delivery_header = DeliveryInHeader.objects.get(pk=pk)
        old_items = {item.id: {
            'original_delivery_item': item.original_delivery_item,
            'returned_quantity': item.returned_quantity,
            'to_warehouse': item.to_warehouse
        } for item in delivery_header.items.all()}

        header_form = DeliveryInHeaderForm(request.POST, instance=delivery_header)
        item_formset = self.DeliveryInItemFormSet(request.POST, instance=delivery_header)

        if header_form.is_valid() and item_formset.is_valid():
            # 1. Reverse all original stock movements
            for item_id, old_data in old_items.items():
                original_item = old_data['original_delivery_item']
                original_item.returned_quantity -= old_data['returned_quantity']
                original_item.save()
                
                stock, _ = OpeningStock.objects.get_or_create(item=original_item.item, warehouse=old_data['to_warehouse'])
                stock.quantity -= old_data['returned_quantity']
                stock.save()

            # 2. Save form changes
            header_form.save()
            item_formset.save()

            # 3. Apply new stock movements
            for item_instance in delivery_header.items.all():
                original_item = item_instance.original_delivery_item
                original_item.returned_quantity += item_instance.returned_quantity
                original_item.save()
                
                stock, _ = OpeningStock.objects.get_or_create(item=original_item.item, warehouse=item_instance.to_warehouse)
                stock.quantity += item_instance.returned_quantity
                stock.save()

            messages.success(request, 'Material In transaction updated successfully!')
            return redirect('delivery_note_report')
        
        context = {'header_form': header_form, 'item_formset': item_formset, 'object': delivery_header}
        return render(request, 'inventory/delivery_in_edit.html', context)
        
class DeliveryInDeleteView(LoginRequiredMixin, DeleteView):
    model = DeliveryInHeader
    template_name = 'inventory/delivery_in_confirm_delete.html'
    success_url = reverse_lazy('delivery_note_report')

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        # For each item returned, reverse the stock movements
        for item in self.object.items.all():
            # Decrease stock in the warehouse it was returned to
            stock, _ = OpeningStock.objects.get_or_create(item=item.original_delivery_item.item, warehouse=item.to_warehouse)
            stock.quantity -= item.returned_quantity
            stock.save()

            # Increase the returned_quantity on the original DeliveryOutItem
            original_item = item.original_delivery_item
            original_item.returned_quantity -= item.returned_quantity
            original_item.save()
            
        messages.success(request, f"Material In transaction has been deleted and stock updated.")
        return super().post(request, *args, **kwargs)
        


class PeriodSettingView(LoginRequiredMixin, View):
    def get(self, request):
        # We'll use a single setting record with a specific name
        setting, created = SystemSetting.objects.get_or_create(
            name="Active Period",
            defaults={'start_date': timezone.now().date(), 'end_date': timezone.now().date()}
        )
        form = SystemSettingForm(instance=setting)
        context = {'form': form}
        return render(request, 'inventory/period_setting.html', context)

    def post(self, request):
        setting = SystemSetting.objects.get(name="Active Period")
        form = SystemSettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            messages.success(request, "Active period has been updated.")
            return redirect('period_setting')
        context = {'form': form}
        return render(request, 'inventory/period_setting.html', context)

def get_items_by_group(request, group_id):
    items = Item.objects.filter(group_id=group_id).values('id', 'name')
    return JsonResponse(list(items), safe=False)
class UserListView(LoginRequiredMixin, View):
    def get(self, request):
        # Admins can only see users from their own company
        users = User.objects.filter(company=request.user.company).order_by('username')
        context = {'users': users}
        return render(request, 'inventory/user_list.html', context)

class UserCreateView(LoginRequiredMixin, View):
    def get(self, request):
        form = CustomUserCreationForm()
        # Ensure the new user is assigned to the creator's company
        form.fields['company'].initial = request.user.company
        form.fields['company'].disabled = True
        return render(request, 'inventory/user_form.html', {'form': form, 'title': 'Create New User'})

    def post(self, request):
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.company = request.user.company # Enforce company assignment
            user.save()
            messages.success(request, 'User created successfully.')
            return redirect('user_list')
        return render(request, 'inventory/user_form.html', {'form': form, 'title': 'Create New User'})

class UserUpdateView(LoginRequiredMixin, View):
    def get(self, request, pk):
        user_to_edit = User.objects.get(pk=pk, company=request.user.company) # Security check
        form = CustomUserChangeForm(instance=user_to_edit)
        form.fields['company'].disabled = True
        return render(request, 'inventory/user_form.html', {'form': form, 'title': f'Edit User: {user_to_edit.username}'})

    def post(self, request, pk):
        user_to_edit = User.objects.get(pk=pk, company=request.user.company) # Security check
        form = CustomUserChangeForm(request.POST, instance=user_to_edit)
        if form.is_valid():
            form.save()
            messages.success(request, 'User updated successfully.')
            return redirect('user_list')
        return render(request, 'inventory/user_form.html', {'form': form, 'title': f'Edit User: {user_to_edit.username}'})
        

class OpeningStockUpdateView(LoginRequiredMixin, UpdateView):
    model = OpeningStock
    form_class = OpeningStockForm
    template_name = 'inventory/opening_stock_edit.html'
    success_url = reverse_lazy('opening_stock')

    def form_valid(self, form):
        messages.success(self.request, "Opening stock record updated successfully.")
        return super().form_valid(form)

class OpeningStockDeleteView(LoginRequiredMixin, DeleteView):
    model = OpeningStock
    template_name = 'inventory/opening_stock_confirm_delete.html'
    success_url = reverse_lazy('opening_stock')

    def form_valid(self, form):
        messages.success(self.request, "Opening stock record deleted successfully.")
        return super().form_valid(form)


