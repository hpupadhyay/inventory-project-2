import csv
import io
from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.forms import inlineformset_factory
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.db import models
from django.views.generic.edit import UpdateView, DeleteView
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from datetime import datetime

# Import your models
from .models import (
    ItemMaster, InwardHeader, GroupMaster, WarehouseMaster, Contact, OpeningStock, 
    InwardItem, OutwardHeader, OutwardItem, ProductionHeader, ProductionItem, 
    WarehouseTransferHeader, WarehouseTransferItem, DeliveryOutHeader, 
    DeliveryOutItem, DeliveryInHeader, DeliveryInItem, StockAdjustmentHeader, StockAdjustmentItem, BillOfMaterial, BOMItem,
)

# Import your forms
from .forms import (
    ItemMasterForm, GroupMasterForm, WarehouseMasterForm, ContactForm, InwardHeaderForm, 
    InwardItemForm, OutwardHeaderForm, OutwardItemForm, ProductionHeaderForm, ProductionItemForm,
    WarehouseTransferHeaderForm, WarehouseTransferItemForm, DeliveryOutHeaderForm, 
    DeliveryOutItemForm, DeliveryInHeaderForm, StockAdjustmentHeaderForm, StockAdjustmentItemForm, BOMForm, BOMItemForm
)


# --- AUTH & DASHBOARD ---
class CustomLoginView(LoginView):
    template_name = 'inventory/login.html'
    redirect_authenticated_user = True

class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        total_items = ItemMaster.objects.count()
        inward_count = InwardHeader.objects.count()
        top_stock = ItemMaster.objects.annotate(stock_count=Count('id')).order_by('-stock_count')[:5]
        context = {
            'total_items': total_items,
            'inward_count': inward_count,
            'outward_count': 0, 
            'low_stock_count': 0,
            'chart_labels': [item.name for item in top_stock],
            'chart_data': [item.stock_count for item in top_stock],
        }
        return render(request, 'inventory/dashboard.html', context)

# View for Item Master page

