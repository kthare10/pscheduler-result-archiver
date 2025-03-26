from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import redis, json
from django.conf import settings

r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)

def index(request):
    keys = r.keys("entry:*")
    entries = sorted([k.split(":")[1] for k in keys], reverse=True)
    return render(request, 'index.html', {'entries': entries})

def view_entry(request, timestamp):
    key = f"entry:{timestamp}"
    value = r.get(key)
    if not value:
        return JsonResponse({"error": "Not found"}, status=404)
    return render(request, 'view.html', {'timestamp': timestamp, 'data': json.loads(value)})

@csrf_exempt
def save_entry(request):
    if request.method == 'POST':
        body = json.loads(request.body)
        data = body.get('content')
        ts = body.get('timestamp_utc') or "unknown"
        category = body.get('category') or "uncategorized"
        filename = body.get('filename') or "unnamed.json"

        entry = {
            "category": category,
            "filename": filename,
            "content": data
        }

        r.set(f"entry:{ts}", json.dumps(entry))
        return JsonResponse({'status': 'saved', 'timestamp': ts})
    return JsonResponse({'error': 'POST required'}, status=400)