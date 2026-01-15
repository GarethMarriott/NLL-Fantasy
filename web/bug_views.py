from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone
from django.core.paginator import Paginator

from .models import BugReport
from .bug_forms import BugReportForm, BugReportFilterForm
import sentry_sdk


@login_required
def report_bug(request):
    """View for users to report a new bug"""
    if request.method == 'POST':
        form = BugReportForm(request.POST)
        if form.is_valid():
            bug = form.save(commit=False)
            bug.reporter = request.user
            bug.save()
            
            # Log to Sentry with user context
            sentry_sdk.capture_message(
                f"User reported bug: {bug.title}",
                level='info',
                tags={
                    'bug_id': bug.id,
                    'priority': bug.priority,
                }
            )
            
            messages.success(request, 'Thank you! Your bug report has been submitted.')
            return redirect('bug_list')
    else:
        form = BugReportForm()
    
    return render(request, 'web/report_bug.html', {'form': form})


@login_required
def bug_list(request):
    """View to display list of bug reports with filtering"""
    bugs = BugReport.objects.all()
    filter_form = BugReportFilterForm(request.GET)
    
    # Apply filters
    if filter_form.is_valid():
        status = filter_form.cleaned_data.get('status')
        priority = filter_form.cleaned_data.get('priority')
        search = filter_form.cleaned_data.get('search')
        
        if status:
            bugs = bugs.filter(status=status)
        if priority:
            bugs = bugs.filter(priority=priority)
        if search:
            bugs = bugs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )
    
    # Pagination
    paginator = Paginator(bugs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'bugs': page_obj.object_list,
        'filter_form': filter_form,
        'total_bugs': paginator.count,
    }
    
    return render(request, 'web/bug_list.html', context)


@login_required
def bug_detail(request, bug_id):
    """View for bug report details"""
    bug = get_object_or_404(BugReport, id=bug_id)
    
    # Check if user can view this (own bug or staff)
    if bug.reporter != request.user and not request.user.is_staff:
        messages.error(request, 'You do not have permission to view this bug report.')
        return redirect('bug_list')
    
    return render(request, 'web/bug_detail.html', {'bug': bug})


@login_required
@require_POST
def update_bug_status(request, bug_id):
    """AJAX endpoint to update bug status (staff only)"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    bug = get_object_or_404(BugReport, id=bug_id)
    new_status = request.POST.get('status')
    
    if new_status in dict(BugReport.STATUS_CHOICES):
        bug.status = new_status
        if new_status == 'resolved':
            bug.resolved_at = timezone.now()
        bug.save()
        return JsonResponse({'success': True, 'new_status': bug.get_status_display()})
    
    return JsonResponse({'error': 'Invalid status'}, status=400)


@login_required
@require_POST
def add_bug_note(request, bug_id):
    """AJAX endpoint to add admin notes (staff only)"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    bug = get_object_or_404(BugReport, id=bug_id)
    note = request.POST.get('note', '').strip()
    
    if note:
        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        new_note = f"[{timestamp} - {request.user.username}]\n{note}\n\n"
        bug.admin_notes = new_note + bug.admin_notes
        bug.save()
        return JsonResponse({'success': True, 'note': new_note})
    
    return JsonResponse({'error': 'Note cannot be empty'}, status=400)


def bug_report_api(request):
    """JavaScript API for reporting bugs without page navigation"""
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            import json
            data = json.loads(request.body)
            
            # Create bug report from client-side error data
            bug = BugReport.objects.create(
                reporter=request.user if request.user.is_authenticated else None,
                title=data.get('title', 'Client-side error'),
                description=data.get('description', ''),
                priority='medium',
                page_url=data.get('page_url', ''),
                browser_info=data.get('browser_info', ''),
                error_message=data.get('error_message', ''),
            )
            
            return JsonResponse({
                'success': True,
                'bug_id': bug.id,
                'message': 'Error report submitted. Thank you for helping us improve!'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)