class ItemMasterView(LoginRequiredMixin, View):
    def get(self, request):
        # The get method for displaying the page remains the same
        form = ItemMasterForm()
        items_list = ItemMaster.objects.select_related('group').all().order_by('name')
        search_query = request.GET.get('search_query', '')
        group_filter = request.GET.get('group_filter', '')
        per_page = request.GET.get('per_page', 10)

        if search_query:
            items_list = items_list.filter(Q(name__icontains=search_query) | Q(code__icontains=search_query))
        if group_filter:
            items_list = items_list.filter(group_id=group_filter)

        paginator = Paginator(items_list, per_page)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'form': form, 'items': page_obj, 'groups': GroupMaster.objects.all(),
            'search_query': search_query, 'group_filter': int(group_filter) if group_filter else None,
            'per_page': per_page,
        }
        return render(request, 'inventory/item_master.html', context)

    @transaction.atomic
    def post(self, request):
        # --- NEW: AJAX CSV Import Logic ---
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            csv_file = request.FILES.get('csv_file')
            if not csv_file:
                return JsonResponse({'status': 'error', 'message': 'No file was uploaded.'})

            try:
                # Decoding logic...
                file_data = csv_file.read()
                decoded_file = None
                for encoding in ['utf-8', 'latin-1', 'windows-1252']:
                    try: decoded_file = file_data.decode(encoding); break
                    except UnicodeDecodeError: continue
                if decoded_file is None:
                    return JsonResponse({'status': 'error', 'message': 'File encoding not supported. Please save as UTF-8.'})

                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string)
                header = next(reader)
                
                valid_rows, error_rows = [], []
                existing_names = set(ItemMaster.objects.values_list('name', flat=True))
                existing_codes = set(ItemMaster.objects.filter(code__isnull=False).values_list('code', flat=True))

                for i, row in enumerate(reader, start=2):
                    item_name, item_code = row[0].strip(), row[1].strip() or None
                    error_found = False
                    if item_name in existing_names:
                        error_rows.append(row + [f'Line {i}: Item name "{item_name}" already exists.']); error_found = True
                    if item_code and item_code in existing_codes:
                        error_rows.append(row + [f'Line {i}: Item code "{item_code}" already exists.']); error_found = True
                    if not error_found:
                        valid_rows.append(row); existing_names.add(item_name)
                        if item_code: existing_codes.add(item_code)
                
                if error_rows:
                    # Create the error report as a string
                    output = io.StringIO()
                    writer = csv.writer(output)
                    writer.writerow(header + ['Error Message'])
                    writer.writerows(error_rows)
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Import failed. See report for details.',
                        'error_report': output.getvalue()
                    })

                for row in valid_rows:
                    item_name, item_code, group_name, unit = row
                    group, _ = GroupMaster.objects.get_or_create(name=group_name.strip())
                    ItemMaster.objects.create(name=item_name.strip(), code=item_code.strip() or None, group=group, unit=unit.strip())
                
                return JsonResponse({'status': 'success', 'message': f'Successfully imported {len(valid_rows)} new items.'})

            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {e}'})

        # --- Standard Form Submission Logic (for adding a single item) ---
        form = ItemMasterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item added successfully!')
            return redirect('item_master')
        
        # If form is not valid, re-render the page with context
        # (This part is copied from your get method for consistency)
        items_list = ItemMaster.objects.select_related('group').all().order_by('name')
        paginator = Paginator(items_list, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        context = {'form': form, 'items': page_obj, 'groups': GroupMaster.objects.all()}
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
        stock_data = OpeningStock.objects.select_related('item', 'warehouse').all()
        context = {'stock_data': stock_data}
        return render(request, 'inventory/opening_stock.html', context)

    @transaction.atomic
    def post(self, request):
        # --- Download Template Logic (remains the same) ---
        if 'download_template' in request.POST:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="opening_stock_template.csv"'
            writer = csv.writer(response)
            writer.writerow(['Item Name', 'Warehouse Name', 'Quantity'])
            return response

        # --- Advanced CSV Import Logic ---
        if 'import_csv' in request.POST:
            csv_file = request.FILES.get('csv_file')
            if not csv_file or not csv_file.name.endswith('.csv'):
                messages.error(request, 'Please upload a valid .csv file.')
                return redirect('opening_stock')
            
            try:
                # Decode the file
                file_data = csv_file.read()
                decoded_file = None
                for encoding in ['utf-8', 'latin-1', 'windows-1252']:
                    try:
                        decoded_file = file_data.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                if decoded_file is None:
                    messages.error(request, 'Failed to decode file. Please re-save as UTF-8.')
                    return redirect('opening_stock')

                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string)
                header = next(reader)

                valid_rows = []
                error_rows = []
                
                # First pass: Validate all rows
                for i, row in enumerate(reader, start=2):
                    try:
                        item_name, warehouse_name, quantity_str = row
                        item = ItemMaster.objects.get(name=item_name.strip())
                        warehouse = WarehouseMaster.objects.get(name=warehouse_name.strip())
                        quantity = int(quantity_str.strip())
                        valid_rows.append({'item': item, 'warehouse': warehouse, 'quantity': quantity})
                    except ItemMaster.DoesNotExist:
                        error_rows.append(row + [f'Line {i}: Item "{item_name}" does not exist.'])
                    except WarehouseMaster.DoesNotExist:
                        error_rows.append(row + [f'Line {i}: Warehouse "{warehouse_name}" does not exist.'])
                    except (ValueError, IndexError):
                        error_rows.append(row + [f'Line {i}: Invalid data format or missing columns.'])

                # If there are errors, generate a report and stop
                if error_rows:
                    response = HttpResponse(content_type='text/csv')
                    response['Content-Disposition'] = 'attachment; filename="import_errors.csv"'
                    writer = csv.writer(response)
                    writer.writerow(header + ['Error Message']) # Add error column to header
                    writer.writerows(error_rows)
                    messages.error(request, 'Import failed. Please check the downloaded error report.')
                    return response

                # If no errors, process the valid rows
                for data in valid_rows:
                    OpeningStock.objects.update_or_create(
                        item=data['item'], warehouse=data['warehouse'],
                        defaults={'quantity': data['quantity']}
                    )
                
                messages.success(request, f'Successfully imported {len(valid_rows)} stock records.')

            except Exception as e:
                messages.error(request, f'An unexpected error occurred: {e}')
            
            return redirect('opening_stock')
        
        return redirect('opening_stock')  
        
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
    # Create a formset factory for InwardItem, linked to InwardHeader
    InwardItemFormSet = inlineformset_factory(
        InwardHeader, 
        InwardItem, 
        form=InwardItemForm, 
        extra=1, 
        can_delete=True, 

    )

    def get(self, request):
        header_form = InwardHeaderForm()
        item_formset = self.InwardItemFormSet()
        
        context = {
            'header_form': header_form, 
            'item_formset': item_formset,
        }
        
        return render(request, 'inventory/inward.html', context)

    @transaction.atomic
    def post(self, request):
        header_form = InwardHeaderForm(request.POST)
        item_formset = self.InwardItemFormSet(request.POST)

        # --- Logic to create new supplier if it doesn't exist ---
        supplier_id_or_name = request.POST.get('supplier')
        if supplier_id_or_name and not supplier_id_or_name.isnumeric():
            # If the value is not a number, it's a new supplier name
            new_supplier, created = Contact.objects.get_or_create(
                name=supplier_id_or_name.strip(), 
                defaults={'type': 'Supplier'}
            )
            # Create a mutable copy of the POST data to modify it
            post_data = request.POST.copy()
            post_data['supplier'] = new_supplier.id
            header_form = InwardHeaderForm(post_data) # Re-initialize the form with the new ID
        
        if header_form.is_valid() and item_formset.is_valid():
            # (The rest of the saving and stock update logic remains the same)
            # ...
            inward_header = header_form.save(commit=False)
            inward_header.created_by = request.user
            inward_header.save()
            
            item_formset.instance = inward_header
            item_formset.save()
            for form in item_formset.cleaned_data:
                if form and not form.get('DELETE'):
                    stock, _ = OpeningStock.objects.get_or_create(item=form['item'], warehouse=form['warehouse'])
                    stock.quantity += form['quantity']
                    stock.save()
            messages.success(request, 'Inward entry successful!')
            return redirect('inward')
        
        context = {
            'header_form': header_form, 
            'item_formset': item_formset,
        }
        return render(request, 'inventory/inward.html', context)
        
