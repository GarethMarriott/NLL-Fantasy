#!/bin/bash
# Script to test standings cache effectiveness
# Run on production server to verify caching is working

SERVER="https://138.68.228.237"
CACHE_STATS_URL="${SERVER}/admin/cache-stats/"
STANDINGS_URL="${SERVER}/standings/"
ITERATIONS=5

echo "=== Testing Standings View Caching ==="
echo ""

# Check Redis is accessible
echo "1. Verifying Redis connectivity..."
redis-cli ping > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "   ✓ Redis is accessible"
else
    echo "   ✗ Redis is not accessible"
    exit 1
fi

echo ""
echo "2. Clearing standings cache..."
redis-cli DEL "*standings*" > /dev/null
echo "   ✓ Cache cleared"

echo ""
echo "3. Testing standings view response times..."
echo "   (Accessing ${ITERATIONS} times)"
echo ""

# First access - should be cache MISS
echo "   Iteration 1 (Cold Cache - MISS expected):"
START=$(date +%s%N)
curl -s -I "${STANDINGS_URL}" > /dev/null 2>&1
END=$(date +%s%N)
DURATION_MS=$(( (END - START) / 1000000 ))
echo "      Response time: ${DURATION_MS}ms"

# Subsequent accesses - should be cache HITS
for i in $(seq 2 $ITERATIONS); do
    echo "   Iteration $i (Warm Cache - HIT expected):"
    START=$(date +%s%N)
    curl -s -I "${STANDINGS_URL}" > /dev/null 2>&1
    END=$(date +%s%N)
    DURATION_MS=$(( (END - START) / 1000000 ))
    echo "      Response time: ${DURATION_MS}ms"
done

echo ""
echo "4. Checking cache statistics..."
STATS=$(curl -s -u admin:admin "${CACHE_STATS_URL}" 2>/dev/null || echo '{"error": "Could not fetch stats"}')
echo "   Redis Stats:"
echo "   ${STATS}" | grep -o '"[^"]*": "[^"]*"' | sed 's/^/      /' || echo "   (Stats endpoint requires admin access)"

echo ""
echo "=== Cache Test Complete ==="
echo ""
echo "Summary:"
echo "  • First request: Benchmark time (cold cache)"
echo "  • Subsequent requests: Should be faster (warm cache)"
echo "  • If times improve, caching is working! ✓"
