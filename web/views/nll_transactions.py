"""
NLL transactions view
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from web.models import NLLTransaction


@login_required
def nll_transactions(request):
    """
    Display all NLL transactions
    """
    # Get all transactions, ordered by most recent first
    transactions = NLLTransaction.objects.all().order_by('-transaction_date')
    
    # Filter by type if specified
    trans_type = request.GET.get('type', '')
    if trans_type:
        transactions = transactions.filter(transaction_type=trans_type)
    
    # Filter by team if specified
    team_search = request.GET.get('team', '')
    if team_search:
        transactions = transactions.filter(
            Q(from_team__icontains=team_search) | 
            Q(to_team__icontains=team_search)
        )
    
    # Search by player name if specified
    player_search = request.GET.get('player', '')
    if player_search:
        transactions = transactions.filter(player_name__icontains=player_search)
    
    # Pagination
    paginator = Paginator(transactions, 50)  # 50 transactions per page
    page = request.GET.get('page', 1)
    transactions_page = paginator.get_page(page)
    
    # Get distinct transaction types for filter dropdown
    transaction_types = NLLTransaction.TRANSACTION_TYPE_CHOICES
    
    context = {
        'transactions': transactions_page,
        'transaction_types': transaction_types,
        'selected_type': trans_type,
        'selected_team': team_search,
        'selected_player': player_search,
        'total_count': transactions.count(),
    }
    
    return render(request, 'web/nll_transactions.html', context)