# inventory/views.py

class OutwardView(LoginRequiredMixin, View):
    OutwardItemFormSet = inlineformset_factory(
        OutwardHeader, OutwardItem, form=OutwardItemForm, extra=1,
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
        # --- THIS IS THE NEW LOGIC FOR CUSTOMER CREATION ---
        # Get the submitted value for the customer
        customer_id_or_name = request.POST.get('customer')
        post_data = request.POST.copy() # Create a mutable copy

        # Check if the value is a new name (not a number/ID)
        if customer_id_or_name and not customer_id_or_name.isnumeric():
            new_customer, created = Contact.objects.get_or_create(
                name=customer_id_or_name.strip(), 
                defaults={'type': 'Customer'}
            )
            # Replace the text name with the new ID in our copy of the data
            post_data['customer'] = new_customer.id
            post_data = request.POST.copy()
            post_data['customer'] = new_customer.id
            header_form = OutwardHeaderForm(post_data)
        
        if header_form.is_valid() and item_formset.is_valid():
            outward_header = header_form.save(commit=False)
            outward_header.created_by = request.user
            outward_header.save()
            
            for form in item_formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    item_instance = form.save(commit=False)
                    item_instance.header = outward_header
                    item_instance.save()
                    stock, _ = OpeningStock.objects.get_or_create(
                        item=item_instance.item, warehouse=item_instance.warehouse
                    )
                    stock.quantity -= item_instance.quantity
                    stock.save()

            messages.success(request, 'Outward entry successful!')
            return redirect('outward')
        
        context = {
            'header_form': header_form, 
            'item_formset': item_formset,
        }
        return render(request, 'inventory/outward.html', context)
        


class ProductionView(LoginRequiredMixin, View):
    ProducedItemFormSet = inlineformset_factory(
        ProductionHeader, ProductionItem, form=ProductionItemForm,
        extra=1, can_delete=True,
    )
    ConsumedItemFormSet = inlineformset_factory(
        ProductionHeader, ProductionItem, form=ProductionItemForm,
        extra=1, can_delete=True,
    )

    def get(self, request):
        header_form = ProductionHeaderForm()
        produced_formset = self.ProducedItemFormSet()
        consumed_formset = self.ConsumedItemFormSet()
        recent_productions = ProductionHeader.objects.order_by('-date', '-created_at')[:10]
        context = {
            'header_form': header_form,
            'produced_formset': produced_formset,
            'consumed_formset': consumed_formset,
            'recent_productions': recent_productions,
        }
        return render(request, 'inventory/production.html', context)

    @transaction.atomic
    def post(self, request):
        header_form = ProductionHeaderForm(request.POST)
        produced_formset = self.ProducedItemFormSet(request.POST)
        consumed_formset = self.ConsumedItemFormSet(request.POST)
        if header_form.is_valid() and produced_formset.is_valid() and consumed_formset.is_valid():
            production_header = header_form.save(commit=False)
            production_header.created_by = request.user
            production_header.save()
            for form in produced_formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    item_instance = form.save(commit=False)
                    item_instance.header = production_header
                    item_instance.type = 'Produced'
                    item_instance.save()
                    stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.warehouse)
                    stock.quantity += item_instance.quantity
                    stock.save()
            for form in consumed_formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    item_instance = form.save(commit=False)
                    item_instance.header = production_header
                    item_instance.type = 'Consumed'
                    item_instance.save()
                    stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.warehouse)
                    stock.quantity -= item_instance.quantity
                    stock.save()
            messages.success(request, 'Production entry successful!')
            return redirect('production')
        recent_productions = ProductionHeader.objects.order_by('-date', '-created_at')[:10]
        context = {
            'header_form': header_form,
            'produced_formset': produced_formset,
            'consumed_formset': consumed_formset,
            'recent_productions': recent_productions,
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
            
            # --- NEW VALIDATION ---
            # Check if any forms in the formset have data
            has_items = False
            for form in item_formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    has_items = True
                    break
            
            if not has_items:
                messages.error(request, "You must add at least one item to the transfer.")
            else:
                # If there are items, proceed with saving
                transfer_header = header_form.save(commit=False)
                transfer_header.created_by = request.user
                transfer_header.save()

                for form in item_formset:
                    if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                        item_instance = form.save(commit=False)
                        item_instance.header = transfer_header
                        item_instance.save()
                        
                        from_stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.from_warehouse)
                        from_stock.quantity -= item_instance.quantity
                        from_stock.save()

                        to_stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.to_warehouse)
                        to_stock.quantity += item_instance.quantity
                        to_stock.save()

                messages.success(request, 'Warehouse transfer successful!')
                return redirect('warehouse_transfer')

        # This part runs if there are form errors or the validation fails
        recent_transfers = WarehouseTransferHeader.objects.order_by('-date', '-created_at')[:10]
        context = {
            'header_form': header_form,
            'item_formset': item_formset,
            'recent_transfers': recent_transfers,
            'groups': GroupMaster.objects.all()
        }
        return render(request, 'inventory/warehouse_transfer.html', context)


