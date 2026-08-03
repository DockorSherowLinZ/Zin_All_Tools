import urllib.request
import json
import time
from urllib.parse import urlparse

urls = [
    'http://10.6.180.60:9901/mcp',
    'http://10.6.180.60:9902/mcp',
    'http://10.6.180.60:9903/mcp',
    'http://10.6.180.60:9904/mcp'
]

names = [
    'omniUI-mcp-server-723d3739',
    'kit-tools-mcp-server-d900e5a3',
    'usd-tools-mcp-server-6500bf22',
    'isaac-sim-mcp-server-b83de378'
]

for name, url in zip(names, urls):
    try:
        # Request SSE endpoint
        sse_req = urllib.request.Request(url, headers={'Accept': 'text/event-stream'})
        post_endpoint = None
        
        with urllib.request.urlopen(sse_req) as response:
            for _ in range(10):
                line = response.readline().decode('utf-8').strip()
                if line.startswith('event: endpoint'):
                    data_line = response.readline().decode('utf-8').strip()
                    if data_line.startswith('data: '):
                        post_endpoint = data_line[6:]
                        break
                        
        if not post_endpoint:
            if url.endswith('/sse'):
                post_endpoint = url.replace('/sse', '/message')
            else:
                post_endpoint = url + '/message'
                
        if post_endpoint.startswith('/'):
            parsed = urlparse(url)
            post_endpoint = f'{parsed.scheme}://{parsed.netloc}{post_endpoint}'
            
        # Call tools/list
        req_data = json.dumps({
            'jsonrpc': '2.0', 
            'id': 1, 
            'method': 'tools/list'
        }).encode('utf-8')
        
        post_req = urllib.request.Request(
            post_endpoint, 
            data=req_data, 
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            with urllib.request.urlopen(post_req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                tools = res_data.get('result', {}).get('tools', [])
                print(f'\n=== Server: {name} ({url}) ===')
                if not tools:
                    print('No tools found.')
                for t in tools:
                    desc = t.get('description', '')
                    desc_first_line = desc.split('\n')[0] if desc else 'No description'
                    print(f"- {t.get('name')}: {desc_first_line}")
        except Exception as e:
            print(f'\n=== Server: {name} ({url}) ===\nFailed POST to {post_endpoint}: {e}')
            
    except Exception as e:
        print(f'\n=== Server: {name} ({url}) ===\nConnection error: {e}')
