"""
Custom middleware for NLL Fantasy application
"""


class NoCacheForAuthenticatedUserMiddleware:
    """
    Prevent ALL caching of authenticated pages across browser, mobile, and proxies.
    This ensures that when users switch accounts or tabs, they always see fresh
    data specific to the currently logged-in user.
    
    Issue: User logs into multiple accounts on phone in different tabs.
           Switching tabs shows correct team but wrong username in sidebar.
    Root Cause: Session data can leak between tabs on mobile browsers if pages are cached.
    Fix: Force all authenticated responses to bypass every level of caching:
         - Browser private cache
         - Browser shared cache  
         - Mobile browser cache
         - Any proxies/CDN
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Add aggressive no-cache headers for ALL requests (both authenticated and not)
        # This prevents session confusion between tabs/windows
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0, private'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response['Vary'] = 'Cookie'  # Ensure responses with different cookies aren't mixed
        
        # For authenticated users, add additional headers to ensure freshness
        if request.user.is_authenticated:
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0, private'
            # Add a timestamp to force cache invalidation
            from datetime import datetime
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
        
        return response