class DeliveryOutView(LoginRequiredMixin, View):
    DeliveryOutItemFormSet = inlineformset_factory(
        DeliveryOutHeader, 
        DeliveryOutItem, 
        form=DeliveryOutItemForm, 
        extra=1, 
        can_delete=False
    )
    def get(self, request):
        header_form = DeliveryOutHeaderForm()
        item_formset = self.DeliveryOutItemFormSet()
        context = {'header_form': header_form, 'item_formset': item_formset}
        return render(request, 'inventory/delivery_out.html', context)

    @transaction.atomic
    def post(self, request):
        header_form = DeliveryOutHeaderForm(request.POST)
        item_formset = self.DeliveryOutItemFormSet(request.POST)

        if header_form.is_valid() and item_formset.is_valid():
            delivery_header = header_form.save(commit=False)
            delivery_header.created_by = request.user
            delivery_header.save()

            items = item_formset.save(commit=False)
            for item_instance in items:
                item_instance.header = delivery_header
                item_instance.save()
                
                # DECREASE stock when material is sent out
                stock, _ = OpeningStock.objects.get_or_create(
                    item=item_instance.item, warehouse=item_instance.from_warehouse
                )
                stock.quantity -= item_instance.issued_quantity
                stock.save()

            messages.success(request, 'Material Out entry successful!')
            return redirect('delivery_out')

        context = {'header_form': header_form, 'item_formset': item_formset}
        return render(request, 'inventory/delivery_out.html', context)

