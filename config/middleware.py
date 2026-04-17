"""
Custom middleware for NLL Fantasy application
"""


class NoCacheForAuthenticatedUserMiddleware:
    """
    Prevent browser caching of pages for authenticated users.
    This ensures that when users switch accounts, they don't see cached
    data from the previous user in the sidebar or other UI elements.
    
    Issue: User switches accounts but sees old username in sidebar header
    Fix: Add no-cache headers to prevent browser from reusing cached responses
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Add no-cache headers for authenticated requests
        if request.user.is_authenticated:
            # Prevent browser from caching this page
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        
        return response