# inventory/views.py

class DeliveryInView(LoginRequiredMixin, View):
    def get(self, request):
        header_form = DeliveryInHeaderForm()
        
        # This query now fetches the contact's name instead of their ID.
        pending_deliveries = DeliveryOutItem.objects.filter(
            issued_quantity__gt=models.F('returned_quantity')
        ).values('header__to_person__name').distinct().order_by('header__to_person__name')
        
        context = {
            'header_form': header_form,
            'pending_persons': [p['header__to_person__name'] for p in pending_deliveries],
            # We also need to pass the list of warehouses for the JavaScript to use.
            'warehouses': WarehouseMaster.objects.all(),
        }
        return render(request, 'inventory/delivery_in.html', context)

    @transaction.atomic
    def post(self, request):
        header_form = DeliveryInHeaderForm(request.POST)
        original_item_ids = request.POST.getlist('original_item_id')
        return_quantities = request.POST.getlist('return_quantity')
        return_warehouse_ids = request.POST.getlist('return_warehouse_id')

        # Safely combine the lists into tuples
        returned_items_data = zip(original_item_ids, return_quantities, return_warehouse_ids)

        if header_form.is_valid() and original_item_ids:
            delivery_header = header_form.save(commit=False)
            delivery_header.created_by = request.user
            delivery_header.save()

            # Loop through the combined data
            for item_id, qty_str, warehouse_id in returned_items_data:
                return_qty = int(qty_str)
                if return_qty > 0:
                    original_item = DeliveryOutItem.objects.get(pk=item_id)
                    return_warehouse = WarehouseMaster.objects.get(pk=warehouse_id)
                    
                    if return_qty > original_item.pending_quantity:
                        messages.error(request, f"Cannot return {return_qty} of {original_item.item.name}, only {original_item.pending_quantity} is pending.")
                        return redirect('delivery_in')

                    DeliveryInItem.objects.create(
                        header=delivery_header,
                        original_delivery_item=original_item,
                        returned_quantity=return_qty,
                        to_warehouse=return_warehouse
                    )
                    
                    original_item.returned_quantity += return_qty
                    original_item.save()

                    stock, _ = OpeningStock.objects.get_or_create(
                        item=original_item.item, warehouse=return_warehouse
                    )
                    stock.quantity += return_qty
                    stock.save()

            messages.success(request, 'Material In entry successful!')
            return redirect('delivery_in')

        messages.error(request, 'An error occurred. Please check your entries.')
        return redirect('delivery_in')
    
# inventory/views.py

class StockReportView(LoginRequiredMixin, View):
    def get(self, request):
        # --- 1. Get Parameters ---
        sort_by_group = request.GET.get('sort_by') == 'item_group'
        per_page = request.GET.get('per_page', 10)
        hide_zero = request.GET.get('hide_zero')

        # --- 2. Get Data From Database ---
        warehouses = WarehouseMaster.objects.order_by('name')
        items_query = ItemMaster.objects.select_related('group').all()
        if sort_by_group:
            items_query = items_query.order_by('group__name', 'name')
        else:
            items_query = items_query.order_by('name')
        
        stock_levels = OpeningStock.objects.all()
        stock_map = {(stock.item_id, stock.warehouse_id): stock.quantity for stock in stock_levels}
        
        pending_deliveries = DeliveryOutItem.objects.filter(
            issued_quantity__gt=models.F('returned_quantity')
        ).values('item_id').annotate(total_pending=Sum('issued_quantity') - Sum('returned_quantity'))
        pending_map = {p['item_id']: p['total_pending'] for p in pending_deliveries}

        # --- 3. Build the Full Report Data ---
        full_report_data = []
        for item in items_query:
            row = {
                'item_name': item.name, 'item_code': item.code, 'item_group': item.group.name,
                'stock_by_warehouse': [], 'total_stock': 0, 'pending': pending_map.get(item.id, 0)
            }
            for wh in warehouses:
                quantity = stock_map.get((item.id, wh.id), 0)
                row['stock_by_warehouse'].append(quantity)
                row['total_stock'] += quantity
            full_report_data.append(row)

        # --- 4. Calculate Grand Totals (based on the full dataset) ---
        column_totals = [sum(stock_map.get((item.id, wh.id), 0) for item in items_query) for wh in warehouses]
        grand_total_stock = sum(column_totals)
        grand_total_pending = sum(pending_map.values())
        
        # --- 5. Handle Export Request (uses the full dataset) ---
        if request.GET.get('export') == 'csv':
            # This part remains the same, but we'll use 'full_report_data'
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="item_wise_stock_report.csv"'
            writer = csv.writer(response)
            headers = ['Item Name', 'Item Code', 'Item Group'] + [wh.name for wh in warehouses] + ['Total In Stock', 'Pending Return']
            writer.writerow(headers)
            for row_data in full_report_data:
                row_to_write = [row_data['item_name'], row_data['item_code'], row_data['item_group']] + row_data['stock_by_warehouse'] + [row_data['total_stock'], row_data['pending']]
                writer.writerow(row_to_write)
            footer = ['Grand Total', '', ''] + column_totals + [grand_total_stock, grand_total_pending]
            writer.writerow(footer)
            return response

        # --- 6. Filter for Display (if checked) ---
        display_data = full_report_data
        if hide_zero:
            display_data = [
                row for row in full_report_data 
                if row['total_stock'] != 0 or row['pending'] != 0
            ]

        # --- 7. Apply Pagination (to the final display data) ---
        paginator = Paginator(display_data, per_page)
        page_number = request.GET.get('page')
        report_page = paginator.get_page(page_number)

        context = {
            'report_page': report_page,
            'warehouses': warehouses,
            'sort_by_group': sort_by_group,
            'column_totals': column_totals,
            'grand_total_stock': grand_total_stock,
            'grand_total_pending': grand_total_pending,
            'per_page': per_page,
            'hide_zero': hide_zero,
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
        per_page = request.GET.get('per_page', 10)

        # The main query is now on the transaction header
        inward_headers = InwardHeader.objects.select_related(
            'supplier', 'created_by'
        ).prefetch_related(
            'items', 'items__item', 'items__warehouse' # Pre-fetches all related items for efficiency
        ).all().order_by('-date')
        
        if start_date:
            inward_headers = inward_headers.filter(date__gte=start_date)
        if end_date:
            inward_headers = inward_headers.filter(date__lte=end_date)
        
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
            'end_date': end_date
        }
        return render(request, 'inventory/inward_report.html', context)
        

class InwardUpdateView(LoginRequiredMixin, View):
    InwardItemFormSet = inlineformset_factory(
        InwardHeader, InwardItem, form=InwardItemForm, extra=1, can_delete=True,
    )

    def get(self, request, pk):
        inward_header = InwardHeader.objects.get(pk=pk)
        header_form = InwardHeaderForm(instance=inward_header)
        item_formset = self.InwardItemFormSet(instance=inward_header)
        for form in item_formset:
            if form.instance.pk and form.instance.item:
                form.fields['group'].initial = form.instance.item.group
        context = {'header_form': header_form, 'item_formset': item_formset, 'object': inward_header}
        return render(request, 'inventory/inward_edit.html', context)

    @transaction.atomic
    def post(self, request, pk):
        inward_header = InwardHeader.objects.get(pk=pk)
        
        # Store the "before" state of all items for stock calculation
        old_items = {item.id: {
            'item_id': item.item_id, 
            'quantity': item.quantity, 
            'warehouse_id': item.warehouse_id
        } for item in inward_header.items.all()}

        header_form = InwardHeaderForm(request.POST, instance=inward_header)
        item_formset = self.InwardItemFormSet(request.POST, instance=inward_header)

        if header_form.is_valid() and item_formset.is_valid():
            
            # 1. Reverse stock for all items that existed before this update
            for item_id, old_data in old_items.items():
                # --- THIS IS THE FIX ---
                # Use get_or_create to safely find the stock record, even if it's zero
                stock, _ = OpeningStock.objects.get_or_create(
                    item_id=old_data['item_id'], 
                    warehouse_id=old_data['warehouse_id']
                )
                stock.quantity -= old_data['quantity']
                stock.save()

            # 2. Save the form changes (this will handle additions, updates, and deletions)
            header_form.save()
            item_formset.save()

            # 3. Apply new stock for all items that currently exist in the transaction
            for item_instance in inward_header.items.all():
                stock, _ = OpeningStock.objects.get_or_create(
                    item=item_instance.item, 
                    warehouse=item_instance.warehouse
                )
                stock.quantity += item_instance.quantity
                stock.save()
                
            messages.success(request, 'Inward transaction updated successfully!')
            return redirect('inward_report')
        
        context = {'header_form': header_form, 'item_formset': item_formset, 'object': inward_header}
        return render(request, 'inventory/inward_edit.html', context)
        
class InwardDeleteView(LoginRequiredMixin, DeleteView):
    model = InwardHeader
    template_name = 'inventory/inward_confirm_delete.html' # Create this template for confirmation
    success_url = reverse_lazy('inward_report') # Redirect to the inward report after deletion
    
# inventory/views.py

# ADD THIS FUNCTION AT THE END OF THE FILE
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
    

class OutwardReportView(LoginRequiredMixin, View):
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        per_page = request.GET.get('per_page', 10)

        # The main query is now on the transaction header
        outward_headers = OutwardHeader.objects.select_related(
            'customer', 'created_by'
        ).prefetch_related(
            'items', 'items__item', 'items__warehouse'
        ).all().order_by('-date')
        
        if start_date:
            outward_headers = outward_headers.filter(date__gte=start_date)
        if end_date:
            outward_headers = outward_headers.filter(date__lte=end_date)
        
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
            'end_date': end_date
        }
        return render(request, 'inventory/outward_report.html', context)

class ProductionReportView(LoginRequiredMixin, View):
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        per_page = request.GET.get('per_page', 10)

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
            adj_header = header_form.save(commit=False)
            adj_header.created_by = request.user
            adj_header.save()

            # --- THIS IS THE CORRECTED LOGIC ---
            # Loop through each form in the formset
            for form in item_formset:
                # Check if the form has data and is not marked for deletion
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    item_instance = form.save(commit=False)
                    item_instance.header = adj_header
                    item_instance.save()
                    
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

        recent_adjustments = StockAdjustmentHeader.objects.order_by('-date', '-created_at')[:5]
        context = {
            'header_form': header_form,
            'item_formset': item_formset,
            'recent_adjustments': recent_adjustments,
            'groups': GroupMaster.objects.all(),
        }
        return render(request, 'inventory/stock_adjustment.html', context)
        


# inventory/views.py

class WarehouseTransferReportView(LoginRequiredMixin, View):
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        per_page = request.GET.get('per_page', 10)

        transfer_items_list = WarehouseTransferItem.objects.select_related(
            'header', 'item', 'from_warehouse', 'to_warehouse'
        ).all().order_by('-header__date')
        
        if start_date:
            transfer_items_list = transfer_items_list.filter(header__date__gte=start_date)
        if end_date:
            transfer_items_list = transfer_items_list.filter(header__date__lte=end_date)
        
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="warehouse_transfer_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Ref No.', 'Item', 'From Warehouse', 'To Warehouse', 'Quantity'])
            for item in transfer_items_list:
                writer.writerow([
                    item.header.date, item.header.reference_no, item.item.name,
                    item.from_warehouse.name, item.to_warehouse.name, item.quantity
                ])
            return response

        paginator = Paginator(transfer_items_list, per_page)
        page_number = request.GET.get('page')
        transfer_items_page = paginator.get_page(page_number)
        
        context = {
            'transfer_items': transfer_items_page,
            'per_page': per_page,
            'start_date': start_date,
            'end_date': end_date
        }
        return render(request, 'inventory/warehouse_transfer_report.html', context)


class WarehouseTransferUpdateView(LoginRequiredMixin, View):
    TransferItemFormSet = inlineformset_factory(
        WarehouseTransferHeader, WarehouseTransferItem, form=WarehouseTransferItemForm,
        extra=0, can_delete=True,
    )

    def get(self, request, pk):
        transfer_header = WarehouseTransferHeader.objects.get(pk=pk)
        header_form = WarehouseTransferHeaderForm(instance=transfer_header)
        item_formset = self.TransferItemFormSet(instance=transfer_header)
        context = {'header_form': header_form, 'item_formset': item_formset, 'object': transfer_header}
        return render(request, 'inventory/warehouse_transfer_edit.html', context)

    @transaction.atomic
    def post(self, request, pk):
        transfer_header = WarehouseTransferHeader.objects.get(pk=pk)
        old_items = {item.id: {
            'item_id': item.item_id, 'quantity': item.quantity, 
            'from_warehouse_id': item.from_warehouse_id, 'to_warehouse_id': item.to_warehouse_id
        } for item in transfer_header.items.all()}

        header_form = WarehouseTransferHeaderForm(request.POST, instance=transfer_header)
        item_formset = self.TransferItemFormSet(request.POST, instance=transfer_header)

        if header_form.is_valid() and item_formset.is_valid():
            # 1. Reverse all original stock movements
            for item_id, old_data in old_items.items():
                from_stock, _ = OpeningStock.objects.get_or_create(item_id=old_data['item_id'], warehouse_id=old_data['from_warehouse_id'])
                from_stock.quantity += old_data['quantity']
                from_stock.save()
                to_stock, _ = OpeningStock.objects.get_or_create(item_id=old_data['item_id'], warehouse_id=old_data['to_warehouse_id'])
                to_stock.quantity -= old_data['quantity']
                to_stock.save()

            # 2. Save the form changes
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
            
            messages.success(request, 'Transfer updated successfully!')
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

class StockAdjustmentUpdateView(LoginRequiredMixin, View):
    # (The logic for this is highly complex, as seen in InwardUpdateView.
    # The best practice is to delete and re-create the adjustment.)
    pass

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

        elif 'import' in action:
            csv_file = request.FILES.get('csv_file')
            if not csv_file: return JsonResponse({'status': 'error', 'message': 'No file uploaded.'})
            
            try:
                csv_header, original_rows = self._decode_csv_file(csv_file)
                if action == 'import_inward':
                    response_data = self._handle_inward_import(csv_header, original_rows, request)
                elif action == 'import_outward':
                    response_data = self._handle_outward_import(csv_header, original_rows, request)
                else:
                    response_data = {'status': 'error', 'message': 'Unknown import action.'}
                return JsonResponse(response_data)
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f'A critical error occurred: {e}'})
            
        return redirect('import_page')
class OutwardUpdateView(LoginRequiredMixin, View):
    OutwardItemFormSet = inlineformset_factory(
        OutwardHeader, OutwardItem, form=OutwardItemForm,
        extra=0, can_delete=True,
    )

    def get(self, request, pk):
        outward_header = OutwardHeader.objects.get(pk=pk)
        header_form = OutwardHeaderForm(instance=outward_header)
        item_formset = self.OutwardItemFormSet(instance=outward_header)
        
        # --- THIS IS THE FIX ---
        # Manually set the initial value for the 'group' field in each form
        # based on the item that is already in that row.
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
            # 1. Reverse all original stock movements (add stock back)
            for item_id, old_data in old_items.items():
                stock, _ = OpeningStock.objects.get_or_create(item_id=old_data['item_id'], warehouse_id=old_data['warehouse_id'])
                stock.quantity += old_data['quantity']
                stock.save()

            # 2. Save the form changes
            header_form.save()
            item_formset.save()

            # 3. Apply new stock for all current items (subtract stock)
            for item_instance in outward_header.items.all():
                stock, _ = OpeningStock.objects.get_or_create(item=item_instance.item, warehouse=item_instance.warehouse)
                stock.quantity -= item_instance.quantity
                stock.save()
            
            messages.success(request, 'Outward transaction updated successfully!')
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

            # Apply new stock for all current items
            for item in production_header.items.all():
                stock, _ = OpeningStock.objects.get_or_create(item=item.item, warehouse=item.warehouse)
                if item.type == 'Produced':
                    stock.quantity += item.quantity
                elif item.type == 'Consumed':
                    stock.quantity -= item.quantity
                stock.save()

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
    BOMItemFormSet = inlineformset_factory(BillOfMaterial, BOMItem, form=BOMItemForm, extra=1, can_delete=True),

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